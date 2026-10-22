"""Refusing passwords already leaked in data breaches elsewhere.

Reused passwords are the commonest way into accounts. A new password is checked against Have I
Been Pwned's list of leaked passwords without the password, or anything that identifies the
person, leaving Lekhara: only the first five characters of the password's SHA-1 hash are sent
(the k-anonymity range API), the answer lists every leaked hash starting with them, and the
match is made here. If the service cannot be reached in a couple of seconds the password is
accepted, so an outside service being slow never stops anyone signing up.
"""

import hashlib
import logging
import urllib.request

from lekhara.config import Settings
from lekhara.services import ServiceError

log = logging.getLogger("lekhara.passwords")
RANGE_URL = "https://api.pwnedpasswords.com/range/"


def times_leaked(password: str, timeout: float = 2.0) -> int:
    """How many times this password appears in known breaches."""
    # SHA-1 because that is the service's format; nothing is stored with it.
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, rest = digest[:5], digest[5:]
    request = urllib.request.Request(
        RANGE_URL + prefix, headers={"Add-Padding": "true", "User-Agent": "Lekhara"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed https URL
        body = response.read().decode("utf-8", errors="replace")
    for line in body.splitlines():
        suffix, _, count = line.strip().partition(":")
        if suffix == rest:
            return int(count or 0)
    return 0


def refuse_leaked(settings: Settings, password: str | None) -> None:
    if not settings.password_breach_check or not password:
        return
    try:
        leaked = times_leaked(password)
    except (OSError, ValueError) as exc:
        log.warning("Could not check the password against known breaches: %s", exc)
        return
    if leaked:
        raise ServiceError(
            "This password has appeared in data breaches elsewhere, so it is among the first "
            "an attacker would try. Choose another."
        )
