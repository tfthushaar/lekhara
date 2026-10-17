"""How set up a project is: which data is in, how fresh it is, and what each missing piece
unlocks, so a builder always knows the next thing to bring in."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara import registers, services
from lekhara.models import (
    Bill,
    EscrowTxn,
    Landowner,
    LedgerEntry,
    ProgressCertificate,
    Project,
    ProjectAccess,
    Receipt,
    Unit,
)

STALE_DAYS = 45
PROGRESS_STALE_DAYS = 100
CERTIFIER_ROLES = {"architect": "architect", "engineer": "engineer", "ca": "CA"}


@dataclass(frozen=True)
class Item:
    key: str
    title: str
    status: str
    """done, partial, stale or missing."""
    detail: str
    unlocks: str
    action: str
    href: str


def _fresh(last: date | None, as_of: date, days: int = STALE_DAYS) -> bool:
    return last is not None and (as_of - last).days <= days


def _when(d: date | None) -> str:
    return d.strftime("%d %b %Y") if d else ""


def _count_and_last(session: Session, column_date, model, *where) -> tuple[int, date | None]:
    count = session.scalar(select(func.count()).select_from(model).where(*where)) or 0
    last = session.scalar(select(func.max(column_date)).where(*where)) if count else None
    return count, last


def readiness(session: Session, project: Project, as_of: date) -> list[Item]:
    p = project
    items: list[Item] = []
    base = f"/projects/{p.id}"

    missing = [
        label
        for label, value in (
            ("the possession date", p.possession_due_on),
            ("the escrow bank", p.escrow_bank),
        )
        if not value
    ]
    items.append(
        Item(
            "details",
            "Project details",
            "partial" if missing else "done",
            f"Add {' and '.join(missing)}." if missing else f"K-RERA {p.krera_registration}.",
            "Delay interest from the promised possession date; the escrow bank on every pack.",
            "Change the details",
            f"{base}/setup#details",
        )
    )

    units = list(session.scalars(select(Unit).where(Unit.project_id == p.id)))
    sold = sum(1 for u in units if u.booked)
    items.append(
        Item(
            "units",
            "Units and buyers",
            "done" if units else "missing",
            f"{len(units)} units, {sold} sold." if units else "No units yet.",
            "Collections, registration and handover, GST on development rights, the "
            "guidance-value check.",
            "Import units",
            f"{base}/import",
        )
    )

    stages = registers.payment_plan(session, p)
    items.append(
        Item(
            "plan",
            "Payment plan",
            "done" if stages else "missing",
            f"{len(stages)} stages." if stages else "No payment plan yet.",
            "Demands raised the moment a stage is certified.",
            "Set the payment plan",
            f"{base}/collections",
        )
    )

    latest = session.scalars(
        select(ProgressCertificate)
        .where(ProgressCertificate.project_id == p.id, ProgressCertificate.as_of <= as_of)
        .order_by(ProgressCertificate.as_of.desc())
    ).first()
    items.append(
        Item(
            "progress",
            "Certified progress",
            "missing"
            if latest is None
            else "done"
            if _fresh(latest.as_of, as_of, PROGRESS_STALE_DAYS)
            else "stale",
            f"{latest.completion_pct.normalize():f}% on {_when(latest.as_of)}, "
            f"by {latest.certified_by}."
            if latest
            else "No architect's certificate recorded.",
            "Demands, escrow withdrawals, and the check that spending keeps pace with progress.",
            "Record the latest certificate",
            f"{base}/setup#progress",
        )
    )

    lines = registers.cost_lines(session, p)
    budget = sum((line.revised_budget for line in lines), registers.ZERO)
    items.append(
        Item(
            "cost_lines",
            "Cost lines and budget",
            "missing" if not lines else "done" if budget > 0 else "partial",
            f"{len(lines)} cost lines" + ("." if budget > 0 else ", no budgets yet.")
            if lines
            else "No cost lines yet.",
            "Anticipated final cost, overruns and contingency.",
            "Set up cost lines",
            f"{base}/budget",
        )
    )

    for key, title, model, column, unlocks, action in (
        (
            "costs",
            "Costs from your accounts",
            LedgerEntry,
            LedgerEntry.entry_date,
            "Cost incurred and paid, and how much can be withdrawn from the RERA account.",
            "Import from Tally",
        ),
        (
            "bills",
            "Suppliers' bills",
            Bill,
            Bill.bill_date,
            "The 80% registered-supplier test and the MSME 45-day clock.",
            "Import from Tally",
        ),
        (
            "receipts",
            "Buyer payments",
            Receipt,
            Receipt.received_on,
            "Collections, overdue interest and the 70% deposit check.",
            "Import a bank statement or Tally",
        ),
        (
            "escrow",
            "RERA account movements",
            EscrowTxn,
            EscrowTxn.txn_date,
            "The 70% deposit check and withdrawals.",
            "Import the RERA account's statement",
        ),
    ):
        count, last = _count_and_last(session, column, model, model.project_id == p.id)
        items.append(
            Item(
                key,
                title,
                "missing" if not count else "done" if _fresh(last, as_of) else "stale",
                f"Up to {_when(last)}." if count else "Nothing yet.",
                unlocks,
                action,
                f"{base}/import",
            )
        )

    if p.land_structure.startswith("jda"):
        owners = session.scalar(
            select(func.count()).select_from(Landowner).where(Landowner.project_id == p.id)
        )
        items.append(
            Item(
                "landowners",
                "Landowners",
                "done" if owners else "missing",
                f"{owners} recorded." if owners else "None recorded for this joint development.",
                "The landowners' share, and TDS on payments to them under s.194-IC.",
                "Add landowners",
                f"{base}/units",
            )
        )

    docs = services.documents_for(session, p, as_of)
    gaps = sum(1 for i in docs.checklist if i.status == "missing")
    items.append(
        Item(
            "documents",
            "Documents",
            "done" if not gaps else "partial" if docs.documents else "missing",
            f"{gaps} of the checklist still missing." if gaps else "The checklist is complete.",
            "What banks and K-RERA ask for, kept ready, and reminders before approvals lapse.",
            "Open the documents",
            f"{base}/documents",
        )
    )

    roles = {
        a.role
        for a in session.scalars(select(ProjectAccess).where(ProjectAccess.project_id == p.id))
    }
    absent = [label for role, label in CERTIFIER_ROLES.items() if role not in roles]
    items.append(
        Item(
            "certifiers",
            "Architect, engineer and CA",
            "done" if not absent else "partial" if roles else "missing",
            f"Not invited yet: {', '.join(absent)}." if absent else "All three can sign.",
            "Withdrawal certificates prepared for them to check and sign.",
            "Invite them",
            "/settings",
        )
    )
    return items


def summary(items: list[Item]) -> dict:
    done = sum(1 for i in items if i.status == "done")
    return {
        "done": done,
        "total": len(items),
        "next": next((i.key for i in items if i.status != "done"), None),
    }
