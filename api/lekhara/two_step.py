"""Two-step sign-in with an authenticator app (Google Authenticator, Microsoft Authenticator and
the like): after the password, a six-digit code that changes every 30 seconds.

The codes follow RFC 6238 (TOTP, SHA-1, 30 seconds, 6 digits), which every authenticator app
reads. The shared secret is sealed with the server's key; a code once used cannot be used again;
eight recovery codes, each good once, get a person in if the phone is lost.
"""

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara.auth import _now, _token_hash, start_session, verify_password
from lekhara.config import Settings
from lekhara.models import OneTimeToken, User
from lekhara.secretbox import seal, unseal
from lekhara.services import ServiceError

STEP = 30
DIGITS = 6
TICKET_MINUTES = 10
RECOVERY_CODES = 8


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def _counter(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP)


def _matching_step(secret: str, code: str, now: float | None = None) -> int | None:
    """The time step the code belongs to, allowing one step either side for clock drift."""
    code = "".join(c for c in (code or "") if c.isdigit())
    if len(code) != DIGITS:
        return None
    current = _counter(now)
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def setup_uri(secret: str, email: str) -> str:
    label = quote(f"Lekhara:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer=Lekhara&digits={DIGITS}&period={STEP}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").strip().casefold().encode()).hexdigest()


def _recovery_codes() -> list[str]:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return [
        "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2))
        for _ in range(RECOVERY_CODES)
    ]


# Turning it on and off


def start(session: Session, settings: Settings, user: User) -> dict:
    """A new secret for the person to add to their app; it counts once they confirm a code."""
    secret = new_secret()
    user.totp_pending = seal(settings, secret)
    session.commit()
    grouped = " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))
    return {"secret": grouped, "uri": setup_uri(secret, user.email)}


def confirm(session: Session, settings: Settings, user: User, code: str) -> list[str]:
    secret = unseal(settings, user.totp_pending) if user.totp_pending else None
    if secret is None:
        raise ServiceError("Start again: add Lekhara to your authenticator app first.")
    step = _matching_step(secret, code)
    if step is None:
        raise ServiceError("That code does not match. Enter the six digits your app shows now.")
    codes = _recovery_codes()
    user.totp_secret = user.totp_pending
    user.totp_pending = None
    user.totp_last_step = step
    user.two_step_on = _now()
    user.recovery_codes = json.dumps([_hash(c) for c in codes])
    session.commit()
    return codes


def disable(session: Session, user: User, password: str) -> None:
    if not verify_password(password or "", user.password_hash):
        raise ServiceError("That password does not match.", 401)
    user.totp_secret = None
    user.totp_pending = None
    user.totp_last_step = None
    user.two_step_on = None
    user.recovery_codes = None
    session.commit()


def check_code(session: Session, settings: Settings, user: User, code: str) -> None:
    """Accepts a code from the app, used once, or one of the recovery codes, each used once."""
    secret = unseal(settings, user.totp_secret) if user.totp_secret else None
    if secret is not None:
        step = _matching_step(secret, code)
        if step is not None and (user.totp_last_step is None or step > user.totp_last_step):
            user.totp_last_step = step
            return
    remaining = json.loads(user.recovery_codes or "[]")
    hashed = _hash(code or "")
    if hashed in remaining:
        remaining.remove(hashed)
        user.recovery_codes = json.dumps(remaining)
        return
    raise ServiceError("That code does not match. Enter the six digits your app shows now.", 401)


# Signing in


def ticket(session: Session, user: User) -> str:
    """After the password: a short-lived ticket the second step exchanges for a session."""
    token = secrets.token_urlsafe(32)
    now = _now()
    session.add(
        OneTimeToken(
            user_id=user.id,
            purpose="two_step",
            token_hash=_token_hash(token),
            created_at=now,
            expires_at=now + timedelta(minutes=TICKET_MINUTES),
        )
    )
    session.commit()
    return token


def finish(session: Session, settings: Settings, token: str, code: str) -> tuple[str, User]:
    row = session.scalars(
        select(OneTimeToken).where(
            OneTimeToken.token_hash == _token_hash(token or ""), OneTimeToken.purpose == "two_step"
        )
    ).first()
    if row is None or row.used_at is not None or row.expires_at < _now():
        raise ServiceError("This sign-in has timed out. Enter your email and password again.", 401)
    user = session.get(User, row.user_id)
    check_code(session, settings, user, code)
    row.used_at = _now()
    return start_session(session, user), user


def remaining_recovery_codes(user: User) -> int:
    return len(json.loads(user.recovery_codes or "[]"))
