"""The review queue: everything waiting for the builder, across the projects they work on.

Imports that need a choice wait rather than guess, and they wait here: bank statements whose
account is not yet known or whose payments could not be placed, Tally exports and sheets not yet
brought in, emails from outside the team waiting to be allowed, and files that could not be read
(a statement waiting for its password). Each entry says what it is and opens where it is settled.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara.bank import service as bank
from lekhara.config import Settings
from lekhara.models import (
    BankStatement,
    Connector,
    GstImport,
    ImportBatch,
    InboundItem,
    InboundMessage,
    Project,
    TallyImport,
    utcnow,
)
from lekhara.records import RECORD_TYPES
from lekhara.services import ServiceError
from lekhara.storage import Storage
from lekhara.tally import service as tally

RECENT_DAYS = 120
"""Statements older than this are not looked at again for payments to place."""


@dataclass(frozen=True)
class Waiting:
    project_id: str
    project_name: str
    kind: str
    title: str
    detail: str
    href: str
    since: datetime


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else many or one + 's'}"


def waiting(
    session: Session, storage: Storage, settings: Settings, projects: list[Project]
) -> list[Waiting]:
    if not projects:
        return []
    by_id = {p.id: p for p in projects}
    ids = list(by_id)
    out: list[Waiting] = []

    def add(project_id, kind, title, detail, href, since) -> None:
        out.append(Waiting(project_id, by_id[project_id].name, kind, title, detail, href, since))

    recent = utcnow() - timedelta(days=RECENT_DAYS)
    for row in session.scalars(
        select(BankStatement).where(
            BankStatement.project_id.in_(ids),
            BankStatement.status.in_(("review", "applied")),
            BankStatement.created_at >= recent,
        )
    ):
        href = f"/bank/{row.id}"
        if not bank.options(row).get("role"):
            add(
                row.project_id,
                "bank",
                "Which account is this statement for?",
                row.filename,
                href,
                row.created_at,
            )
            continue
        passwords = bank.statement_passwords(
            session, settings, by_id[row.project_id].organization_id
        )
        try:
            _, plan = bank.review(session, storage, row, settings.as_of(), passwords)
        except (ServiceError, FileNotFoundError):
            continue
        placing = plan.counts.get("needs_unit", 0)
        if placing:
            add(
                row.project_id,
                "bank",
                f"{_plural(placing, 'payment')} to place",
                f"{row.filename}: choose the buyer's unit, or mark it as not a buyer's payment.",
                href,
                row.created_at,
            )
        elif row.status == "review":
            add(
                row.project_id,
                "bank",
                "A bank statement to bring in",
                f"{row.filename}: {_plural(plan.counts.get('to_add', 0), 'transaction')}.",
                href,
                row.created_at,
            )

    for c in session.scalars(
        select(Connector).where(
            Connector.project_id.in_(ids),
            Connector.status == "active",
            Connector.last_import_id.is_not(None),
        )
    ):
        row = session.get(TallyImport, c.last_import_id)
        if row is None or row.status != "applied":
            continue
        try:
            _, plan = tally.review(session, storage, row, settings.as_of())
        except (ServiceError, FileNotFoundError):
            continue
        blocking = [a.title for a in plan.alerts if a.level == "blocking"]
        if blocking:
            add(
                c.project_id,
                "tally",
                "Choices for the connected Tally",
                "; ".join(blocking) + ". What they hold back comes in on the next sync.",
                f"/tally/{row.id}",
                c.last_sync_at or row.created_at,
            )

    for row in session.scalars(
        select(TallyImport).where(TallyImport.project_id.in_(ids), TallyImport.status == "review")
    ):
        add(
            row.project_id,
            "tally",
            "A Tally export to bring in",
            f"{row.filename}{f' from {row.company}' if row.company else ''}: check its choices.",
            f"/tally/{row.id}",
            row.created_at,
        )

    for row in session.scalars(
        select(GstImport).where(GstImport.project_id.in_(ids), GstImport.status == "review")
    ):
        add(
            row.project_id,
            "gst",
            f"A {row.form} to check",
            f"{row.filename}: {row.invoices} suppliers' invoices to check against your bills.",
            f"/gst/{row.id}",
            row.created_at,
        )

    for row in session.scalars(
        select(ImportBatch).where(ImportBatch.project_id.in_(ids), ImportBatch.status == "preview")
    ):
        title = RECORD_TYPES[row.kind].title.lower() if row.kind in RECORD_TYPES else row.kind
        add(
            row.project_id,
            "sheet",
            f"A sheet of {title} to check",
            f"{row.filename}: look over the preview, then import it.",
            f"/imports/{row.id}",
            row.created_at,
        )

    for msg in session.scalars(
        select(InboundMessage).where(
            InboundMessage.project_id.in_(ids), InboundMessage.status == "held"
        )
    ):
        add(
            msg.project_id,
            "mail",
            "An email to allow or turn away",
            f"From {msg.from_address}"
            + (f": {msg.subject}" if msg.subject else "")
            + ". It is not from your team or a sender you trust.",
            f"/projects/{msg.project_id}/import",
            msg.received_at,
        )
    for item, msg in session.execute(
        select(InboundItem, InboundMessage)
        .join(InboundMessage, InboundMessage.id == InboundItem.message_id)
        .where(
            InboundMessage.project_id.in_(ids),
            InboundItem.status.in_(("review", "failed")),
            InboundItem.result_id.is_(None),
        )
    ):
        add(
            msg.project_id,
            "mail",
            f"{item.filename} could not be brought in",
            item.note or "Open it to see why.",
            f"/projects/{msg.project_id}/import",
            msg.received_at,
        )

    out.sort(key=lambda w: w.since)
    return out
