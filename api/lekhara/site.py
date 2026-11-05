"""The site: one daily report a day, the materials on site, and asking the office for more.

- The daily report: the work done, how many workers, any problems, the material used, and up to
  six photos from a phone.
- Stock: what came in (received against a request, or just arrived) less what the daily reports
  say was used. An item can carry a low level, and the page says when it falls below.
- Requests: site asks for an item and quantity, by a date. The office adds the suppliers' quotes,
  picks one, and that becomes a purchase order on the budget. When it arrives, site marks it
  received and it goes into stock.
"""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara import purchases
from lekhara.models import (
    Commitment,
    CostLineRow,
    DailyReport,
    DailyReportPhoto,
    MaterialItem,
    MaterialMove,
    MaterialQuote,
    MaterialRequest,
    Project,
    User,
    utcnow,
)
from lekhara.money import ZERO, rupees
from lekhara.services import ServiceError
from lekhara.storage import Storage

MAX_PHOTOS = 6
MAX_PHOTO_BYTES = 10_000_000
STATUS = {"requested": "Asked for", "ordered": "Ordered", "received": "Received",
          "cancelled": "Cancelled"}  # fmt: skip


def _qty(value, label: str, *, required: bool = True) -> Decimal | None:
    text = str(value if value is not None else "").replace(",", "").strip()
    if not text:
        if required:
            raise ServiceError(f"Enter {label}.")
        return None
    try:
        q = Decimal(text)
    except InvalidOperation:
        raise ServiceError(f"{label.capitalize()} is not a number.") from None
    if q <= 0:
        raise ServiceError(f"{label.capitalize()} should be above zero.")
    return q.quantize(Decimal("0.01"))


def _date(value, label: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ServiceError(f"{label} is not a date.") from None


def _n(q: Decimal) -> str:
    return f"{q.normalize():f}" if q == q.to_integral() else f"{q:.2f}"


# Items and stock


def item_for(session: Session, project: Project, name: str, unit: str | None) -> MaterialItem:
    name = (name or "").strip()
    if not name:
        raise ServiceError("Say which material.")
    found = session.scalars(
        select(MaterialItem).where(
            MaterialItem.project_id == project.id,
            func.lower(MaterialItem.name) == name.lower(),
        )
    ).first()
    if found:
        return found
    item = MaterialItem(
        project_id=project.id, name=name[:120], unit=(unit or "").strip()[:24] or "nos"
    )
    session.add(item)
    session.flush()
    return item


def stock(session: Session, project: Project) -> list[dict]:
    items = list(
        session.scalars(
            select(MaterialItem)
            .where(MaterialItem.project_id == project.id)
            .order_by(MaterialItem.name)
        )
    )
    moves = session.execute(
        select(
            MaterialMove.item_id,
            MaterialMove.kind,
            func.coalesce(func.sum(MaterialMove.quantity), 0),
        )
        .where(MaterialMove.project_id == project.id)
        .group_by(MaterialMove.item_id, MaterialMove.kind)
    ).all()
    totals: dict[str, dict[str, Decimal]] = {}
    for item_id, kind, total in moves:
        totals.setdefault(item_id, {})[kind] = Decimal(total)
    out = []
    for i in items:
        t = totals.get(i.id, {})
        left = t.get("received", ZERO) - t.get("used", ZERO)
        out.append({
            "id": i.id, "name": i.name, "unit": i.unit, "in_stock": _n(left),
            "received": _n(t.get("received", ZERO)), "used": _n(t.get("used", ZERO)),
            "min_level": _n(i.min_level) if i.min_level is not None else None,
            "low": i.min_level is not None and left < i.min_level,
        })  # fmt: skip
    return out


def received(
    session: Session, project: Project, fields: dict, *, as_of: date, user_id: str | None
) -> MaterialMove:
    item = item_for(session, project, fields.get("item"), fields.get("unit"))
    move = MaterialMove(
        project_id=project.id, item_id=item.id, kind="received",
        on=_date(fields.get("on"), "The date") or as_of,
        quantity=_qty(fields.get("quantity"), "how much came in"),
        note=(fields.get("note") or "").strip()[:200] or None, user_id=user_id,
    )  # fmt: skip
    session.add(move)
    session.commit()
    return move


def set_min_level(session: Session, item: MaterialItem, value) -> None:
    item.min_level = _qty(value, "the low level", required=False)
    session.commit()


# The daily report


def _image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "image/heic"
    return None


def save_report(
    session: Session, storage: Storage, project: Project, fields: dict,
    photos: list[tuple[str, bytes]], *, as_of: date, user_id: str | None,
) -> DailyReport:  # fmt: skip
    on = _date(fields.get("on"), "The date") or as_of
    if on > as_of:
        raise ServiceError("A daily report can't be for a day still to come.")
    work = (fields.get("work_done") or "").strip()
    if not work:
        raise ServiceError("Write what work was done today.")
    workers = fields.get("workers")
    try:
        workers = int(str(workers).strip()) if str(workers or "").strip() else None
    except ValueError:
        raise ServiceError("Enter the number of workers as a number.") from None
    report = session.scalars(
        select(DailyReport).where(DailyReport.project_id == project.id, DailyReport.on == on)
    ).first()
    if report is None:
        report = DailyReport(project_id=project.id, on=on, work_done=work, user_id=user_id)
        session.add(report)
        session.flush()
    report.work_done, report.workers = work[:5000], workers
    report.issues = (fields.get("issues") or "").strip()[:3000] or None
    # The material used: what the report says replaces what it said before.
    for old in session.scalars(select(MaterialMove).where(MaterialMove.report_id == report.id)):
        session.delete(old)
    for line in fields.get("used") or []:
        name, qty = (line.get("item") or "").strip(), str(line.get("quantity") or "").strip()
        if not name and not qty:
            continue
        item = item_for(session, project, name, line.get("unit"))
        session.add(MaterialMove(project_id=project.id, item_id=item.id, kind="used", on=on,
                                 quantity=_qty(qty, f"how much {item.name} was used"),
                                 report_id=report.id, user_id=user_id))  # fmt: skip
    have = (
        session.scalar(
            select(func.count())
            .select_from(DailyReportPhoto)
            .where(DailyReportPhoto.report_id == report.id)
        )
        or 0
    )
    photos = [(n, d) for n, d in photos if d]
    if have + len(photos) > MAX_PHOTOS:
        raise ServiceError(f"A day's report can have up to {MAX_PHOTOS} photos.")
    for filename, data in photos:
        kind = _image_type(data)
        if kind is None:
            raise ServiceError(f"{filename} is not a photo. Add JPEG, PNG or HEIC photos.")
        if len(data) > MAX_PHOTO_BYTES:
            raise ServiceError(f"{filename} is over 10 MB.")
        session.add(DailyReportPhoto(project_id=project.id, report_id=report.id,
                                     storage_key=storage.put(data), filename=filename[:200],
                                     content_type=kind))  # fmt: skip
    session.commit()
    return report


def photo(
    session: Session, storage: Storage, report: DailyReport, photo_id: str
) -> tuple[bytes, str]:
    p = session.get(DailyReportPhoto, photo_id)
    if p is None or p.report_id != report.id:
        raise ServiceError("Photo not found.", 404)
    return storage.get(p.storage_key), p.content_type


def site_view(session: Session, project: Project, *, as_of: date, can_report: bool) -> dict:
    reports = list(
        session.scalars(
            select(DailyReport)
            .where(DailyReport.project_id == project.id)
            .order_by(DailyReport.on.desc())
            .limit(14)
        )
    )
    names = {
        u.id: u.name
        for u in session.scalars(
            select(User).where(User.id.in_({r.user_id for r in reports if r.user_id}))
        )
    }
    items = {
        i.id: i
        for i in session.scalars(select(MaterialItem).where(MaterialItem.project_id == project.id))
    }

    def row(r: DailyReport) -> dict:
        used = session.scalars(select(MaterialMove).where(MaterialMove.report_id == r.id))
        pics = session.scalars(select(DailyReportPhoto).where(DailyReportPhoto.report_id == r.id))
        return {
            "id": r.id, "on": r.on.isoformat(), "work_done": r.work_done, "workers": r.workers,
            "issues": r.issues, "by": names.get(r.user_id),
            "used": [{"item": items[m.item_id].name, "unit": items[m.item_id].unit,
                      "quantity": _n(m.quantity)} for m in used],
            "photos": [p.id for p in pics],
        }  # fmt: skip

    today = next((r for r in reports if r.on == as_of), None)
    missed = []
    for back in range(1, 7):
        day = as_of - timedelta(days=back)
        if day.weekday() != 6 and not any(r.on == day for r in reports):
            missed.append(day.isoformat())
    return {
        "can_report": can_report,
        "today": as_of.isoformat(),
        "today_report": row(today) if today else None,
        "reports": [row(r) for r in reports if r.on != as_of],
        "missed": missed[:3],
        "items": [
            {"name": i.name, "unit": i.unit} for i in sorted(items.values(), key=lambda i: i.name)
        ],
    }


# Requests for material


def request(
    session: Session, project: Project, fields: dict, *, as_of: date, user_id: str | None
) -> MaterialRequest:
    item = item_for(session, project, fields.get("item"), fields.get("unit"))
    r = MaterialRequest(
        project_id=project.id, item_id=item.id,
        quantity=_qty(fields.get("quantity"), "how much is needed"),
        needed_by=_date(fields.get("needed_by"), "The date it is needed by"),
        note=(fields.get("note") or "").strip()[:300] or None, requested_by=user_id,
    )  # fmt: skip
    session.add(r)
    session.commit()
    return r


def add_quote(session: Session, r: MaterialRequest, fields: dict) -> MaterialQuote:
    if r.status != "requested":
        raise ServiceError("This request has already been ordered.")
    supplier = (fields.get("supplier") or "").strip()
    if not supplier:
        raise ServiceError("Enter the supplier's name.")
    try:
        rate = rupees(Decimal(str(fields.get("rate") or "").replace(",", "").strip()))
    except InvalidOperation:
        raise ServiceError("Enter the rate for each unit, in rupees.") from None
    if rate <= 0:
        raise ServiceError("Enter the rate for each unit, in rupees.")
    q = MaterialQuote(project_id=r.project_id, request_id=r.id, supplier=supplier[:200], rate=rate)
    session.add(q)
    session.commit()
    return q


def order(
    session: Session, project: Project, r: MaterialRequest, fields: dict, *, as_of: date,
    user_id: str | None,
) -> Commitment:  # fmt: skip
    if r.status != "requested":
        raise ServiceError("This request has already been ordered.")
    q = session.get(MaterialQuote, fields.get("quote_id") or "")
    if q is None or q.request_id != r.id:
        raise ServiceError("Choose one of the quotes.")
    line = fields.get("cost_line") or None
    if not line:
        first = session.scalars(
            select(CostLineRow)
            .where(CostLineRow.project_id == project.id, CostLineRow.category == "construction")
            .order_by(CostLineRow.code)
        ).first()
        if first is None:
            raise ServiceError("Set up the budget first, so the order has a part to count against.")
        line = first.code
    item = session.get(MaterialItem, r.item_id)
    n = session.scalar(
        select(func.count()).select_from(Commitment).where(Commitment.project_id == project.id)
    )
    c = purchases.create_commitment(
        session, project,
        {"reference": f"PO-{(n or 0) + 1:03d}", "supplier": q.supplier, "cost_line": line,
         "amount": rupees(q.rate * r.quantity), "committed_on": as_of,
         "description": f"{_n(r.quantity)} {item.unit} {item.name}"},
        as_of=as_of, user_id=user_id,
    )  # fmt: skip
    q.chosen = True
    r.status, r.commitment_id, r.ordered_at = "ordered", c.id, utcnow()
    session.commit()
    return c


def receive(
    session: Session, r: MaterialRequest, fields: dict, *, as_of: date, user_id: str | None
) -> None:
    if r.status in ("received", "cancelled"):
        raise ServiceError("This request is already closed.")
    qty = _qty(fields.get("quantity"), "how much came in", required=False) or r.quantity
    on = _date(fields.get("on"), "The date") or as_of
    session.add(MaterialMove(project_id=r.project_id, item_id=r.item_id, kind="received", on=on,
                             quantity=qty, request_id=r.id, user_id=user_id))  # fmt: skip
    r.status, r.received_on = "received", on
    session.commit()


def cancel(session: Session, r: MaterialRequest) -> None:
    if r.status != "requested":
        raise ServiceError("Only a request not yet ordered can be cancelled.")
    r.status = "cancelled"
    session.commit()


def materials_view(
    session: Session, project: Project, *, as_of: date, can_ask: bool, can_order: bool
) -> dict:
    items = {
        i.id: i
        for i in session.scalars(select(MaterialItem).where(MaterialItem.project_id == project.id))
    }
    rows = list(
        session.scalars(
            select(MaterialRequest)
            .where(MaterialRequest.project_id == project.id)
            .order_by(MaterialRequest.created_at.desc())
            .limit(40)
        )
    )
    names = {
        u.id: u.name
        for u in session.scalars(
            select(User).where(User.id.in_({r.requested_by for r in rows if r.requested_by}))
        )
    }
    lines = session.scalars(
        select(CostLineRow).where(CostLineRow.project_id == project.id).order_by(CostLineRow.code)
    )

    def req(r: MaterialRequest) -> dict:
        item = items[r.item_id]
        quotes = list(
            session.scalars(
                select(MaterialQuote)
                .where(MaterialQuote.request_id == r.id)
                .order_by(MaterialQuote.rate)
            )
        )
        order_ref = session.get(Commitment, r.commitment_id).reference if r.commitment_id else None
        return {
            "id": r.id, "item": item.name, "unit": item.unit, "quantity": _n(r.quantity),
            "needed_by": r.needed_by.isoformat() if r.needed_by else None,
            "late": bool(r.needed_by and r.needed_by < as_of
                         and r.status in ("requested", "ordered")),
            "note": r.note, "status": r.status, "status_label": STATUS[r.status],
            "by": names.get(r.requested_by), "order": order_ref,
            "received_on": r.received_on.isoformat() if r.received_on else None,
            "quotes": [{"id": q.id, "supplier": q.supplier, "rate": f"{q.rate:.2f}",
                        "total": f"{q.rate * r.quantity:.2f}", "chosen": q.chosen,
                        "cheapest": i == 0} for i, q in enumerate(quotes)],
        }  # fmt: skip

    open_ = [req(r) for r in rows if r.status in ("requested", "ordered")]
    return {
        "can_ask": can_ask,
        "can_order": can_order,
        "open": open_,
        "closed": [req(r) for r in rows if r.status in ("received", "cancelled")][:15],
        "stock": stock(session, project),
        "cost_lines": [{"value": x.code, "label": x.name} for x in lines],
    }
