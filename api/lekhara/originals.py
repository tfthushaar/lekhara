"""The register of originals: where each paper original is, and where it has been.

Builders keep paper originals that cannot be replaced: title and mother deeds, the sanctioned
plan, the occupancy certificate, sale deeds before they go to buyers. Many spend years with the
lending bank as security, or travel to the lawyer, the sub-registrar or an authority and back.
When a buyer's bank or a registrar asks for one, someone has to know where it is.

Each original gets a number (O-0001, O-0002 and on, for the whole firm) that goes on a printed
barcode label stuck to its folder. Scanning the label with an ordinary barcode reader, which
types like a keyboard, opens its record. Every move is kept: from where, to where, when, by
whom and why. The idea comes from Paperless-ngx's archive serial numbers.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara.engines.documents import CATEGORY_LABEL
from lekhara.models import Document, Original, OriginalMove, Project
from lekhara.services import ServiceError

HELD_AT = {
    "office": "In the office",
    "bank": "With a bank, as security",
    "lawyer": "With the lawyer",
    "registrar": "At the sub-registrar",
    "authority": "With an authority",
    "buyer": "Handed over to the buyer",
    "other": "Elsewhere",
}
AWAY_DAYS = 30
"""An original with the lawyer, the registrar or an authority longer than this is worth chasing."""
AWAY = ("lawyer", "registrar", "authority", "other")


def _number(session: Session, organization_id: str) -> str:
    count = session.scalar(
        select(func.count())
        .select_from(Original)
        .where(Original.organization_id == organization_id)
    )
    return f"O-{count + 1:04d}"


def _place(fields: dict, as_of: date) -> dict:
    held_at = fields.get("held_at") or "office"
    if held_at not in HELD_AT:
        raise ServiceError("Choose where it is.")
    held_by = (fields.get("held_by") or "").strip()
    if held_at != "office" and not held_by:
        raise ServiceError("Say who has it: the bank and branch, the lawyer's name, the office.")
    since = fields.get("since") or as_of
    if since > as_of:
        raise ServiceError("It cannot have moved in the future.")
    return {
        "held_at": held_at,
        "held_by": held_by[:200] or None,
        "since": since,
        "against": (fields.get("against") or "").strip()[:200] or None,
    }


def create(session: Session, project: Project, fields: dict, user_id: str, as_of: date) -> Original:
    title = (fields.get("title") or "").strip()
    if not title:
        raise ServiceError("Name the original: the title deed of survey 42, the OC for tower A.")
    kind = fields.get("kind") or "other"
    if kind not in CATEGORY_LABEL:
        raise ServiceError("Choose what kind of document it is.")
    document_id = fields.get("document_id") or None
    if document_id is not None:
        doc = session.get(Document, document_id)
        if doc is None or doc.project_id != project.id:
            raise ServiceError("That document is not in this project's vault.")
        document_id = doc.family_id
    place = _place(fields, as_of)
    original = Original(
        organization_id=project.organization_id,
        project_id=project.id,
        number=_number(session, project.organization_id),
        title=title[:300],
        kind=kind,
        document_family_id=document_id,
        note=(fields.get("note") or "").strip()[:1000] or None,
        created_by=user_id,
        **place,
    )
    session.add(original)
    session.flush()
    session.add(
        OriginalMove(
            original_id=original.id, recorded_by=user_id, note="Entered in the register", **place
        )
    )
    session.commit()
    return original


def move(session: Session, original: Original, fields: dict, user_id: str, as_of: date) -> Original:
    place = _place(fields, as_of)
    if place["since"] < original.since:
        raise ServiceError("It cannot have moved before its last move.")
    note = (fields.get("note") or "").strip()[:500] or None
    session.add(OriginalMove(original_id=original.id, recorded_by=user_id, note=note, **place))
    for key, value in place.items():
        setattr(original, key, value)
    session.commit()
    return original


def find(session: Session, organization_ids: set[str], number: str) -> Original | None:
    """The original with this number, as scanned or typed (o-12, O-0012 and 12 all find it)."""
    digits = "".join(c for c in number if c.isdigit())
    if not digits:
        return None
    return session.scalars(
        select(Original).where(
            Original.organization_id.in_(organization_ids),
            Original.number == f"O-{int(digits):04d}",
        )
    ).first()


def of_project(session: Session, project: Project) -> list[Original]:
    return list(
        session.scalars(
            select(Original).where(Original.project_id == project.id).order_by(Original.number)
        )
    )


def moves(session: Session, original: Original) -> list[OriginalMove]:
    return list(
        session.scalars(
            select(OriginalMove)
            .where(OriginalMove.original_id == original.id)
            .order_by(OriginalMove.since.desc(), OriginalMove.recorded_at.desc())
        )
    )


def away_too_long(original: Original, as_of: date) -> bool:
    return original.held_at in AWAY and (as_of - original.since).days > AWAY_DAYS


def row(original: Original, as_of: date) -> dict:
    return {
        "id": original.id,
        "number": original.number,
        "title": original.title,
        "kind": original.kind,
        "kind_label": CATEGORY_LABEL[original.kind],
        "held_at": original.held_at,
        "held_at_label": HELD_AT[original.held_at],
        "held_by": original.held_by,
        "since": original.since.isoformat(),
        "against": original.against,
        "note": original.note,
        "document_family_id": original.document_family_id,
        "away_too_long": away_too_long(original, as_of),
        "days_there": (as_of - original.since).days,
    }
