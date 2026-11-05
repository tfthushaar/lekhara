"""Contractors' work orders and running bills, and paying bills with a second person's approval.

A contractor's work order is an order (a Commitment) with what is held back from each bill: the
retention share, the mobilisation advance to recover, and whether 1% labour cess is deducted.
Each running bill is also a Bill, so its value counts as cost on the order's cost line, and it
waits for approval and payment with every other bill.

From each running bill, Lekhara works out:
- retention: the order's share of the work value;
- advance recovery: the advance in proportion to the work value, until it is all back;
- TDS: 1% for an individual or HUF, 2% for anyone else, once a single bill or the year's bills
  to that contractor pass the thresholds; at a higher rate when there is no PAN;
- labour cess, when the order says so;
- what to pay: the work value and GST, less all of the above.

Every bill not yet paid waits for the owner or finance to approve it (or hold it, with a reason).
Accounts records the payment of an approved bill. The owner and finance can pay directly.
"""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara import purchases
from lekhara.engines.tax import financial_year
from lekhara.models import (
    Bill,
    Commitment,
    CostLineRow,
    Organization,
    Project,
    RaBill,
    User,
    Vendor,
    utcnow,
)
from lekhara.money import ZERO, rupees
from lekhara.rules import KARNATAKA, RulesPack
from lekhara.services import ServiceError


def _money(value, label: str, *, required: bool = False) -> Decimal | None:
    text = str(value if value is not None else "").replace(",", "").replace("₹", "").strip()
    if not text:
        if required:
            raise ServiceError(f"Enter {label}.")
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ServiceError(f"{label.capitalize()} is not an amount.") from None
    if amount < 0:
        raise ServiceError(f"{label.capitalize()} cannot be below zero.")
    return rupees(amount)


def _date(value, label: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ServiceError(f"{label} is not a date.") from None


# Work orders


def is_work_order(c: Commitment, billed: bool = False) -> bool:
    return billed or c.retention_pct > 0 or c.advance > 0 or c.deduct_cess


def create_order(
    session: Session, project: Project, fields: dict, *, as_of: date, user_id: str | None,
    rules: RulesPack = KARNATAKA,
) -> Commitment:  # fmt: skip
    contractor = (fields.get("contractor") or "").strip()
    if not contractor:
        raise ServiceError("Enter the contractor's name.")
    amount = _money(fields.get("amount"), "the order's value", required=True)
    if not amount:
        raise ServiceError("Enter the order's value.")
    line = fields.get("cost_line") or None
    if line is None:
        first = session.scalars(
            select(CostLineRow)
            .where(CostLineRow.project_id == project.id, CostLineRow.category == "construction")
            .order_by(CostLineRow.code)
        ).first()
        if first is None:
            raise ServiceError("Set up the budget first, so the work has a part to count against.")
        line = first.code
    count = session.scalar(
        select(func.count()).select_from(Commitment).where(Commitment.project_id == project.id)
    )
    order = purchases.create_commitment(
        session,
        project,
        {
            "reference": (fields.get("reference") or "").strip() or f"WO-{(count or 0) + 1:03d}",
            "supplier": contractor,
            "cost_line": line,
            "amount": amount,
            "committed_on": _date(fields.get("committed_on"), "The order date") or as_of,
            "description": (fields.get("description") or "").strip() or None,
        },
        as_of=as_of,
        user_id=user_id,
    )
    retention = fields.get("retention_pct")
    order.retention_pct = (
        Decimal(str(retention))
        if retention not in (None, "")
        else rules.value("contract.retention_default", as_of)
    )
    if not 0 <= order.retention_pct <= 20:
        raise ServiceError("Retention is usually between 0 and 20 per cent.")
    order.advance = _money(fields.get("advance"), "the advance") or ZERO
    order.deduct_cess = str(fields.get("deduct_cess", "")).lower() in ("yes", "true", "on", "1")
    session.commit()
    return order


def _billed(session: Session, order: Commitment) -> list[RaBill]:
    return list(
        session.scalars(
            select(RaBill).where(RaBill.commitment_id == order.id).order_by(RaBill.number)
        )
    )


def _tds_rate(vendor: Vendor, on: date, rules: RulesPack) -> tuple[Decimal, str | None]:
    pan = (vendor.pan or "").upper()
    if len(pan) != 10:
        return rules.value(
            "it.tds_no_pan_rate", on
        ), "No PAN recorded, so TDS is at the higher rate."
    if pan[3] in ("P", "H"):
        return rules.value("it.contractor_tds_rate_individual", on), None
    return rules.value("it.contractor_tds_rate_other", on), None


def _year_billed(session: Session, org_id: str, vendor_id: str, on: date) -> Decimal:
    start, end = financial_year(on)
    total = session.scalar(
        select(func.coalesce(func.sum(Bill.taxable_value), 0))
        .join(Project, Project.id == Bill.project_id)
        .where(
            Project.organization_id == org_id,
            Bill.vendor_id == vendor_id,
            Bill.bill_date.between(start, end),
        )
    )
    return Decimal(total or 0)


def work_out(
    session: Session, project: Project, order: Commitment, work_value: Decimal, on: date,
    *, recovery: Decimal | None = None, rules: RulesPack = KARNATAKA,
) -> dict:  # fmt: skip
    """What is held back from a running bill of this value, and what is left to pay."""
    vendor = session.get(Vendor, order.vendor_id)
    done = _billed(session, order)
    retention = rupees(work_value * order.retention_pct / 100)
    recovered = sum((b.advance_recovery for b in done), ZERO)
    left = max(order.advance - recovered, ZERO)
    if recovery is None:
        share = order.advance * work_value / order.amount if order.amount else ZERO
        recovery = rupees(min(share, left))
    if recovery > left:
        raise ServiceError(f"Only {left:,.0f} of the advance is left to recover.")
    rate, note = _tds_rate(vendor, on, rules)
    before = _year_billed(session, project.organization_id, vendor.id, on)
    over = work_value > rules.value("it.contractor_tds_single", on) or (
        before + work_value > rules.value("it.contractor_tds_aggregate", on)
    )
    tds = rupees(work_value * rate) if over else ZERO
    cess = (
        rupees(work_value * rules.value("labour.bocw_cess_rate", on)) if order.deduct_cess else ZERO
    )
    return {
        "retention": retention,
        "advance_recovery": recovery,
        "tds": tds,
        "tds_rate": rate if over else ZERO,
        "cess": cess,
        "note": note,
    }


def add_running_bill(
    session: Session, project: Project, order: Commitment, fields: dict, *, as_of: date,
    user_id: str | None, rules: RulesPack = KARNATAKA,
) -> RaBill:  # fmt: skip
    if order.vendor_id is None:
        raise ServiceError("This order has no contractor.")
    work_value = _money(fields.get("work_value"), "the value of work done", required=True)
    if not work_value:
        raise ServiceError("Enter the value of work done in this bill.")
    gst = _money(fields.get("gst"), "the GST") or ZERO
    on = _date(fields.get("period_to"), "The bill date") or as_of
    recovery = _money(fields.get("advance_recovery"), "the advance recovered")
    held = work_out(session, project, order, work_value, on, recovery=recovery, rules=rules)
    number = len(_billed(session, order)) + 1
    vendor = session.get(Vendor, order.vendor_id)
    line = session.get(CostLineRow, order.cost_line_id)
    bill = purchases.create_bill(
        session,
        project,
        {
            "supplier": vendor.name,
            "bill_no": (fields.get("bill_no") or "").strip() or f"{order.reference}/RA-{number}",
            "bill_date": on,
            "taxable_value": work_value,
            "gst_amount": gst or None,
            "cost_line": line.code if line else None,
        },
        as_of=as_of,
        user_id=user_id,
    )
    net = (
        work_value + gst - held["retention"] - held["advance_recovery"] - held["tds"] - held["cess"]
    )
    ra = RaBill(
        project_id=project.id,
        commitment_id=order.id,
        bill_id=bill.id,
        number=number,
        period_to=on,
        work_value=work_value,
        gst=gst,
        retention=held["retention"],
        advance_recovery=held["advance_recovery"],
        tds=held["tds"],
        cess=held["cess"],
        net_payable=net,
        created_by=user_id,
    )
    session.add(ra)
    session.commit()
    return ra


def release_retention(session: Session, order: Commitment, *, as_of: date) -> None:
    if order.retention_released_on:
        raise ServiceError("The retention on this order has already been released.")
    order.retention_released_on = as_of
    session.commit()


def contractors_view(session: Session, project: Project, *, as_of: date, can_edit: bool) -> dict:
    orders = list(
        session.scalars(
            select(Commitment)
            .where(Commitment.project_id == project.id, Commitment.vendor_id.is_not(None))
            .order_by(Commitment.committed_on.desc())
        )
    )
    out = []
    for o in orders:
        bills = _billed(session, o)
        if not is_work_order(o, bool(bills)):
            continue
        vendor = session.get(Vendor, o.vendor_id)
        billed = sum((b.work_value for b in bills), ZERO)
        retention = sum((b.retention for b in bills), ZERO)
        recovered = sum((b.advance_recovery for b in bills), ZERO)
        out.append({
            "id": o.id, "reference": o.reference, "contractor": vendor.name,
            "description": o.description, "amount": f"{o.amount:.2f}",
            "billed": f"{billed:.2f}", "left": f"{max(o.amount - billed, ZERO):.2f}",
            "over": billed > o.amount,
            "retention_pct": f"{o.retention_pct}", "retention_held": f"{retention:.2f}",
            "retention_released_on": o.retention_released_on.isoformat()
            if o.retention_released_on else None,
            "advance": f"{o.advance:.2f}",
            "advance_left": f"{max(o.advance - recovered, ZERO):.2f}",
            "deduct_cess": o.deduct_cess, "has_pan": bool(vendor.pan),
            "bills": [_ra_row(session, b) for b in reversed(bills)],
        })  # fmt: skip
    lines = session.scalars(
        select(CostLineRow).where(CostLineRow.project_id == project.id).order_by(CostLineRow.code)
    )
    return {
        "can_edit": can_edit,
        "orders": out,
        "cost_lines": [{"value": x.code, "label": x.name} for x in lines],
        "retention_default": f"{KARNATAKA.value('contract.retention_default', as_of)}",
    }


def _ra_row(session: Session, b: RaBill) -> dict:
    bill = session.get(Bill, b.bill_id)
    return {
        "id": b.id, "bill_id": b.bill_id, "number": b.number, "bill_no": bill.bill_no,
        "period_to": b.period_to.isoformat(), "work_value": f"{b.work_value:.2f}",
        "gst": f"{b.gst:.2f}", "retention": f"{b.retention:.2f}",
        "advance_recovery": f"{b.advance_recovery:.2f}", "tds": f"{b.tds:.2f}",
        "cess": f"{b.cess:.2f}", "net_payable": f"{b.net_payable:.2f}",
        "state": bill_state(bill), "paid_on": bill.paid_on.isoformat() if bill.paid_on else None,
    }  # fmt: skip


# Paying bills, with a second person's approval


def bill_state(bill: Bill) -> str:
    """paid, held, approved or waiting (for approval)."""
    if bill.paid_on:
        return "paid"
    return bill.approval or "waiting"


def payable(session: Session, bill: Bill) -> Decimal:
    ra = session.scalars(select(RaBill).where(RaBill.bill_id == bill.id)).first()
    return ra.net_payable if ra else bill.taxable_value + (bill.gst_amount or ZERO)


def pay_by(session: Session, bill: Bill, rules: RulesPack = KARNATAKA) -> date:
    """When the bill should be paid: the MSME limit for a micro or small supplier, otherwise
    30 days after the bill."""
    vendor = bill.vendor
    if vendor and vendor.msme_category in ("micro", "small"):
        key = (
            "it.msme.days_with_agreement"
            if vendor.written_agreement
            else "it.msme.days_without_agreement"
        )
        return bill.accepted_on + timedelta(days=int(rules.value(key, bill.accepted_on)))
    return bill.bill_date + timedelta(days=30)


def approve(session: Session, bill: Bill, *, user_id: str | None) -> None:
    if bill.paid_on:
        raise ServiceError("This bill is already paid.")
    bill.approval, bill.approval_by, bill.approval_at = "approved", user_id, utcnow()
    bill.approval_note = None
    session.commit()


def hold(session: Session, bill: Bill, note: str | None, *, user_id: str | None) -> None:
    if bill.paid_on:
        raise ServiceError("This bill is already paid.")
    if not (note or "").strip():
        raise ServiceError("Say why it is on hold, so accounts knows what to sort out.")
    bill.approval, bill.approval_by, bill.approval_at = "held", user_id, utcnow()
    bill.approval_note = note.strip()[:300]
    session.commit()


def pay(
    session: Session, bill: Bill, fields: dict, *, as_of: date, user_id: str | None,
    approver: bool,
) -> None:  # fmt: skip
    if bill.paid_on:
        raise ServiceError("This bill is already paid.")
    if not approver and bill.approval != "approved":
        raise ServiceError("This bill is waiting for the owner or finance to approve it.")
    project = session.get(Project, bill.project_id)
    on = _date(fields.get("paid_on"), "The payment date") or as_of
    purchases.update_bill(session, project, bill, {"paid_on": on}, as_of=as_of, user_id=user_id)
    if approver and bill.approval != "approved":
        bill.approval, bill.approval_by, bill.approval_at = "approved", user_id, utcnow()
    bill.pay_reference = (fields.get("reference") or "").strip()[:200] or None
    session.commit()


def payables_view(
    session: Session, org: Organization, *, as_of: date, can_approve: bool, can_pay: bool
) -> dict:
    projects = {
        p.id: p for p in session.scalars(select(Project).where(Project.organization_id == org.id))
    }
    bills = list(
        session.scalars(
            select(Bill)
            .where(Bill.project_id.in_(projects), Bill.paid_on.is_(None), Bill.excluded.is_(False))
            .order_by(Bill.bill_date)
        )
    )
    names = {
        u.id: u.name
        for u in session.scalars(
            select(User).where(User.id.in_({b.approval_by for b in bills if b.approval_by}))
        )
    }
    groups: dict[str, list] = {"waiting": [], "approved": [], "held": []}
    for b in bills:
        ra = session.scalars(select(RaBill).where(RaBill.bill_id == b.id)).first()
        due = pay_by(session, b)
        groups[bill_state(b)].append({
            "id": b.id, "project": projects[b.project_id].name, "project_id": b.project_id,
            "supplier": b.vendor.name if b.vendor else "", "bill_no": b.bill_no,
            "bill_date": b.bill_date.isoformat(), "amount": f"{payable(session, b):.2f}",
            "running_bill": ra.number if ra else None,
            "held_back": f"{(ra.retention + ra.advance_recovery + ra.tds + ra.cess):.2f}"
            if ra else None,
            "pay_by": due.isoformat(), "late": due < as_of,
            "msme": bool(b.vendor and b.vendor.msme_category in ("micro", "small")),
            "note": b.approval_note, "decided_by": names.get(b.approval_by),
        })  # fmt: skip
    return {
        "can_approve": can_approve,
        "can_pay": can_pay,
        "waiting": groups["waiting"],
        "approved": groups["approved"],
        "held": groups["held"],
        "totals": {
            k: f"{sum((Decimal(x['amount']) for x in v), ZERO):.2f}" for k, v in groups.items()
        },
    }


def counts(session: Session, org: Organization) -> dict:
    rows = session.execute(
        select(Bill.approval, func.count())
        .join(Project, Project.id == Bill.project_id)
        .where(Project.organization_id == org.id, Bill.paid_on.is_(None), Bill.excluded.is_(False))
        .group_by(Bill.approval)
    ).all()
    by = {k or "waiting": n for k, n in rows}
    return {"waiting": by.get("waiting", 0), "approved": by.get("approved", 0),
            "held": by.get("held", 0)}  # fmt: skip
