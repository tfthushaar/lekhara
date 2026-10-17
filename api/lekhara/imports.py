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

from lekhara import registers
from lekhara.models import ImportBatch, ImportMapping, Project, Receipt, Unit, utcnow
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
        rows = [list(r) for r in csv.reader(io.StringIO(text))]
    elif name.endswith((".xlsx", ".xlsm")):
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
    record = record_type(kind)
    rows = read_rows(filename, data)
    if not rows:
        raise ServiceError("The file is empty.")
    header_at = find_header(record, rows)
    headers = [str(v) for v in rows[header_at]]
    body = rows[header_at + 1 :]
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

    def add(self, session, project, values, *, user_id, batch_id, ctx) -> str:
        unit = registers.create_unit(
            session, project, values, user_id=user_id, source="import", batch_id=batch_id
        )
        return unit.id

    def update(self, session, project, key, values, *, user_id, batch_id) -> tuple[str, dict]:
        unit = registers.units_by_label(session, project)[key.casefold()]
        changes = registers.update_unit(
            session, project, unit, values, user_id=user_id, source="import", batch_id=batch_id
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

    def add(self, session, project, values, *, user_id, batch_id, ctx) -> str:
        unit = ctx["units"][values["unit"].casefold()]
        receipt = registers.create_receipt(
            session, project, unit, values, user_id=user_id, source="import", batch_id=batch_id
        )
        return receipt.id

    def update(self, session, project, key, values, *, user_id, batch_id):
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


HANDLERS = {h.kind: h for h in (UnitImport(), ReceiptImport())}


def evaluate(session: Session, batch: ImportBatch) -> list[dict]:
    """What each row would do: add, update, unchanged or error, with the reasons."""
    record = record_type(batch.kind)
    handler = HANDLERS[batch.kind]
    project = session.get(Project, batch.project_id)
    ctx = handler.context(session, project)
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


def apply(session: Session, batch: ImportBatch, *, user_id: str | None) -> dict:
    if batch.status != "preview":
        raise ServiceError("This import has already been applied.")
    record = record_type(batch.kind)
    handler = HANDLERS[batch.kind]
    project = session.get(Project, batch.project_id)
    rows = evaluate(session, batch)
    ctx = handler.context(session, project)
    done = []
    for row in rows:
        if row["action"] not in ("add", "update"):
            continue
        values = {k: registers.from_json(record, k, v) for k, v in row["values"].items()}
        if row["action"] == "add":
            record_id = handler.add(
                session, project, values, user_id=user_id, batch_id=batch.id, ctx=ctx
            )
            done.append(
                {"row": row["row"], "action": "add", "id": record_id, "after": row["values"]}
            )
        else:
            record_id, changes = handler.update(
                session, project, row["key"], values, user_id=user_id, batch_id=batch.id
            )
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
        sheet.append(row)
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
    writer.writerows(rows)
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
