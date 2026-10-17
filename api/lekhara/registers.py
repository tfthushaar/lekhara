"""Registers: the records a builder adds, edits and imports, with a history of every change.

Typing a value into a form and importing it from a spreadsheet go through the same parsing
and the same checks, so a record is never valid one way and invalid the other.
"""

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara.models import (
    ChangeEntry,
    CostLineRow,
    DemandRow,
    DisputeCase,
    Document,
    Landowner,
    LedgerEntry,
    PaymentMilestone,
    ProgressCertificate,
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


# Cost lines


STANDARD_LINES = (
    ("LAND", "Land, deposit and registration", "land", "land"),
    ("APPR", "Approvals, premium FAR and fees", "approvals", "land"),
    ("CIVIL", "Civil and structure", "construction", "development"),
    ("MEP", "Mechanical, electrical and plumbing", "construction", "development"),
    ("FIN", "Finishes", "construction", "development"),
    ("EXT", "External works and amenities", "construction", "development"),
    ("CONS", "Consultants", "construction", "development"),
    ("FINC", "Finance cost", "finance", "development"),
    ("MKT", "Sales and marketing", "marketing", "development"),
    ("OH", "Project overheads", "overheads", "development"),
    ("CONT", "Contingency", "contingency", "development"),
)
CATEGORY_LABEL = {
    "land": "Land",
    "approvals": "Approvals",
    "construction": "Construction",
    "finance": "Finance",
    "marketing": "Marketing",
    "overheads": "Overheads",
    "contingency": "Contingency",
}


def cost_lines(session: Session, project: Project) -> list[CostLineRow]:
    return list(
        session.scalars(
            select(CostLineRow)
            .where(CostLineRow.project_id == project.id)
            .order_by(CostLineRow.position)
        )
    )


def add_standard_lines(session: Session, project: Project, *, user_id: str | None) -> int:
    existing = {line.code for line in cost_lines(session, project)}
    position = len(existing)
    added = 0
    for code, name, category, head in STANDARD_LINES:
        if code in existing:
            continue
        line = CostLineRow(
            project_id=project.id,
            code=code,
            name=name,
            category=category,
            rera_head=head,
            original_budget=ZERO,
            revised_budget=ZERO,
            position=position,
        )
        session.add(line)
        session.flush()
        log_change(
            session,
            project,
            "cost_line",
            line.id,
            "created",
            {"name": [None, name]},
            user_id=user_id,
            source="typed",
        )
        position += 1
        added += 1
    return added


def _line_values(fields: dict) -> dict:
    values = {}
    for key in ("code", "name"):
        if fields.get(key) is not None:
            text = str(fields[key]).strip()
            if not text:
                raise ServiceError("Give the cost line a code and a name.")
            values[key] = text[:32] if key == "code" else text[:200]
    if fields.get("category") is not None:
        if fields["category"] not in CATEGORY_LABEL:
            raise ServiceError("Choose the kind of cost from the list.")
        values["category"] = fields["category"]
        values["rera_head"] = (
            "land" if fields["category"] in ("land", "approvals") else "development"
        )
    for key in ("original_budget", "revised_budget"):
        raw = fields.get(key)
        if raw is not None and str(raw).strip():
            try:
                value = parse_value(UNITS.field("list_price"), raw)
            except ParseError as exc:
                raise ServiceError(f"The budget {exc}.") from None
            values[key] = value
    return values


def create_cost_line(
    session: Session, project: Project, fields: dict, *, user_id: str | None
) -> CostLineRow:
    values = _line_values(fields)
    if "code" not in values or "name" not in values or "category" not in values:
        raise ServiceError("Give the cost line a code, a name and a kind.")
    if values["code"].casefold() in {line.code.casefold() for line in cost_lines(session, project)}:
        raise ServiceError(f"The code {values['code']} is already used in this project.")
    budget = values.get("original_budget", ZERO)
    line = CostLineRow(
        project_id=project.id,
        position=len(cost_lines(session, project)),
        original_budget=budget,
        revised_budget=values.get("revised_budget", budget),
        **{k: v for k, v in values.items() if k not in ("original_budget", "revised_budget")},
    )
    session.add(line)
    session.flush()
    log_change(
        session,
        project,
        "cost_line",
        line.id,
        "created",
        {k: [None, to_json(v)] for k, v in values.items()},
        user_id=user_id,
        source="typed",
    )
    return line


def update_cost_line(
    session: Session, project: Project, line: CostLineRow, fields: dict, *, user_id: str | None
) -> None:
    values = _line_values(fields)
    taken = {x.code.casefold() for x in cost_lines(session, project) if x.id != line.id}
    if "code" in values and values["code"].casefold() in taken:
        raise ServiceError(f"The code {values['code']} is already used in this project.")
    changes = {}
    for key, value in values.items():
        if getattr(line, key) != value:
            changes[key] = [to_json(getattr(line, key)), to_json(value)]
            setattr(line, key, value)
    if changes:
        log_change(
            session,
            project,
            "cost_line",
            line.id,
            "updated",
            changes,
            user_id=user_id,
            source="typed",
        )


def delete_cost_line(
    session: Session, project: Project, line: CostLineRow, *, user_id: str | None
) -> None:
    used = session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.cost_line_id == line.id)
    )
    if used:
        raise ServiceError(f"{line.name} has costs recorded against it, so it cannot be deleted.")
    log_change(
        session,
        project,
        "cost_line",
        line.id,
        "deleted",
        {"name": [line.name, None]},
        user_id=user_id,
        source="typed",
    )
    session.delete(line)


# Landowners


def _landowner_values(fields: dict, *, new: bool) -> dict:
    values = {}
    name = fields.get("name")
    if name is not None:
        if not str(name).strip():
            raise ServiceError("Enter the landowner's name.")
        values["name"] = str(name).strip()[:200]
    if fields.get("share_type") is not None:
        if fields["share_type"] not in ("area", "revenue"):
            raise ServiceError("The share is either of the built area or of revenue.")
        values["share_type"] = fields["share_type"]
    if fields.get("share_pct") not in (None, ""):
        try:
            share = Decimal(str(fields["share_pct"]).replace("%", "").strip())
        except InvalidOperation:
            raise ServiceError("The share should be a percentage, like 40.") from None
        if not 0 < share < 100:
            raise ServiceError("The share should be between 0 and 100 per cent.")
        values["share_pct"] = share
    if fields.get("refundable_deposit") not in (None, ""):
        try:
            values["refundable_deposit"] = parse_value(
                UNITS.field("list_price"), fields["refundable_deposit"]
            )
        except ParseError as exc:
            raise ServiceError(f"The deposit {exc}.") from None
    if fields.get("pan") not in (None, ""):
        pan = str(fields["pan"]).strip().upper()
        if not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", pan):
            raise ServiceError("A PAN has ten characters, like ABCDE1234F.")
        values["pan"] = pan
    if new and not {"name", "share_type", "share_pct"} <= set(values):
        raise ServiceError("Enter the landowner's name, the kind of share and the share.")
    return values


def create_landowner(
    session: Session, project: Project, fields: dict, *, user_id: str | None
) -> Landowner:
    values = _landowner_values(fields, new=True)
    owner = Landowner(project_id=project.id, **values)
    session.add(owner)
    session.flush()
    log_change(
        session,
        project,
        "landowner",
        owner.id,
        "created",
        {k: [None, to_json(v)] for k, v in values.items()},
        user_id=user_id,
        source="typed",
    )
    return owner


def update_landowner(
    session: Session, project: Project, owner: Landowner, fields: dict, *, user_id: str | None
) -> None:
    values = _landowner_values(fields, new=False)
    changes = {}
    for key, value in values.items():
        if getattr(owner, key) != value:
            changes[key] = [to_json(getattr(owner, key)), to_json(value)]
            setattr(owner, key, value)
    if changes:
        log_change(
            session,
            project,
            "landowner",
            owner.id,
            "updated",
            changes,
            user_id=user_id,
            source="typed",
        )


# Buyer payments


def create_receipt(
    session: Session,
    project: Project,
    unit: Unit,
    values: dict,
    *,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> Receipt:
    if not unit.booked:
        raise ServiceError(f"Unit {unit.label} is not sold, so it has no buyer to receive from.")
    amount = values.get("amount")
    if amount is None or amount <= 0:
        raise ServiceError("Enter the amount received.")
    if values.get("received_on") is None:
        raise ServiceError("Enter the date the money was received.")
    receipt = Receipt(
        project_id=project.id,
        unit_id=unit.id,
        amount=amount,
        received_on=values["received_on"],
        tds_deducted=values.get("tds_deducted") or ZERO,
        reference=(values.get("reference") or "").strip()[:200] or None,
        source_ref=f"import:{batch_id}" if batch_id else None,
    )
    session.add(receipt)
    session.flush()
    log_change(
        session,
        project,
        "receipt",
        receipt.id,
        "created",
        {k: [None, to_json(v)] for k, v in values.items() if v is not None and k != "unit"}
        | {"unit": [None, unit.label]},
        user_id=user_id,
        source=source,
        batch_id=batch_id,
    )
    return receipt


def delete_receipt(
    session: Session, project: Project, receipt: Receipt, *, user_id: str | None
) -> None:
    if receipt.source_ref and receipt.source_ref.startswith("tally:"):
        raise ServiceError("This payment came from Tally. Correct it in Tally and import again.")
    log_change(
        session,
        project,
        "receipt",
        receipt.id,
        "deleted",
        {
            "amount": [to_json(receipt.amount), None],
            "received_on": [to_json(receipt.received_on), None],
        },
        user_id=user_id,
        source="typed",
    )
    session.delete(receipt)


def unit_receipts(session: Session, unit: Unit) -> list[Receipt]:
    return list(
        session.scalars(
            select(Receipt).where(Receipt.unit_id == unit.id).order_by(Receipt.received_on)
        )
    )


# Payment plans


PLAN_TEMPLATES = {
    "construction_linked": (
        "Construction-linked, ten stages",
        (
            ("On booking", "booking", None, "10"),
            ("On the agreement for sale", "agreement", None, "10"),
            ("On completion of the foundation", "progress", "10", "10"),
            ("On completion of the 2nd floor slab", "progress", "20", "10"),
            ("On completion of the 5th floor slab", "progress", "35", "10"),
            ("On completion of the 8th floor slab", "progress", "50", "10"),
            ("On completion of the roof slab", "progress", "65", "10"),
            ("On completion of brickwork and plastering", "progress", "80", "10"),
            ("On completion of flooring and finishes", "progress", "90", "10"),
            ("On possession", "possession", None, "10"),
        ),
    ),
    "front_loaded": (
        "Construction-linked, front-loaded",
        (
            ("On booking", "booking", None, "10"),
            ("On the agreement for sale", "agreement", None, "15"),
            ("On completion of the foundation", "progress", "10", "10"),
            ("On completion of the 4th floor slab", "progress", "30", "15"),
            ("On completion of the roof slab", "progress", "60", "15"),
            ("On completion of finishes", "progress", "85", "20"),
            ("On possession", "possession", None, "15"),
        ),
    ),
    "twenty_eighty": (
        "20:80",
        (
            ("On booking", "booking", None, "10"),
            ("On the agreement for sale", "agreement", None, "10"),
            ("On possession", "possession", None, "80"),
        ),
    ),
}
TRIGGERS = ("booking", "agreement", "progress", "possession")


def payment_plan(session: Session, project: Project) -> list[PaymentMilestone]:
    return list(
        session.scalars(
            select(PaymentMilestone)
            .where(PaymentMilestone.project_id == project.id)
            .order_by(PaymentMilestone.sequence)
        )
    )


def demands_by_milestone(session: Session, project: Project) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in session.scalars(select(DemandRow).where(DemandRow.project_id == project.id)):
        out[d.milestone_id] = out.get(d.milestone_id, 0) + 1
    return out


def _milestone(raw: dict, index: int) -> dict:
    name = (raw.get("name") or "").strip()
    trigger = raw.get("trigger") or ""
    if trigger not in TRIGGERS:
        raise ServiceError(f"Stage {index}: choose when it falls due.")
    if not name:
        raise ServiceError(f"Stage {index}: give it a name.")
    try:
        share = Decimal(str(raw.get("share_pct") or "").replace("%", "").strip())
    except InvalidOperation:
        raise ServiceError(f"Stage {index}: the share should be a percentage.") from None
    if share <= 0:
        raise ServiceError(f"Stage {index}: the share should be above zero.")
    progress = None
    if trigger == "progress":
        try:
            progress = Decimal(str(raw.get("progress_pct") or "").replace("%", "").strip())
        except InvalidOperation:
            raise ServiceError(
                f"Stage {index}: enter the certified progress it falls due at."
            ) from None
        if not 0 < progress <= 100:
            raise ServiceError(f"Stage {index}: progress should be between 0 and 100 per cent.")
    return {
        "id": raw.get("id") or None,
        "name": name[:200],
        "trigger": trigger,
        "progress_pct": progress,
        "share_pct": share,
    }


def replace_plan(
    session: Session, project: Project, stages: list[dict], *, user_id: str | None
) -> None:
    """Sets the whole plan. Stages that already have demands raised keep their timing and share."""
    if not stages:
        raise ServiceError("A payment plan needs at least one stage.")
    clean = [_milestone(raw, i + 1) for i, raw in enumerate(stages)]
    current = {m.id: m for m in payment_plan(session, project)}
    raised = demands_by_milestone(session, project)
    kept = {s["id"] for s in clean if s["id"] in current}
    for milestone_id, milestone in current.items():
        if milestone_id not in kept and raised.get(milestone_id):
            raise ServiceError(
                f"{milestone.name} has demands raised against it, so it cannot be removed."
            )
    for stage in clean:
        existing = current.get(stage["id"]) if stage["id"] else None
        if (
            existing
            and raised.get(existing.id)
            and (
                existing.trigger != stage["trigger"]
                or existing.share_pct != stage["share_pct"]
                or existing.progress_pct != stage["progress_pct"]
            )
        ):
            raise ServiceError(
                f"{existing.name} has demands raised against it; its timing and share are fixed."
            )
    total = sum((s["share_pct"] for s in clean), ZERO)
    if abs(total - Decimal(100)) > Decimal("0.01"):
        raise ServiceError(
            f"The stages add up to {total.normalize():f}%; they should add up to 100%."
        )
    for milestone_id, milestone in current.items():
        if milestone_id not in kept:
            session.delete(milestone)
    session.flush()
    for sequence, stage in enumerate(clean, start=1):
        existing = current.get(stage["id"]) if stage["id"] else None
        if existing is None:
            existing = PaymentMilestone(project_id=project.id)
            session.add(existing)
        existing.sequence = sequence
        existing.name = stage["name"]
        existing.trigger = stage["trigger"]
        existing.progress_pct = stage["progress_pct"]
        existing.share_pct = stage["share_pct"]
    log_change(
        session,
        project,
        "payment_plan",
        project.id,
        "updated",
        {"stages": [len(current), len(clean)]},
        user_id=user_id,
        source="typed",
    )


def apply_template(session: Session, project: Project, key: str, *, user_id: str | None) -> None:
    if key not in PLAN_TEMPLATES:
        raise ServiceError("Choose a plan from the list.")
    if any(demands_by_milestone(session, project).values()):
        raise ServiceError(
            "Demands have already been raised, so change the plan stage by stage instead."
        )
    _, stages = PLAN_TEMPLATES[key]
    replace_plan(
        session,
        project,
        [{"name": n, "trigger": t, "progress_pct": p, "share_pct": s} for n, t, p, s in stages],
        user_id=user_id,
    )


# Project details and certified progress


PROJECT_TEXT = {
    "name": 200,
    "locality": 200,
    "city": 100,
    "krera_registration": 100,
    "spv_name": 200,
    "escrow_bank": 200,
    "statutory_auditor_firm": 200,
    "oc_reference": 200,
}
PROJECT_DATES = (
    "registered_on",
    "possession_due_on",
    "oc_received_on",
    "association_formed_on",
    "common_areas_conveyed_on",
)
OC_STATUSES = ("none", "applied", "partial", "received")
PROJECT_OPTIONAL_TEXT = ("escrow_bank", "statutory_auditor_firm", "oc_reference")


def _project_values(project: Project, fields: dict) -> dict:
    values: dict = {}
    for key, size in PROJECT_TEXT.items():
        if key in fields and fields[key] is not None:
            text = str(fields[key]).strip()
            if key in ("name", "krera_registration") and not text:
                raise ServiceError("The project's name and K-RERA number cannot be blank.")
            text = (text.upper() if key == "krera_registration" else text)[:size]
            values[key] = text or (None if key in PROJECT_OPTIONAL_TEXT else "")
    for key in PROJECT_DATES:
        if key not in fields or fields[key] is None:
            continue
        if not str(fields[key]).strip():
            # A blank date clears it, except the registration date every project has.
            if key != "registered_on":
                values[key] = None
            continue
        try:
            values[key] = parse_value(UNITS.field("booked_on"), fields[key])
        except ParseError as exc:
            raise ServiceError(f"{key.replace('_', ' ').capitalize()}: {exc}.") from None
    if fields.get("land_structure"):
        if fields["land_structure"] not in ("own", "jda_area_share", "jda_revenue_share"):
            raise ServiceError("Choose the land structure from the list.")
        values["land_structure"] = fields["land_structure"]
    if fields.get("gst_regime"):
        if fields["gst_regime"] not in (
            "affordable_1pc",
            "residential_5pc",
            "commercial_12pc",
            "rrep_mixed",
        ):
            raise ServiceError("Choose the GST scheme from the list.")
        values["gst_regime"] = fields["gst_regime"]
    if fields.get("oc_status"):
        if fields["oc_status"] not in OC_STATUSES:
            raise ServiceError("Choose the occupancy certificate's state from the list.")
        values["oc_status"] = fields["oc_status"]
    for key in ("development_rights_value", "cess_paid"):
        if key not in fields or fields[key] is None:
            continue
        if not str(fields[key]).strip():
            values[key] = None if key == "development_rights_value" else ZERO
            continue
        try:
            values[key] = parse_value(UNITS.field("list_price"), fields[key])
        except ParseError as exc:
            raise ServiceError(f"{key.replace('_', ' ').capitalize()} {exc}.") from None
    merged = {
        k: values.get(k, getattr(project, k))
        for k in ("registered_on", "possession_due_on", "oc_status", "oc_received_on")
    }
    if (
        merged["possession_due_on"]
        and merged["registered_on"]
        and merged["possession_due_on"] < merged["registered_on"]
    ):
        raise ServiceError("The possession date cannot be before the K-RERA registration.")
    if merged["oc_status"] in ("partial", "received") and not merged["oc_received_on"]:
        raise ServiceError("Enter the date the occupancy certificate was received.")
    return values


def update_project(
    session: Session, project: Project, fields: dict, *, user_id: str | None
) -> dict:
    values = _project_values(project, fields)
    if "krera_registration" in values:
        clash = session.scalars(
            select(Project).where(
                Project.organization_id == project.organization_id,
                Project.krera_registration == values["krera_registration"],
                Project.id != project.id,
            )
        ).first()
        if clash is not None:
            raise ServiceError(f'This K-RERA number is already used by "{clash.name}".')
    changes = {}
    for key, value in values.items():
        if getattr(project, key) != value:
            changes[key] = [to_json(getattr(project, key)), to_json(value)]
            setattr(project, key, value)
    if changes:
        log_change(
            session,
            project,
            "project",
            project.id,
            "updated",
            changes,
            user_id=user_id,
            source="typed",
        )
    return changes


def record_progress(
    session: Session,
    project: Project,
    fields: dict,
    *,
    as_of: date,
    certified_by: str,
    user_id: str | None,
) -> ProgressCertificate:
    try:
        on = parse_value(UNITS.field("booked_on"), fields.get("as_of"))
        pct = Decimal(str(fields.get("completion_pct") or "").replace("%", "").strip())
    except (ParseError, InvalidOperation):
        raise ServiceError("Enter the certificate's date and the per cent complete.") from None
    if on is None:
        raise ServiceError("Enter the certificate's date.")
    if on > as_of:
        raise ServiceError("The certificate's date cannot be in the future.")
    if not 0 < pct <= 100:
        raise ServiceError("Progress should be between 0 and 100 per cent.")
    earlier = session.scalars(
        select(ProgressCertificate)
        .where(ProgressCertificate.project_id == project.id, ProgressCertificate.as_of <= on)
        .order_by(ProgressCertificate.as_of.desc())
    ).first()
    if earlier is not None and earlier.completion_pct > pct:
        raise ServiceError(
            f"An earlier certificate already shows {earlier.completion_pct.normalize():f}%; "
            "certified progress cannot go down."
        )
    row = ProgressCertificate(
        project_id=project.id, completion_pct=pct, as_of=on, certified_by=certified_by[:200]
    )
    session.add(row)
    session.flush()
    log_change(
        session,
        project,
        "progress",
        row.id,
        "created",
        {"completion_pct": [None, to_json(pct)], "as_of": [None, to_json(on)]},
        user_id=user_id,
        source="typed",
    )
    return row
