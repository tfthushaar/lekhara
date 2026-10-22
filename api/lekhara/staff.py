"""Our own admin console: the firms using Lekhara, their trials and payments, and support access.

Only staff reach it (people marked here from the command line), and only with two-step sign-in
turned on. It reads across firms by design, so its requests are not restricted by row-level
security; it shows account facts (who is in a firm, how many projects, what was paid), never a
firm's records. Seeing those needs the firm's consent: an owner or finance allows support for a
few days, a support session is then read-only and ends when the consent does, and every request
it makes goes into the firm's own access log.

    python -m lekhara.staff add someone@lekhara.in
    python -m lekhara.staff remove someone@lekhara.in
    python -m lekhara.staff list
"""

import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara import auth, passkeys, records, services
from lekhara.models import (
    AccessEvent,
    Membership,
    Organization,
    Project,
    SubscriptionPayment,
    SupportGrant,
    Unit,
    User,
    UserSession,
)
from lekhara.services import ServiceError

METHODS = {
    "bank_transfer": "Bank transfer",
    "upi": "UPI",
    "cheque": "Cheque",
    "razorpay": "Razorpay",
}

SUPPORT_DAYS = (1, 3, 7, 14)
"""How long a firm can let support see its workspace for."""

STAFF_ACTIONS = ("staff_trial_extended", "staff_payment_recorded", "staff_payment_removed",
                 "support_opened")  # fmt: skip


def require_staff(session: Session, user: User | None) -> User:
    """Staff with two-step sign-in on. Anyone else is told the console does not exist."""
    if user is None or not user.is_staff:
        raise ServiceError("Not found.", 404)
    if user.two_step_on is None and not passkeys.has_passkey(session, user.id):
        raise ServiceError(
            "The admin console needs two-step sign-in or a passkey. Add one in Settings first.",
            403,
        )
    return user


# The firms


def iso(value: datetime | None) -> str | None:
    return None if value is None else value.replace(microsecond=0).isoformat()


def firm_rows(session: Session, as_of: date, query: str = "") -> list[dict]:
    q = query.strip().casefold()
    orgs = session.scalars(select(Organization).order_by(Organization.name)).all()
    people = dict(
        session.execute(
            select(Membership.organization_id, func.count()).group_by(Membership.organization_id)
        ).all()
    )
    projects = dict(
        session.execute(
            select(Project.organization_id, func.count()).group_by(Project.organization_id)
        ).all()
    )
    last_in = dict(
        session.execute(
            select(AccessEvent.organization_id, func.max(AccessEvent.at))
            .where(AccessEvent.action == "sign_in")
            .group_by(AccessEvent.organization_id)
        ).all()
    )
    emails: dict[str, list[str]] = {}
    if q:
        for org_id, email in session.execute(
            select(Membership.organization_id, User.email).join(User)
        ):
            emails.setdefault(org_id, []).append(email.casefold())
    rows = []
    for org in orgs:
        if q and q not in org.name.casefold() and not any(q in e for e in emails.get(org.id, [])):
            continue
        grant = auth.support_grant(session, org.id)
        rows.append(
            {
                "id": org.id,
                "name": org.name,
                "created_on": org.created_on.isoformat() if org.created_on else None,
                "access": services.access_state(org, as_of),
                "trial_ends_on": org.trial_ends_on.isoformat() if org.trial_ends_on else None,
                "paid_until": org.paid_until.isoformat() if org.paid_until else None,
                "people": people.get(org.id, 0),
                "projects": projects.get(org.id, 0),
                "last_sign_in": iso(last_in.get(org.id)),
                "support_until": iso(grant.expires_at) if grant else None,
                "closing": org.delete_after.isoformat() if org.delete_after else None,
                "is_sample": org.is_sample,
            }
        )
    return rows


def firm_detail(session: Session, org: Organization, as_of: date) -> dict:
    row = next(r for r in firm_rows(session, as_of) if r["id"] == org.id)
    last_in = dict(
        session.execute(
            select(AccessEvent.user_id, func.max(AccessEvent.at))
            .where(AccessEvent.action == "sign_in", AccessEvent.organization_id == org.id)
            .group_by(AccessEvent.user_id)
        ).all()
    )
    members = [
        {
            "name": user.name,
            "email": user.email,
            "role": auth.ORG_ROLE_LABEL[auth.OrgRole(m.role)],
            "two_step": user.two_step_on is not None,
            "last_sign_in": iso(last_in.get(user.id)),
        }
        for m, user in session.execute(
            select(Membership, User)
            .join(User)
            .where(Membership.organization_id == org.id)
            .order_by(User.name)
        )
    ]
    units = dict(
        session.execute(
            select(Unit.project_id, func.count())
            .join(Project)
            .where(Project.organization_id == org.id)
            .group_by(Unit.project_id)
        ).all()
    )
    projects = [
        {
            "name": p.name,
            "registration": p.krera_registration,
            "units": units.get(p.id, 0),
        }
        for p in session.scalars(
            select(Project).where(Project.organization_id == org.id).order_by(Project.name)
        )
    ]
    payments = [
        {
            "id": pay.id,
            "paid_on": pay.paid_on.isoformat(),
            "amount": str(pay.amount),
            "method": METHODS.get(pay.method, pay.method),
            "reference": pay.reference,
            "covers_from": pay.covers_from.isoformat(),
            "covers_to": pay.covers_to.isoformat(),
            "note": pay.note,
            "recorded_by": pay.recorded_by,
        }
        for pay in session.scalars(
            select(SubscriptionPayment)
            .where(SubscriptionPayment.organization_id == org.id)
            .order_by(SubscriptionPayment.paid_on.desc())
        )
    ]
    log = [
        {"at": iso(e.at), "who": e.who, "action": e.action, "detail": e.detail}
        for e in session.scalars(
            select(AccessEvent)
            .where(AccessEvent.organization_id == org.id, AccessEvent.action.in_(STAFF_ACTIONS))
            .order_by(AccessEvent.at.desc())
            .limit(50)
        )
    ]
    return {
        **row,
        "legal_name": org.legal_name,
        "gstin": org.gstin,
        "members": members,
        "projects_list": projects,
        "payments": payments,
        "staff_log": log,
        "methods": [{"value": k, "label": v} for k, v in METHODS.items()],
    }


def get_firm(session: Session, org_id: str) -> Organization:
    org = session.get(Organization, org_id)
    if org is None:
        raise ServiceError("Firm not found.", 404)
    return org


# Trials and payments


def _parse(label: str, raw: object, parse) -> object:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ServiceError(f"Enter {label}.")
    try:
        return parse(raw)
    except records.ParseError as exc:
        raise ServiceError(f"{label.capitalize()}: “{raw}” {exc}.") from None


def extend_trial(session: Session, org: Organization, values: dict, as_of: date) -> str:
    if org.is_sample:
        raise ServiceError("The sample firm has no trial.")
    if org.access == "active" and services.access_state(org, as_of) == "active":
        raise ServiceError("This firm has paid; record a payment instead.")
    ends_on = _parse("the new last day", values.get("ends_on"), records._date)
    if ends_on < as_of:
        raise ServiceError("The new last day cannot be in the past.")
    reason = (values.get("reason") or "").strip()
    if not reason:
        raise ServiceError("Say why, for the record.")
    org.access = "trial"
    org.trial_ends_on = ends_on
    return f"to {ends_on.isoformat()}: {reason}"


def record_payment(session: Session, org: Organization, values: dict, staff: User) -> str:
    if org.is_sample:
        raise ServiceError("The sample firm does not pay.")
    amount = _parse("the amount", values.get("amount"), records._money)
    if amount <= 0:
        raise ServiceError("The amount must be above zero.")
    paid_on = _parse("the day it was paid", values.get("paid_on"), records._date)
    covers_from = _parse("the first day it pays for", values.get("covers_from"), records._date)
    covers_to = _parse("the last day it pays for", values.get("covers_to"), records._date)
    if covers_to < covers_from:
        raise ServiceError("The last day it pays for comes before the first.")
    method = values.get("method") or ""
    if method not in METHODS:
        raise ServiceError("Choose how it was paid.")
    reference = (values.get("reference") or "").strip()
    if not reference:
        raise ServiceError("Enter the bank or UPI reference, or the cheque number.")
    session.add(
        SubscriptionPayment(
            organization_id=org.id,
            firm_name=org.name,
            amount=Decimal(amount),
            paid_on=paid_on,
            method=method,
            reference=reference[:120],
            covers_from=covers_from,
            covers_to=covers_to,
            note=(values.get("note") or "").strip()[:500] or None,
            recorded_by=staff.email,
        )
    )
    org.access = "active"
    org.paid_until = max(covers_to, org.paid_until or covers_to)
    return f"₹{amount} by {METHODS[method]}, {reference}, for {covers_from} to {covers_to}"


def remove_payment(session: Session, payment: SubscriptionPayment) -> str:
    """For a payment recorded by mistake. The firm is then paid to the end of what is left."""
    org = session.get(Organization, payment.organization_id)
    detail = f"₹{payment.amount}, {payment.reference}"
    session.delete(payment)
    session.flush()
    if org is not None:
        last = session.scalar(
            select(func.max(SubscriptionPayment.covers_to)).where(
                SubscriptionPayment.organization_id == org.id
            )
        )
        if last is not None:
            org.paid_until = last
        else:
            # Nothing paid any more: back to where the trial left it.
            org.access = "trial"
            org.paid_until = None
    return detail


# The firm's consent for support


def support_view(session: Session, org: Organization) -> dict:
    grant = auth.support_grant(session, org.id)
    by = session.get(User, grant.granted_by) if grant else None
    return {
        "allowed_until": iso(grant.expires_at) if grant else None,
        "allowed_by": by.name if by else None,
        "days": list(SUPPORT_DAYS),
    }


def allow_support(session: Session, org: Organization, user: User, days: int) -> datetime:
    if days not in SUPPORT_DAYS:
        raise ServiceError("Choose how long support may see your workspace.")
    now = auth._now()
    for grant in session.scalars(
        select(SupportGrant).where(
            SupportGrant.organization_id == org.id, SupportGrant.withdrawn_at.is_(None)
        )
    ):
        grant.withdrawn_at = now
        grant.withdrawn_by = user.id
    expires = now + timedelta(days=days)
    session.add(
        SupportGrant(organization_id=org.id, granted_by=user.id, granted_at=now, expires_at=expires)
    )
    return expires


def withdraw_support(session: Session, org: Organization, user: User) -> bool:
    """Ends the consent, and with it every support session open on the firm."""
    now = auth._now()
    found = False
    for grant in session.scalars(
        select(SupportGrant).where(
            SupportGrant.organization_id == org.id,
            SupportGrant.withdrawn_at.is_(None),
            SupportGrant.expires_at > now,
        )
    ):
        grant.withdrawn_at = now
        grant.withdrawn_by = user.id
        found = True
    for row in session.scalars(select(UserSession).where(UserSession.support_org_id == org.id)):
        session.delete(row)
    return found


# The command line


def main(argv: list[str]) -> int:
    from lekhara.config import get_settings
    from lekhara.db import make_engine, make_sessionmaker

    if (
        len(argv) < 1
        or argv[0] not in ("add", "remove", "list")
        or (argv[0] != "list" and len(argv) != 2)
    ):
        print(__doc__)
        return 2
    make = make_sessionmaker(make_engine(get_settings().database_url))
    with make() as session:
        if argv[0] == "list":
            for user in session.scalars(select(User).where(User.is_staff).order_by(User.email)):
                two = "two-step on" if user.two_step_on else "two-step OFF"
                print(f"{user.email}  {user.name}  ({two})")
            return 0
        email = argv[1].strip().casefold()
        user = session.scalars(select(User).where(func.lower(User.email) == email)).first()
        if user is None:
            print(f"No one has signed up as {email}. They sign up first, then are made staff.")
            return 1
        user.is_staff = argv[0] == "add"
        session.commit()
        print(f"{email} is {'now' if user.is_staff else 'no longer'} staff.")
        if user.is_staff and user.two_step_on is None:
            print("They need to turn on two-step sign-in in Settings before the console opens.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
