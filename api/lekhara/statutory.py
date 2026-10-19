"""Approvals and K-RERA filings: added, changed, imported and exported like every other record,
with a history of every change.

Approvals are the project's permissions, consents and no-objection certificates: when each was
applied for, granted, and until when it holds. Filings are the quarterly progress reports and
annual audit reports filed with K-RERA; they clear the matching deadlines on Today.
"""

import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara.models import Approval, Filing, Project
from lekhara.records import APPROVALS, FILINGS
from lekhara.registers import log_change, to_json
from lekhara.services import ServiceError

APPROVAL_KEYS = tuple(f.key for f in APPROVALS.fields)
FILING_KEYS = tuple(f.key for f in FILINGS.fields)
FILING_LABEL = dict(FILINGS.field("kind").choices)


def _fold(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def _changes(before: dict, after: dict) -> dict:
    return {
        k: [to_json(before.get(k)), to_json(v)]
        for k, v in after.items()
        if to_json(before.get(k)) != to_json(v)
    }


# Approvals

STANDARD_APPROVALS = (
    ("Land conversion (DC conversion)", "Deputy Commissioner"),
    ("Building plan sanction", "Planning authority"),
    ("Commencement certificate", "Planning authority"),
    ("Environmental clearance", "SEIAA, Karnataka"),
    ("Consent to establish", "Karnataka State Pollution Control Board"),
    ("Fire NOC (provisional)", "Karnataka State Fire and Emergency Services"),
    ("Height clearance", "Airports Authority of India"),
    ("Power supply sanction", "BESCOM"),
    ("Water supply and sewerage", "BWSSB"),
    ("Fire NOC (final)", "Karnataka State Fire and Emergency Services"),
    ("Consent to operate", "Karnataka State Pollution Control Board"),
    ("Occupancy certificate", "Planning authority"),
)

STATUS_TEXT = {
    "lapsed": "Lapsed",
    "lapsing": "Lapsing soon",
    "granted": "Granted",
    "applied": "Applied for",
    "to_apply": "Not applied for",
}


def approvals_of(session: Session, project: Project) -> list[Approval]:
    return list(
        session.scalars(
            select(Approval).where(Approval.project_id == project.id).order_by(Approval.name)
        )
    )


def approval_values(a: Approval) -> dict:
    return {k: getattr(a, k) for k in APPROVAL_KEYS}


def approval_status(a: Approval, *, as_of: date, notice_days: int) -> str:
    if a.valid_until is not None and a.granted_on is not None:
        if a.valid_until < as_of:
            return "lapsed"
        if a.valid_until <= as_of + timedelta(days=notice_days):
            return "lapsing"
    if a.granted_on is not None:
        return "granted"
    if a.applied_on is not None:
        return "applied"
    return "to_apply"


def find_approval(
    session: Session, project: Project, name: str | None, *, exclude_id: str | None = None
) -> Approval | None:
    for a in approvals_of(session, project):
        if a.id != exclude_id and _fold(a.name) == _fold(name):
            return a
    return None


def check_approval(values: dict, *, as_of: date, existing: Approval | None = None) -> list[str]:
    merged = {**(approval_values(existing) if existing else {}), **values}
    problems = []
    if not (merged.get("name") or "").strip():
        problems.append("Enter what the approval is.")
    applied, granted, until = (
        merged.get("applied_on"),
        merged.get("granted_on"),
        merged.get("valid_until"),
    )
    if applied and applied > as_of:
        problems.append("The application date cannot be in the future.")
    if granted and granted > as_of:
        problems.append("The date it was granted cannot be in the future.")
    if applied and granted and granted < applied:
        problems.append("It cannot have been granted before it was applied for.")
    if until and not granted:
        problems.append("Enter when it was granted, since it has a validity.")
    if until and granted and until <= granted:
        problems.append("It should be valid until a date after it was granted.")
    return problems


def _clean_approval(values: dict) -> dict:
    out = {}
    for key, value in values.items():
        if key in ("name", "authority", "reference", "note") and value is not None:
            limit = 500 if key == "note" else 200
            value = str(value).strip()[:limit] or None
        out[key] = value
    return out


def create_approval(
    session: Session,
    project: Project,
    values: dict,
    *,
    as_of: date,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> Approval:
    problems = check_approval(values, as_of=as_of)
    if problems:
        raise ServiceError(" ".join(problems))
    values = _clean_approval(values)
    if find_approval(session, project, values["name"]):
        raise ServiceError(f"{values['name']} is already in the list.")
    a = Approval(project_id=project.id, **{k: v for k, v in values.items() if k in APPROVAL_KEYS})
    session.add(a)
    session.flush()
    log_change(
        session,
        project,
        "approval",
        a.id,
        "created",
        {k: [None, to_json(v)] for k, v in approval_values(a).items() if v is not None},
        user_id=user_id,
        source=source,
        batch_id=batch_id,
    )
    return a


def update_approval(
    session: Session,
    project: Project,
    a: Approval,
    values: dict,
    *,
    as_of: date,
    user_id: str | None,
    clear: tuple[str, ...] = (),
    source: str = "typed",
    batch_id: str | None = None,
) -> dict:
    """`values` sets fields; `clear` empties the optional fields named in it."""
    wanted = {**values, **{k: None for k in clear if k in APPROVAL_KEYS and k != "name"}}
    problems = check_approval(wanted, as_of=as_of, existing=a)
    if problems:
        raise ServiceError(" ".join(problems))
    wanted = _clean_approval(wanted)
    if wanted.get("name") and find_approval(session, project, wanted["name"], exclude_id=a.id):
        raise ServiceError(f"{wanted['name']} is already in the list.")
    before = approval_values(a)
    for key, value in wanted.items():
        if key in APPROVAL_KEYS:
            setattr(a, key, value)
    changes = _changes(before, approval_values(a))
    if changes:
        log_change(
            session,
            project,
            "approval",
            a.id,
            "updated",
            changes,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
    return changes


def delete_approval(session: Session, project: Project, a: Approval, *, user_id: str | None):
    log_change(
        session,
        project,
        "approval",
        a.id,
        "deleted",
        {k: [to_json(v), None] for k, v in approval_values(a).items() if v is not None},
        user_id=user_id,
        source="typed",
    )
    session.delete(a)


def add_standard_approvals(
    session: Session, project: Project, *, as_of: date, user_id: str | None
) -> int:
    added = 0
    for name, authority in STANDARD_APPROVALS:
        if find_approval(session, project, name) is None:
            create_approval(
                session,
                project,
                {"name": name, "authority": authority},
                as_of=as_of,
                user_id=user_id,
            )
            added += 1
    return added


# K-RERA filings

_QUARTER_ENDS = {(3, 31), (6, 30), (9, 30), (12, 31)}


def filings_of(session: Session, project: Project) -> list[Filing]:
    return list(
        session.scalars(
            select(Filing)
            .where(Filing.project_id == project.id)
            .order_by(Filing.period_end.desc(), Filing.kind)
        )
    )


def filing_values(f: Filing) -> dict:
    return {k: getattr(f, k) for k in FILING_KEYS}


def find_filing(
    session: Session, project: Project, kind: str, period_end: date, *, exclude_id=None
) -> Filing | None:
    return session.scalars(
        select(Filing).where(
            Filing.project_id == project.id,
            Filing.kind == kind,
            Filing.period_end == period_end,
            Filing.id != (exclude_id or ""),
        )
    ).first()


def check_filing(values: dict, *, as_of: date, existing: Filing | None = None) -> list[str]:
    merged = {**(filing_values(existing) if existing else {}), **values}
    problems = []
    kind, end, filed = merged.get("kind"), merged.get("period_end"), merged.get("filed_on")
    if kind not in FILING_LABEL:
        problems.append("Choose whether it is a quarterly progress report or an annual audit.")
    if end is None:
        problems.append("Enter the last day of the period it covers.")
    if filed is None:
        problems.append("Enter the date it was filed.")
    if problems:
        return problems
    if kind == "qpr" and (end.month, end.day) not in _QUARTER_ENDS:
        problems.append(
            "A quarterly report covers a quarter ending on 31 March, 30 June, 30 September or "
            "31 December."
        )
    if kind == "annual_audit" and (end.month, end.day) != (3, 31):
        problems.append("An annual audit covers a financial year ending on 31 March.")
    if filed > as_of:
        problems.append("The filing date cannot be in the future.")
    if filed < end:
        problems.append("It cannot have been filed before the period it covers ended.")
    return problems


def create_filing(
    session: Session,
    project: Project,
    values: dict,
    *,
    as_of: date,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> Filing:
    problems = check_filing(values, as_of=as_of)
    if problems:
        raise ServiceError(" ".join(problems))
    if find_filing(session, project, values["kind"], values["period_end"]):
        label = FILING_LABEL[values["kind"]].lower()
        raise ServiceError(f"The {label} for that period is already recorded.")
    f = Filing(
        project_id=project.id,
        kind=values["kind"],
        period_end=values["period_end"],
        filed_on=values["filed_on"],
        reference=(values.get("reference") or "").strip()[:200] or None,
    )
    session.add(f)
    session.flush()
    log_change(
        session,
        project,
        "filing",
        f.id,
        "created",
        {k: [None, to_json(v)] for k, v in filing_values(f).items() if v is not None},
        user_id=user_id,
        source=source,
        batch_id=batch_id,
    )
    return f


def update_filing(
    session: Session,
    project: Project,
    f: Filing,
    values: dict,
    *,
    as_of: date,
    user_id: str | None,
    source: str = "typed",
    batch_id: str | None = None,
) -> dict:
    problems = check_filing(values, as_of=as_of, existing=f)
    if problems:
        raise ServiceError(" ".join(problems))
    merged = {**filing_values(f), **values}
    if find_filing(session, project, merged["kind"], merged["period_end"], exclude_id=f.id):
        raise ServiceError("A filing for that period is already recorded.")
    before = filing_values(f)
    for key in ("kind", "period_end", "filed_on"):
        if values.get(key) is not None:
            setattr(f, key, values[key])
    if "reference" in values:
        f.reference = (values["reference"] or "").strip()[:200] or None
    changes = _changes(before, filing_values(f))
    if changes:
        log_change(
            session,
            project,
            "filing",
            f.id,
            "updated",
            changes,
            user_id=user_id,
            source=source,
            batch_id=batch_id,
        )
    return changes


def delete_filing(session: Session, project: Project, f: Filing, *, user_id: str | None) -> None:
    log_change(
        session,
        project,
        "filing",
        f.id,
        "deleted",
        {k: [to_json(v), None] for k, v in filing_values(f).items() if v is not None},
        user_id=user_id,
        source="typed",
    )
    session.delete(f)
