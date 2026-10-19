"""What the API returns for landowners and their payments, approvals, K-RERA filings, and
records edited as a table."""

import json
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from lekhara import imports, registers, statutory
from lekhara.engines.obligations import _month_end_after, _quarter_ends
from lekhara.engines.tax import LandownerPayment, financial_year, landowner_tds_shortfalls
from lekhara.models import ChangeEntry, Landowner, Project
from lekhara.records import APPROVALS, FILINGS, LANDOWNER_PAYMENTS, RECORD_TYPES
from lekhara.rules import KARNATAKA, RulesPack

ZERO = Decimal("0")


def _m(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _d(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def history_rows(
    changes: list[ChangeEntry],
    names: dict[str, str],
    labels: dict[str, str],
    subjects: dict[str, str] | None = None,
) -> list[dict]:
    return [
        {
            "at": c.at.replace(microsecond=0).isoformat(),
            "action": c.action,
            "source": c.source,
            "by": names.get(c.user_id, "Lekhara"),
            "subject": (subjects or {}).get(c.record_type),
            "changes": [
                {"field": labels.get(k, k), "before": b, "after": a}
                for k, (b, a) in json.loads(c.changes).items()
            ],
        }
        for c in changes
    ]


def _source(ref: str | None) -> str:
    if ref and ref.startswith("tally:"):
        return "tally"
    if ref and ref.startswith("import:"):
        return "import"
    return "typed"


# Landowners


def landowner_detail(
    session: Session,
    owner: Landowner,
    project: Project,
    names: dict[str, str],
    *,
    can_edit: bool,
    rules: RulesPack = KARNATAKA,
) -> dict:
    payments = sorted(owner.payments, key=lambda p: (p.paid_on, p.id), reverse=True)
    checked = [
        LandownerPayment(owner.name, p.amount, p.paid_on, p.tds_deducted, p.monetary_consideration)
        for p in payments
    ]
    short = {id(s.payment): s.short for s in landowner_tds_shortfalls(checked, rules=rules)}
    shortfalls = {
        p.id: short[id(c)] for p, c in zip(payments, checked, strict=True) if id(c) in short
    }
    consideration = [p for p in payments if p.monetary_consideration]
    deposits = [p for p in payments if not p.monetary_consideration]
    labels = {f.key: f.label for f in LANDOWNER_PAYMENTS.fields} | {
        "name": "Name",
        "share_type": "Share of",
        "share_pct": "Share (per cent)",
        "refundable_deposit": "Refundable deposit",
        "pan": "PAN",
    }
    changes = registers.landowner_history(session, owner)
    return {
        "id": owner.id,
        "project_id": project.id,
        "project_name": project.name,
        "can_edit": can_edit,
        "name": owner.name,
        "pan": owner.pan,
        "share_type": owner.share_type,
        "share_pct": _m(owner.share_pct),
        "refundable_deposit": _m(owner.refundable_deposit),
        "totals": {
            "consideration": _m(sum((p.amount for p in consideration), ZERO)),
            "tds": _m(sum((p.tds_deducted for p in payments), ZERO)),
            "deposits": _m(sum((p.amount for p in deposits), ZERO)),
            "tds_short": _m(sum(shortfalls.values(), ZERO)),
        },
        "payments": [
            {
                "id": p.id,
                "paid_on": _d(p.paid_on),
                "amount": _m(p.amount),
                "tds_deducted": _m(p.tds_deducted),
                "deposit": not p.monetary_consideration,
                "reference": p.note,
                "source": _source(p.source_ref),
                "tds_short": _m(shortfalls.get(p.id)),
            }
            for p in payments
        ],
        "history": history_rows(changes, names, labels, {"landowner_payment": "Payment"}),
    }


# Approvals


def approvals_view(
    session: Session,
    project: Project,
    names_for,
    *,
    can_edit: bool,
    as_of: date,
    rules: RulesPack = KARNATAKA,
) -> dict:
    notice = rules.value("approvals.renewal_notice_days", as_of)
    rows = statutory.approvals_of(session, project)
    labels = {f.key: f.label for f in APPROVALS.fields}
    order = {"lapsed": 0, "lapsing": 1, "applied": 2, "to_apply": 3, "granted": 4}
    items = []
    for a in rows:
        status = statutory.approval_status(a, as_of=as_of, notice_days=notice)
        changes = registers.history(session, "approval", a.id)
        items.append(
            {
                "id": a.id,
                "name": a.name,
                "authority": a.authority,
                "reference": a.reference,
                "applied_on": _d(a.applied_on),
                "granted_on": _d(a.granted_on),
                "valid_until": _d(a.valid_until),
                "note": a.note,
                "status": status,
                "status_text": statutory.STATUS_TEXT[status],
                "days_left": (a.valid_until - as_of).days if a.valid_until else None,
                "history": history_rows(changes, names_for(changes), labels),
            }
        )
    items.sort(key=lambda x: (order[x["status"]], x["valid_until"] or "9999", x["name"]))
    counts = {k: sum(1 for x in items if x["status"] == k) for k in order}
    return {
        "project_id": project.id,
        "can_edit": can_edit,
        "approvals": items,
        "counts": counts,
        "standard_missing": sum(
            1
            for name, _ in statutory.STANDARD_APPROVALS
            if statutory.find_approval(session, project, name) is None
        ),
    }


# K-RERA filings


def krera_view(
    session: Session,
    project: Project,
    names_for,
    *,
    can_edit: bool,
    as_of: date,
    rules: RulesPack = KARNATAKA,
) -> dict:
    due_days = rules.value("krera.qpr_due_days", as_of)
    months = rules.value("krera.annual_audit_months", as_of)
    filings = statutory.filings_of(session, project)
    by_key = {(f.kind, f.period_end): f for f in filings}
    labels = {f.key: f.label for f in FILINGS.fields}

    def filing(f) -> dict | None:
        if f is None:
            return None
        changes = registers.history(session, "filing", f.id)
        return {
            "id": f.id,
            "filed_on": _d(f.filed_on),
            "reference": f.reference,
            "history": history_rows(changes, names_for(changes), labels),
        }

    def state(due: date, period_end: date, f) -> str:
        if f is not None:
            return "filed"
        if period_end > as_of:
            return "open"
        return "late" if due < as_of else "due"

    quarters = []
    for qe in reversed(_quarter_ends(project.registered_on, as_of + timedelta(days=92))):
        due = qe + timedelta(days=due_days)
        f = by_key.get(("qpr", qe))
        quarters.append(
            {
                "period_end": _d(qe),
                "period_start": _d(_quarter_start(qe)),
                "due_on": _d(due),
                "state": state(due, qe, f),
                "filing": filing(f),
            }
        )
    audits = []
    fy_start, _ = financial_year(as_of)
    year_end = fy_start - timedelta(days=1)
    while year_end > project.registered_on:
        due = _month_end_after(year_end, months)
        f = by_key.get(("annual_audit", year_end))
        audits.append(
            {
                "period_end": _d(year_end),
                "period_start": _d(date(year_end.year - 1, 4, 1)),
                "due_on": _d(due),
                "state": state(due, year_end, f),
                "filing": filing(f),
            }
        )
        year_end = date(year_end.year - 1, 3, 31)
    return {
        "project_id": project.id,
        "can_edit": can_edit,
        "registered_on": _d(project.registered_on),
        "quarters": quarters,
        "audits": audits,
        "qpr_due_days": due_days,
        "audit_months": months,
    }


def _quarter_start(qe: date) -> date:
    return date(qe.year, qe.month - 2, 1)


# Editing records as a table

LOCKED = {
    "units": ("label",),
    "suppliers": ("name",),
    "bills": ("supplier", "bill_no"),
    "commitments": ("reference",),
    "approvals": ("name",),
}
TABLE_PAGE = 50


def _cell_text(field, value) -> str:
    if value in (None, ""):
        return ""
    if field.kind == "bool":
        return "Yes" if value is True or str(value).casefold() in ("true", "yes") else "No"
    if field.kind == "money":
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
        return f"{amount:f}".removesuffix(".00")
    return str(value)


def table_view(session: Session, project: Project, kind: str, *, page: int) -> dict:
    record = RECORD_TYPES[kind]
    rows = imports.HANDLERS[kind].export_rows(session, project, record)
    pages = max(1, -(-len(rows) // TABLE_PAGE))
    page = min(max(page, 1), pages)
    shown = rows[(page - 1) * TABLE_PAGE : page * TABLE_PAGE]
    return {
        "project_id": project.id,
        "project_name": project.name,
        "kind": kind,
        "title": record.title,
        "page": page,
        "pages": pages,
        "total": len(rows),
        "fields": [
            {
                "key": f.key,
                "label": f.label,
                "kind": f.kind,
                "locked": f.key in LOCKED[kind],
                "choices": [{"value": label, "label": label} for _, label in f.choices],
            }
            for f in record.fields
        ],
        "rows": [
            [_cell_text(f, v) for f, v in zip(record.fields, row, strict=True)] for row in shown
        ],
    }
