"""What the law asks of Lekhara as a service, in code: the terms, privacy notice and data
processing terms people accept (and when), the access log, deleting a person's account, and
closing a firm's account with its data deleted after a wait.

Plan section 18 has the research behind it: the DPDP Act and Rules, the IT Act and the SPDI
Rules, the CERT-In Directions (logs kept 180 days in India), and the consumer authority's
guidelines on dark patterns.
"""

import secrets
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from lekhara import jobs
from lekhara.auth import OrgRole, hash_password
from lekhara.config import Settings
from lekhara.models import (
    Acceptance,
    AccessEvent,
    Membership,
    OneTimeToken,
    Organization,
    ProjectAccess,
    User,
    UserSession,
    utcnow,
)
from lekhara.services import ServiceError

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
    session.add(
        AccessEvent(
            organization_id=organization_id,
            user_id=user.id if user else None,
            who=user.email if user else None,
            action=action[:48],
            detail=(detail or None) and detail[:300],
            ip=(ip or None) and ip[:64],
            user_agent=(user_agent or None) and user_agent[:300],
        )
    )
    if commit:
        session.commit()


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

    steps = [
        (m.DataRoomVisit, m.DataRoomVisit.room_id, rooms),
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
        (m.StatementPassword, m.StatementPassword.organization_id, [org.id]),
        (m.Invitation, m.Invitation.organization_id, [org.id]),
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


jobs.every("legal.daily", 24 * 3600)
