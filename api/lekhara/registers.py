"""Registers: the records a builder adds, edits and imports, with a history of every change.

Typing a value into a form and importing it from a spreadsheet go through the same parsing
and the same checks, so a record is never valid one way and invalid the other.
"""

import json
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara.models import (
    ChangeEntry,
    DemandRow,
    DisputeCase,
    Document,
    Project,
    Receipt,
    Unit,
    UnitHandover,
)
from lekhara.records import UNITS, ParseError, RecordType, check_unit, parse_value
from lekhara.services import ServiceError

ZERO = Decimal("0")


# Values in and out of JSON, for the history and for import batches


def to_json(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, date):
        return value.isoformat()
    return value


def from_json(record: RecordType, key: str, value):
    if value is None:
        return None
    kind = record.field(key).kind
    if kind == "money":
        return Decimal(value)
    if kind == "date":
        return date.fromisoformat(value)
    return value


def parse_row(record: RecordType, raw: dict) -> tuple[dict, list[str]]:
    """Field key to clean value for every cell given, and the problems found, in plain words."""
    values, problems = {}, []
    for key, cell in raw.items():
        field = record.field(key)
        try:
            values[key] = parse_value(field, cell)
        except ParseError as exc:
            problems.append(f"{field.label}: “{cell}” {exc}.")
    return values, problems


# History


def log_change(
    session: Session,
    project: Project,
    record_type: str,
    record_id: str,
    action: str,
    changes: dict,
    *,
    user_id: str | None,
    source: str,
    batch_id: str | None = None,
) -> None:
    session.add(
        ChangeEntry(
            organization_id=project.organization_id,
            project_id=project.id,
            record_type=record_type,
            record_id=record_id,
            action=action,
            changes=json.dumps(changes),
            source=source,
            import_batch_id=batch_id,
            user_id=user_id,
        )
    )


def history(session: Session, record_type: str, record_id: str) -> list[ChangeEntry]:
    return list(
        session.scalars(
            select(ChangeEntry)
            .where(ChangeEntry.record_type == record_type, ChangeEntry.record_id == record_id)
            .order_by(ChangeEntry.at.desc())
        )
    )


# Units


UNIT_KEYS = tuple(f.key for f in UNITS.fields)


def unit_values(unit: Unit) -> dict:
    return {key: getattr(unit, key) for key in UNIT_KEYS}


def units_by_label(session: Session, project: Project) -> dict[str, Unit]:
    return {
        u.label.casefold(): u
        for u in session.scalars(select(Unit).where(Unit.project_id == project.id))
    }


def unit_problems(values: dict, existing: Unit | None) -> list[str]:
    return check_unit(values, unit_values(existing) if existing else None)


def _apply(unit: Unit, values: dict) -> dict:
    """Sets the given values; returns {field: [before, after]} for what changed."""
    changes = {}
    for key, value in values.items():
        if value is None:
            continue
        before = getattr(unit, key)
        if before != value:
            changes[key] = [to_json(before), to_json(value)]
            setattr(unit, key, value)
    unit.booked = bool(unit.buyer_name)
    return changes


def create_unit(
    session: Session,
    project: Project,
    values: dict,
    *,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> Unit:
    label = (values.get("label") or "").strip()
    if label.casefold() in units_by_label(session, project):
        raise ServiceError(f"Unit {label} is already in this project.")
    problems = unit_problems(values, None)
    if problems:
        raise ServiceError(" ".join(problems))
    unit = Unit(
        project_id=project.id,
        label=label,
        tower="",
        owner_share="developer",
        list_price=ZERO,
        guidance_value=ZERO,
        carpet_area_sqft=values["carpet_area_sqft"],
    )
    session.add(unit)
    changes = _apply(unit, {**values, "label": label})
    session.flush()
    log_change(
        session,
        project,
        "unit",
        unit.id,
        "created",
        changes,
        user_id=user_id,
        source=source,
        batch_id=batch_id,
    )
    return unit


def update_unit(
    session: Session,
    project: Project,
    unit: Unit,
    values: dict,
    *,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> dict:
    label = values.get("label")
    renamed = label and label.casefold() != unit.label.casefold()
    if renamed and label.casefold() in units_by_label(session, project):
        raise ServiceError(f"Unit {label} is already in this project.")
    problems = unit_problems(values, unit)
    if problems:
        raise ServiceError(" ".join(problems))
    changes = _apply(unit, values)
    if changes:
        log_change(
            session,
            project,
            "unit",
            unit.id,
            "updated",
            changes,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
    return changes


def clear_buyer(session: Session, project: Project, unit: Unit, *, user_id: str | None) -> None:
    """Marks a unit unsold again, for a cancelled booking. Refused once money has moved."""
    blockers = [b for b in unit_dependents(session, unit) if "demand" in b or "payment" in b]
    if blockers:
        raise ServiceError(
            f"Unit {unit.label} has {blockers[0]}; cancel the booking through collections."
        )
    changes = {}
    for key in ("buyer_name", "buyer_phone", "buyer_email", "booked_on", "agreement_value"):
        if getattr(unit, key) is not None:
            changes[key] = [to_json(getattr(unit, key)), None]
            setattr(unit, key, None)
    unit.booked = False
    if changes:
        log_change(
            session, project, "unit", unit.id, "updated", changes, user_id=user_id, source="typed"
        )


def unit_dependents(session: Session, unit: Unit) -> list[str]:
    """What refers to the unit, so it cannot simply be deleted."""
    found = []
    checks = (
        (DemandRow, DemandRow.unit_id, "demands raised"),
        (Receipt, Receipt.unit_id, "payments received"),
        (UnitHandover, UnitHandover.unit_id, "a handover record"),
        (DisputeCase, DisputeCase.unit_id, "a dispute"),
    )
    for model, column, words in checks:
        if session.scalar(select(func.count()).select_from(model).where(column == unit.id)):
            found.append(words)
    documents = session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.link_type == "unit", Document.link_id == unit.id)
    )
    if documents:
        found.append("documents filed against it")
    return found


def delete_unit(session: Session, project: Project, unit: Unit, *, user_id: str | None) -> None:
    blockers = unit_dependents(session, unit)
    if blockers:
        raise ServiceError(f"Unit {unit.label} has {', '.join(blockers)}, so it cannot be deleted.")
    log_change(
        session,
        project,
        "unit",
        unit.id,
        "deleted",
        {k: [to_json(v), None] for k, v in unit_values(unit).items() if v is not None},
        user_id=user_id,
        source="typed",
    )
    session.delete(unit)


def parse_unit_form(raw: dict) -> dict:
    values, problems = parse_row(UNITS, {k: v for k, v in raw.items() if k in UNIT_KEYS})
    if problems:
        raise ServiceError(" ".join(problems))
    return values
