"""The Import centre: a spreadsheet in, a preview of what would change, then apply or undo.

- Excel (.xlsx) or CSV. Title rows above the header are skipped: the header is the row that
  matches the most known columns.
- Columns are matched by name and common aliases, or by a mapping saved from the last file
  with the same headers.
- Rows are matched on the record's key (the unit number for units), so the same file
  imported twice changes nothing. Blank cells never erase what is there.
- An applied import can be undone for 30 days, unless the records have changed since.
"""

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import crm, purchases, registers, safe_files, sheets, statutory
from lekhara.models import (
    Approval,
    Bill,
    Commitment,
    Filing,
    ImportBatch,
    ImportMapping,
    Landowner,
    LandownerPaymentRow,
    Project,
    Receipt,
    Unit,
    Vendor,
    utcnow,
)
from lekhara.records import RECORD_TYPES, RecordType, match_columns, normalise_header
from lekhara.services import ServiceError

MAX_ROWS = 5000
UNDO_DAYS = 30
_HEADER_SEARCH = 15


def record_type(kind: str) -> RecordType:
    if kind not in RECORD_TYPES:
        raise ServiceError("Lekhara cannot import that kind of record yet.", 404)
    return RECORD_TYPES[kind]


# Reading files


def _cell(value):
    """A cell as JSON can hold it."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int | float):
        return value
    return str(value).strip()


def read_rows(filename: str, data: bytes) -> list[list]:
    name = filename.casefold()
    if name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")
        rows = [[sheets.from_csv(v) for v in r] for r in csv.reader(io.StringIO(text))]
    elif name.endswith((".xlsx", ".xlsm")):
        safe_files.check_zip(data)
        try:
            book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except (InvalidFileException, BadZipFile, KeyError, OSError, ValueError):
            raise ServiceError(
                "This Excel file could not be opened. Save it as .xlsx and try again."
            ) from None
        sheet = book.worksheets[0]
        rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        book.close()
    else:
        raise ServiceError(
            "Import takes Excel (.xlsx) or CSV files. Save the sheet as one of those."
        )
    cleaned = [[_cell(v) for v in row] for row in rows]
    return [row for row in cleaned if any(v != "" for v in row)]


def find_header(record: RecordType, rows: list[list]) -> int:
    best, best_matches = 0, -1
    for i, row in enumerate(rows[:_HEADER_SEARCH]):
        matches = len(match_columns(record, [str(v) for v in row]))
        if matches > best_matches:
            best, best_matches = i, matches
    return best


def _signature(headers: list[str]) -> str:
    joined = "|".join(normalise_header(h) for h in headers)
    return hashlib.sha256(joined.encode()).hexdigest()


# Batches


def start(
    session: Session,
    project: Project,
    kind: str,
    *,
    filename: str,
    data: bytes,
    user_id: str | None,
) -> ImportBatch:
    return start_rows(
        session, project, kind, filename=filename, rows=read_rows(filename, data), user_id=user_id
    )


def start_rows(
    session: Session,
    project: Project,
    kind: str,
    *,
    filename: str,
    rows: list[list],
    user_id: str | None,
    origin: str = "file",
) -> ImportBatch:
    record = record_type(kind)
    if not rows:
        raise ServiceError("The file is empty.")
    header_at = find_header(record, rows)
    headers = [str(v) for v in rows[header_at]]
    body = rows[header_at + 1 :]
    recognised = crm.recognise(headers) if origin == "file" else None
    headers, body = crm.prepare(kind, headers, body)
    if not body:
        raise ServiceError("The file has a header row but no rows below it.")
    if len(body) > MAX_ROWS:
        raise ServiceError(f"Import up to {MAX_ROWS} rows at a time. Split the file and try again.")
    saved = session.scalars(
        select(ImportMapping).where(
            ImportMapping.organization_id == project.organization_id,
            ImportMapping.kind == kind,
            ImportMapping.signature == _signature(headers),
        )
    ).first()
    mapping = (
        {int(k): v for k, v in json.loads(saved.mapping).items()}
        if saved
        else match_columns(record, headers)
    )
    batch = ImportBatch(
        organization_id=project.organization_id,
        project_id=project.id,
        kind=kind,
        filename=filename[:300],
        headers=json.dumps(headers),
        header_row=header_at + 1,
        rows=json.dumps(body),
        mapping=json.dumps(mapping),
        created_by_user_id=user_id,
        origin=origin,
        recognised=recognised,
    )
    session.add(batch)
    session.commit()
    return batch


def get_batch(session: Session, batch_id: str) -> ImportBatch:
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise ServiceError("Import not found.", 404)
    return batch


def mapping_of(batch: ImportBatch) -> dict[int, str]:
    return {int(k): v for k, v in json.loads(batch.mapping).items()}


def set_mapping(session: Session, batch: ImportBatch, mapping: dict) -> None:
    if batch.status != "preview":
        raise ServiceError("This import has already been applied.")
    record = record_type(batch.kind)
    known = {f.key for f in record.fields}
    clean: dict[int, str] = {}
    for column, key in mapping.items():
        if not key:
            continue
        if key not in known:
            raise ServiceError("Choose a column name from the list.")
        if key in clean.values():
            field = record.field(key)
            raise ServiceError(f"Two columns are set to “{field.label}”. Choose one.")
        clean[int(column)] = key
    batch.mapping = json.dumps(clean)
    session.commit()


class UnitImport:
    """Units and buyers: matched on the unit number; new ones added, changed ones updated."""

    kind = "units"

    def context(self, session: Session, project: Project) -> dict:
        return {"units": registers.units_by_label(session, project)}

    def evaluate(self, values: dict, problems: list[str], seen: set, ctx: dict) -> dict:
        label = values.get("label")
        if label is None:
            problems.insert(0, "The unit number is missing.")
        elif label.casefold() in seen:
            problems.insert(0, f"Unit {label} appears more than once in the file.")
        if label:
            seen.add(label.casefold())
        unit = ctx["units"].get(label.casefold()) if label else None
        if not problems:
            problems = registers.unit_problems(values, unit)
        if problems:
            return {"key": label, "action": "error", "messages": problems, "changes": {}}
        if unit is None:
            return {"key": label, "action": "add", "messages": [], "changes": {}}
        before = registers.unit_values(unit)
        changes = {
            k: [registers.to_json(before[k]), registers.to_json(v)]
            for k, v in values.items()
            if v is not None and before[k] != v
        }
        action = "update" if changes else "unchanged"
        return {"key": label, "action": action, "messages": [], "changes": changes}

    def add(self, session, project, values, *, user_id, batch_id, ctx, source="import") -> str:
        unit = registers.create_unit(
            session, project, values, user_id=user_id, source=source, batch_id=batch_id
        )
        return unit.id

    def update(
        self, session, project, key, values, *, user_id, batch_id, source="import"
    ) -> tuple[str, dict]:
        unit = registers.units_by_label(session, project)[key.casefold()]
        changes = registers.update_unit(
            session, project, unit, values, user_id=user_id, source=source, batch_id=batch_id
        )
        return unit.id, changes

    def blocker(self, session, item) -> str | None:
        unit = session.get(Unit, item["id"])
        if unit is None:
            return f"row {item['row']} (the unit has been deleted)"
        now = {k: registers.to_json(v) for k, v in registers.unit_values(unit).items()}
        expected = (
            item["after"]
            if item["action"] == "add"
            else {k: after for k, (_, after) in item["changes"].items()}
        )
        if any(now.get(k) != v for k, v in expected.items()):
            return f"unit {unit.label} (changed since)"
        dependents = registers.unit_dependents(session, unit)
        if item["action"] == "add" and dependents:
            return f"unit {unit.label} (now has {dependents[0]})"
        return None

    def reverse(self, session, project, item, *, user_id, batch_id) -> None:
        unit = session.get(Unit, item["id"])
        if item["action"] == "add":
            registers.delete_unit(session, project, unit, user_id=user_id)
            return
        record = record_type(self.kind)
        before = {k: registers.from_json(record, k, b) for k, (b, _) in item["changes"].items()}
        for key, value in before.items():
            setattr(unit, key, value)
        unit.booked = bool(unit.buyer_name)
        registers.log_change(
            session,
            project,
            "unit",
            unit.id,
            "updated",
            {k: [after, b] for k, (b, after) in item["changes"].items()},
            user_id=user_id,
            source="undo",
            batch_id=batch_id,
        )

    def export_rows(self, session, project, record) -> list[list]:
        units = sorted(registers.units_by_label(session, project).values(), key=lambda u: u.label)
        return [[_display(record, k, getattr(u, k)) for k in registers.UNIT_KEYS] for u in units]


class ReceiptImport:
    """Buyer payments: each row is one payment to one sold unit. A payment already recorded with
    the same unit, date, amount and reference is left as it is, so a file can be imported again."""

    kind = "receipts"

    def context(self, session: Session, project: Project) -> dict:
        units = registers.units_by_label(session, project)
        recorded = {
            self._key(r.unit_id, r.received_on, r.amount, r.reference)
            for r in session.scalars(select(Receipt).where(Receipt.project_id == project.id))
        }
        return {"units": units, "recorded": recorded}

    @staticmethod
    def _key(unit_id, on, amount, reference) -> tuple:
        return (unit_id, on, registers.to_json(amount), (reference or "").strip().casefold())

    def evaluate(self, values: dict, problems: list[str], seen: set, ctx: dict) -> dict:
        label = values.get("unit")
        unit = ctx["units"].get(label.casefold()) if label else None
        if label is None:
            problems.insert(0, "The unit number is missing.")
        elif unit is None:
            problems.insert(0, f"There is no unit {label} in this project.")
        elif not unit.booked:
            problems.insert(0, f"Unit {label} is not sold yet; record its buyer first.")
        for name, words in (
            ("received_on", "The date is missing."),
            ("amount", "The amount is missing."),
        ):
            if values.get(name) is None and not any(words in p for p in problems):
                problems.append(words)
        if values.get("amount") is not None and values["amount"] <= 0:
            problems.append("The amount should be above zero.")
        if problems:
            return {"key": label, "action": "error", "messages": problems, "changes": {}}
        key = self._key(unit.id, values["received_on"], values["amount"], values.get("reference"))
        if key in seen:
            return {
                "key": label,
                "action": "error",
                "messages": ["The same payment appears twice in the file."],
                "changes": {},
            }
        seen.add(key)
        if key in ctx["recorded"]:
            return {"key": label, "action": "unchanged", "messages": [], "changes": {}}
        return {"key": label, "action": "add", "messages": [], "changes": {}}

    def add(self, session, project, values, *, user_id, batch_id, ctx, source="import") -> str:
        unit = ctx["units"][values["unit"].casefold()]
        receipt = registers.create_receipt(
            session, project, unit, values, user_id=user_id, source=source, batch_id=batch_id
        )
        return receipt.id

    def update(self, session, project, key, values, *, user_id, batch_id, source="import"):
        raise ServiceError("Payments are only ever added.")

    def blocker(self, session, item) -> str | None:
        if session.get(Receipt, item["id"]) is None:
            return f"row {item['row']} (the payment has been deleted)"
        return None

    def reverse(self, session, project, item, *, user_id, batch_id) -> None:
        receipt = session.get(Receipt, item["id"])
        registers.log_change(
            session,
            project,
            "receipt",
            receipt.id,
            "deleted",
            {"amount": [registers.to_json(receipt.amount), None]},
            user_id=user_id,
            source="undo",
            batch_id=batch_id,
        )
        session.delete(receipt)

    def export_rows(self, session, project, record) -> list[list]:
        units = {u.id: u.label for u in registers.units_by_label(session, project).values()}
        receipts = session.scalars(
            select(Receipt).where(Receipt.project_id == project.id).order_by(Receipt.received_on)
        )
        return [
            [
                units.get(r.unit_id, ""),
                r.received_on.strftime("%d/%m/%Y"),
                float(r.amount),
                float(r.tds_deducted or 0),
                r.reference or "",
            ]
            for r in receipts
        ]


def _same(a, b) -> bool:
    return registers.to_json(a) == registers.to_json(b)


class SupplierImport:
    """Suppliers: matched on GSTIN or name; new ones added, changed details filled in. They belong
    to the firm, so a supplier imported in one project serves every project."""

    kind = "suppliers"

    def context(self, session: Session, project: Project) -> dict:
        return {"session": session, "org": project.organization_id}

    def evaluate(self, values: dict, problems: list[str], seen: set, ctx: dict) -> dict:
        name = values.get("name")
        key = (name or "").strip()
        if not key:
            problems.insert(0, "The supplier's name is missing.")
        else:
            folded = purchases._fold(key)
            if folded in seen or (values.get("gstin") and values["gstin"].upper() in seen):
                problems.insert(0, f"{key} appears more than once in the file.")
            seen.add(folded)
            if values.get("gstin"):
                seen.add(values["gstin"].upper())
        existing = None
        if not problems:
            existing = purchases.find_vendor(
                ctx["session"], ctx["org"], values.get("gstin")
            ) or purchases.find_vendor(ctx["session"], ctx["org"], key)
            values, more = purchases.clean_vendor(values, existing)
            problems.extend(more)
        if problems:
            return {"key": key, "action": "error", "messages": problems, "changes": {}}
        if existing is None:
            return {"key": key, "action": "add", "messages": [], "changes": {}}
        before = purchases.vendor_values(existing)
        changes = {
            k: [registers.to_json(before[k]), registers.to_json(v)]
            for k, v in values.items()
            if v is not None and k in before and not _same(before[k], v)
        }
        return {
            "key": existing.id,
            "action": "update" if changes else "unchanged",
            "messages": [],
            "changes": changes,
        }

    def add(self, session, project, values, *, user_id, batch_id, ctx, source="import") -> str:
        vendor = purchases.create_vendor(
            session,
            project.organization_id,
            values,
            project=project,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
        return vendor.id

    def update(
        self, session, project, key, values, *, user_id, batch_id, source="import"
    ) -> tuple[str, dict]:
        vendor = session.get(Vendor, key)
        changes = purchases.update_vendor(
            session, vendor, values, project=project, user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return vendor.id, changes

    def blocker(self, session, item) -> str | None:
        vendor = session.get(Vendor, item["id"])
        if vendor is None:
            return f"row {item['row']} (the supplier has been deleted)"
        if item["action"] == "add" and purchases.vendor_bills(session, vendor):
            return f"{vendor.name} (now has bills)"
        return None

    def reverse(self, session, project, item, *, user_id, batch_id) -> None:
        vendor = session.get(Vendor, item["id"])
        if item["action"] == "add":
            purchases.delete_vendor(session, vendor, user_id=user_id)
            return
        record = record_type(self.kind)
        for k, (before, _) in item["changes"].items():
            setattr(vendor, k, registers.from_json(record, k, before))
        vendor.registered = bool(vendor.gstin)

    def export_rows(self, session, project, record) -> list[list]:
        return [
            [_display(record, k, v) for k, v in purchases.vendor_values(vendor).items()]
            for vendor in purchases.vendors_of(session, project.organization_id)
        ]


class BillImport:
    """Suppliers' bills: matched on the supplier and the bill number; a supplier not yet in
    Lekhara is added. A bill with a cost line counts as cost incurred, and as paid once paid."""

    kind = "bills"

    def context(self, session: Session, project: Project) -> dict:
        return {"session": session, "project": project}

    def evaluate(self, values: dict, problems: list[str], seen: set, ctx: dict) -> dict:
        session, project = ctx["session"], ctx["project"]
        supplier = (values.get("supplier") or "").strip()
        bill_no = (values.get("bill_no") or "").strip()
        label = f"{bill_no} from {supplier}" if supplier and bill_no else bill_no or supplier
        if not problems:
            problems = purchases.check_bill(session, project, values, as_of=ctx["as_of"])
        pair = (purchases._fold(supplier), purchases._fold(bill_no))
        if supplier and bill_no:
            if pair in seen:
                problems.insert(0, f"Bill {bill_no} from {supplier} appears more than once.")
            seen.add(pair)
        if problems:
            return {"key": label, "action": "error", "messages": problems, "changes": {}}
        vendor = purchases.find_vendor(session, project.organization_id, supplier)
        if vendor is None:
            return {
                "key": label,
                "action": "add",
                "messages": [f"{supplier} is new and will be added as a supplier."],
                "changes": {},
            }
        bill = purchases._bill_clash(session, project, vendor.id, bill_no)
        if bill is None:
            return {"key": label, "action": "add", "messages": [], "changes": {}}
        before = purchases.bill_values(session, bill)
        line = purchases.find_cost_line(session, project, values.get("cost_line"))
        wanted = {**values, "supplier": vendor.name}
        if line is not None:
            wanted["cost_line"] = line.code
        changes = {
            k: [registers.to_json(before[k]), registers.to_json(v)]
            for k, v in wanted.items()
            if v is not None and k in before and not _same(before[k], v)
        }
        return {
            "key": bill.id,
            "action": "update" if changes else "unchanged",
            "messages": [],
            "changes": changes,
        }

    def add(self, session, project, values, *, user_id, batch_id, ctx, source="import") -> str:
        bill = purchases.create_bill(
            session, project, values, as_of=ctx["as_of"], user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return bill.id

    def update(
        self, session, project, key, values, *, user_id, batch_id, source="import"
    ) -> tuple[str, dict]:
        bill = session.get(Bill, key)
        changes = purchases.update_bill(
            session, project, bill, values, as_of=date.max, user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return bill.id, changes

    def blocker(self, session, item) -> str | None:
        if session.get(Bill, item["id"]) is None:
            return f"row {item['row']} (the bill has been deleted)"
        return None

    def reverse(self, session, project, item, *, user_id, batch_id) -> None:
        bill = session.get(Bill, item["id"])
        if item["action"] == "add":
            purchases.delete_bill(session, project, bill, user_id=user_id)
            return
        record = record_type(self.kind)
        before = {k: registers.from_json(record, k, b) for k, (b, _) in item["changes"].items()}
        for key in [k for k, v in before.items() if v is None]:
            purchases.clear_bill_field(session, project, bill, key, user_id=user_id)
        restore = {k: v for k, v in before.items() if v is not None}
        if restore:
            purchases.update_bill(
                session, project, bill, restore, as_of=date.max, user_id=user_id, source="undo",
                batch_id=batch_id,
            )  # fmt: skip

    def export_rows(self, session, project, record) -> list[list]:
        return [
            [_display(record, k, v) for k, v in purchases.bill_values(session, bill).items()]
            for bill in reversed(purchases.bills_of(session, project))
        ]


class CommitmentImport:
    """Commitments: work orders, purchase orders and contracts, matched on their number; a
    changed amount (a variation) updates the commitment on its cost line."""

    kind = "commitments"

    def context(self, session: Session, project: Project) -> dict:
        return {"session": session, "project": project}

    def evaluate(self, values: dict, problems: list[str], seen: set, ctx: dict) -> dict:
        session, project = ctx["session"], ctx["project"]
        reference = (values.get("reference") or "").strip()
        if not problems:
            problems = purchases.check_commitment(session, project, values, as_of=ctx["as_of"])
        if reference:
            if purchases._fold(reference) in seen:
                problems.insert(0, f"Order {reference} appears more than once in the file.")
            seen.add(purchases._fold(reference))
        if problems:
            return {"key": reference, "action": "error", "messages": problems, "changes": {}}
        existing = purchases.find_commitment(session, project, reference)
        if existing is None:
            return {"key": reference, "action": "add", "messages": [], "changes": {}}
        before = purchases.commitment_values(session, existing)
        line = purchases.find_cost_line(session, project, values.get("cost_line"))
        wanted = {**values, "cost_line": line.code if line else values.get("cost_line")}
        changes = {
            k: [registers.to_json(before[k]), registers.to_json(v)]
            for k, v in wanted.items()
            if v is not None and k in before and not _same(before[k], v)
        }
        return {
            "key": existing.id,
            "action": "update" if changes else "unchanged",
            "messages": [],
            "changes": changes,
        }

    def add(self, session, project, values, *, user_id, batch_id, ctx, source="import") -> str:
        c = purchases.create_commitment(
            session, project, values, as_of=ctx["as_of"], user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return c.id

    def update(
        self, session, project, key, values, *, user_id, batch_id, source="import"
    ) -> tuple[str, dict]:
        c = session.get(Commitment, key)
        changes = purchases.update_commitment(
            session, project, c, values, as_of=date.max, user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return c.id, changes

    def blocker(self, session, item) -> str | None:
        if session.get(Commitment, item["id"]) is None:
            return f"row {item['row']} (the order has been deleted)"
        return None

    def reverse(self, session, project, item, *, user_id, batch_id) -> None:
        c = session.get(Commitment, item["id"])
        if item["action"] == "add":
            purchases.delete_commitment(session, project, c, user_id=user_id)
            return
        record = record_type(self.kind)
        before = {k: registers.from_json(record, k, b) for k, (b, _) in item["changes"].items()}
        purchases.update_commitment(
            session, project, c, before, as_of=date.max, user_id=user_id, source="undo",
            batch_id=batch_id,
        )  # fmt: skip

    def export_rows(self, session, project, record) -> list[list]:
        return [
            [_display(record, k, v) for k, v in purchases.commitment_values(session, c).items()]
            for c in reversed(purchases.commitments_of(session, project))
        ]


class LandownerPaymentImport:
    """Payments to landowners: each row is one payment, to a landowner found by name or PAN. A
    payment already recorded with the same landowner, date, amount and reference is left alone,
    so a file can be imported again."""

    kind = "landowner_payments"

    def context(self, session: Session, project: Project) -> dict:
        recorded = {
            self._key(p.landowner_id, p.paid_on, p.amount, p.note)
            for p in session.scalars(
                select(LandownerPaymentRow)
                .join(Landowner)
                .where(Landowner.project_id == project.id)
            )
        }
        return {"session": session, "project": project, "recorded": recorded}

    @staticmethod
    def _key(owner_id, on, amount, reference) -> tuple:
        return (owner_id, on, registers.to_json(amount), (reference or "").strip().casefold())

    def evaluate(self, values: dict, problems: list[str], seen: set, ctx: dict) -> dict:
        name = values.get("landowner")
        owner = registers.find_landowner(ctx["session"], ctx["project"], name)
        if name is None:
            problems.insert(0, "The landowner is missing.")
        elif owner is None:
            problems.insert(
                0, f"There is no landowner {name} in this project. Add them on the Units page."
            )
        if not problems:
            problems = registers.check_landowner_payment(values, as_of=ctx["as_of"])
        if problems:
            return {"key": name, "action": "error", "messages": problems, "changes": {}}
        key = self._key(owner.id, values["paid_on"], values["amount"], values.get("reference"))
        if key in seen:
            return {
                "key": name,
                "action": "error",
                "messages": ["The same payment appears twice in the file."],
                "changes": {},
            }
        seen.add(key)
        action = "unchanged" if key in ctx["recorded"] else "add"
        return {"key": owner.name, "action": action, "messages": [], "changes": {}}

    def add(self, session, project, values, *, user_id, batch_id, ctx, source="import") -> str:
        owner = registers.find_landowner(session, project, values["landowner"])
        payment = registers.create_landowner_payment(
            session, project, owner, values, as_of=ctx["as_of"], user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return payment.id

    def update(self, session, project, key, values, *, user_id, batch_id, source="import"):
        raise ServiceError("Payments are only ever added.")

    def blocker(self, session, item) -> str | None:
        if session.get(LandownerPaymentRow, item["id"]) is None:
            return f"row {item['row']} (the payment has been deleted)"
        return None

    def reverse(self, session, project, item, *, user_id, batch_id) -> None:
        payment = session.get(LandownerPaymentRow, item["id"])
        registers.delete_landowner_payment(
            session, project, payment, user_id=user_id, source="undo", batch_id=batch_id
        )

    def export_rows(self, session, project, record) -> list[list]:
        payments = session.scalars(
            select(LandownerPaymentRow)
            .join(Landowner)
            .where(Landowner.project_id == project.id)
            .order_by(LandownerPaymentRow.paid_on, Landowner.name)
        )
        return [
            [_display(record, k, v) for k, v in registers.landowner_payment_values(p).items()]
            for p in payments
        ]


class ApprovalImport:
    """Approvals: matched on what the approval is; new ones added, changed dates filled in."""

    kind = "approvals"

    def context(self, session: Session, project: Project) -> dict:
        return {"session": session, "project": project}

    def evaluate(self, values: dict, problems: list[str], seen: set, ctx: dict) -> dict:
        session, project = ctx["session"], ctx["project"]
        name = (values.get("name") or "").strip()
        existing = statutory.find_approval(session, project, name) if name else None
        if not problems:
            problems = statutory.check_approval(values, as_of=ctx["as_of"], existing=existing)
        if name:
            if statutory._fold(name) in seen:
                problems.insert(0, f"{name} appears more than once in the file.")
            seen.add(statutory._fold(name))
        if problems:
            return {"key": name, "action": "error", "messages": problems, "changes": {}}
        if existing is None:
            return {"key": name, "action": "add", "messages": [], "changes": {}}
        before = statutory.approval_values(existing)
        changes = {
            k: [registers.to_json(before[k]), registers.to_json(v)]
            for k, v in values.items()
            if v is not None and k != "name" and not _same(before[k], v)
        }
        return {
            "key": existing.id,
            "action": "update" if changes else "unchanged",
            "messages": [],
            "changes": changes,
        }

    def add(self, session, project, values, *, user_id, batch_id, ctx, source="import") -> str:
        a = statutory.create_approval(
            session, project, values, as_of=ctx["as_of"], user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return a.id

    def update(
        self, session, project, key, values, *, user_id, batch_id, source="import"
    ) -> tuple[str, dict]:
        a = session.get(Approval, key)
        values = {k: v for k, v in values.items() if k != "name"}
        changes = statutory.update_approval(
            session, project, a, values, as_of=date.max, user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return a.id, changes

    def blocker(self, session, item) -> str | None:
        if session.get(Approval, item["id"]) is None:
            return f"row {item['row']} (the approval has been deleted)"
        return None

    def reverse(self, session, project, item, *, user_id, batch_id) -> None:
        a = session.get(Approval, item["id"])
        if item["action"] == "add":
            statutory.delete_approval(session, project, a, user_id=user_id)
            return
        record = record_type(self.kind)
        before = {k: registers.from_json(record, k, b) for k, (b, _) in item["changes"].items()}
        statutory.update_approval(
            session, project, a, {k: v for k, v in before.items() if v is not None},
            as_of=date.max, user_id=user_id, clear=tuple(k for k, v in before.items() if v is None),
            source="undo", batch_id=batch_id,
        )  # fmt: skip

    def export_rows(self, session, project, record) -> list[list]:
        return [
            [_display(record, k, v) for k, v in statutory.approval_values(a).items()]
            for a in statutory.approvals_of(session, project)
        ]


class FilingImport:
    """K-RERA filings: matched on the kind of filing and the period it covers."""

    kind = "filings"

    def context(self, session: Session, project: Project) -> dict:
        return {"session": session, "project": project}

    def evaluate(self, values: dict, problems: list[str], seen: set, ctx: dict) -> dict:
        session, project = ctx["session"], ctx["project"]
        kind, end = values.get("kind"), values.get("period_end")
        label = (
            f"{statutory.FILING_LABEL.get(kind, 'Filing')}, {end.strftime('%d/%m/%Y')}"
            if end
            else statutory.FILING_LABEL.get(kind, "Filing")
        )
        existing = statutory.find_filing(session, project, kind, end) if kind and end else None
        if not problems:
            problems = statutory.check_filing(values, as_of=ctx["as_of"], existing=existing)
        if kind and end:
            if (kind, end) in seen:
                problems.insert(0, f"{label} appears more than once in the file.")
            seen.add((kind, end))
        if problems:
            return {"key": label, "action": "error", "messages": problems, "changes": {}}
        if existing is None:
            return {"key": label, "action": "add", "messages": [], "changes": {}}
        before = statutory.filing_values(existing)
        changes = {
            k: [registers.to_json(before[k]), registers.to_json(v)]
            for k, v in values.items()
            if v is not None and k in ("filed_on", "reference") and not _same(before[k], v)
        }
        return {
            "key": existing.id,
            "action": "update" if changes else "unchanged",
            "messages": [],
            "changes": changes,
        }

    def add(self, session, project, values, *, user_id, batch_id, ctx, source="import") -> str:
        f = statutory.create_filing(
            session, project, values, as_of=ctx["as_of"], user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return f.id

    def update(
        self, session, project, key, values, *, user_id, batch_id, source="import"
    ) -> tuple[str, dict]:
        f = session.get(Filing, key)
        values = {k: v for k, v in values.items() if k in ("filed_on", "reference")}
        changes = statutory.update_filing(
            session, project, f, values, as_of=date.max, user_id=user_id, source=source,
            batch_id=batch_id,
        )  # fmt: skip
        return f.id, changes

    def blocker(self, session, item) -> str | None:
        if session.get(Filing, item["id"]) is None:
            return f"row {item['row']} (the filing has been deleted)"
        return None

    def reverse(self, session, project, item, *, user_id, batch_id) -> None:
        f = session.get(Filing, item["id"])
        if item["action"] == "add":
            statutory.delete_filing(session, project, f, user_id=user_id)
            return
        record = record_type(self.kind)
        before = {k: registers.from_json(record, k, b) for k, (b, _) in item["changes"].items()}
        statutory.update_filing(
            session, project, f, before, as_of=date.max, user_id=user_id, source="undo",
            batch_id=batch_id,
        )  # fmt: skip

    def export_rows(self, session, project, record) -> list[list]:
        return [
            [_display(record, k, v) for k, v in statutory.filing_values(f).items()]
            for f in statutory.filings_of(session, project)
        ]


HANDLERS = {
    h.kind: h
    for h in (
        UnitImport(),
        ReceiptImport(),
        SupplierImport(),
        BillImport(),
        CommitmentImport(),
        LandownerPaymentImport(),
        ApprovalImport(),
        FilingImport(),
    )
}

EDITABLE_AS_TABLE = ("units", "suppliers", "bills", "commitments", "approvals")
"""Record types whose existing rows can be edited as a table: those an import can update."""


def evaluate(session: Session, batch: ImportBatch, *, as_of: date | None = None) -> list[dict]:
    """What each row would do: add, update, unchanged or error, with the reasons."""
    record = record_type(batch.kind)
    handler = HANDLERS[batch.kind]
    project = session.get(Project, batch.project_id)
    ctx = handler.context(session, project)
    ctx["as_of"] = as_of or date.today()
    mapping = mapping_of(batch)
    seen: set = set()
    out = []
    first_row = batch.header_row + 1
    for offset, row in enumerate(json.loads(batch.rows)):
        raw = {key: row[col] for col, key in mapping.items() if col < len(row) and row[col] != ""}
        values, problems = registers.parse_row(record, raw)
        result = handler.evaluate(values, problems, seen, ctx)
        result["row"] = first_row + offset
        result["values"] = {k: registers.to_json(v) for k, v in values.items() if v is not None}
        out.append(result)
    return out


def apply(
    session: Session, batch: ImportBatch, *, user_id: str | None, as_of: date | None = None
) -> dict:
    if batch.status != "preview":
        raise ServiceError("This import has already been applied.")
    record = record_type(batch.kind)
    handler = HANDLERS[batch.kind]
    project = session.get(Project, batch.project_id)
    rows = evaluate(session, batch, as_of=as_of)
    ctx = handler.context(session, project)
    ctx["as_of"] = as_of or date.today()
    source = "edited" if batch.origin == "table" else "import"
    done = []
    for row in rows:
        if row["action"] not in ("add", "update"):
            continue
        values = {k: registers.from_json(record, k, v) for k, v in row["values"].items()}
        if row["action"] == "add":
            record_id = handler.add(
                session, project, values, user_id=user_id, batch_id=batch.id, ctx=ctx,
                source=source,
            )  # fmt: skip
            done.append(
                {"row": row["row"], "action": "add", "id": record_id, "after": row["values"]}
            )
        else:
            record_id, changes = handler.update(
                session, project, row["key"], values, user_id=user_id, batch_id=batch.id,
                source=source,
            )  # fmt: skip
            done.append(
                {"row": row["row"], "action": "update", "id": record_id, "changes": changes}
            )
    batch.status = "applied"
    batch.applied_at = utcnow()
    batch.result = json.dumps(
        {
            "done": done,
            "added": sum(1 for d in done if d["action"] == "add"),
            "updated": sum(1 for d in done if d["action"] == "update"),
            "unchanged": sum(1 for r in rows if r["action"] == "unchanged"),
            "errors": sum(1 for r in rows if r["action"] == "error"),
        }
    )
    _remember_mapping(session, batch)
    session.commit()
    return json.loads(batch.result)


def _remember_mapping(session: Session, batch: ImportBatch) -> None:
    signature = _signature(json.loads(batch.headers))
    saved = session.scalars(
        select(ImportMapping).where(
            ImportMapping.organization_id == batch.organization_id,
            ImportMapping.kind == batch.kind,
            ImportMapping.signature == signature,
        )
    ).first()
    if saved is None:
        saved = ImportMapping(
            organization_id=batch.organization_id, kind=batch.kind, signature=signature
        )
        session.add(saved)
    saved.mapping = batch.mapping
    saved.updated_at = utcnow()


def can_undo(batch: ImportBatch) -> bool:
    return (
        batch.status == "applied"
        and batch.applied_at is not None
        and utcnow() - batch.applied_at <= timedelta(days=UNDO_DAYS)
    )


def undo(session: Session, batch: ImportBatch, *, user_id: str | None) -> None:
    if not can_undo(batch):
        raise ServiceError(f"An import can be undone for {UNDO_DAYS} days after it is applied.")
    handler = HANDLERS[batch.kind]
    project = session.get(Project, batch.project_id)
    done = json.loads(batch.result)["done"]
    blockers = [b for b in (handler.blocker(session, item) for item in done) if b]
    if blockers:
        listed = ", ".join(blockers[:5]) + (" and others" if len(blockers) > 5 else "")
        raise ServiceError(
            f"This import cannot be undone, because some of its records have moved on: {listed}. "
            "Change them by hand instead."
        )
    for item in reversed(done):
        handler.reverse(session, project, item, user_id=user_id, batch_id=batch.id)
    batch.status = "undone"
    batch.undone_at = utcnow()
    session.commit()


def project_batches(session: Session, project: Project, limit: int = 20) -> list[ImportBatch]:
    return list(
        session.scalars(
            select(ImportBatch)
            .where(ImportBatch.project_id == project.id)
            .order_by(ImportBatch.created_at.desc())
            .limit(limit)
        )
    )


# Templates and exports, in the same layout


def _xlsx(record: RecordType, rows: list[list], *, notes: bool) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = record.title[:31]
    sheet.append([f.label for f in record.fields])
    for row in rows:
        sheets.append(sheet, row)
    for i, f in enumerate(record.fields):
        sheet.column_dimensions[sheet.cell(row=1, column=i + 1).column_letter].width = max(
            14, len(f.label) + 4
        )
    if notes:
        help_sheet = book.create_sheet("How to fill this in")
        help_sheet.append(["Column", "Needed", "What to put"])
        for f in record.fields:
            choices = " or ".join(label for _, label in f.choices)
            help_sheet.append(
                [f.label, "Yes" if f.required else "", " ".join(x for x in (f.help, choices) if x)]
            )
        help_sheet.column_dimensions["A"].width = 24
        help_sheet.column_dimensions["C"].width = 90
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _csv(record: RecordType, rows: list[list]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([f.label for f in record.fields])
    writer.writerows([[sheets.csv_value(v) for v in row] for row in rows])
    return out.getvalue().encode("utf-8-sig")


def _display(record: RecordType, key: str, value):
    field = record.field(key)
    if value is None:
        return ""
    if field.kind == "choice":
        return dict(field.choices).get(value, value)
    if field.kind == "date":
        return value.strftime("%d/%m/%Y")
    if field.kind == "money":
        return float(value)
    return value


def template(kind: str, fmt: str) -> bytes:
    record = record_type(kind)
    example = [[f.example for f in record.fields]]
    if fmt == "xlsx":
        return _xlsx(record, example, notes=True)
    return _csv(record, example)


def export(session: Session, project: Project, kind: str, fmt: str) -> bytes:
    record = record_type(kind)
    rows = HANDLERS[kind].export_rows(session, project, record)
    if fmt == "xlsx":
        return _xlsx(record, rows, notes=False)
    return _csv(record, rows)
