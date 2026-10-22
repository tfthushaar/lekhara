"""The signing record on certificates, and the public page a bank checks a certificate on."""

import re
from datetime import timedelta

from conftest import DEMO_PASSWORD
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from lekhara.models import User, UserSession, WithdrawalCertificate, utcnow
from lekhara.pdf import read_pages

SG = "sarjapur-greens"
FROM = {
    "X-Lekhara-Client-IP": "198.51.100.7",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:131.0) Gecko/20100101 Firefox/131.0",
}


def open_request(owner) -> str:
    return owner.get(f"/projects/{SG}").json()["open_request_id"]


def sign_as_ca(ca, request_id: str) -> dict:
    r = ca.get(f"/withdrawals/{request_id}").json()
    books = {f["field"]: f["books"] for f in r["certificates"][2]["figures"]}
    figures = ca.put(f"/withdrawals/{request_id}/certificates/ca", json=books, headers=FROM)
    assert figures.status_code == 200, figures.text
    signed = ca.post(f"/withdrawals/{request_id}/certificates/ca/sign", json={}, headers=FROM)
    assert signed.status_code == 200, signed.text
    return signed.json()["certificates"][2]


def test_signing_keeps_a_record_the_bank_can_check(app, owner, ca) -> None:
    request_id = open_request(owner)
    record = sign_as_ca(ca, request_id)["record"]
    assert record["kept"] and record["unchanged"] and record["two_step"] is False
    assert re.fullmatch(r"[A-Z2-7]{4}(-[A-Z2-7]{4}){3}", record["check_code"])
    assert re.fullmatch(r"[0-9a-f]{64}", record["fingerprint"])
    assert "ca@demo.lekhara" in record["from"] and "198.51.100.7" in record["from"]
    assert "Firefox on Windows" in record["from"]

    # The demo's architect signed in Lekhara too; its record is kept the same way.
    view = owner.get(f"/withdrawals/{request_id}").json()
    assert view["certificates"][0]["record"]["kept"]

    # Anyone with the code sees what was signed, typed any way.
    bank = TestClient(app)
    code = record["check_code"]
    for typed in (code, code.replace("-", "").lower(), f" {code} "):
        found = bank.get(f"/check/{typed}")
        assert found.status_code == 200, found.text
    found = found.json()
    assert found["certificate"] == "Certificate of the chartered accountant"
    assert found["fingerprint"] == record["fingerprint"] and found["unchanged"]
    assert "may be withdrawn" in found["statement"] and found["signer_name"]
    assert bank.get("/check/AAAA-BBBB-CCCC-DDDD").status_code == 404
    assert bank.get("/check/not-a-code").status_code == 404

    # The certificate's PDF ends with its signing record.
    pdf = owner.get(f"/withdrawals/{request_id}/certificates/ca.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    text = " ".join(read_pages(pdf.content))
    assert "Signing record" in text and code in text
    assert record["fingerprint"][:32] in text and "http://localhost:3000/check" in text
    assert "Figures entered by" in text and "Signed by" in text
    pack = " ".join(read_pages(owner.get(f"/withdrawals/{request_id}/pack.pdf").content))
    assert pack.count("Signing record") == 3

    # A figure changed after signing no longer agrees with what was signed.
    with app.state.session_factory() as session:
        row = session.scalars(
            select(WithdrawalCertificate).where(WithdrawalCertificate.check_code == code)
        ).one()
        row.withdrawable_amount = row.withdrawable_amount + 100000
        session.commit()
    assert bank.get(f"/check/{code}").json()["unchanged"] is False


def test_signing_needs_the_person_to_have_confirmed_it_is_them(app, owner, ca) -> None:
    request_id = open_request(owner)
    with app.state.session_factory() as session:
        ca_id = session.scalars(select(User.id).where(User.email == "ca@demo.lekhara")).one()
        session.execute(
            update(UserSession)
            .where(UserSession.user_id == ca_id)
            .values(confirmed_at=utcnow() - timedelta(hours=1))
        )
        session.commit()
    late = ca.post(f"/withdrawals/{request_id}/certificates/ca/sign", json={})
    assert late.status_code == 428
    assert ca.post("/auth/confirm", json={"password": DEMO_PASSWORD}).status_code == 200
    assert ca.post(f"/withdrawals/{request_id}/certificates/ca/sign", json={}).status_code == 200
