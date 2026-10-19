"""Handing homes and the project over: the letter offering each buyer possession, the checklist
for handing the project to the residents' association, and cancelling a booking.

A cancelled booking keeps its history: the buyer's demands and payments point to the
cancellation, so they stay in the project's money (and in any case about them) but no longer
count for the unit, which can then be sold again.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import registers, services
from lekhara.engines.disputes import CasePosition, OrderKind
from lekhara.engines.handover import _add_months
from lekhara.models import (
    BookingCancellation,
    DemandRow,
    DisputeCase,
    HandoverItem,
    Project,
    Receipt,
    Unit,
    UnitHandover,
)
from lekhara.money import ZERO
from lekhara.registers import log_change, to_json
from lekhara.rules import KARNATAKA, RulesPack
from lekhara.services import ServiceError


def _indian(value: Decimal) -> str:
    whole = str(int(abs(value).quantize(Decimal("1"))))
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join([*groups, tail])


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 10: "ten"}


def _count(n: int) -> str:
    return WORDS.get(int(n), str(n))


def _when(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


# The possession letter


def possession_letter(
    session: Session, project: Project, unit: Unit, as_of: date, rules: RulesPack = KARNATAKA
) -> dict:
    if not unit.booked:
        raise ServiceError(f"Unit {unit.label} has no buyer to offer possession to.")
    if project.oc_status not in ("received", "partial") or project.oc_received_on is None:
        raise ServiceError(
            "Possession can be offered once the occupancy certificate is in. Record it on the "
            "project's Set-up tab."
        )
    handover = services.handover_for(session, project, as_of)
    readiness = next(r for r in handover.units if r.unit.unit_id == unit.id)
    months = rules.value("rera.s19_possession_months", as_of)
    take_by = _add_months(project.oc_received_on, months)
    years = rules.value("rera.s14_defect_liability_years", as_of)
    balance = readiness.unit.balance_due
    cost = readiness.cost
    paragraphs = [
        f"We are glad to tell you that the occupancy certificate for {project.name} was issued on "
        f"{_when(project.oc_received_on)}"
        + (f" (reference {project.oc_reference})" if project.oc_reference else "")
        + f", and we offer you possession of your home, unit {unit.label}.",
        f"Under section 19(10) of the Real Estate (Regulation and Development) Act, 2016, please "
        f"take possession within {_count(months)} months of the occupancy certificate, that is by "
        f"{_when(take_by)}.",
    ]
    lines = []
    if balance > 0:
        lines.append({"label": "Balance due to us under your agreement", "value": _indian(balance)})
    lines += [
        {"label": "Stamp duty (estimate)", "value": _indian(cost.stamp_duty)},
        {"label": "Cess on stamp duty (estimate)", "value": _indian(cost.cess)},
        {"label": "Registration fee (estimate)", "value": _indian(cost.registration_fee)},
    ]
    after = [
        "The stamp duty, cess and registration fee are paid by you at registration, on the "
        "higher of the agreement value and the guidance value; the figures above are estimates.",
        "Before taking possession, please inspect your home with our site team and note anything "
        "that needs attention; we will put it right before handing over the keys.",
        f"For {_count(years)} years from the date of possession, we will rectify any structural "
        "defect, or any defect in workmanship, quality or services, that you report to us, "
        "within 30 days, as section 14(3) of the Act provides.",
        "Please bring proof of identity and address, the receipts for your payments, and, if "
        "you have a home loan, the letter from your bank. Maintenance charges and deposits are "
        "payable as set out in your agreement.",
    ]
    return {
        "unit_id": unit.id,
        "project_id": project.id,
        "from": project.organization.name,
        "project": f"{project.name}, {project.locality}, {project.city}",
        "krera_registration": project.krera_registration,
        "date": as_of.isoformat(),
        "to": unit.buyer_name,
        "unit": unit.label,
        "subject": f"Offer of possession: unit {unit.label}",
        "paragraphs": paragraphs,
        "lines": lines,
        "take_by": take_by.isoformat(),
        "after": after,
        "note": "Draft prepared by Lekhara. Your team sends it from your own address.",
    }


# Handing over to the residents' association

PROJECT_FIELD = {
    "association_formed": "association_formed_on",
    "conveyance": "common_areas_conveyed_on",
}

ASSOCIATION_ITEMS = (
    ("association_formed", "The residents' association is formed and registered"),
    ("corpus", "The corpus fund handed over, with its account"),
    ("maintenance", "Maintenance deposits handed over, with the accounts to date"),
    ("papers", "Copies of the approved plans, the occupancy certificate and the approvals"),
    ("drawings", "As-built drawings: structure, electrical, plumbing and fire"),
    ("fire", "Fire systems handed over, with the final fire NOC"),
    ("lifts", "Lift licences and maintenance contracts transferred"),
    ("plant", "Generator, sewage and water treatment plants, with manuals and contracts"),
    ("warranties", "Equipment warranties and guarantees transferred"),
    ("utilities", "Power and water connections for common areas in the association's name"),
    ("insurance", "Insurance of the common areas arranged or transferred"),
    ("keys", "Keys to common areas, plant rooms and terraces"),
    ("contractors", "Contractors and suppliers to call for defects in the liability period"),
    ("conveyance", "Common areas conveyed to the association by registered deed"),
)
ITEM_LABEL = dict(ASSOCIATION_ITEMS)


def association_items(session: Session, project: Project) -> list[dict]:
    stored = {
        i.key: i
        for i in session.scalars(select(HandoverItem).where(HandoverItem.project_id == project.id))
    }
    out = []
    for key, label in ASSOCIATION_ITEMS:
        item = stored.get(key)
        done = (
            getattr(project, PROJECT_FIELD[key])
            if key in PROJECT_FIELD
            else (item and item.done_on)
        )
        out.append(
            {
                "key": key,
                "label": label,
                "done_on": done.isoformat() if done else None,
                "note": item.note if item else None,
            }
        )
    return out


def set_association_item(
    session: Session,
    project: Project,
    key: str,
    *,
    done_on: date | None,
    note: str | None,
    as_of: date,
    user_id: str | None,
) -> None:
    if key not in ITEM_LABEL:
        raise ServiceError("That is not an item of the handover.", 404)
    if done_on is not None and done_on > as_of:
        raise ServiceError("The date cannot be in the future.")
    if done_on is not None and (project.oc_received_on is None or done_on < project.oc_received_on):
        raise ServiceError("The handover to the association comes after the occupancy certificate.")
    if key in PROJECT_FIELD:
        registers.update_project(
            session,
            project,
            {PROJECT_FIELD[key]: done_on.isoformat() if done_on else ""},
            user_id=user_id,
        )
    item = session.scalars(
        select(HandoverItem).where(HandoverItem.project_id == project.id, HandoverItem.key == key)
    ).first()
    if item is None:
        item = HandoverItem(project_id=project.id, key=key)
        session.add(item)
        session.flush()
    before = {"done_on": to_json(item.done_on), "note": item.note}
    if key not in PROJECT_FIELD:
        item.done_on = done_on
    item.note = (note or "").strip()[:500] or None
    after = {"done_on": to_json(item.done_on), "note": item.note}
    changes = {
        f"{ITEM_LABEL[key]}: {'done on' if k == 'done_on' else 'note'}": [before[k], after[k]]
        for k in after
        if before[k] != after[k]
    }
    if changes:
        log_change(
            session, project, "handover_item", project.id, "updated", changes, user_id=user_id,
            source="typed",
        )  # fmt: skip


# Cancelling a booking


def cancel_booking(
    session: Session,
    project: Project,
    unit: Unit,
    *,
    cancelled_on: date,
    as_of: date,
    user_id: str | None,
    refunded: Decimal | None = None,
    refunded_on: date | None = None,
    reason: str | None = None,
    case_id: str | None = None,
) -> BookingCancellation:
    if not unit.booked:
        raise ServiceError(f"Unit {unit.label} has no booking to cancel.")
    if cancelled_on > as_of:
        raise ServiceError("The cancellation date cannot be in the future.")
    if unit.booked_on and cancelled_on < unit.booked_on:
        raise ServiceError("A booking cannot be cancelled before it was made.")
    if refunded is not None and refunded < 0:
        raise ServiceError("The refund cannot be negative.")
    if refunded_on is not None and refunded_on > as_of:
        raise ServiceError("The refund date cannot be in the future.")
    handover = session.scalars(select(UnitHandover).where(UnitHandover.unit_id == unit.id)).first()
    if handover is not None and handover.registered_on is not None:
        raise ServiceError(
            f"Unit {unit.label} is registered in the buyer's name; that needs a cancellation "
            "deed, not a cancelled booking."
        )
    row = BookingCancellation(
        project_id=project.id,
        unit_id=unit.id,
        cancelled_on=cancelled_on,
        buyer_name=unit.buyer_name,
        booked_on=unit.booked_on,
        agreement_value=unit.agreement_value,
        refunded=refunded,
        refunded_on=refunded_on,
        reason=(reason or "").strip()[:500] or None,
        case_id=case_id,
        created_by_user_id=user_id,
    )
    session.add(row)
    session.flush()
    for model in (DemandRow, Receipt):
        for record in session.scalars(
            select(model).where(model.unit_id == unit.id, model.cancellation_id.is_(None))
        ):
            record.cancellation_id = row.id
    if handover is not None:
        session.delete(handover)
    changes = {}
    for key in ("buyer_name", "buyer_phone", "buyer_email", "booked_on", "agreement_value"):
        if getattr(unit, key) is not None:
            changes[key] = [to_json(getattr(unit, key)), None]
            setattr(unit, key, None)
    unit.booked = False
    log_change(
        session, project, "unit", unit.id, "updated", changes, user_id=user_id,
        source="cancellation",
    )  # fmt: skip
    return row


def earlier_bookings(session: Session, unit: Unit) -> list[dict]:
    rows = session.scalars(
        select(BookingCancellation)
        .where(BookingCancellation.unit_id == unit.id)
        .order_by(BookingCancellation.cancelled_on.desc())
    )
    out = []
    for c in rows:
        paid = sum(
            (
                r.amount + r.tds_deducted
                for r in session.scalars(select(Receipt).where(Receipt.cancellation_id == c.id))
            ),
            ZERO,
        )
        out.append(
            {
                "id": c.id,
                "buyer_name": c.buyer_name,
                "booked_on": c.booked_on.isoformat() if c.booked_on else None,
                "cancelled_on": c.cancelled_on.isoformat(),
                "agreement_value": str(c.agreement_value) if c.agreement_value else None,
                "paid": str(paid),
                "refunded": str(c.refunded) if c.refunded is not None else None,
                "refunded_on": c.refunded_on.isoformat() if c.refunded_on else None,
                "reason": c.reason,
                "case_id": c.case_id,
            }
        )
    return out


def case_booking(session: Session, row: DisputeCase, position: CasePosition) -> dict | None:
    """For a case about a unit: whether the refund under the order is paid, so the booking can
    be cancelled and the unit sold again."""
    if not row.unit_id:
        return None
    unit = session.get(Unit, row.unit_id)
    cancellation = session.scalars(
        select(BookingCancellation).where(BookingCancellation.case_id == row.id)
    ).first()
    refunds = [o for o in position.orders if o.order.kind == OrderKind.REFUND]
    settled = (
        row.relief == "refund"
        and row.settlement_agreed is not None
        and position.paid >= row.settlement_agreed
    )
    refund_paid = settled or any(o.due > 0 and o.outstanding <= 0 for o in refunds)
    handover = session.scalars(select(UnitHandover).where(UnitHandover.unit_id == unit.id)).first()
    registered = bool(handover and handover.registered_on)
    return {
        "unit_id": unit.id,
        "unit": unit.label,
        "refund_paid": refund_paid,
        "registered": registered,
        "can_cancel": refund_paid and unit.booked and cancellation is None and not registered,
        "cancelled_on": cancellation.cancelled_on.isoformat() if cancellation else None,
    }
