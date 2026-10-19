"""Firms and the people in them: sign-up, the free month, email checks, password resets,
invitations and the team.

A builder firm is one organisation and one subscription. It starts with a free month on
its own data; after that, an unpaid workspace becomes read-only, never locked or deleted.
"""

import hashlib
import re
import secrets
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara.auth import (
    CERTIFIER_LABEL,
    ORG_ROLE_LABEL,
    OrgRole,
    Principal,
    hash_password,
    start_session,
    verify_password,
)
from lekhara.config import Settings
from lekhara.engines.escrow import CertifierRole
from lekhara.mail import send_email
from lekhara.models import (
    Invitation,
    Membership,
    OneTimeToken,
    Organization,
    Project,
    ProjectAccess,
    User,
    UserSession,
    utcnow,
)
from lekhara.services import ServiceError

MIN_PASSWORD = 10
VERIFY_DAYS = 7
RESET_HOURS = 1
INVITE_DAYS = 7

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GSTIN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# The state each GSTIN belongs to, from its first two digits.
GSTIN_STATE = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
}

LAND_STRUCTURES = ("own", "jda_area_share", "jda_revenue_share")
GST_REGIMES = ("affordable_1pc", "residential_5pc", "commercial_12pc", "rrep_mixed")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalise_email(email: str | None) -> str:
    email = (email or "").strip().casefold()
    if not _EMAIL.match(email):
        raise ServiceError("Enter a valid email address.")
    return email


def check_password(password: str | None) -> str:
    if not password or len(password) < MIN_PASSWORD:
        raise ServiceError(f"Use a password of at least {MIN_PASSWORD} characters.")
    return password


CONSTITUTION = {
    "C": "Company",
    "F": "Partnership firm or LLP",
    "P": "Proprietor",
    "H": "Hindu undivided family",
    "A": "Association of persons",
    "B": "Body of individuals",
    "T": "Trust",
    "L": "Local authority",
    "J": "Artificial juridical person",
    "G": "Government",
}


def gstin_facts(gstin: str | None) -> dict:
    """What a GSTIN itself says: the state, the PAN inside it, and from the PAN, the kind of
    business. The legal name is not in the number; it is on the GST certificate."""
    if not gstin:
        return {"state": None, "pan": None, "constitution": None}
    pan = gstin[2:12]
    return {
        "state": GSTIN_STATE.get(gstin[:2]),
        "pan": pan,
        "constitution": CONSTITUTION.get(pan[3]),
    }


def check_gstin(gstin: str | None) -> str | None:
    gstin = (gstin or "").strip().upper()
    if not gstin:
        return None
    if not _GSTIN.match(gstin):
        raise ServiceError("A GSTIN has 15 characters, like 29ABCDE1234F1Z5.")
    total = 0
    for i, char in enumerate(gstin[:14]):
        product = _GSTIN_CHARS.index(char) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    if _GSTIN_CHARS[(36 - total % 36) % 36] != gstin[14]:
        raise ServiceError("This GSTIN does not add up. Check it against your registration.")
    return gstin


# One-time links: confirming an email, resetting a password


def _one_time(session: Session, user: User, purpose: str, lifetime: timedelta) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    session.add(
        OneTimeToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=_hash(token),
            created_at=now,
            expires_at=now + lifetime,
        )
    )
    return token


def _redeem(session: Session, token: str, purpose: str) -> OneTimeToken:
    row = session.scalars(
        select(OneTimeToken).where(
            OneTimeToken.token_hash == _hash(token or ""), OneTimeToken.purpose == purpose
        )
    ).first()
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        raise ServiceError("This link has expired or has already been used.", 400)
    row.used_at = utcnow()
    return row


def send_verification(session: Session, settings: Settings, user: User) -> None:
    token = _one_time(session, user, "verify_email", timedelta(days=VERIFY_DAYS))
    send_email(
        session,
        settings,
        to=user.email,
        kind="verify_email",
        subject="Confirm your email for Lekhara",
        body=(
            f"Hello {user.name},\n\n"
            f"Confirm your email address for Lekhara:\n{settings.web_url}/verify/{token}\n\n"
            f"The link works for {VERIFY_DAYS} days."
        ),
    )


def verify_email(session: Session, token: str) -> User:
    row = _redeem(session, token, "verify_email")
    user = session.get(User, row.user_id)
    user.email_verified_at = utcnow()
    session.commit()
    return user


def forgot_password(session: Session, settings: Settings, email: str | None) -> None:
    """Sends a reset link if the account exists. Says nothing either way, so the form cannot be
    used to find out who has an account."""
    try:
        email = normalise_email(email)
    except ServiceError:
        return
    user = session.scalars(select(User).where(User.email == email)).first()
    if user is None or not user.is_active:
        return
    token = _one_time(session, user, "reset_password", timedelta(hours=RESET_HOURS))
    send_email(
        session,
        settings,
        to=user.email,
        kind="reset_password",
        subject="Reset your Lekhara password",
        body=(
            f"Hello {user.name},\n\n"
            f"Set a new password for Lekhara:\n{settings.web_url}/reset/{token}\n\n"
            "The link works for one hour. If you did not ask for this, ignore this email."
        ),
    )
    session.commit()


def reset_password(session: Session, token: str, password: str | None) -> None:
    check_password(password)
    row = _redeem(session, token, "reset_password")
    user = session.get(User, row.user_id)
    user.password_hash = hash_password(password)
    for old in session.scalars(select(UserSession).where(UserSession.user_id == user.id)):
        session.delete(old)
    session.commit()


# Sign-up


def signup(
    session: Session,
    settings: Settings,
    *,
    name: str | None,
    email: str | None,
    password: str | None,
    firm: str | None,
    as_of: date,
) -> tuple[str, User]:
    name = (name or "").strip()
    firm = (firm or "").strip()
    if not name:
        raise ServiceError("Enter your name.")
    if not firm:
        raise ServiceError("Enter your firm's name.")
    email = normalise_email(email)
    check_password(password)
    if session.scalars(select(User).where(User.email == email)).first() is not None:
        raise ServiceError("An account with this email already exists. Sign in instead.", 409)
    org = Organization(
        name=firm[:200],
        access="trial",
        created_on=as_of,
        trial_ends_on=as_of + timedelta(days=settings.trial_days),
    )
    user = User(name=name[:200], email=email, password_hash=hash_password(password))
    session.add_all([org, user])
    session.flush()
    session.add(Membership(user_id=user.id, organization_id=org.id, role=OrgRole.OWNER.value))
    send_verification(session, settings, user)
    token = start_session(session, user)
    return token, user


# The firm and its team


def current_org(session: Session, me: Principal) -> Organization:
    """The firm the person belongs to. Certifiers who are only on other firms' projects have
    none."""
    orgs = sorted(
        (session.get(Organization, org_id) for org_id in me.org_roles), key=lambda o: o.name
    )
    if not orgs:
        raise ServiceError("Not found.", 404)
    return orgs[0]


def require_manager(me: Principal, org: Organization, *, owner: bool = False) -> None:
    role = me.org_roles.get(org.id)
    allowed = (OrgRole.OWNER,) if owner else (OrgRole.OWNER, OrgRole.FINANCE)
    if role not in allowed:
        who = "the owner" if owner else "the owner or finance"
        raise ServiceError(f"Only {who} can do this.", 403)


def update_org(session: Session, org: Organization, fields: dict) -> Organization:
    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise ServiceError("Enter the firm's name.")
        org.name = name[:200]
    if "legal_name" in fields:
        org.legal_name = (fields["legal_name"] or "").strip()[:200] or None
    if "gstin" in fields:
        org.gstin = check_gstin(fields["gstin"])
    session.commit()
    return org


def team(session: Session, org: Organization) -> list[tuple[User, str]]:
    rows = session.scalars(select(Membership).where(Membership.organization_id == org.id))
    return sorted(((m.user, m.role) for m in rows), key=lambda r: r[0].name)


def certifiers(session: Session, org: Organization) -> list[tuple[User, str, list[Project]]]:
    projects = {
        p.id: p for p in session.scalars(select(Project).where(Project.organization_id == org.id))
    }
    grouped: dict[tuple[str, str], list[Project]] = {}
    users: dict[str, User] = {}
    for access in session.scalars(
        select(ProjectAccess).where(ProjectAccess.project_id.in_(projects))
    ):
        users[access.user_id] = access.user
        grouped.setdefault((access.user_id, access.role), []).append(projects[access.project_id])
    out = [
        (users[uid], role, sorted(ps, key=lambda p: p.name)) for (uid, role), ps in grouped.items()
    ]
    return sorted(out, key=lambda r: (r[0].name, r[1]))


def pending_invitations(session: Session, org: Organization) -> list[Invitation]:
    now = utcnow()
    return list(
        session.scalars(
            select(Invitation)
            .where(
                Invitation.organization_id == org.id,
                Invitation.accepted_at.is_(None),
                Invitation.cancelled_at.is_(None),
                Invitation.expires_at >= now,
            )
            .order_by(Invitation.created_at.desc())
        )
    )


ROLE_LABEL = {
    **{role.value: label for role, label in ORG_ROLE_LABEL.items()},
    **{role.value: label for role, label in CERTIFIER_LABEL.items()},
}


def invite(
    session: Session,
    settings: Settings,
    org: Organization,
    me: Principal,
    *,
    email: str | None,
    role: str | None,
    project_ids: list[str] | None,
) -> tuple[Invitation, str]:
    require_manager(me, org, owner=role == OrgRole.OWNER.value)
    email = normalise_email(email)
    project_ids = list(dict.fromkeys(project_ids or []))
    org_role = certifier_role = None
    if role in {r.value for r in OrgRole}:
        org_role = role
    elif role in {r.value for r in CertifierRole}:
        certifier_role = role
        own = {
            p.id for p in session.scalars(select(Project).where(Project.organization_id == org.id))
        }
        if not project_ids or not set(project_ids) <= own:
            raise ServiceError("Choose the projects they certify.")
    else:
        raise ServiceError("Choose a role from the list.")
    existing = session.scalars(select(User).where(User.email == email)).first()
    if org_role and existing is not None and existing.id in {u.id for u, _ in team(session, org)}:
        raise ServiceError("This person is already in your team.")
    token = secrets.token_urlsafe(32)
    now = utcnow()
    row = Invitation(
        organization_id=org.id,
        email=email,
        org_role=org_role,
        certifier_role=certifier_role,
        project_ids=",".join(project_ids) or None,
        token_hash=_hash(token),
        invited_by_user_id=me.user_id,
        created_at=now,
        expires_at=now + timedelta(days=INVITE_DAYS),
    )
    session.add(row)
    link = f"{settings.web_url}/invite/{token}"
    send_email(
        session,
        settings,
        to=email,
        kind="invitation",
        subject=f"{me.name} has invited you to {org.name} on Lekhara",
        body=(
            f"{me.name} has invited you to join {org.name} on Lekhara as "
            f"{ROLE_LABEL[role].lower()}.\n\nAccept the invitation:\n{link}\n\n"
            f"The link works for {INVITE_DAYS} days."
        ),
    )
    session.commit()
    return row, link


def invitation_by_token(session: Session, token: str) -> Invitation:
    row = session.scalars(
        select(Invitation).where(Invitation.token_hash == _hash(token or ""))
    ).first()
    if (
        row is None
        or row.accepted_at is not None
        or row.cancelled_at is not None
        or row.expires_at < utcnow()
    ):
        raise ServiceError("This invitation has expired or has already been used.", 404)
    return row


def invitation_projects(session: Session, row: Invitation) -> list[Project]:
    ids = [i for i in (row.project_ids or "").split(",") if i]
    return [p for p in (session.get(Project, i) for i in ids) if p is not None]


def accept_invitation(
    session: Session,
    settings: Settings,
    token: str,
    *,
    name: str | None,
    password: str | None,
    firm: str | None,
    code: str | None = None,
) -> str:
    row = invitation_by_token(session, token)
    user = session.scalars(select(User).where(User.email == row.email)).first()
    if user is None:
        name = (name or "").strip()
        if not name:
            raise ServiceError("Enter your name.")
        check_password(password)
        user = User(
            name=name[:200],
            email=row.email,
            password_hash=hash_password(password),
            firm=(firm or "").strip()[:200] or None,
        )
        session.add(user)
        session.flush()
        send_verification(session, settings, user)
    elif not verify_password(password or "", user.password_hash):
        raise ServiceError("That password does not match your existing Lekhara account.", 401)
    elif user.two_step_on is not None:
        from lekhara import two_step

        if not code:
            raise ServiceError(
                "You use two-step sign-in. Enter the code from your authenticator app too.", 401
            )
        two_step.check_code(session, settings, user, code)
    if row.org_role:
        if (
            session.scalars(
                select(Membership).where(
                    Membership.user_id == user.id, Membership.organization_id == row.organization_id
                )
            ).first()
            is None
        ):
            session.add(
                Membership(user_id=user.id, organization_id=row.organization_id, role=row.org_role)
            )
    else:
        if firm and not user.firm:
            user.firm = firm.strip()[:200]
        for project in invitation_projects(session, row):
            exists = session.scalars(
                select(ProjectAccess).where(
                    ProjectAccess.user_id == user.id,
                    ProjectAccess.project_id == project.id,
                    ProjectAccess.role == row.certifier_role,
                )
            ).first()
            if exists is None:
                session.add(
                    ProjectAccess(user_id=user.id, project_id=project.id, role=row.certifier_role)
                )
    row.accepted_at = utcnow()
    return start_session(session, user)


def cancel_invitation(session: Session, org: Organization, me: Principal, invitation_id: str):
    require_manager(me, org)
    row = session.get(Invitation, invitation_id)
    if row is None or row.organization_id != org.id:
        raise ServiceError("Invitation not found.", 404)
    row.cancelled_at = utcnow()
    session.commit()


def _membership(session: Session, org: Organization, user_id: str) -> Membership:
    row = session.scalars(
        select(Membership).where(
            Membership.organization_id == org.id, Membership.user_id == user_id
        )
    ).first()
    if row is None:
        raise ServiceError("This person is not in your team.", 404)
    return row


def _keep_an_owner(session: Session, org: Organization, leaving: Membership) -> None:
    owners = [
        m
        for m in session.scalars(select(Membership).where(Membership.organization_id == org.id))
        if m.role == OrgRole.OWNER.value
    ]
    if leaving.role == OrgRole.OWNER.value and len(owners) == 1:
        raise ServiceError("The firm needs at least one owner. Make someone else an owner first.")


def change_role(
    session: Session, org: Organization, me: Principal, user_id: str, role: str | None
) -> None:
    require_manager(me, org, owner=True)
    if role not in {r.value for r in OrgRole}:
        raise ServiceError("Choose a role from the list.")
    member = _membership(session, org, user_id)
    if role != OrgRole.OWNER.value:
        _keep_an_owner(session, org, member)
    member.role = role
    session.commit()


def remove_member(session: Session, org: Organization, me: Principal, user_id: str) -> None:
    require_manager(me, org, owner=True)
    member = _membership(session, org, user_id)
    _keep_an_owner(session, org, member)
    session.delete(member)
    session.commit()


# Projects


def create_project(session: Session, org: Organization, me: Principal, fields: dict) -> Project:
    if me.org_roles.get(org.id) not in (OrgRole.OWNER, OrgRole.FINANCE, OrgRole.ACCOUNTS):
        raise ServiceError("Only the owner, finance or accounts can add a project.", 403)
    name = (fields.get("name") or "").strip()
    registration = (fields.get("krera_registration") or "").strip().upper()
    if not name:
        raise ServiceError("Enter the project's name.")
    if not registration:
        raise ServiceError("Enter the K-RERA registration number.")
    if fields.get("registered_on") is None:
        raise ServiceError("Enter the date of K-RERA registration.")
    duplicate = session.scalars(
        select(Project).where(
            Project.organization_id == org.id, Project.krera_registration == registration
        )
    ).first()
    if duplicate is not None:
        raise ServiceError(f'This K-RERA number is already used by "{duplicate.name}".')
    land = fields.get("land_structure") or "own"
    regime = fields.get("gst_regime") or "residential_5pc"
    if land not in LAND_STRUCTURES or regime not in GST_REGIMES:
        raise ServiceError("Choose the land structure and GST regime from the lists.")
    possession = fields.get("possession_due_on")
    if possession is not None and possession < fields["registered_on"]:
        raise ServiceError("The possession date cannot be before the K-RERA registration.")
    project = Project(
        organization_id=org.id,
        name=name[:200],
        locality=(fields.get("locality") or "").strip()[:200],
        city=(fields.get("city") or "Bengaluru").strip()[:100] or "Bengaluru",
        krera_registration=registration[:100],
        registered_on=fields["registered_on"],
        possession_due_on=possession,
        spv_name=(fields.get("spv_name") or org.legal_name or org.name).strip()[:200],
        land_structure=land,
        gst_regime=regime,
        escrow_bank=(fields.get("escrow_bank") or "").strip()[:200] or None,
    )
    session.add(project)
    session.commit()
    return project
