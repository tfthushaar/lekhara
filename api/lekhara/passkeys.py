"""Passkeys: signing in with the phone's or computer's own lock (a fingerprint, the face, a PIN)
through WebAuthn.

A passkey cannot be phished: the browser only uses it on Lekhara's own address, and nothing a
person could type into a fake page would work elsewhere. It is something the person has,
unlocked by something they are or know, so it counts as two-step sign-in: the firm's two-step
rule and the admin console accept it in place of an authenticator app's code.

The browser does the cryptography. Lekhara sends a one-time challenge, the authenticator signs
it, and py_webauthn checks the signature against the public key kept when the passkey was added.
Challenges are kept for five minutes and used once.
"""

import secrets
from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from lekhara.config import Settings
from lekhara.models import Passkey, PasskeyChallenge, User, utcnow
from lekhara.services import ServiceError

CHALLENGE_MINUTES = 5
MAX_PASSKEYS = 10


def _party(settings: Settings) -> tuple[str, str]:
    """The site a passkey belongs to (its host name) and the address pages are served from."""
    url = urlparse(settings.web_url)
    return url.hostname or "localhost", f"{url.scheme}://{url.netloc}"


def has_passkey(session: Session, user_id: str) -> bool:
    count = session.scalar(
        select(func.count()).select_from(Passkey).where(Passkey.user_id == user_id)
    )
    return bool(count)


def of(session: Session, user_id: str) -> list[Passkey]:
    return list(
        session.scalars(
            select(Passkey).where(Passkey.user_id == user_id).order_by(Passkey.created_at)
        )
    )


def _challenge(session: Session, purpose: str, user_id: str | None) -> tuple[str, bytes]:
    """A fresh challenge, and the ticket that names it."""
    challenge, ticket = secrets.token_bytes(32), secrets.token_urlsafe(24)
    session.add(
        PasskeyChallenge(
            id=ticket,
            user_id=user_id,
            purpose=purpose,
            challenge=bytes_to_base64url(challenge),
            expires_at=utcnow() + timedelta(minutes=CHALLENGE_MINUTES),
        )
    )
    return ticket, challenge


def _take_challenge(session: Session, **where) -> PasskeyChallenge:
    """The challenge, used up, or an error if it has expired or was never given."""
    query = select(PasskeyChallenge)
    for column, value in where.items():
        query = query.where(getattr(PasskeyChallenge, column) == value)
    row = session.scalars(query.order_by(PasskeyChallenge.expires_at.desc())).first()
    if row is None or row.expires_at < utcnow():
        raise ServiceError("This took too long. Try again.", 400)
    session.delete(row)
    return row


# Adding a passkey


def registration_options(session: Session, settings: Settings, user: User) -> str:
    if len(of(session, user.id)) >= MAX_PASSKEYS:
        raise ServiceError(f"You have {MAX_PASSKEYS} passkeys already. Remove one first.")
    rp_id, _ = _party(settings)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Lekhara",
        user_id=user.id.encode(),
        user_name=user.email,
        user_display_name=user.name,
        challenge=_challenge(session, "register", user.id)[1],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.credential_id))
            for p in of(session, user.id)
        ],
    )
    session.commit()
    return options_to_json(options)


def register(
    session: Session, settings: Settings, user: User, response: dict, name: str | None
) -> Passkey:
    row = _take_challenge(session, user_id=user.id, purpose="register")
    rp_id, origin = _party(settings)
    try:
        verified = verify_registration_response(
            credential=response,
            expected_challenge=base64url_to_bytes(row.challenge),
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except (InvalidRegistrationResponse, ValueError, KeyError) as exc:
        session.commit()
        raise ServiceError(f"The passkey could not be added: {exc}") from None
    passkey = Passkey(
        user_id=user.id,
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=bytes_to_base64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        name=((name or "").strip() or "Passkey")[:100],
    )
    session.add(passkey)
    session.commit()
    return passkey


def remove(session: Session, user: User, passkey_id: str) -> Passkey:
    passkey = session.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != user.id:
        raise ServiceError("Passkey not found.", 404)
    session.delete(passkey)
    session.commit()
    return passkey


# Signing in with one


def login_options(session: Session, settings: Settings) -> tuple[str, str]:
    """A ticket naming the challenge, and the options for the browser. No email is asked for:
    the browser offers the passkeys it holds for Lekhara."""
    rp_id, _ = _party(settings)
    ticket, challenge = _challenge(session, "login", None)
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    session.commit()
    return ticket, options_to_json(options)


def login(session: Session, settings: Settings, ticket: str, response: dict) -> User:
    row = _take_challenge(session, id=ticket, purpose="login")
    credential_id = str(response.get("rawId") or response.get("id") or "")
    passkey = session.scalars(select(Passkey).where(Passkey.credential_id == credential_id)).first()
    if passkey is None:
        session.commit()
        raise ServiceError("This passkey is not known to Lekhara. Sign in with your password.", 401)
    rp_id, origin = _party(settings)
    try:
        verified = verify_authentication_response(
            credential=response,
            expected_challenge=base64url_to_bytes(row.challenge),
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=base64url_to_bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError):
        session.commit()
        raise ServiceError("That passkey did not check out. Try again.", 401) from None
    user = session.get(User, passkey.user_id)
    if user is None or not user.is_active:
        session.commit()
        raise ServiceError("This account is closed.", 401)
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = utcnow()
    session.commit()
    return user
