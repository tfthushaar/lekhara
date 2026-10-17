"""Secrets kept for a firm, such as the passwords its banks put on emailed statements, sealed
with the server's secret key (LEKHARA_SECRET_KEY) so the database alone does not reveal them."""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from lekhara.config import Settings

log = logging.getLogger("lekhara.secretbox")
_DEVELOPMENT_KEY = "lekhara-development-only"


def _fernet(settings: Settings) -> Fernet:
    secret = settings.secret_key
    if not secret:
        if not settings.demo:
            log.warning("LEKHARA_SECRET_KEY is not set; secrets are sealed with a development key.")
        secret = _DEVELOPMENT_KEY
    key = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(settings: Settings, text: str) -> str:
    return _fernet(settings).encrypt(text.encode()).decode()


def unseal(settings: Settings, token: str) -> str | None:
    """The secret, or None if it was sealed with another key."""
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
