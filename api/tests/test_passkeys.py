"""Passkeys: added after confirming it is you, used to sign in without a password, refused for
any other site, and counted as two-step sign-in."""

import base64
import hashlib
import json
import os
import struct
from datetime import timedelta

import cbor2
from conftest import signed_in
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import select

from lekhara import auth
from lekhara.models import User, UserSession


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SoftAuthenticator:
    """A passkey held in memory, answering the way a phone or laptop would."""

    def __init__(self, rp_id: str = "localhost", origin: str = "http://localhost:3000") -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.rp_id, self.origin, self.count = rp_id, origin, 0

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}
        ).encode()

    def _public_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _ids(self) -> dict:
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
        }

    def create(self, options: dict) -> dict:
        client = self._client_data("webauthn.create", options["challenge"])
        flags = 0x01 | 0x04 | 0x40  # the person was present and verified; a new key follows
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([flags])
            + struct.pack(">I", 0)
            + bytes(16)
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._public_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            **self._ids(),
            "response": {"clientDataJSON": b64(client), "attestationObject": b64(attestation)},
            "clientExtensionResults": {},
        }

    def get(self, options: dict) -> dict:
        self.count += 1
        client = self._client_data("webauthn.get", options["challenge"])
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([0x05])
            + struct.pack(">I", self.count)
        )
        signature = self.key.sign(
            auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            **self._ids(),
            "response": {
                "clientDataJSON": b64(client),
                "authenticatorData": b64(auth_data),
                "signature": b64(signature),
            },
            "clientExtensionResults": {},
        }


def add_passkey(client: TestClient, device: SoftAuthenticator, name: str = "Laptop") -> None:
    options = client.post("/auth/passkeys/options").json()
    added = client.post("/auth/passkeys", json={"response": device.create(options), "name": name})
    assert added.status_code == 201, added.text


def sign_in_with(app, device: SoftAuthenticator):
    client = TestClient(app)
    started = client.post("/auth/passkey/login/options").json()
    answer = device.get(started["options"])
    return (
        client,
        client.post("/auth/passkey/login", json={"ticket": started["ticket"], "response": answer}),
        (started["ticket"], answer),
    )


def test_a_passkey_signs_in_without_a_password(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    phone = SoftAuthenticator()
    add_passkey(owner, phone, "Phone")
    listed = owner.get("/auth/passkeys").json()["passkeys"]
    assert [p["name"] for p in listed] == ["Phone"]

    client, done, (ticket, answer) = sign_in_with(app, phone)
    assert done.status_code == 200, done.text
    client.headers["Authorization"] = f"Bearer {done.json()['token']}"
    assert client.get("/auth/me").json()["user"]["email"] == "promoter@demo.lekhara"

    # The same answer again: its challenge is spent.
    again = TestClient(app).post("/auth/passkey/login", json={"ticket": ticket, "response": answer})
    assert again.status_code == 400


def test_a_passkey_for_another_site_is_refused(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    phone = SoftAuthenticator()
    add_passkey(owner, phone)
    phone.origin = "https://lekhara-login.example"  # a look-alike page
    _, done, _ = sign_in_with(app, phone)
    assert done.status_code == 401

    stranger = SoftAuthenticator()  # never added
    _, unknown, _ = sign_in_with(app, stranger)
    assert unknown.status_code == 401 and "not known" in unknown.json()["detail"]


def test_adding_and_removing_ask_to_confirm_first(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    phone = SoftAuthenticator()
    add_passkey(owner, phone)
    with app.state.session_factory() as session:
        user = session.scalars(select(User).where(User.email == "promoter@demo.lekhara")).one()
        for row in session.scalars(select(UserSession).where(UserSession.user_id == user.id)):
            row.confirmed_at = auth._now() - timedelta(minutes=30)
        session.commit()
    assert owner.post("/auth/passkeys/options").status_code == 428
    passkey_id = owner.get("/auth/passkeys").json()["passkeys"][0]["id"]
    assert owner.post(f"/auth/passkeys/{passkey_id}/delete").status_code == 428

    # Signing in with the passkey counts as proving it is you.
    client, done, _ = sign_in_with(app, phone)
    client.headers["Authorization"] = f"Bearer {done.json()['token']}"
    assert client.post(f"/auth/passkeys/{passkey_id}/delete").status_code == 200
    _, after, _ = sign_in_with(app, phone)
    assert after.status_code == 401


def test_a_passkey_counts_as_two_step(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    refused = owner.put("/organization/two-step-rule", json={"required": True})
    assert refused.status_code == 400
    add_passkey(owner, SoftAuthenticator())
    assert owner.get("/auth/me").json()["two_step_on"] is True
    assert owner.put("/organization/two-step-rule", json={"required": True}).status_code == 200
