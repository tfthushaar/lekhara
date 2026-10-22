"""What the law asks of Lekhara as a service, in code: the terms, privacy notice and data
processing terms people accept (and when), the access log, deleting a person's account, and
closing a firm's account with its data deleted after a wait.

Plan section 18 has the research behind it: the DPDP Act and Rules, the IT Act and the SPDI
Rules, the CERT-In Directions (logs kept 180 days in India), and the consumer authority's
guidelines on dark patterns.
"""

import hashlib
import logging
import secrets
import sys
from datetime import date, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lekhara import jobs
from lekhara.auth import OrgRole, hash_password
from lekhara.config import Settings
from lekhara.models import (
    Acceptance,
    AccessEvent,
    AccessLogHead,
    Membership,
    OneTimeToken,
    Organization,
    Passkey,
    ProjectAccess,
    User,
    UserSession,
    utcnow,
)
from lekhara.services import ServiceError

log = logging.getLogger("lekhara.legal")

VERSION = "2026-10-18"
"""The version of the terms, the privacy notice and the data processing terms in force."""
DOCUMENTS = ("terms", "privacy", "data_processing")
CLOSE_AFTER_DAYS = 30
LOG_DAYS = 365
"""Access events are kept a year: more than the 180 days CERT-In asks for."""

SUB_PROCESSORS = (
    ("Hosting and file storage", "A cloud provider's data centres in India"),
    ("Email", "An email delivery service, for the emails Lekhara sends and receives"),
    ("Payments", "Razorpay, for the subscription; Lekhara never sees card or bank details"),
    ("AI document reading", "AI providers chosen per task, in India by default"),
)


def public_info(settings: Settings) -> dict:
    return {
        "version": VERSION,
        "company_name": settings.company_name,
        "company_address": settings.company_address,
        "grievance_officer": settings.grievance_officer,
        "grievance_email": settings.grievance_email,
        "contact_email": settings.contact_email,
        "contact_phone": settings.contact_phone,
        "price_per_month": settings.price_per_month,
        "months_charged_per_year": settings.months_charged_per_year,
        "trial_days": settings.trial_days,
        "close_after_days": CLOSE_AFTER_DAYS,
        "log_days": LOG_DAYS,
        "sub_processors": [{"what": w, "who": who} for w, who in SUB_PROCESSORS],
    }


# Acceptance


def accept(
    session: Session,
    user: User,
    *,
    organization_id: str | None,
    ip: str | None,
    manager: bool,
) -> None:
    """Record that a person accepted the current terms and privacy notice, and, for an owner
    or finance, the data processing terms on the firm's behalf."""
    documents = DOCUMENTS if manager else ("terms", "privacy")
    for document in documents:
        session.add(
            Acceptance(
                user_id=user.id,
                organization_id=organization_id,
                document=document,
                version=VERSION,
                ip=(ip or None) and ip[:64],
            )
        )


def accepted(session: Session, user_id: str) -> bool:
    found = session.scalar(
        select(func.count())
        .select_from(Acceptance)
        .where(Acceptance.user_id == user_id, Acceptance.version == VERSION)
    )
    return bool(found)


def require_acceptance(flag: bool | None) -> None:
    if not flag:
        raise ServiceError("Read and accept the terms of service and the privacy notice to go on.")


# The access log


def record(
    session: Session,
    action: str,
    *,
    user: User | None = None,
    organization_id: str | None = None,
    detail: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    commit: bool = True,
) -> None:
    """Adds an event to the access log. Once committed it is chained to the one before it
    (see seal_log); an event recorded without committing joins the chain at the next seal."""
    event = AccessEvent(
        at=utcnow(),
        organization_id=organization_id,
        user_id=user.id if user else None,
        who=user.email if user else None,
        action=action[:48],
        detail=(detail or None) and detail[:300],
        ip=(ip or None) and ip[:64],
        user_agent=(user_agent or None) and user_agent[:300],
    )
    session.add(event)
    if commit:
        session.commit()
        seal_log(session)


def seal_log(session: Session) -> int:
    """Chains every committed event not yet in the chain, in a transaction of its own on this
    session (which must have nothing uncommitted).

    It begins by writing to the chain's end, which takes the database's write lock (a row lock
    on Postgres, the file's on SQLite) before anything is read, so requests arriving together
    queue here instead of forking the chain. An event whose request was rolled back never
    reaches the chain, since only committed events are seen."""
    moved = session.execute(
        update(AccessLogHead).where(AccessLogHead.id == 1).values(seq=AccessLogHead.seq)
    ).rowcount
    if not moved:
        try:
            session.add(AccessLogHead(id=1, seq=0, hash=""))
            session.flush()
        except IntegrityError:
            session.rollback()
            return seal_log(session)  # another server started the chain first
    head = session.get(AccessLogHead, 1, populate_existing=True)
    events = list(
        session.scalars(
            select(AccessEvent)
            .where(AccessEvent.seq.is_(None))
            .order_by(AccessEvent.at, AccessEvent.id)
        )
    )
    for event in events:
        event.seq, event.prev_hash = head.seq + 1, head.hash
        event.hash = _event_hash(event)
        head.seq, head.hash = event.seq, event.hash
    session.commit()
    return len(events)


def _event_hash(event: AccessEvent) -> str:
    fields = (
        event.prev_hash or "",
        str(event.seq),
        event.at.isoformat(),
        event.organization_id or "",
        event.user_id or "",
        event.who or "",
        event.action,
        event.detail or "",
        event.ip or "",
        event.user_agent or "",
    )
    return hashlib.sha256("\x1f".join(fields).encode("utf-8")).hexdigest()


def verify_log(session: Session) -> dict:
    """Walks the access log's chain from its oldest kept event. Any event changed, inserted or
    taken out since it was written (other than the oldest, pruned after a year) breaks it."""
    checked, previous = 0, None
    for event in session.scalars(
        select(AccessEvent).where(AccessEvent.seq.is_not(None)).order_by(AccessEvent.seq)
    ):
        if previous is not None and (
            event.seq != previous.seq + 1 or event.prev_hash != previous.hash
        ):
            return {"intact": False, "checked": checked, "broken_at": event.seq}
        if _event_hash(event) != event.hash:
            return {"intact": False, "checked": checked, "broken_at": event.seq}
        checked, previous = checked + 1, event
    head = session.get(AccessLogHead, 1)
    if previous is not None and head is not None and head.hash != previous.hash:
        # The newest events were taken out.
        return {"intact": False, "checked": checked, "broken_at": previous.seq + 1}
    return {"intact": True, "checked": checked, "broken_at": None}


def events_for(session: Session, organization_id: str, limit: int = 200) -> list[AccessEvent]:
    return list(
        session.scalars(
            select(AccessEvent)
            .where(AccessEvent.organization_id == organization_id)
            .order_by(AccessEvent.at.desc())
            .limit(limit)
        )
    )


def prune_log(session: Session) -> int:
    cutoff = utcnow() - timedelta(days=LOG_DAYS)
    result = session.execute(delete(AccessEvent).where(AccessEvent.at < cutoff))
    session.commit()
    return result.rowcount or 0


# A person's own account


def _sole_owner_of(session: Session, user: User) -> list[Organization]:
    """Firms this person is the only owner of: deleting the account would leave them
    without anyone who can manage, pay for or close them."""
    out = []
    for m in session.scalars(
        select(Membership).where(Membership.user_id == user.id, Membership.role == "owner")
    ):
        owners = session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.organization_id == m.organization_id, Membership.role == "owner")
        )
        org = session.get(Organization, m.organization_id)
        if owners == 1 and org is not None and not org.is_sample:
            out.append(org)
    return out


def anonymise(session: Session, user: User) -> None:
    """Take a person's details out of Lekhara, keeping the records they made (signed
    certificates, changes in the history) under "A former user"."""
    session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    session.execute(delete(OneTimeToken).where(OneTimeToken.user_id == user.id))
    session.execute(delete(Passkey).where(Passkey.user_id == user.id))
    session.execute(delete(Membership).where(Membership.user_id == user.id))
    session.execute(delete(ProjectAccess).where(ProjectAccess.user_id == user.id))
    user.name = "A former user"
    user.email = f"deleted-{user.id}@deleted.invalid"
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.firm = None
    user.phone = None
    user.is_active = False


def delete_account(session: Session, user: User, *, ip: str | None) -> None:
    owned = _sole_owner_of(session, user)
    if owned:
        names = ", ".join(o.name for o in owned)
        raise ServiceError(
            f"You are the only owner of {names}. Make someone else an owner first, or close "
            "the firm's account in Settings."
        )
    orgs = list(
        session.scalars(select(Membership.organization_id).where(Membership.user_id == user.id))
    )
    record(
        session,
        "account_deleted",
        user=user,
        organization_id=orgs[0] if orgs else None,
        ip=ip,
        commit=False,
    )
    anonymise(session, user)
    session.commit()


# Closing a firm's account


def close_firm(
    session: Session, org: Organization, *, confirm: str, as_of: date, user: User, ip
) -> None:
    if org.is_sample:
        raise ServiceError("The sample firm cannot be closed.")
    if org.closing_on is not None:
        raise ServiceError("The firm's account is already being closed.")
    if " ".join((confirm or "").split()).casefold() != " ".join(org.name.split()).casefold():
        raise ServiceError("Type the firm's name exactly to confirm.")
    org.closing_on = as_of
    org.delete_after = as_of + timedelta(days=CLOSE_AFTER_DAYS)
    record(
        session,
        "firm_close_requested",
        user=user,
        organization_id=org.id,
        detail=f"Data to be deleted after {org.delete_after.isoformat()}",
        ip=ip,
        commit=False,
    )
    session.commit()


def keep_firm(session: Session, org: Organization, *, user: User, ip) -> None:
    if org.closing_on is None:
        raise ServiceError("The firm's account is not being closed.")
    org.closing_on = None
    org.delete_after = None
    record(session, "firm_close_cancelled", user=user, organization_id=org.id, ip=ip, commit=False)
    session.commit()


def _purge_scoped(session: Session, org: Organization) -> list[str]:
    """Delete every row of the firm's data, children first, and return the storage keys of
    files it held. Bulk deletes bypass the append-only guards, which protect history from
    edits, not from the firm's own request to be forgotten."""
    from lekhara import export
    from lekhara import models as m

    scope = export.scope_for(session, org)
    projects, units, cases = scope.projects, scope.units, scope.cases
    rooms, requests, landowners = scope.rooms, scope.requests, scope.landowners
    documents = list(
        session.scalars(select(m.Document.id).where(m.Document.organization_id == org.id))
    )
    messages = list(
        session.scalars(
            select(m.InboundMessage.id).where(m.InboundMessage.organization_id == org.id)
        )
    )
    keys: list[str] = []
    for model, column, ids in (
        (m.Document, m.Document.organization_id, [org.id]),
        (m.BankStatement, m.BankStatement.organization_id, [org.id]),
        (m.TallyImport, m.TallyImport.organization_id, [org.id]),
        (m.GstImport, m.GstImport.organization_id, [org.id]),
        (m.InboundMessage, m.InboundMessage.organization_id, [org.id]),
        (m.InboundItem, m.InboundItem.message_id, messages),
    ):
        keys += [r.storage_key for r in session.scalars(select(model).where(column.in_(ids)))]
    keys += [
        c.masters_key
        for c in session.scalars(select(m.Connector).where(m.Connector.organization_id == org.id))
        if c.masters_key
    ]

    originals = list(
        session.scalars(select(m.Original.id).where(m.Original.organization_id == org.id))
    )
    steps = [
        (m.OriginalMove, m.OriginalMove.original_id, originals),
        (m.Original, m.Original.organization_id, [org.id]),
        (m.DataRoomVisit, m.DataRoomVisit.room_id, rooms),
        (m.DataRoomVisitor, m.DataRoomVisitor.room_id, rooms),
        (m.DataRoomDocument, m.DataRoomDocument.room_id, rooms),
        (m.DataRoom, m.DataRoom.project_id, projects),
        (m.ChecklistWaiver, m.ChecklistWaiver.project_id, projects),
        (m.DocumentPage, m.DocumentPage.document_id, documents),
        (m.Document, m.Document.organization_id, [org.id]),
        (m.Receipt, m.Receipt.project_id, projects),
        (m.DemandRow, m.DemandRow.project_id, projects),
        (m.BookingCancellation, m.BookingCancellation.project_id, projects),
        (m.HandoverItem, m.HandoverItem.project_id, projects),
        (m.DisputePayment, m.DisputePayment.case_id, cases),
        (m.DisputeOrder, m.DisputeOrder.case_id, cases),
        (m.DisputeHearing, m.DisputeHearing.case_id, cases),
        (m.DisputeCase, m.DisputeCase.project_id, projects),
        (m.WithdrawalCertificate, m.WithdrawalCertificate.request_id, requests),
        (m.WithdrawalRequest, m.WithdrawalRequest.project_id, projects),
        (m.LandownerPaymentRow, m.LandownerPaymentRow.landowner_id, landowners),
        (m.Landowner, m.Landowner.project_id, projects),
        (m.PaymentMilestone, m.PaymentMilestone.project_id, projects),
        (m.UnitHandover, m.UnitHandover.unit_id, units),
        (m.BankRule, m.BankRule.organization_id, [org.id]),
        (m.BankPayer, m.BankPayer.project_id, projects),
        (m.BankAccount, m.BankAccount.project_id, projects),
        (m.BankStatement, m.BankStatement.organization_id, [org.id]),
        (m.GstImport, m.GstImport.organization_id, [org.id]),
        (m.InboundItem, m.InboundItem.message_id, messages),
        (m.InboundMessage, m.InboundMessage.organization_id, [org.id]),
        (m.Connector, m.Connector.organization_id, [org.id]),
        (m.TallyLink, m.TallyLink.project_id, projects),
        (m.TallyImport, m.TallyImport.organization_id, [org.id]),
        (m.ImportBatch, m.ImportBatch.organization_id, [org.id]),
        (m.ImportMapping, m.ImportMapping.organization_id, [org.id]),
        (m.Commitment, m.Commitment.project_id, projects),
        (m.Bill, m.Bill.project_id, projects),
        (m.LedgerEntry, m.LedgerEntry.project_id, projects),
        (m.EscrowTxn, m.EscrowTxn.project_id, projects),
        (m.CostLineRow, m.CostLineRow.project_id, projects),
        (m.ProgressCertificate, m.ProgressCertificate.project_id, projects),
        (m.Filing, m.Filing.project_id, projects),
        (m.Approval, m.Approval.project_id, projects),
        (m.ChangeEntry, m.ChangeEntry.organization_id, [org.id]),
        (m.Unit, m.Unit.project_id, projects),
        (m.ProjectAccess, m.ProjectAccess.project_id, projects),
        (m.Project, m.Project.organization_id, [org.id]),
        (m.Vendor, m.Vendor.organization_id, [org.id]),
        (m.TrustedSender, m.TrustedSender.organization_id, [org.id]),
        (m.FilingRule, m.FilingRule.organization_id, [org.id]),
        (m.StatementPassword, m.StatementPassword.organization_id, [org.id]),
        (m.Invitation, m.Invitation.organization_id, [org.id]),
        (m.SupportGrant, m.SupportGrant.organization_id, [org.id]),
        (m.UserSession, m.UserSession.support_org_id, [org.id]),
    ]
    for model, column, ids in steps:
        if ids:
            session.execute(delete(model).where(column.in_(ids)))
    return keys


def purge_firm(session: Session, storage, org: Organization) -> None:
    """Delete a closed firm's data and files, take out the people who worked only for it,
    and keep the access log (kept on its own for CERT-In)."""
    from lekhara import models as m

    members = list(
        session.scalars(select(m.Membership.user_id).where(m.Membership.organization_id == org.id))
    )
    keys = _purge_scoped(session, org)
    session.execute(delete(m.Membership).where(m.Membership.organization_id == org.id))
    session.flush()
    for user_id in members:
        user = session.get(User, user_id)
        if user is None:
            continue
        elsewhere = session.scalar(
            select(func.count()).select_from(m.Membership).where(m.Membership.user_id == user_id)
        ) or session.scalar(
            select(func.count())
            .select_from(m.ProjectAccess)
            .where(m.ProjectAccess.user_id == user_id)
        )
        if not elsewhere:
            anonymise(session, user)
    record(
        session,
        "firm_deleted",
        organization_id=org.id,
        detail=f"{org.name}: data deleted after closing",
        commit=False,
    )
    session.delete(org)
    session.flush()
    still_used = set()
    for model, attr in (
        (m.Document, "storage_key"),
        (m.BankStatement, "storage_key"),
        (m.TallyImport, "storage_key"),
        (m.GstImport, "storage_key"),
        (m.InboundMessage, "storage_key"),
        (m.InboundItem, "storage_key"),
    ):
        column = getattr(model, attr)
        still_used |= set(session.scalars(select(column).where(column.in_(keys))))
    session.commit()
    for key in set(keys) - still_used:
        if key:
            storage.delete(key)


def due_for_deletion(session: Session, as_of: date) -> list[Organization]:
    return list(
        session.scalars(
            select(Organization).where(
                Organization.delete_after.is_not(None), Organization.delete_after <= as_of
            )
        )
    )


def manager_roles() -> tuple[str, str]:
    return (OrgRole.OWNER.value, OrgRole.FINANCE.value)


@jobs.handler("legal.daily")
def _daily(ctx: jobs.Context, payload: dict) -> None:
    """Delete firms whose closing wait is over, and access events past their keeping."""
    for org in due_for_deletion(ctx.session, ctx.settings.as_of()):
        purge_firm(ctx.session, ctx.storage, org)
    prune_log(ctx.session)
    seal_log(ctx.session)
    checked = verify_log(ctx.session)
    if not checked["intact"]:
        log.error("The access log's chain is broken at event %s.", checked["broken_at"])


jobs.every("legal.daily", 24 * 3600)


def main(argv: list[str]) -> int:
    """python -m lekhara.legal verify-log: checks the access log has not been altered."""
    from lekhara.config import get_settings
    from lekhara.db import make_engine, make_sessionmaker

    if argv != ["verify-log"]:
        print(main.__doc__)
        return 2
    with make_sessionmaker(make_engine(get_settings().database_url))() as session:
        result = verify_log(session)
    if result["intact"]:
        print(f"The access log is intact: {result['checked']} events checked.")
        return 0
    print(f"The access log has been altered at event {result['broken_at']}.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
