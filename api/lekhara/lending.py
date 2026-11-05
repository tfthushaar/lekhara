"""Cash: what is coming in and going out over the next three months, and the project's loans.

The forecast counts only what is already known, and guesses nothing:
- in: what buyers owe on demands already raised (an overdue amount counts this month), and loan
  money planned to be drawn;
- out: bills not yet paid, each in the month it should be paid by, and loan repayments and
  interest planned;
- beside it, what can be drawn from the RERA account today.

A loan has its sanctioned amount, what has been drawn and repaid (a date still to come is a
planned payment), and the lender's conditions, each with the date it is due.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara import contractors
from lekhara.models import (
    Bill,
    DemandRow,
    Loan,
    LoanCondition,
    LoanMove,
    Project,
    Receipt,
    Unit,
)
from lekhara.money import ZERO, rupees
from lekhara.services import ServiceError

KINDS = {"drawdown": "Drawn", "repayment": "Repaid", "interest": "Interest paid"}


def _money(value, label: str) -> Decimal:
    text = str(value if value is not None else "").replace(",", "").replace("₹", "").strip()
    lakh = text.lower().removesuffix("lakh").strip() if text.lower().endswith("lakh") else None
    crore = text.lower().removesuffix("crore").strip() if text.lower().endswith("crore") else None
    try:
        if lakh is not None:
            amount = Decimal(lakh) * 100000
        elif crore is not None:
            amount = Decimal(crore) * 10000000
        else:
            amount = Decimal(text)
    except InvalidOperation:
        raise ServiceError(f"Enter {label} in rupees, or as 50 lakh or 2 crore.") from None
    if amount <= 0:
        raise ServiceError(f"Enter {label}.")
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


def add_loan(session: Session, project: Project, fields: dict) -> Loan:
    lender = (fields.get("lender") or "").strip()
    if not lender:
        raise ServiceError("Enter the lender's name.")
    rate = str(fields.get("rate_pct") or "").strip().rstrip("%")
    try:
        rate_pct = Decimal(rate) if rate else None
    except InvalidOperation:
        raise ServiceError("Enter the interest rate as a number, like 11.5.") from None
    loan = Loan(
        project_id=project.id, lender=lender[:200],
        sanctioned=_money(fields.get("sanctioned"), "the amount sanctioned"),
        rate_pct=rate_pct, sanctioned_on=_date(fields.get("sanctioned_on"), "The sanction date"),
        note=(fields.get("note") or "").strip()[:300] or None,
    )  # fmt: skip
    session.add(loan)
    session.commit()
    return loan


def _sums(session: Session, loan: Loan, as_of: date) -> dict[str, Decimal]:
    rows = session.execute(
        select(LoanMove.kind, func.coalesce(func.sum(LoanMove.amount), 0))
        .where(LoanMove.loan_id == loan.id, LoanMove.on <= as_of)
        .group_by(LoanMove.kind)
    ).all()
    return {k: Decimal(v) for k, v in rows}


def add_move(session: Session, loan: Loan, fields: dict, *, as_of: date) -> LoanMove:
    kind = fields.get("kind") or ""
    if kind not in KINDS:
        raise ServiceError("Say whether money was drawn, repaid or paid as interest.")
    amount = _money(fields.get("amount"), "the amount")
    on = _date(fields.get("on"), "The date") or as_of
    if kind == "drawdown":
        drawn = session.scalar(
            select(func.coalesce(func.sum(LoanMove.amount), 0)).where(
                LoanMove.loan_id == loan.id, LoanMove.kind == "drawdown"
            )
        )
        drawn = Decimal(drawn or 0)
        if drawn + amount > loan.sanctioned:
            raise ServiceError(f"That is more than the {loan.sanctioned:,.0f} sanctioned.")
    move = LoanMove(project_id=loan.project_id, loan_id=loan.id, kind=kind, on=on, amount=amount,
                    note=(fields.get("note") or "").strip()[:200] or None)  # fmt: skip
    session.add(move)
    session.commit()
    return move


def add_condition(session: Session, loan: Loan, fields: dict) -> LoanCondition:
    text = (fields.get("text") or "").strip()
    if not text:
        raise ServiceError("Write what the lender needs.")
    c = LoanCondition(project_id=loan.project_id, loan_id=loan.id, text=text[:300],
                      due_on=_date(fields.get("due_on"), "The due date"))  # fmt: skip
    session.add(c)
    session.commit()
    return c


def meet_condition(session: Session, c: LoanCondition, *, as_of: date) -> None:
    c.met_on = as_of
    session.commit()


def _month(d: date) -> tuple[int, int]:
    return d.year, d.month


def _months(as_of: date, n: int = 3) -> list[tuple[int, int]]:
    out, y, m = [], as_of.year, as_of.month
    for _ in range(n):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def forecast(session: Session, project: Project, *, as_of: date) -> dict:
    months = _months(as_of)
    first = months[0]
    buckets = {k: {"in": ZERO, "out": ZERO} for k in months}

    def put(on: date, key: str, amount: Decimal) -> None:
        slot = max(_month(on), first)
        if slot in buckets:
            buckets[slot][key] += amount

    # Money in: each buyer's balance on demands raised, by the last demand's due date.
    demanded = session.execute(
        select(
            DemandRow.unit_id,
            func.sum(DemandRow.amount + DemandRow.gst),
            func.max(DemandRow.due_on),
        )
        .where(DemandRow.project_id == project.id, DemandRow.cancellation_id.is_(None))
        .group_by(DemandRow.unit_id)
    ).all()
    paid = dict(
        session.execute(
            select(Receipt.unit_id, func.sum(Receipt.amount + Receipt.tds_deducted))
            .where(Receipt.project_id == project.id, Receipt.cancellation_id.is_(None))
            .group_by(Receipt.unit_id)
        ).all()
    )
    for unit_id, total, due in demanded:
        # A sum over an expression comes back in paise; over one column, already in rupees.
        owed = Decimal(total or 0) / 100 - Decimal(paid.get(unit_id) or 0) / 100
        if owed > 0 and due:
            put(due, "in", owed)
    # Money out: unpaid bills by when they should be paid.
    for b in session.scalars(
        select(Bill).where(
            Bill.project_id == project.id, Bill.paid_on.is_(None), Bill.excluded.is_(False)
        )  # fmt: skip
    ):
        put(contractors.pay_by(session, b), "out", contractors.payable(session, b))
    # Planned loan money.
    for m in session.scalars(
        select(LoanMove).where(LoanMove.project_id == project.id, LoanMove.on > as_of)
    ):
        put(m.on, "in" if m.kind == "drawdown" else "out", m.amount)
    rows = []
    for y, m in months:
        b = buckets[(y, m)]
        rows.append({
            "month": f"{y}-{m:02d}", "in": f"{b['in']:.2f}", "out": f"{b['out']:.2f}",
            "net": f"{b['in'] - b['out']:.2f}",
        })  # fmt: skip
    return {"months": rows}


def cash_view(
    session: Session, project: Project, *, as_of: date, drawable: Decimal, can_edit: bool
) -> dict:
    loans = []
    for loan in session.scalars(
        select(Loan).where(Loan.project_id == project.id).order_by(Loan.created_at)
    ):
        s = _sums(session, loan, as_of)
        drawn, repaid = s.get("drawdown", ZERO), s.get("repayment", ZERO)
        moves = list(
            session.scalars(
                select(LoanMove).where(LoanMove.loan_id == loan.id).order_by(LoanMove.on.desc())
            )
        )
        planned = [m for m in moves if m.on > as_of]
        conditions = list(
            session.scalars(
                select(LoanCondition)
                .where(LoanCondition.loan_id == loan.id)
                .order_by(LoanCondition.met_on.is_not(None), LoanCondition.due_on)
            )
        )
        loans.append({
            "id": loan.id, "lender": loan.lender, "sanctioned": f"{loan.sanctioned:.2f}",
            "rate_pct": f"{loan.rate_pct}" if loan.rate_pct is not None else None,
            "drawn": f"{drawn:.2f}", "repaid": f"{repaid:.2f}",
            "outstanding": f"{drawn - repaid:.2f}",
            "can_draw": f"{max(loan.sanctioned - drawn, ZERO):.2f}",
            "interest_paid": f"{s.get('interest', ZERO):.2f}",
            "next": {"on": planned[-1].on.isoformat(), "kind": KINDS[planned[-1].kind],
                     "amount": f"{planned[-1].amount:.2f}"} if planned else None,
            "moves": [{"on": m.on.isoformat(), "kind": m.kind, "kind_label": KINDS[m.kind],
                       "amount": f"{m.amount:.2f}", "note": m.note, "planned": m.on > as_of}
                      for m in moves[:20]],
            "conditions": [{"id": c.id, "text": c.text,
                            "due_on": c.due_on.isoformat() if c.due_on else None,
                            "met_on": c.met_on.isoformat() if c.met_on else None,
                            "late": bool(c.due_on and not c.met_on and c.due_on < as_of)}
                           for c in conditions],
        })  # fmt: skip
    return {
        "can_edit": can_edit,
        "drawable": f"{drawable:.2f}",
        "forecast": forecast(session, project, as_of=as_of)["months"],
        "loans": loans,
        "kinds": [{"value": k, "label": v} for k, v in KINDS.items()],
    }


def due_conditions(session: Session, project_ids: list[str], as_of: date, days: int = 14) -> int:
    from datetime import timedelta

    return (
        session.scalar(
            select(func.count())
            .select_from(LoanCondition)
            .where(
                LoanCondition.project_id.in_(project_ids),
                LoanCondition.met_on.is_(None),
                LoanCondition.due_on <= as_of + timedelta(days=days),
            )
        )
        or 0
    )


def unit_buyer(session: Session, unit_id: str) -> str | None:
    u = session.get(Unit, unit_id)
    return u.buyer_name if u else None
