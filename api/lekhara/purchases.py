"""Suppliers, their bills and the project's commitments: typed in, imported from a sheet,
changed and removed, each with a history.

Suppliers belong to the firm and serve every project; bills and commitments belong to a project.
A bill typed in or imported from a sheet can name a cost line: it then counts as cost incurred
on that line (with the GST, when the project's GST scheme gives no input credit), and as cost
paid once paid. A commitment counts as committed on its line. The money ledger is append-only,
so changing a bill or a commitment adds the entries that bring the ledger to the new figures.
"""

import json
import re
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara import accounts
from lekhara.models import (
    Bill,
    ChangeEntry,
    Commitment,
    CostLineRow,
    LedgerEntry,
    Project,
    Vendor,
)
from lekhara.records import BILLS, COMMITMENTS, SUPPLIERS, RecordType
from lekhara.registers import ZERO, log_change, parse_row, to_json
from lekhara.services import ServiceError

_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
VENDOR_KEYS = tuple(f.key for f in SUPPLIERS.fields)
BILL_KEYS = tuple(f.key for f in BILLS.fields)
COMMITMENT_KEYS = tuple(f.key for f in COMMITMENTS.fields)


def _fold(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def parse_form(record: RecordType, form: dict) -> tuple[dict, list[str]]:
    """A form's fields, blanks left out, parsed the way a sheet's cells are."""
    raw = {
        k: v for k, v in form.items() if k in {f.key for f in record.fields} and v not in (None, "")
    }
    return parse_row(record, raw)


def _changes(before: dict, after: dict) -> dict:
    return {
        k: [to_json(before.get(k)), to_json(v)]
        for k, v in after.items()
        if to_json(before.get(k)) != to_json(v)
    }


# Suppliers


def vendors_of(session: Session, organization_id: str) -> list[Vendor]:
    return list(
        session.scalars(
            select(Vendor).where(Vendor.organization_id == organization_id).order_by(Vendor.name)
        )
    )


def find_vendor(session: Session, organization_id: str, text: str | None) -> Vendor | None:
    """A supplier by GSTIN, or by name ignoring case and spacing."""
    wanted = (text or "").strip()
    if not wanted:
        return None
    upper = wanted.upper()
    for v in vendors_of(session, organization_id):
        if (v.gstin and v.gstin == upper) or _fold(v.name) == _fold(wanted):
            return v
    return None


def vendor_values(v: Vendor) -> dict:
    return {
        "name": v.name,
        "gstin": v.gstin,
        "pan": v.pan,
        "state": v.state,
        "msme_category": v.msme_category,
        "udyam_number": v.udyam_number,
        "written_agreement": v.written_agreement,
    }


def clean_vendor(values: dict, existing: Vendor | None = None) -> tuple[dict, list[str]]:
    """Check a supplier's details and fill in what the GSTIN gives: the PAN and the state."""
    out = dict(values)
    problems: list[str] = []
    name = (out.get("name") or "").strip() if "name" in out else None
    if name is not None:
        if not name:
            problems.append("The supplier's name is missing.")
        out["name"] = name[:200]
    elif existing is None:
        problems.append("The supplier's name is missing.")
    if out.get("gstin"):
        try:
            out["gstin"] = accounts.check_gstin(out["gstin"])
        except ServiceError as exc:
            problems.append(f"GSTIN: {exc}")
        else:
            gstin = out["gstin"]
            if not out.get("pan") and not (existing and existing.pan):
                out["pan"] = gstin[2:12]
            if not out.get("state") and not (existing and existing.state):
                state = accounts.GSTIN_STATE.get(gstin[:2])
                if state:
                    out["state"] = state
    if out.get("pan"):
        pan = str(out["pan"]).strip().upper()
        if not _PAN.match(pan):
            problems.append("PAN: a PAN has 10 characters, like ABCDE1234F.")
        out["pan"] = pan
        gstin = out.get("gstin") or (existing.gstin if existing else None)
        if gstin and gstin[2:12] != pan and not problems:
            problems.append("PAN: it does not match the PAN inside the GSTIN.")
    if out.get("udyam_number"):
        out["udyam_number"] = str(out["udyam_number"]).strip().upper()[:32]
    if out.get("state"):
        out["state"] = str(out["state"]).strip()[:64]
    return out, problems


def _log_vendor(session, vendor, action, changes, *, project, user_id, source, batch_id=None):
    if project is not None:
        log_change(
            session,
            project,
            "vendor",
            vendor.id,
            action,
            changes,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
        return
    session.add(
        ChangeEntry(
            organization_id=vendor.organization_id,
            project_id=None,
            record_type="vendor",
            record_id=vendor.id,
            action=action,
            changes=json.dumps(changes),
            source=source,
            import_batch_id=batch_id,
            user_id=user_id,
        )
    )


def create_vendor(
    session: Session,
    organization_id: str,
    values: dict,
    *,
    project: Project | None,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> Vendor:
    values, problems = clean_vendor(values)
    if problems:
        raise ServiceError(" ".join(problems))
    clash = find_vendor(session, organization_id, values.get("gstin")) or find_vendor(
        session, organization_id, values["name"]
    )
    if clash is not None:
        raise ServiceError(f"{clash.name} is already a supplier.")
    vendor = Vendor(
        organization_id=organization_id,
        name=values["name"],
        gstin=values.get("gstin"),
        registered=bool(values.get("gstin")),
        msme_category=values.get("msme_category") or "none",
        written_agreement=values.get("written_agreement", True),
        pan=values.get("pan"),
        state=values.get("state"),
        udyam_number=values.get("udyam_number"),
    )
    session.add(vendor)
    session.flush()
    _log_vendor(
        session,
        vendor,
        "created",
        {k: [None, to_json(v)] for k, v in vendor_values(vendor).items() if v is not None},
        project=project,
        user_id=user_id,
        source=source,
        batch_id=batch_id,
    )
    return vendor


def update_vendor(
    session: Session,
    vendor: Vendor,
    values: dict,
    *,
    project: Project | None,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> dict:
    values, problems = clean_vendor(values, vendor)
    if problems:
        raise ServiceError(" ".join(problems))
    if values.get("gstin") and values["gstin"] != vendor.gstin:
        clash = find_vendor(session, vendor.organization_id, values["gstin"])
        if clash is not None and clash.id != vendor.id:
            raise ServiceError(f"This GSTIN belongs to {clash.name}.")
    if values.get("name") and _fold(values["name"]) != _fold(vendor.name):
        clash = find_vendor(session, vendor.organization_id, values["name"])
        if clash is not None and clash.id != vendor.id:
            raise ServiceError(f"{clash.name} is already a supplier.")
    changes = _changes(vendor_values(vendor), values)
    for key in changes:
        setattr(vendor, key, values[key])
    if "gstin" in changes:
        vendor.registered = bool(vendor.gstin)
    if changes:
        _log_vendor(
            session,
            vendor,
            "updated",
            changes,
            project=project,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
    return changes


def clear_vendor_field(session, vendor, key, *, user_id) -> None:
    """Empty an optional detail, such as a GSTIN entered by mistake."""
    if key not in ("gstin", "pan", "state", "udyam_number"):
        raise ServiceError("That detail cannot be cleared.")
    before = getattr(vendor, key)
    if before is None:
        return
    setattr(vendor, key, None)
    if key == "gstin":
        vendor.registered = False
    _log_vendor(
        session, vendor, "updated", {key: [before, None]}, project=None, user_id=user_id,
        source="typed",
    )  # fmt: skip


def vendor_bills(session: Session, vendor: Vendor) -> list[Bill]:
    return list(
        session.scalars(select(Bill).where(Bill.vendor_id == vendor.id).order_by(Bill.bill_date))
    )


def delete_vendor(session: Session, vendor: Vendor, *, user_id: str | None) -> None:
    bills = session.scalar(
        select(func.count()).select_from(Bill).where(Bill.vendor_id == vendor.id)
    )
    orders = session.scalar(
        select(func.count()).select_from(Commitment).where(Commitment.vendor_id == vendor.id)
    )
    if bills or orders:
        raise ServiceError(
            f"{vendor.name} has bills or orders recorded; a supplier with records stays."
        )
    _log_vendor(
        session, vendor, "deleted", {"name": [vendor.name, None]}, project=None, user_id=user_id,
        source="typed",
    )  # fmt: skip
    session.delete(vendor)


# Cost lines and the ledger


def find_cost_line(session: Session, project: Project, text: str | None) -> CostLineRow | None:
    wanted = _fold(text)
    if not wanted:
        return None
    lines = list(session.scalars(select(CostLineRow).where(CostLineRow.project_id == project.id)))
    for line in lines:
        if _fold(line.code) == wanted or _fold(line.name) == wanted:
            return line
    starts = [line for line in lines if _fold(line.name).startswith(wanted)]
    return starts[0] if len(starts) == 1 else None


def sync_ledger(
    session: Session,
    project: Project,
    prefix: str,
    desired: list[tuple[str, str, Decimal, date]],
) -> None:
    """Bring the ledger's entries for one record (all referenced under prefix) to the desired
    (kind, cost line, amount, date) figures, by adding entries: the ledger is append-only."""
    have: dict[tuple, Decimal] = {}
    for e in session.scalars(
        select(LedgerEntry).where(
            LedgerEntry.project_id == project.id, LedgerEntry.reference.startswith(prefix)
        )
    ):
        key = (e.kind, e.cost_line_id, e.entry_date)
        have[key] = have.get(key, ZERO) + e.amount
    want: dict[tuple, Decimal] = {}
    for kind, line_id, amount, on in desired:
        key = (kind, line_id, on)
        want[key] = want.get(key, ZERO) + amount
    for key in sorted(set(have) | set(want), key=str):
        diff = want.get(key, ZERO) - have.get(key, ZERO)
        if diff == 0:
            continue
        kind, line_id, on = key
        session.add(
            LedgerEntry(
                project_id=project.id,
                cost_line_id=line_id,
                kind=kind,
                amount=diff,
                entry_date=on,
                reference=f"{prefix}{kind}" if key not in have else f"{prefix}{kind}:change",
            )
        )


# Bills


def bills_of(session: Session, project: Project) -> list[Bill]:
    return list(
        session.scalars(
            select(Bill)
            .where(Bill.project_id == project.id)
            .order_by(Bill.bill_date.desc(), Bill.bill_no)
        )
    )


def bill_values(session: Session, bill: Bill) -> dict:
    line = session.get(CostLineRow, bill.cost_line_id) if bill.cost_line_id else None
    return {
        "supplier": bill.vendor.name if bill.vendor else None,
        "bill_no": bill.bill_no,
        "bill_date": bill.bill_date,
        "taxable_value": bill.taxable_value,
        "gst_amount": bill.gst_amount,
        "accepted_on": bill.accepted_on,
        "paid_on": bill.paid_on,
        "cost_line": line.code if line else None,
        "is_cement": bill.is_cement,
        "rcm_paid": bill.rcm_paid,
        "excluded": bill.excluded,
    }


def bill_cost(project: Project, bill: Bill) -> Decimal:
    """What a bill adds to cost: the taxable value, and the GST when there is no input credit."""
    gst = bill.gst_amount or ZERO
    return bill.taxable_value + (gst if project.gst_regime != "commercial_12pc" else ZERO)


def _sync_bill(session: Session, project: Project, bill: Bill) -> None:
    desired = []
    if bill.cost_line_id:
        cost = bill_cost(project, bill)
        desired.append(("incurred", bill.cost_line_id, cost, bill.accepted_on or bill.bill_date))
        if bill.paid_on:
            desired.append(("paid", bill.cost_line_id, cost, bill.paid_on))
    sync_ledger(session, project, f"bill:{bill.id}:", desired)


def check_bill(
    session: Session,
    project: Project,
    values: dict,
    *,
    as_of: date,
    existing: Bill | None = None,
) -> list[str]:
    problems: list[str] = []
    merged = {**(bill_values(session, existing) if existing else {}), **values}
    for key, words in (
        ("supplier", "The supplier is missing."),
        ("bill_no", "The bill number is missing."),
        ("bill_date", "The bill date is missing."),
        ("taxable_value", "The taxable value is missing."),
    ):
        if merged.get(key) in (None, ""):
            problems.append(words)
    if merged.get("taxable_value") is not None and merged["taxable_value"] <= 0:
        problems.append("The taxable value should be above zero.")
    if merged.get("gst_amount") is not None and merged["gst_amount"] < 0:
        problems.append("GST cannot be below zero.")
    for key, label in (
        ("bill_date", "bill date"),
        ("accepted_on", "acceptance"),
        ("paid_on", "payment"),
    ):
        if merged.get(key) and merged[key] > as_of:
            problems.append(f"The {label} date cannot be in the future.")
    if values.get("cost_line") and find_cost_line(session, project, values["cost_line"]) is None:
        problems.append(f"There is no cost line {values['cost_line']} in this project.")
    return problems


def _bill_clash(session, project, vendor_id, bill_no, exclude_id=None) -> Bill | None:
    for b in session.scalars(
        select(Bill).where(Bill.project_id == project.id, Bill.vendor_id == vendor_id)
    ):
        if _fold(b.bill_no) == _fold(bill_no) and b.id != exclude_id:
            return b
    return None


def create_bill(
    session: Session,
    project: Project,
    values: dict,
    *,
    as_of: date,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> Bill:
    problems = check_bill(session, project, values, as_of=as_of)
    if problems:
        raise ServiceError(" ".join(problems))
    vendor = find_vendor(session, project.organization_id, values["supplier"])
    if vendor is None:
        vendor = create_vendor(
            session,
            project.organization_id,
            {"name": values["supplier"]},
            project=project,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
    if _bill_clash(session, project, vendor.id, values["bill_no"]):
        raise ServiceError(f"Bill {values['bill_no']} from {vendor.name} is already recorded.")
    line = find_cost_line(session, project, values.get("cost_line"))
    bill = Bill(
        project_id=project.id,
        vendor_id=vendor.id,
        bill_no=str(values["bill_no"]).strip()[:64],
        bill_date=values["bill_date"],
        accepted_on=values.get("accepted_on") or values["bill_date"],
        taxable_value=values["taxable_value"],
        gst_amount=values.get("gst_amount"),
        paid_on=values.get("paid_on"),
        is_cement=bool(values.get("is_cement")),
        rcm_paid=bool(values.get("rcm_paid")),
        excluded=bool(values.get("excluded")),
        cost_line_id=line.id if line else None,
    )
    session.add(bill)
    session.flush()
    _sync_bill(session, project, bill)
    log_change(
        session,
        project,
        "bill",
        bill.id,
        "created",
        {
            k: [None, to_json(v)]
            for k, v in bill_values(session, bill).items()
            if v not in (None, False)
        },
        user_id=user_id,
        source=source,
        batch_id=batch_id,
    )
    return bill


def update_bill(
    session: Session,
    project: Project,
    bill: Bill,
    values: dict,
    *,
    as_of: date,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> dict:
    problems = check_bill(session, project, values, as_of=as_of, existing=bill)
    if problems:
        raise ServiceError(" ".join(problems))
    before = bill_values(session, bill)
    if values.get("supplier") and _fold(values["supplier"]) != _fold(before["supplier"]):
        vendor = find_vendor(session, project.organization_id, values["supplier"])
        if vendor is None:
            raise ServiceError(f"There is no supplier {values['supplier']}; add them first.")
        bill.vendor_id = vendor.id
        session.flush()
        session.refresh(bill)
    if values.get("bill_no") and _bill_clash(
        session, project, bill.vendor_id, values["bill_no"], exclude_id=bill.id
    ):
        raise ServiceError(f"Bill {values['bill_no']} is already recorded for this supplier.")
    for key in ("bill_no", "bill_date", "taxable_value", "gst_amount", "accepted_on", "paid_on"):
        if key in values:
            setattr(bill, key, values[key])
    for key in ("is_cement", "rcm_paid", "excluded"):
        if key in values:
            setattr(bill, key, bool(values[key]))
    if "cost_line" in values:
        line = (
            find_cost_line(session, project, values["cost_line"]) if values["cost_line"] else None
        )
        bill.cost_line_id = line.id if line else None
    after = bill_values(session, bill)
    changes = _changes(before, after)
    if changes:
        _sync_bill(session, project, bill)
        log_change(
            session,
            project,
            "bill",
            bill.id,
            "updated",
            changes,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
    return changes


def clear_bill_field(session, project, bill, key, *, user_id) -> None:
    """Empty an optional detail: the payment date, the GST, the cost line."""
    if key not in ("paid_on", "gst_amount", "cost_line"):
        raise ServiceError("That detail cannot be cleared.")
    before = bill_values(session, bill)
    if before[key] is None:
        return
    if key == "cost_line":
        bill.cost_line_id = None
    else:
        setattr(bill, key, None)
    _sync_bill(session, project, bill)
    log_change(
        session, project, "bill", bill.id, "updated", {key: [to_json(before[key]), None]},
        user_id=user_id, source="typed",
    )  # fmt: skip


def delete_bill(session: Session, project: Project, bill: Bill, *, user_id: str | None) -> None:
    if bill.source_ref and bill.source_ref.startswith("tally:"):
        raise ServiceError("This bill came from Tally. Correct it in Tally and import again.")
    sync_ledger(session, project, f"bill:{bill.id}:", [])
    log_change(
        session,
        project,
        "bill",
        bill.id,
        "deleted",
        {
            k: [to_json(v), None]
            for k, v in bill_values(session, bill).items()
            if v not in (None, False)
        },
        user_id=user_id,
        source="typed",
    )
    session.delete(bill)


# Commitments


def commitments_of(session: Session, project: Project) -> list[Commitment]:
    return list(
        session.scalars(
            select(Commitment)
            .where(Commitment.project_id == project.id)
            .order_by(Commitment.committed_on.desc(), Commitment.reference)
        )
    )


def commitment_values(session: Session, c: Commitment) -> dict:
    line = session.get(CostLineRow, c.cost_line_id)
    vendor = session.get(Vendor, c.vendor_id) if c.vendor_id else None
    return {
        "reference": c.reference,
        "cost_line": line.code if line else None,
        "amount": c.amount,
        "committed_on": c.committed_on,
        "supplier": vendor.name if vendor else None,
        "description": c.description,
    }


def find_commitment(session: Session, project: Project, reference: str) -> Commitment | None:
    for c in commitments_of(session, project):
        if _fold(c.reference) == _fold(reference):
            return c
    return None


def check_commitment(
    session: Session,
    project: Project,
    values: dict,
    *,
    as_of: date,
    existing: Commitment | None = None,
) -> list[str]:
    problems: list[str] = []
    merged = {**(commitment_values(session, existing) if existing else {}), **values}
    for key, words in (
        ("reference", "The order number is missing."),
        ("cost_line", "The cost line is missing."),
        ("amount", "The amount is missing."),
        ("committed_on", "The order date is missing."),
    ):
        if merged.get(key) in (None, ""):
            problems.append(words)
    if merged.get("amount") is not None and merged["amount"] <= 0:
        problems.append("The amount should be above zero.")
    if merged.get("committed_on") and merged["committed_on"] > as_of:
        problems.append("The order date cannot be in the future.")
    if values.get("cost_line") and find_cost_line(session, project, values["cost_line"]) is None:
        problems.append(f"There is no cost line {values['cost_line']} in this project.")
    return problems


def _sync_commitment(session: Session, project: Project, c: Commitment) -> None:
    sync_ledger(
        session,
        project,
        f"commitment:{c.id}:",
        [("commitment", c.cost_line_id, c.amount, c.committed_on)],
    )


def _supplier_for(session, project, name, *, user_id, source, batch_id) -> Vendor | None:
    if not name:
        return None
    vendor = find_vendor(session, project.organization_id, name)
    if vendor is None:
        vendor = create_vendor(
            session,
            project.organization_id,
            {"name": name},
            project=project,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
    return vendor


def create_commitment(
    session: Session,
    project: Project,
    values: dict,
    *,
    as_of: date,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> Commitment:
    problems = check_commitment(session, project, values, as_of=as_of)
    if problems:
        raise ServiceError(" ".join(problems))
    if find_commitment(session, project, values["reference"]):
        raise ServiceError(f"Order {values['reference']} is already recorded.")
    line = find_cost_line(session, project, values["cost_line"])
    vendor = _supplier_for(
        session, project, values.get("supplier"), user_id=user_id, source=source, batch_id=batch_id
    )
    c = Commitment(
        project_id=project.id,
        cost_line_id=line.id,
        vendor_id=vendor.id if vendor else None,
        reference=str(values["reference"]).strip()[:100],
        description=(values.get("description") or None) and str(values["description"])[:300],
        amount=values["amount"],
        committed_on=values["committed_on"],
    )
    session.add(c)
    session.flush()
    _sync_commitment(session, project, c)
    log_change(
        session,
        project,
        "commitment",
        c.id,
        "created",
        {k: [None, to_json(v)] for k, v in commitment_values(session, c).items() if v is not None},
        user_id=user_id,
        source=source,
        batch_id=batch_id,
    )
    return c


def update_commitment(
    session: Session,
    project: Project,
    c: Commitment,
    values: dict,
    *,
    as_of: date,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> dict:
    problems = check_commitment(session, project, values, as_of=as_of, existing=c)
    if problems:
        raise ServiceError(" ".join(problems))
    before = commitment_values(session, c)
    if values.get("reference") and _fold(values["reference"]) != _fold(c.reference):
        if find_commitment(session, project, values["reference"]):
            raise ServiceError(f"Order {values['reference']} is already recorded.")
        c.reference = str(values["reference"]).strip()[:100]
    if values.get("cost_line"):
        c.cost_line_id = find_cost_line(session, project, values["cost_line"]).id
    if "supplier" in values:
        vendor = _supplier_for(
            session, project, values["supplier"], user_id=user_id, source=source, batch_id=batch_id
        )
        c.vendor_id = vendor.id if vendor else None
    for key in ("amount", "committed_on"):
        if values.get(key) is not None:
            setattr(c, key, values[key])
    if "description" in values:
        c.description = (values["description"] or None) and str(values["description"])[:300]
    changes = _changes(before, commitment_values(session, c))
    if changes:
        _sync_commitment(session, project, c)
        log_change(
            session,
            project,
            "commitment",
            c.id,
            "updated",
            changes,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
    return changes


def delete_commitment(
    session: Session, project: Project, c: Commitment, *, user_id: str | None
) -> None:
    sync_ledger(session, project, f"commitment:{c.id}:", [])
    log_change(
        session,
        project,
        "commitment",
        c.id,
        "deleted",
        {k: [to_json(v), None] for k, v in commitment_values(session, c).items() if v is not None},
        user_id=user_id,
        source="typed",
    )
    session.delete(c)
