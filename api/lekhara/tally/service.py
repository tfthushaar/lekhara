"""Tally imports in the database: the uploaded file, the review, apply and undo.

The file is kept in storage and read again for each review, so a builder can come back to an
import, make their choices (a unit for each buyer, a cost line for each expense ledger, the RERA
account, the landowners) and apply it later. Applying adds suppliers, their bills, buyers'
payments, cost incurred and paid, the RERA account's movements and landowner payments. The
money ledgers are append-only, so undoing adds reversing entries; everything else is removed.
"""

import json
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import registers
from lekhara.models import (
    Bill,
    CostLineRow,
    DemandRow,
    EscrowTxn,
    Landowner,
    LandownerPaymentRow,
    LedgerEntry,
    PaymentMilestone,
    Project,
    Receipt,
    TallyImport,
    TallyLink,
    Unit,
    Vendor,
    utcnow,
)
from lekhara.money import ZERO
from lekhara.services import ServiceError
from lekhara.storage import Storage
from lekhara.tally import reports
from lekhara.tally.book import Book, from_nodes
from lekhara.tally.ledgers import CostLineRef, LandownerRef
from lekhara.tally.plan import Context, DemandRef, Plan, UnitRef, VendorRef, make_plan
from lekhara.tally.reader import (
    HOW_TO_EXPORT,
    UNREADABLE,
    decode,
    detect,
    read_json,
    read_table,
    read_xml,
)

UNDO_DAYS = 30
ROLES = ("unit", "cost_line", "rera_account", "landowner", "ignore")
SOURCE_LABEL = {
    "xml": "Tally XML",
    "json": "Tally JSON",
    "daybook": "Day Book report",
    "ledger_vouchers": "Ledger Vouchers report",
    "trial_balance": "Trial Balance report",
    "ledger_list": "List of ledgers",
}

_books: "OrderedDict[str, Book]" = OrderedDict()


def read_book(filename: str, data: bytes) -> tuple[str, Book]:
    kind = detect(filename, data)
    if kind in UNREADABLE:
        raise ServiceError(f"{UNREADABLE[kind]} {HOW_TO_EXPORT}")
    if kind == "xml":
        objects, meta = read_xml(decode(data))
        book = from_nodes("xml", objects, meta)
    elif kind == "json":
        objects, meta = read_json(decode(data))
        book = from_nodes("json", objects, meta)
    else:
        rows = read_table(filename, data, kind)
        if not rows:
            raise ServiceError("The file is empty.")
        book = reports.from_rows(rows)
    if not book.vouchers and not book.ledgers:
        raise ServiceError(f"Nothing Lekhara can use was found in this file. {HOW_TO_EXPORT}")
    return kind, book


def _book(storage: Storage, row: TallyImport) -> Book:
    if row.storage_key in _books:
        _books.move_to_end(row.storage_key)
        return _books[row.storage_key]
    try:
        data = storage.get(row.storage_key)
    except FileNotFoundError:
        raise ServiceError("The file for this import is missing from storage.", 404) from None
    _, book = read_book(row.filename, data)
    _books[row.storage_key] = book
    if len(_books) > 8:
        _books.popitem(last=False)
    return book


def upload(
    session: Session,
    storage: Storage,
    project: Project,
    *,
    filename: str,
    data: bytes,
    user_id: str | None,
) -> TallyImport:
    if not data:
        raise ServiceError("The file is empty.")
    kind, book = read_book(filename, data)
    key = storage.put(data)
    _books[key] = book
    row = TallyImport(
        organization_id=project.organization_id,
        project_id=project.id,
        filename=filename[:300],
        file_kind=kind,
        source=book.source,
        storage_key=key,
        company=book.company[:200] or None,
        created_by_user_id=user_id,
    )
    session.add(row)
    session.commit()
    return row


def get_import(session: Session, import_id: str) -> TallyImport:
    row = session.get(TallyImport, import_id)
    if row is None:
        raise ServiceError("Import not found.", 404)
    return row


def project_imports(session: Session, project: Project) -> list[TallyImport]:
    return list(
        session.scalars(
            select(TallyImport)
            .where(TallyImport.project_id == project.id)
            .order_by(TallyImport.created_at.desc())
            .limit(20)
        )
    )


def options(row: TallyImport) -> dict:
    return json.loads(row.options or "{}")


def _live_refs(refs) -> set[str]:
    """References still in force: those added, less those an undo has reversed."""
    refs = [r for r in refs if r]
    reversed_ = {r.removeprefix("undo:") for r in refs if r.startswith("undo:")}
    return {r for r in refs if not r.startswith("undo:") and r not in reversed_}


def context(session: Session, project: Project, row: TallyImport, as_of: date) -> Context:
    units = tuple(
        UnitRef(u.id, u.label, u.buyer_name)
        for u in session.scalars(
            select(Unit).where(Unit.project_id == project.id).order_by(Unit.label)
        )
    )
    vendors = tuple(
        VendorRef(
            v.id, v.name, v.gstin, v.pan, v.state, v.msme_category, v.udyam_number, v.registered
        )
        for v in session.scalars(
            select(Vendor).where(Vendor.organization_id == project.organization_id)
        )
    )
    owners = list(session.scalars(select(Landowner).where(Landowner.project_id == project.id)))
    known = (
        _live_refs(session.scalars(select(Bill.source_ref).where(Bill.project_id == project.id)))
        | _live_refs(
            session.scalars(select(Receipt.source_ref).where(Receipt.project_id == project.id))
        )
        | _live_refs(
            session.scalars(
                select(LedgerEntry.reference).where(LedgerEntry.project_id == project.id)
            )
        )
        | _live_refs(
            session.scalars(select(EscrowTxn.reference).where(EscrowTxn.project_id == project.id))
        )
        | _live_refs(
            session.scalars(
                select(LandownerPaymentRow.source_ref).where(
                    LandownerPaymentRow.landowner_id.in_([o.id for o in owners])
                )
            )
        )
    )
    links = {
        link.ledger: (link.role, link.target_id)
        for link in session.scalars(select(TallyLink).where(TallyLink.project_id == project.id))
    }
    milestones = {
        m.id: m.name
        for m in session.scalars(
            select(PaymentMilestone).where(PaymentMilestone.project_id == project.id)
        )
    }
    demands = tuple(
        DemandRef(d.id, d.unit_id, d.amount, d.gst, d.raised_on, milestones.get(d.milestone_id, ""))
        for d in session.scalars(
            select(DemandRow).where(
                DemandRow.project_id == project.id, DemandRow.cancellation_id.is_(None)
            )
        )
    )
    return Context(
        as_of=as_of,
        registered_on=project.registered_on,
        units=units,
        vendors=vendors,
        known_refs=frozenset(known),
        links=links,
        cost_centre=options(row).get("cost_centre"),
        cost_lines=tuple(
            CostLineRef(c.id, c.code, c.name, c.category)
            for c in registers.cost_lines(session, project)
        ),
        landowners=tuple(LandownerRef(o.id, o.name, o.pan) for o in owners),
        gst_is_cost=project.gst_regime != "commercial_12pc",
        jda=project.land_structure.startswith("jda"),
        demands=demands,
    )


def review(session: Session, storage: Storage, row: TallyImport, as_of: date) -> tuple[Book, Plan]:
    project = session.get(Project, row.project_id)
    book = _book(storage, row)
    return book, make_plan(book, context(session, project, row, as_of))


def _target_ok(session: Session, project_id: str, role: str, target: str | None) -> bool:
    if role in ("ignore", "rera_account"):
        return True
    model = {"unit": Unit, "cost_line": CostLineRow, "landowner": Landowner}[role]
    record = session.get(model, target) if target else None
    return record is not None and record.project_id == project_id


def set_options(
    session: Session, row: TallyImport, *, cost_centre: str | None, links: dict
) -> None:
    """links: a ledger's name to a unit id, "ignore", "" to forget, or {"role", "target"}.
    Choices can still be made once an import is applied: they are the project's, remembered for
    every later import, and applying again brings in what they free."""
    if row.status == "undone":
        raise ServiceError("This import was undone.")
    opts = options(row)
    opts["cost_centre"] = (cost_centre or "").strip() or None
    row.options = json.dumps(opts)
    for ledger_name, choice in links.items():
        key = " ".join(ledger_name.split()).casefold()
        if isinstance(choice, dict):
            role, target = choice.get("role") or "", choice.get("target") or None
        elif choice == "ignore":
            role, target = "ignore", None
        else:
            role, target = ("unit", choice) if choice else ("", None)
        link = session.scalars(
            select(TallyLink).where(TallyLink.project_id == row.project_id, TallyLink.ledger == key)
        ).first()
        if not role or (role != "ignore" and role != "rera_account" and not target):
            if link is not None:
                session.delete(link)
            continue
        if role not in ROLES or not _target_ok(session, row.project_id, role, target):
            raise ServiceError("Choose from the lists for this project.")
        if link is None:
            link = TallyLink(project_id=row.project_id, ledger=key)
            session.add(link)
        link.ledger_name = ledger_name[:200]
        link.role = role
        link.target_id = target
        link.updated_at = utcnow()
    session.commit()


def apply(
    session: Session, storage: Storage, row: TallyImport, *, as_of: date, user_id: str | None
) -> dict:
    if row.status == "undone":
        raise ServiceError("This import was undone.")
    project = session.get(Project, row.project_id)
    _, plan = review(session, storage, row, as_of)
    # Applying again adds only what was waiting (everything else is recognised as already in).
    earlier = json.loads(row.result) if row.status == "applied" and row.result else None
    result = {
        "vendors_added": [],
        "vendors_changed": [],
        "bills_added": [],
        "bills_paid": [],
        "receipts_added": [],
        "cost_entries": [],
        "escrow": [],
        "landowner_payments": [],
    }
    vendor_ids: dict[str, str] = {}
    for vp in plan.vendors:
        if vp.existing_id:
            vendor = session.get(Vendor, vp.existing_id)
            before = {}
            for attr, (_, after) in vp.changes.items():
                column = "udyam_number" if attr == "udyam" else attr
                before[column] = getattr(vendor, column)
                setattr(vendor, column, after)
            if before:
                result["vendors_changed"].append({"id": vendor.id, "before": before})
                registers.log_change(
                    session,
                    project,
                    "vendor",
                    vendor.id,
                    "updated",
                    {
                        k: [registers.to_json(v), registers.to_json(getattr(vendor, k))]
                        for k, v in before.items()
                    },
                    user_id=user_id,
                    source="import",
                )
        else:
            vendor = Vendor(
                organization_id=project.organization_id,
                name=vp.name[:200],
                gstin=vp.gstin,
                registered=vp.registered,
                msme_category=vp.msme_category or "none",
                written_agreement=True,
                pan=vp.pan,
                state=vp.state,
                udyam_number=vp.udyam,
            )
            session.add(vendor)
            session.flush()
            result["vendors_added"].append(vendor.id)
        vendor_ids[vp.key] = vendor.id
    existing_bills = {
        b.source_ref: b
        for b in session.scalars(select(Bill).where(Bill.project_id == project.id))
        if b.source_ref
    }
    for bp in plan.bills:
        if bp.exists:
            bill = existing_bills.get(bp.ref)
            if bill is not None and bill.paid_on is None and bp.paid_on is not None:
                bill.paid_on = bp.paid_on
                result["bills_paid"].append(bill.id)
            if (
                bill is not None
                and bp.debit_notes
                and (bill.taxable_value, bill.gst_amount or ZERO) != (bp.taxable_value, bp.gst)
            ):
                # A debit note in this file has come off a bill brought in earlier.
                result.setdefault("bills_changed", []).append(
                    {
                        "id": bill.id,
                        "taxable_value": str(bill.taxable_value),
                        "gst_amount": str(bill.gst_amount) if bill.gst_amount is not None else None,
                    }
                )
                bill.taxable_value = bp.taxable_value
                bill.gst_amount = bp.gst
            continue
        bill = Bill(
            project_id=project.id,
            vendor_id=vendor_ids[bp.vendor_key],
            bill_no=bp.bill_no,
            bill_date=bp.bill_date,
            accepted_on=bp.accepted_on,
            taxable_value=bp.taxable_value,
            gst_amount=bp.gst,
            is_cement=bp.is_cement,
            paid_on=bp.paid_on,
            source_ref=bp.ref,
        )
        session.add(bill)
        session.flush()
        result["bills_added"].append(bill.id)
    for rp in plan.receipts:
        if rp.exists or rp.unit_id is None:
            continue
        receipt = Receipt(
            project_id=project.id,
            unit_id=rp.unit_id,
            amount=rp.amount,
            received_on=rp.received_on,
            tds_deducted=rp.tds,
            source_ref=rp.ref,
        )
        session.add(receipt)
        session.flush()
        result["receipts_added"].append(receipt.id)
    for cp in plan.money.cost_entries:
        if cp.exists:
            continue
        entry = LedgerEntry(
            project_id=project.id,
            cost_line_id=cp.cost_line_id,
            kind=cp.kind,
            amount=cp.amount,
            entry_date=cp.on,
            reference=cp.ref,
        )
        session.add(entry)
        session.flush()
        result["cost_entries"].append(entry.id)
    for ep in plan.money.escrow:
        if ep.exists:
            continue
        txn = EscrowTxn(
            project_id=project.id, kind=ep.kind, amount=ep.amount, txn_date=ep.on, reference=ep.ref
        )
        session.add(txn)
        session.flush()
        result["escrow"].append(txn.id)
    for lp in plan.money.landowner_payments:
        if lp.exists:
            continue
        payment = LandownerPaymentRow(
            landowner_id=lp.landowner_id,
            amount=lp.amount,
            paid_on=lp.on,
            tds_deducted=lp.tds,
            monetary_consideration=lp.monetary,
            note=lp.voucher[:200],
            source_ref=lp.ref,
        )
        session.add(payment)
        session.flush()
        result["landowner_payments"].append(payment.id)
    if earlier is not None:
        result = {k: earlier.get(k, []) + v for k, v in result.items()}
    else:
        row.applied_at = utcnow()
    row.status = "applied"
    row.result = json.dumps(result)
    session.commit()
    return result


def waiting_count(plan: Plan) -> int:
    """How much in the export is not in Lekhara yet: new bills, payments placed on a unit,
    cost, RERA account movements and landowner payments."""
    return (
        sum(1 for b in plan.bills if not b.exists)
        + sum(1 for r in plan.receipts if not r.exists and r.unit_id)
        + sum(1 for c in plan.money.cost_entries if not c.exists)
        + sum(1 for e in plan.money.escrow if not e.exists)
        + sum(1 for p in plan.money.landowner_payments if not p.exists)
    )


def can_undo(row: TallyImport) -> bool:
    return (
        row.status == "applied"
        and row.applied_at is not None
        and utcnow() - row.applied_at <= timedelta(days=UNDO_DAYS)
    )


def undo(session: Session, row: TallyImport) -> None:
    if not can_undo(row):
        raise ServiceError(f"An import can be undone for {UNDO_DAYS} days after it is applied.")
    result = json.loads(row.result)
    for entry_id in result.get("cost_entries", []):
        entry = session.get(LedgerEntry, entry_id)
        if entry is not None:
            session.add(
                LedgerEntry(
                    project_id=entry.project_id,
                    cost_line_id=entry.cost_line_id,
                    kind=entry.kind,
                    amount=-entry.amount,
                    entry_date=entry.entry_date,
                    reference=f"undo:{entry.reference}",
                )
            )
    for txn_id in result.get("escrow", []):
        txn = session.get(EscrowTxn, txn_id)
        if txn is not None:
            session.add(
                EscrowTxn(
                    project_id=txn.project_id,
                    kind=txn.kind,
                    amount=-txn.amount,
                    txn_date=txn.txn_date,
                    reference=f"undo:{txn.reference}",
                )
            )
    for payment_id in result.get("landowner_payments", []):
        payment = session.get(LandownerPaymentRow, payment_id)
        if payment is not None:
            session.delete(payment)
    for receipt_id in result["receipts_added"]:
        receipt = session.get(Receipt, receipt_id)
        if receipt is not None:
            session.delete(receipt)
    for bill_id in result["bills_added"]:
        bill = session.get(Bill, bill_id)
        if bill is not None:
            session.delete(bill)
    for bill_id in result["bills_paid"]:
        bill = session.get(Bill, bill_id)
        if bill is not None:
            bill.paid_on = None
    for before in result.get("bills_changed", []):
        bill = session.get(Bill, before["id"])
        if bill is not None:
            bill.taxable_value = Decimal(before["taxable_value"])
            bill.gst_amount = Decimal(before["gst_amount"]) if before["gst_amount"] else None
    session.flush()
    for change in result["vendors_changed"]:
        vendor = session.get(Vendor, change["id"])
        if vendor is not None:
            for attr, value in change["before"].items():
                setattr(vendor, attr, value)
    for vendor_id in result["vendors_added"]:
        in_use = session.scalars(select(Bill).where(Bill.vendor_id == vendor_id)).first()
        vendor = session.get(Vendor, vendor_id)
        if vendor is not None and in_use is None:
            session.delete(vendor)
    row.status = "undone"
    row.undone_at = utcnow()
    session.commit()
