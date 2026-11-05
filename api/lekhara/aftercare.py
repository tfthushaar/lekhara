"""After handover: snags, defects and buyers' requests, one list for each project.

- A snag is found before possession, at the walk-through, and is put right before the keys.
- A defect is reported by a buyer after possession. Within five years of possession the promoter
  must put it right within 30 days (RERA Act s.14(3)), or the buyer can claim compensation. The
  30 days are worked out for each one, and a late one is shown first.
- A request is anything else a buyer asks for: a document, a change, a question.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara.models import Project, Unit, UnitHandover, UnitIssue, User
from lekhara.rules import KARNATAKA, RulesPack
from lekhara.services import ServiceError

KINDS = {"snag": "Snag", "defect": "Defect", "request": "Buyer's request"}


def _date(value, label: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ServiceError(f"{label} is not a date.") from None


def possession_of(session: Session, unit: Unit) -> date | None:
    h = session.scalars(select(UnitHandover).where(UnitHandover.unit_id == unit.id)).first()
    return h.possession_on if h else None


def add(
    session: Session, project: Project, fields: dict, *, as_of: date, user_id: str | None,
    rules: RulesPack = KARNATAKA,
) -> UnitIssue:  # fmt: skip
    unit = session.get(Unit, fields.get("unit_id") or "")
    if unit is None or unit.project_id != project.id:
        raise ServiceError("Choose the unit.")
    kind = fields.get("kind") or ""
    if kind not in KINDS:
        raise ServiceError("Say whether it is a snag, a defect or a request.")
    title = (fields.get("title") or "").strip()
    if not title:
        raise ServiceError("Say what it is, in a few words.")
    reported = _date(fields.get("reported_on"), "The date") or as_of
    due = None
    if kind == "defect":
        due = reported + timedelta(days=int(rules.value("rera.defect_rectify_days", reported)))
    issue = UnitIssue(
        project_id=project.id, unit_id=unit.id, kind=kind, title=title[:200],
        detail=(fields.get("detail") or "").strip()[:3000] or None, reported_on=reported,
        due_on=due, user_id=user_id,
    )  # fmt: skip
    session.add(issue)
    session.commit()
    return issue


def close(session: Session, issue: UnitIssue, fields: dict, *, as_of: date) -> None:
    if issue.status == "done":
        raise ServiceError("This is already done.")
    issue.status = "done"
    issue.done_on = _date(fields.get("done_on"), "The date") or as_of
    issue.reply = (fields.get("reply") or "").strip()[:3000] or None
    session.commit()


def reopen(session: Session, issue: UnitIssue) -> None:
    issue.status, issue.done_on = "open", None
    session.commit()


def _row(session: Session, i: UnitIssue, units: dict, names: dict, as_of: date,
         rules: RulesPack) -> dict:  # fmt: skip
    unit = units[i.unit_id]
    note = None
    if i.kind == "defect":
        possession = possession_of(session, unit)
        years = int(rules.value("rera.defect_liability_years", i.reported_on))
        if possession is None:
            note = "Possession is not recorded for this unit."
        elif i.reported_on > possession.replace(year=possession.year + years):
            note = f"Reported more than {years} years after possession."
    return {
        "id": i.id, "unit": unit.label, "unit_id": unit.id, "buyer": unit.buyer_name,
        "kind": i.kind, "kind_label": KINDS[i.kind], "title": i.title, "detail": i.detail,
        "reported_on": i.reported_on.isoformat(),
        "due_on": i.due_on.isoformat() if i.due_on else None,
        "late": bool(i.due_on and i.status == "open" and i.due_on < as_of),
        "days_left": (i.due_on - as_of).days if i.due_on and i.status == "open" else None,
        "status": i.status, "done_on": i.done_on.isoformat() if i.done_on else None,
        "reply": i.reply, "by": names.get(i.user_id), "note": note,
    }  # fmt: skip


def view(
    session: Session, project: Project, *, as_of: date, can_edit: bool,
    rules: RulesPack = KARNATAKA,
) -> dict:  # fmt: skip
    issues = list(
        session.scalars(
            select(UnitIssue)
            .where(UnitIssue.project_id == project.id)
            .order_by(UnitIssue.reported_on.desc())
        )
    )
    units = {
        u.id: u
        for u in session.scalars(
            select(Unit).where(Unit.project_id == project.id).order_by(Unit.tower, Unit.label)
        )
    }
    names = {
        u.id: u.name
        for u in session.scalars(
            select(User).where(User.id.in_({i.user_id for i in issues if i.user_id}))
        )
    }
    rows = [_row(session, i, units, names, as_of, rules) for i in issues]
    open_ = [r for r in rows if r["status"] == "open"]
    open_.sort(key=lambda r: (not r["late"], r["due_on"] or "9999", r["reported_on"]))
    return {
        "can_edit": can_edit,
        "open": open_,
        "done": [r for r in rows if r["status"] == "done"][:30],
        "late": sum(1 for r in open_ if r["late"]),
        "kinds": [{"value": k, "label": v} for k, v in KINDS.items()],
        "units": [
            {"id": u.id, "label": u.label, "buyer": u.buyer_name}
            for u in units.values()
            if u.booked
        ],
        "defect_days": int(rules.value("rera.defect_rectify_days", as_of)),
    }
