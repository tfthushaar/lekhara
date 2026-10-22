"""Sign-in, sessions and who may do what.

Two kinds of people use Lekhara:

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
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara.engines.escrow import CertifierRole
from lekhara.models import (
    Membership,
    Organization,
    Passkey,
    Project,
    ProjectAccess,
    SupportGrant,
    User,
    UserSession,
)
from lekhara.services import ServiceError, access_state, read_only_message

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
    """Slows down password guessing: a few failures per email, then a pause. The same counter,
    with another limit and message, caps requests from one network address.

    With a store (limits.DatabaseStore) every API server shares one count; without one it
    counts in memory, which is enough for a single server and for tests."""

    def __init__(
        self,
        limit: int = 5,
        window_seconds: int = 900,
        message: str = "Too many attempts. Wait fifteen minutes, then try again.",
        store=None,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self.message = message
        self.store = store
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str) -> deque[float]:
        cutoff = time.monotonic() - self.window
        failures = self._failures[key]
        while failures and failures[0] < cutoff:
            failures.popleft()
        return failures

    def _count(self, key: str) -> int:
        if self.store is not None:
            return self.store.recent(key, self.window)
        with self._lock:
            return len(self._recent(key))

    def check(self, key: str) -> None:
        if self._count(key) >= self.limit:
            raise ServiceError(self.message, 429)

    def count(self, key: str) -> None:
        """Refuses once `key` has reached the limit, then counts this request."""
        self.check(key)
        self.failed(key)

    def failed(self, key: str) -> None:
        if self.store is not None:
            self.store.add(key)
            return
        with self._lock:
            self._recent(key).append(time.monotonic())

    def succeeded(self, key: str) -> None:
        if self.store is not None:
            self.store.clear(key)
            return
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
    as_of: date = date.min
    """Today, for deciding whether a firm's workspace can still be changed."""
    is_staff: bool = False
    """Works for Lekhara (see `staff.py`)."""
    support_for: str | None = None
    """On a support session: the firm being seen, read-only, with its consent."""
    support_ends: datetime | None = None
    session_id: str | None = None
    confirmed_at: datetime | None = None
    """When the person last proved it was them in this session (see `require_recent`)."""
    two_step_on: bool = False
    two_step_required: bool = False
    """One of the person's firms requires two-step sign-in."""

    def org_role(self, project: Project) -> OrgRole | None:
        return self.org_roles.get(project.organization_id)

    def can_view(self, project: Project) -> bool:
        return (
            project.organization_id in self.org_roles
            or project.id in self.project_roles
            or project.organization.is_sample
        )

    def is_team(self, project: Project) -> bool:
        """The firm's own team; or, on a sample project, anyone with no other role on it."""
        if self.org_role(project) is not None:
            return True
        return project.organization.is_sample and project.id not in self.project_roles

    def is_team_member(self, project: Project) -> bool:
        """In the firm's own team, as opposed to looking at the sample."""
        return self.org_role(project) is not None

    def views_as_sample(self, project: Project) -> bool:
        """Looking at a sample project with no role on it: read-only."""
        return (
            project.organization.is_sample
            and not self.is_team_member(project)
            and project.id not in self.project_roles
        )

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
        if self.support_for is not None:
            return "Lekhara support, read-only"
        if self.org_roles:
            return ORG_ROLE_LABEL[next(iter(self.org_roles.values()))]
        roles = {role for roles in self.project_roles.values() for role in roles}
        return ", ".join(CERTIFIER_LABEL[r] for r in sorted(roles)) or "No access"


def start_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            created_at=now,
            expires_at=now + timedelta(days=SESSION_DAYS),
            # Signing in proves it is them, so sensitive steps need no second ask at first.
            confirmed_at=now,
            last_seen_at=now,
        )
    )
    session.commit()
    return token


# Asking again before sensitive steps, and the sessions a person has open

CONFIRM_MINUTES = 15
"""How long a confirmation (or a sign-in) covers sensitive steps."""
TOUCH_MINUTES = 5


class ConfirmNeeded(ServiceError):
    """A sensitive step asked for when the person has not proved it was them recently."""

    def __init__(self) -> None:
        super().__init__("Confirm it is you first: enter your password again.", 428)


class TwoStepNeeded(ServiceError):
    """The person's firm requires two-step sign-in and they have not set it up."""

    headers = {"X-Lekhara-Two-Step": "required"}

    def __init__(self) -> None:
        super().__init__(
            "Your firm asks everyone to use two-step sign-in. Set it up to go on.", 403
        )


def require_recent(principal: Principal) -> None:
    """Sensitive steps (downloading everything, changing who may do what, sharing outside the
    firm, staff actions) need the person to have signed in or confirmed in the last minutes, so
    a session left open on a shared computer cannot be used for them."""
    if principal.support_for is not None:
        raise ServiceError("Support can look but not change anything.", 403)
    recent = _now() - timedelta(minutes=CONFIRM_MINUTES)
    if principal.confirmed_at is None or principal.confirmed_at < recent:
        raise ConfirmNeeded()


def mark_confirmed(session: Session, session_id: str) -> None:
    row = session.get(UserSession, session_id)
    if row is not None:
        row.confirmed_at = _now()
        session.commit()


def touch(session: Session, principal: Principal, ip: str | None, agent: str | None) -> None:
    """Notes when and from where a session was last used, at most every few minutes."""
    if principal.session_id is None:
        return
    row = session.get(UserSession, principal.session_id)
    if row is None:
        return
    now = _now()
    changed = False
    if row.ip is None and ip:
        row.ip, row.user_agent, changed = ip[:64], (agent or "")[:300] or None, True
    if row.last_seen_at is None or row.last_seen_at < now - timedelta(minutes=TOUCH_MINUTES):
        row.last_seen_at, changed = now, True
    if changed:
        session.commit()


def describe_session(session: Session, token: str, ip: str | None, agent: str | None) -> None:
    row = session.scalars(
        select(UserSession).where(UserSession.token_hash == _token_hash(token))
    ).first()
    if row is not None:
        row.ip, row.user_agent = (ip or "")[:64] or None, (agent or "")[:300] or None
        session.commit()


def open_sessions(session: Session, user_id: str) -> list[UserSession]:
    """The person's own sessions still open, newest first (support sessions are not theirs)."""
    return list(
        session.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.support_org_id.is_(None),
                UserSession.expires_at > _now(),
            )
            .order_by(UserSession.created_at.desc())
        )
    )


def end_sessions(
    session: Session, user_id: str, *, only: str | None = None, keep: str | None = None
) -> int:
    """Signs the person out: of one session, or of every session but the one in use."""
    ended = 0
    for row in open_sessions(session, user_id):
        if (only is not None and row.id != only) or row.id == keep:
            continue
        session.delete(row)
        ended += 1
    session.commit()
    return ended


def login(
    session: Session, email: str, password: str, throttle: LoginThrottle
) -> tuple[str | None, User]:
    """A session token, or None when the person uses two-step sign-in and still has to give the
    code from their authenticator app."""
    key = email.strip().casefold()
    throttle.check(key)
    user = session.scalars(select(User).where(User.email == key)).first()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        throttle.failed(key)
        raise ServiceError("That email and password do not match.", 401)
    throttle.succeeded(key)
    if user.two_step_on is not None:
        return None, user
    return start_session(session, user), user


def logout(session: Session, token: str) -> None:
    row = session.scalars(
        select(UserSession).where(UserSession.token_hash == _token_hash(token))
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()


def principal_for(
    session: Session, token: str, as_of: date = date.min, *, idle_hours: float | None = None
) -> Principal | None:
    row = session.scalars(
        select(UserSession).where(UserSession.token_hash == _token_hash(token))
    ).first()
    now = _now()
    if row is None or row.expires_at < now:
        return None
    if idle_hours and (row.last_seen_at or row.created_at) < now - timedelta(hours=idle_hours):
        # Unused for too long: a session left open on a shared computer ends by itself.
        session.delete(row)
        session.commit()
        return None
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    if row.support_org_id is not None:
        # Support sees the one firm, as a viewer, only while the firm's consent lasts.
        if not user.is_staff or support_grant(session, row.support_org_id) is None:
            return None
        return Principal(
            user_id=user.id,
            name=user.name,
            email=user.email,
            firm=user.firm,
            org_roles={row.support_org_id: OrgRole.VIEWER},
            project_roles={},
            as_of=as_of,
            support_for=row.support_org_id,
            support_ends=row.expires_at,
        )
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
        as_of=as_of,
        is_staff=user.is_staff,
        session_id=row.id,
        confirmed_at=row.confirmed_at,
        two_step_on=user.two_step_on is not None
        or session.scalar(
            select(func.count()).select_from(Passkey).where(Passkey.user_id == user.id)
        )
        > 0,
        two_step_required=bool(org_roles)
        and session.scalar(
            select(func.count())
            .select_from(Organization)
            .where(Organization.id.in_(org_roles), Organization.require_two_step.is_(True))
        )
        > 0,
    )


SUPPORT_HOURS = 2


def support_grant(session: Session, organization_id: str) -> SupportGrant | None:
    """The firm's consent for support to see its workspace, if it holds now."""
    return session.scalars(
        select(SupportGrant)
        .where(
            SupportGrant.organization_id == organization_id,
            SupportGrant.withdrawn_at.is_(None),
            SupportGrant.expires_at > _now(),
        )
        .order_by(SupportGrant.expires_at.desc())
    ).first()


def start_support_session(
    session: Session, staff: User, organization_id: str
) -> tuple[str, datetime]:
    """A read-only session in the firm's workspace for a member of staff, for two hours at most
    and never past the firm's consent."""
    grant = support_grant(session, organization_id)
    if grant is None:
        raise ServiceError("This firm has not allowed support to see its workspace.", 403)
    token = secrets.token_urlsafe(32)
    now = _now()
    ends = min(grant.expires_at, now + timedelta(hours=SUPPORT_HOURS))
    session.add(
        UserSession(
            user_id=staff.id,
            token_hash=_token_hash(token),
            created_at=now,
            expires_at=ends,
            support_org_id=organization_id,
        )
    )
    session.commit()
    return token, ends


# Checks used by the API. A project outside someone's access looks the same as one that
# does not exist, so nothing leaks about other developers' projects.


def require_view(principal: Principal, project: Project) -> None:
    if not principal.can_view(project):
        raise ServiceError("Project not found.", 404)


def require_writable(principal: Principal, project: Project) -> None:
    if access_state(project.organization, principal.as_of) == "read_only":
        raise ServiceError(read_only_message(project.organization), 402)


def require_team(principal: Principal, project: Project) -> None:
    require_view(principal, project)
    if not principal.is_team(project):
        raise ServiceError("Only the developer's team can see this.", 403)


def require_prepare(principal: Principal, project: Project) -> None:
    require_view(principal, project)
    if not principal.can_prepare(project):
        if principal.views_as_sample(project):
            raise ServiceError("The sample projects are read-only.", 403)
        raise ServiceError("Your role cannot start or send withdrawals.", 403)
    require_writable(principal, project)


def require_share(principal: Principal, project: Project) -> None:
    require_view(principal, project)
    if not principal.can_release(project):
        raise ServiceError(
            "Only the owner or finance can share documents outside the company.", 403
        )
    require_writable(principal, project)


def require_release(principal: Principal, project: Project) -> None:
    require_view(principal, project)
    if not principal.can_release(project):
        raise ServiceError("Only the owner or finance can record what the bank did.", 403)
    require_writable(principal, project)


def require_certifier(principal: Principal, project: Project, role: CertifierRole) -> None:
    require_view(principal, project)
    if not principal.certifies(project, role):
        raise ServiceError(f"Only the project's {CERTIFIER_LABEL[role].lower()} can do this.", 403)
    require_writable(principal, project)
