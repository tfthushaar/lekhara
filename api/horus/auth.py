"""Sign-in, sessions and who may do what.

Two kinds of people use Horus:

- The developer's own team, through a membership of the organisation:
  owner, finance, accounts or viewer.
- Outside people, through access to particular projects: today the architect,
  engineer and CA who certify withdrawals. Each can see the projects they
  certify and can change and sign only their own certificate.
"""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from horus.engines.escrow import CertifierRole
from horus.models import Membership, Project, ProjectAccess, User, UserSession
from horus.services import ServiceError

SESSION_DAYS = 14
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


class OrgRole(StrEnum):
    OWNER = "owner"
    FINANCE = "finance"
    ACCOUNTS = "accounts"
    VIEWER = "viewer"


ORG_ROLE_LABEL = {
    OrgRole.OWNER: "Owner",
    OrgRole.FINANCE: "Finance",
    OrgRole.ACCOUNTS: "Accounts",
    OrgRole.VIEWER: "Viewer",
}

CERTIFIER_LABEL = {
    CertifierRole.ARCHITECT: "Architect",
    CertifierRole.ENGINEER: "Engineer",
    CertifierRole.CA: "Chartered accountant",
}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    expected = _unb64(digest)
    candidate = hashlib.scrypt(
        password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
    )
    return hmac.compare_digest(candidate, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class LoginThrottle:
    """Slows down password guessing: a few failures per email, then a pause."""

    def __init__(self, limit: int = 5, window_seconds: int = 900) -> None:
        self.limit = limit
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str) -> deque[float]:
        cutoff = time.monotonic() - self.window
        failures = self._failures[key]
        while failures and failures[0] < cutoff:
            failures.popleft()
        return failures

    def check(self, key: str) -> None:
        with self._lock:
            if len(self._recent(key)) >= self.limit:
                raise ServiceError("Too many attempts. Wait fifteen minutes, then try again.", 429)

    def failed(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.monotonic())

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str
    email: str
    firm: str | None
    org_roles: dict[str, OrgRole]
    """Organisation id to the person's role in the developer's team."""
    project_roles: dict[str, frozenset[CertifierRole]]
    """Project id to the certifying roles the person holds on it."""

    def org_role(self, project: Project) -> OrgRole | None:
        return self.org_roles.get(project.organization_id)

    def can_view(self, project: Project) -> bool:
        return project.organization_id in self.org_roles or project.id in self.project_roles

    def is_team(self, project: Project) -> bool:
        return self.org_role(project) is not None

    def can_prepare(self, project: Project) -> bool:
        """Start withdrawals and send them to the bank."""
        return self.org_role(project) in (OrgRole.OWNER, OrgRole.FINANCE, OrgRole.ACCOUNTS)

    def can_release(self, project: Project) -> bool:
        """Record what the bank released or rejected."""
        return self.org_role(project) in (OrgRole.OWNER, OrgRole.FINANCE)

    def certifies(self, project: Project, role: CertifierRole) -> bool:
        return role in self.project_roles.get(project.id, frozenset())

    @property
    def is_certifier_only(self) -> bool:
        return not self.org_roles and bool(self.project_roles)

    def describe(self) -> str:
        if self.org_roles:
            return ORG_ROLE_LABEL[next(iter(self.org_roles.values()))]
        roles = {role for roles in self.project_roles.values() for role in roles}
        return ", ".join(CERTIFIER_LABEL[r] for r in sorted(roles)) or "No access"


def login(session: Session, email: str, password: str, throttle: LoginThrottle) -> tuple[str, User]:
    key = email.strip().casefold()
    throttle.check(key)
    user = session.scalars(select(User).where(User.email == key)).first()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        throttle.failed(key)
        raise ServiceError("That email and password do not match.", 401)
    throttle.succeeded(key)
    token = secrets.token_urlsafe(32)
    now = _now()
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            created_at=now,
            expires_at=now + timedelta(days=SESSION_DAYS),
        )
    )
    session.commit()
    return token, user


def logout(session: Session, token: str) -> None:
    row = session.scalars(
        select(UserSession).where(UserSession.token_hash == _token_hash(token))
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()


def principal_for(session: Session, token: str) -> Principal | None:
    row = session.scalars(
        select(UserSession).where(UserSession.token_hash == _token_hash(token))
    ).first()
    if row is None or row.expires_at < _now():
        return None
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    org_roles = {
        m.organization_id: OrgRole(m.role)
        for m in session.scalars(select(Membership).where(Membership.user_id == user.id))
    }
    project_roles: dict[str, set[CertifierRole]] = defaultdict(set)
    for access in session.scalars(select(ProjectAccess).where(ProjectAccess.user_id == user.id)):
        project_roles[access.project_id].add(CertifierRole(access.role))
    return Principal(
        user_id=user.id,
        name=user.name,
        email=user.email,
        firm=user.firm,
        org_roles=org_roles,
        project_roles={k: frozenset(v) for k, v in project_roles.items()},
    )


# Checks used by the API. A project outside someone's access looks the same as one that
# does not exist, so nothing leaks about other developers' projects.


def require_view(principal: Principal, project: Project) -> None:
    if not principal.can_view(project):
        raise ServiceError("Project not found.", 404)


def require_team(principal: Principal, project: Project) -> None:
    require_view(principal, project)
    if not principal.is_team(project):
        raise ServiceError("Only the developer's team can see this.", 403)


def require_prepare(principal: Principal, project: Project) -> None:
    require_view(principal, project)
    if not principal.can_prepare(project):
        raise ServiceError("Your role cannot start or send withdrawals.", 403)


def require_share(principal: Principal, project: Project) -> None:
    require_view(principal, project)
    if not principal.can_release(project):
        raise ServiceError(
            "Only the owner or finance can share documents outside the company.", 403
        )


def require_release(principal: Principal, project: Project) -> None:
    require_view(principal, project)
    if not principal.can_release(project):
        raise ServiceError("Only the owner or finance can record what the bank did.", 403)


def require_certifier(principal: Principal, project: Project, role: CertifierRole) -> None:
    require_view(principal, project)
    if not principal.certifies(project, role):
        raise ServiceError(f"Only the project's {CERTIFIER_LABEL[role].lower()} can do this.", 403)
