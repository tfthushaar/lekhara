"""GSTR-2B imports in the database: the uploaded file, the check against the project's bills,
and applying it: suppliers' GSTINs filled in, missing suppliers and, if chosen, missing invoices
added as bills. Undo takes them out again."""

import json
from collections import OrderedDict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import purchases
from lekhara.gst.plan import BillRef, Plan, VendorRef, make_plan
from lekhara.gst.reader import Return, fold_number, read_return
from lekhara.models import Bill, GstImport, Organization, Project, Vendor, utcnow
from lekhara.services import ServiceError
from lekhara.storage import Storage

UNDO_DAYS = 30
_cache: "OrderedDict[str, Return]" = OrderedDict()


def return_of(storage: Storage, row: GstImport) -> Return:
    cached = _cache.get(row.storage_key)
    if cached is None:
        cached = read_return(row.filename, storage.get(row.storage_key))
        _cache[row.storage_key] = cached
        while len(_cache) > 8:
            _cache.popitem(last=False)
    return cached


def upload(
    session: Session,
    storage: Storage,
    project: Project,
    *,
    filename: str,
    data: bytes,
    user_id: str | None,
) -> GstImport:
    ret = read_return(filename, data)
    key = storage.put(data)
    _cache[key] = ret
    from_tally = session.scalars(
        select(Bill).where(Bill.project_id == project.id, Bill.source_ref.like("tally:%"))
    ).first()
    row = GstImport(
        organization_id=project.organization_id,
        project_id=project.id,
        filename=filename[:300],
        storage_key=key,
        form=ret.form,
        gstin=(ret.gstin or None) and str(ret.gstin)[:15],
        period=(ret.period or None) and str(ret.period)[:16],
        invoices=len(ret.invoices),
        # Bills booked in Tally come in from Tally; adding them from the return too would
        # leave them looking unpaid. So by default only firms without Tally bills add them.
        options=json.dumps({"add_missing": from_tally is None}),
        created_by_user_id=user_id,
    )
    session.add(row)
    session.commit()
    return row


def get_import(session: Session, import_id: str) -> GstImport:
    row = session.get(GstImport, import_id)
    if row is None:
        raise ServiceError("Return not found.", 404)
    return row


def project_imports(session: Session, project: Project) -> list[GstImport]:
    return list(
        session.scalars(
            select(GstImport)
            .where(GstImport.project_id == project.id)
            .order_by(GstImport.created_at.desc())
            .limit(20)
        )
    )


def options(row: GstImport) -> dict:
    return json.loads(row.options or "{}")


def review(session: Session, storage: Storage, row: GstImport) -> tuple[Return, Plan]:
    ret = return_of(storage, row)
    org = session.get(Organization, row.organization_id)
    vendors = [
        VendorRef(v.id, v.name, v.gstin)
        for v in session.scalars(
            select(Vendor).where(Vendor.organization_id == row.organization_id)
        )
    ]
    names = {v.id: v for v in vendors}
    bills = [
        BillRef(
            b.id,
            b.vendor_id,
            names[b.vendor_id].name if b.vendor_id in names else "",
            names[b.vendor_id].gstin if b.vendor_id in names else None,
            b.bill_no,
            b.bill_date,
            b.taxable_value,
            b.gst_amount,
            b.source_ref,
        )
        for b in session.scalars(select(Bill).where(Bill.project_id == row.project_id))
    ]
    return ret, make_plan(ret, bills, vendors, firm_gstin=org.gstin if org else None)


def set_options(session: Session, row: GstImport, body: dict) -> None:
    if row.status != "review":
        raise ServiceError("This return has already been applied.")
    opts = options(row)
    if body.get("add_missing") is not None:
        opts["add_missing"] = bool(body["add_missing"])
    row.options = json.dumps(opts)
    session.commit()


def apply(
    session: Session, storage: Storage, row: GstImport, *, as_of, user_id: str | None
) -> dict:
    if row.status != "review":
        raise ServiceError("This return has already been applied.")
    project = session.get(Project, row.project_id)
    _, plan = review(session, storage, row)
    result: dict[str, list] = {"gstins": [], "suppliers": [], "bills": []}
    for vendor_ref, gstin, _ in plan.gstin_updates:
        vendor = session.get(Vendor, vendor_ref.id)
        if vendor is None or vendor.gstin:
            continue
        try:
            purchases.update_vendor(
                session,
                vendor,
                {"gstin": gstin},
                project=project,
                user_id=user_id,
                source="import",
            )
        except ServiceError:
            continue
        result["gstins"].append(vendor.id)
    created: dict[str, str] = {}
    for gstin, name in plan.new_suppliers.items():
        try:
            vendor = purchases.create_vendor(
                session,
                project.organization_id,
                {"name": name, "gstin": gstin},
                project=project,
                user_id=user_id,
                source="import",
            )
        except ServiceError:
            continue
        created[gstin] = vendor.id
        result["suppliers"].append(vendor.id)
    if options(row).get("add_missing"):
        for line in plan.lines:
            if line.outcome != "missing":
                continue
            inv = line.invoice
            vendor_id = line.vendor_id or created.get(inv.supplier_gstin)
            vendor = session.get(Vendor, vendor_id) if vendor_id else None
            ref = f"gstr2b:{inv.supplier_gstin}:{fold_number(inv.number)}"
            if vendor is None or not inv.on or inv.taxable <= 0:
                continue
            if session.scalars(
                select(Bill).where(Bill.project_id == project.id, Bill.source_ref == ref)
            ).first():
                continue
            bill = purchases.create_bill(
                session,
                project,
                {
                    "supplier": vendor.name,
                    "bill_no": inv.number,
                    "bill_date": inv.on,
                    "taxable_value": inv.taxable,
                    "gst_amount": inv.gst,
                },
                as_of=max(as_of, inv.on),
                user_id=user_id,
                source="import",
            )
            bill.source_ref = ref
            result["bills"].append(bill.id)
    row.status = "applied"
    row.applied_at = utcnow()
    row.result = json.dumps(result)
    session.commit()
    return result


def can_undo(row: GstImport) -> bool:
    return (
        row.status == "applied"
        and row.applied_at is not None
        and utcnow() - row.applied_at <= timedelta(days=UNDO_DAYS)
    )


def undo(session: Session, row: GstImport, *, user_id: str | None) -> None:
    if not can_undo(row):
        raise ServiceError(f"A return can be undone for {UNDO_DAYS} days after it is applied.")
    project = session.get(Project, row.project_id)
    result = json.loads(row.result or "{}")
    for bill_id in result.get("bills", []):
        bill = session.get(Bill, bill_id)
        if bill is not None:
            purchases.delete_bill(session, project, bill, user_id=user_id)
    session.flush()
    for vendor_id in result.get("suppliers", []):
        vendor = session.get(Vendor, vendor_id)
        if vendor is not None and not purchases.vendor_bills(session, vendor):
            purchases.delete_vendor(session, vendor, user_id=user_id)
    for vendor_id in result.get("gstins", []):
        vendor = session.get(Vendor, vendor_id)
        if vendor is not None:
            purchases.clear_vendor_field(session, vendor, "gstin", user_id=user_id)
    row.status = "undone"
    row.undone_at = utcnow()
    session.commit()
