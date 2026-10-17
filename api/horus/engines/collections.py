"""Collections engine: what buyers have been billed, what they paid, and what is next.

A payment plan is a list of milestones. Each is a share of the agreement value
and is triggered by booking, by the agreement, by certified progress reaching a
level, or by possession. When the architect's certificate shows progress
reaching a milestone, the demands for every booked unit are ready to raise.

Receipts are matched to each buyer's demands in order. A demand unpaid after its
due date is overdue, and interest runs on the unpaid part.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from horus.money import ZERO, rupees
from horus.rules import RulesPack


class Trigger(StrEnum):
    BOOKING = "booking"
    AGREEMENT = "agreement"
    PROGRESS = "progress"
    POSSESSION = "possession"


@dataclass(frozen=True)
class Milestone:
    id: str
    sequence: int
    name: str
    share_pct: Decimal
    trigger: Trigger
    progress_pct: Decimal | None = None
    due_days: int = 15


@dataclass(frozen=True)
class BookedUnit:
    id: str
    label: str
    buyer: str | None
    agreement_value: Decimal
    booked_on: date


@dataclass(frozen=True)
class Demand:
    id: str
    unit_id: str
    milestone_id: str
    amount: Decimal
    gst: Decimal
    raised_on: date
    due_on: date

    @property
    def total(self) -> Decimal:
        return self.amount + self.gst


@dataclass(frozen=True)
class Payment:
    unit_id: str
    amount: Decimal
    on: date
    tds: Decimal = ZERO


@dataclass(frozen=True)
class DemandState:
    demand: Demand
    paid: Decimal
    outstanding: Decimal
    overdue: bool
    days_overdue: int
    interest: Decimal


@dataclass(frozen=True)
class UnitAccount:
    unit: BookedUnit
    billed: Decimal
    received: Decimal
    tds: Decimal
    outstanding: Decimal
    overdue: Decimal
    interest: Decimal
    demands: tuple[DemandState, ...]


@dataclass(frozen=True)
class ReadyToRaise:
    milestone: Milestone
    unit_ids: tuple[str, ...]
    amount: Decimal
    gst: Decimal
    reason: str


@dataclass(frozen=True)
class MilestoneStatus:
    milestone: Milestone
    reached: bool
    raised_units: int
    billed: Decimal


@dataclass(frozen=True)
class DepositCheck:
    month_end: date
    receipts: Decimal
    required: Decimal
    deposits: Decimal
    shortfall: Decimal


@dataclass(frozen=True)
class CollectionsPosition:
    as_of: date
    billed: Decimal
    received: Decimal
    outstanding: Decimal
    overdue: Decimal
    overdue_buyers: int
    interest: Decimal
    accounts: tuple[UnitAccount, ...]
    ready: tuple[ReadyToRaise, ...]
    milestones: tuple[MilestoneStatus, ...]
    deposit_checks: tuple[DepositCheck, ...] = field(default_factory=tuple)


def milestone_reached(
    m: Milestone,
    *,
    certified_progress_pct: Decimal | None,
    possession_given: bool,
) -> bool:
    if m.trigger in (Trigger.BOOKING, Trigger.AGREEMENT):
        return True
    if m.trigger == Trigger.POSSESSION:
        return possession_given
    return (
        certified_progress_pct is not None
        and m.progress_pct is not None
        and certified_progress_pct >= m.progress_pct
    )


def _allocate(
    demands: list[Demand], payments: list[Payment], as_of: date, interest_rate: Decimal
) -> list[DemandState]:
    """Match payments to demands in order. Interest runs on the unpaid part since the due date."""
    # TDS a buyer deducts and deposits for the developer counts as paid.
    remaining = sum((p.amount + p.tds for p in payments if p.on <= as_of), ZERO)
    states = []
    for d in sorted(demands, key=lambda d: (d.raised_on, d.due_on)):
        if d.raised_on > as_of:
            continue
        paid = min(remaining, d.total)
        remaining -= paid
        outstanding = d.total - paid
        overdue = outstanding > 0 and d.due_on < as_of
        days = (as_of - d.due_on).days if overdue else 0
        interest = rupees(outstanding * interest_rate * days / 365) if overdue else ZERO
        states.append(DemandState(d, paid, outstanding, overdue, days, interest))
    return states


def collections_position(
    *,
    milestones: list[Milestone],
    units: list[BookedUnit],
    demands: list[Demand],
    payments: list[Payment],
    deposits: list[tuple[date, Decimal]],
    certified_progress_pct: Decimal | None,
    certified_on: date | None,
    possession_given: bool,
    gst_rate_on_sale: Decimal,
    as_of: date,
    rules: RulesPack,
) -> CollectionsPosition:
    interest_rate = rules.value("rera.sbi_mclr", as_of) + rules.value(
        "rera.delay_interest_margin", as_of
    )
    by_unit_demands: dict[str, list[Demand]] = defaultdict(list)
    for d in demands:
        by_unit_demands[d.unit_id].append(d)
    by_unit_payments: dict[str, list[Payment]] = defaultdict(list)
    for p in payments:
        by_unit_payments[p.unit_id].append(p)

    accounts = []
    for unit in units:
        states = _allocate(
            by_unit_demands[unit.id], by_unit_payments[unit.id], as_of, interest_rate
        )
        received = sum((p.amount for p in by_unit_payments[unit.id] if p.on <= as_of), ZERO)
        billed = sum((s.demand.total for s in states), ZERO)
        accounts.append(
            UnitAccount(
                unit=unit,
                billed=billed,
                received=received,
                tds=sum((p.tds for p in by_unit_payments[unit.id] if p.on <= as_of), ZERO),
                outstanding=sum((s.outstanding for s in states), ZERO),
                overdue=sum((s.outstanding for s in states if s.overdue), ZERO),
                interest=sum((s.interest for s in states), ZERO),
                demands=tuple(states),
            )
        )

    raised = {(d.unit_id, d.milestone_id) for d in demands if d.raised_on <= as_of}
    ready = []
    statuses = []
    for m in sorted(milestones, key=lambda m: m.sequence):
        reached = milestone_reached(
            m, certified_progress_pct=certified_progress_pct, possession_given=possession_given
        )
        eligible = [u for u in units if u.booked_on <= as_of and (u.id, m.id) not in raised]
        raised_units = sum(1 for u in units if (u.id, m.id) in raised)
        billed = sum(
            (d.total for d in demands if d.milestone_id == m.id and d.raised_on <= as_of), ZERO
        )
        statuses.append(MilestoneStatus(m, reached, raised_units, billed))
        if reached and eligible:
            amount = sum((rupees(u.agreement_value * m.share_pct / 100) for u in eligible), ZERO)
            if m.trigger == Trigger.PROGRESS and certified_on is not None:
                reason = (
                    f"The architect certified {certified_progress_pct.normalize():f}% on "
                    f"{certified_on.day} {certified_on.strftime('%B %Y')}, which reaches this "
                    "milestone."
                )
            else:
                reason = "This milestone is due for every booked unit."
            ready.append(
                ReadyToRaise(
                    milestone=m,
                    unit_ids=tuple(u.id for u in eligible),
                    amount=amount,
                    gst=rupees(amount * gst_rate_on_sale),
                    reason=reason,
                )
            )

    checks = _deposit_checks(payments, deposits, as_of, rules)
    overdue_accounts = [a for a in accounts if a.overdue > 0]
    return CollectionsPosition(
        as_of=as_of,
        billed=sum((a.billed for a in accounts), ZERO),
        received=sum((a.received for a in accounts), ZERO),
        outstanding=sum((a.outstanding for a in accounts), ZERO),
        overdue=sum((a.overdue for a in overdue_accounts), ZERO),
        overdue_buyers=len(overdue_accounts),
        interest=sum((a.interest for a in accounts), ZERO),
        accounts=tuple(accounts),
        ready=tuple(ready),
        milestones=tuple(statuses),
        deposit_checks=checks,
    )


def new_demand(
    unit: BookedUnit, milestone: Milestone, *, gst_rate_on_sale: Decimal, raised_on: date
) -> tuple[Decimal, Decimal, date]:
    """Amount, GST and due date of a demand raised today."""
    amount = rupees(unit.agreement_value * milestone.share_pct / 100)
    return amount, rupees(amount * gst_rate_on_sale), raised_on + timedelta(days=milestone.due_days)


def _month_ends(as_of: date, months: int) -> list[date]:
    ends = []
    year, month = as_of.year, as_of.month
    for _ in range(months):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        first_of_next = date(year + month // 12, month % 12 + 1, 1)
        ends.append(first_of_next - timedelta(days=1))
    return sorted(ends)


def _deposit_checks(
    payments: list[Payment],
    deposits: list[tuple[date, Decimal]],
    as_of: date,
    rules: RulesPack,
    months: int = 6,
) -> tuple[DepositCheck, ...]:
    """At each recent month end: were 70% of everything buyers paid so far in the RERA account?"""
    share = rules.value("escrow.deposit_share", as_of)
    out = []
    for end in _month_ends(as_of, months):
        receipts = sum((p.amount for p in payments if p.on <= end), ZERO)
        deposited = sum((amount for on, amount in deposits if on <= end), ZERO)
        required = rupees(receipts * share)
        out.append(
            DepositCheck(end, receipts, required, deposited, max(required - deposited, ZERO))
        )
    return tuple(out)
