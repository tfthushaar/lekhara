"""Secrets kept for a firm or a person, sealed with the server's secret key (LEKHARA_SECRET_KEY)
so the database alone does not reveal them: the passwords banks put on emailed statements, and
the shared secrets of authenticator apps.

The key can be changed without losing anything. Set the new key as LEKHARA_SECRET_KEY and the
old one in LEKHARA_OLD_SECRET_KEYS (comma-separated if several): secrets sealed with either can
be opened, and new ones are sealed with the new key. Then run

    python -m lekhara.secretbox reseal

to seal every kept secret with the new key, after which the old key can be removed.
"""

import base64
import hashlib
import logging
import sys

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from lekhara.config import Settings

log = logging.getLogger("lekhara.secretbox")
_DEVELOPMENT_KEY = "lekhara-development-only"


def _fernet_for(secret: str) -> Fernet:
    key = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _keys(settings: Settings) -> list[str]:
    secret = settings.secret_key
    if not secret:
        if not settings.demo:
            log.warning("LEKHARA_SECRET_KEY is not set; secrets are sealed with a development key.")
        secret = _DEVELOPMENT_KEY
    old = [k.strip() for k in (settings.old_secret_keys or "").split(",") if k.strip()]
    return [secret, *old]


def _fernet(settings: Settings) -> MultiFernet:
    """Seals with the current key; opens with the current key or any old one."""
    return MultiFernet([_fernet_for(k) for k in _keys(settings)])


def seal(settings: Settings, text: str) -> str:
    return _fernet(settings).encrypt(text.encode()).decode()


def unseal(settings: Settings, token: str) -> str | None:
    """The secret, or None if it was sealed with a key no longer known."""
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def reseal_all(session, settings: Settings) -> tuple[int, int]:
    """Seals every kept secret with the current key. Returns how many were resealed, and how
    many could not be opened with any known key (left as they are)."""
    from sqlalchemy import select

    from lekhara.models import StatementPassword, User

    fernet = _fernet(settings)
    done = failed = 0
    columns = [(StatementPassword, "sealed"), (User, "totp_secret"), (User, "totp_pending")]
    for model, column in columns:
        for row in session.scalars(select(model).where(getattr(model, column).is_not(None))):
            try:
                setattr(row, column, fernet.rotate(getattr(row, column).encode()).decode())
                done += 1
            except (InvalidToken, ValueError):
                failed += 1
    session.commit()
    return done, failed


def main(argv: list[str]) -> int:
    from lekhara.config import get_settings
    from lekhara.db import make_engine, make_sessionmaker

    if argv != ["reseal"]:
        print(__doc__)
        return 2
    settings = get_settings()
    with make_sessionmaker(make_engine(settings.database_url))() as session:
        done, failed = reseal_all(session, settings)
    print(f"{done} secrets sealed with the current key.")
    if failed:
        print(f"{failed} could not be opened with any key given; they were left as they were.")
        return 1
    print("The old keys in LEKHARA_OLD_SECRET_KEYS can now be removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
