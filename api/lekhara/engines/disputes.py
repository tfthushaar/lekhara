"""Disputes and orders: every case brought against a project, and what it could cost.

Before an order, a case is costed from what the buyer actually paid, using the same
interest rule the promoter owes on delay. Once an order is passed, Lekhara works out
what it directs (interest keeps running until it is paid), the date to comply by,
and the last day to appeal with the deposit an appeal needs first.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from lekhara.money import ZERO, rupees
from lekhara.rules import RulesPack


class Forum(StrEnum):
    KRERA = "krera"
    ADJUDICATING_OFFICER = "adjudicating_officer"
    APPELLATE_TRIBUNAL = "appellate_tribunal"
    CONSUMER_DISTRICT = "consumer_district"
    CONSUMER_STATE = "consumer_state"
    CONSUMER_NATIONAL = "consumer_national"
    HIGH_COURT = "high_court"
    CIVIL_COURT = "civil_court"


FORUM_LABEL = {
    Forum.KRERA: "K-RERA",
    Forum.ADJUDICATING_OFFICER: "K-RERA adjudicating officer",
    Forum.APPELLATE_TRIBUNAL: "Karnataka Real Estate Appellate Tribunal",
    Forum.CONSUMER_DISTRICT: "District Consumer Commission",
    Forum.CONSUMER_STATE: "State Consumer Commission",
    Forum.CONSUMER_NATIONAL: "National Consumer Commission",
    Forum.HIGH_COURT: "High Court of Karnataka",
    Forum.CIVIL_COURT: "Civil court",
}


class Relief(StrEnum):
    REFUND = "refund"
    DELAY_INTEREST = "delay_interest"
    POSSESSION = "possession"
    COMPENSATION = "compensation"
    DEFECTS = "defects"
    OTHER = "other"


RELIEF_LABEL = {
    Relief.REFUND: "Refund with interest",
    Relief.DELAY_INTEREST: "Interest for the delay",
    Relief.POSSESSION: "Possession",
    Relief.COMPENSATION: "Compensation",
    Relief.DEFECTS: "Defects to be fixed",
    Relief.OTHER: "Other",
}


class CaseStatus(StrEnum):
    NOTICE = "notice"
    HEARING = "hearing"
    RESERVED = "reserved"
    ORDERED = "ordered"
    APPEALED = "appealed"
    SETTLING = "settling"
    COMPLIED = "complied"
    SETTLED = "settled"
    DISMISSED = "dismissed"
    WITHDRAWN = "withdrawn"


STATUS_LABEL = {
    CaseStatus.NOTICE: "Notice received",
    CaseStatus.HEARING: "In hearings",
    CaseStatus.RESERVED: "Order reserved",
    CaseStatus.ORDERED: "Order passed",
    CaseStatus.APPEALED: "Under appeal",
    CaseStatus.SETTLING: "Settlement agreed",
    CaseStatus.COMPLIED: "Order complied with",
    CaseStatus.SETTLED: "Settled",
    CaseStatus.DISMISSED: "Dismissed",
    CaseStatus.WITHDRAWN: "Withdrawn",
}

OPEN = frozenset(
    {
        CaseStatus.NOTICE,
        CaseStatus.HEARING,
        CaseStatus.RESERVED,
        CaseStatus.ORDERED,
        CaseStatus.APPEALED,
        CaseStatus.SETTLING,
    }
)


class OrderKind(StrEnum):
    REFUND = "refund"
    DELAY_INTEREST = "delay_interest"
    COMPENSATION = "compensation"
    COSTS = "costs"
    PENALTY = "penalty"
    POSSESSION = "possession"
    DISMISSED = "dismissed"
    OTHER = "other"


ORDER_LABEL = {
    OrderKind.REFUND: "Refund with interest until paid",
    OrderKind.DELAY_INTEREST: "Interest for the delay",
    OrderKind.COMPENSATION: "Compensation",
    OrderKind.COSTS: "Costs",
    OrderKind.PENALTY: "Penalty",
    OrderKind.POSSESSION: "Hand over possession",
    OrderKind.DISMISSED: "Complaint dismissed",
    OrderKind.OTHER: "Other direction",
}

RUNNING = frozenset({OrderKind.REFUND, OrderKind.DELAY_INTEREST})
"""Orders whose amount Lekhara works out from the buyer's payments, to the day."""


@dataclass(frozen=True)
class Appeal:
    to: str
    days_rule: str
    deposit_rule: str | None


def appeal_route(forum: Forum, kind: OrderKind) -> Appeal | None:
    """Where an order goes on appeal, the time allowed and the deposit an appeal needs."""
    if forum in (Forum.KRERA, Forum.ADJUDICATING_OFFICER):
        deposit = (
            "disputes.rera_appeal_deposit_penalty"
            if kind == OrderKind.PENALTY
            else "disputes.rera_appeal_deposit_buyer_dues"
        )
        return Appeal(FORUM_LABEL[Forum.APPELLATE_TRIBUNAL], "disputes.rera_appeal_days", deposit)
    if forum == Forum.APPELLATE_TRIBUNAL:
        return Appeal(FORUM_LABEL[Forum.HIGH_COURT], "disputes.tribunal_appeal_days", None)
    if forum == Forum.CONSUMER_DISTRICT:
        return Appeal(
            FORUM_LABEL[Forum.CONSUMER_STATE],
            "disputes.consumer_district_appeal_days",
            "disputes.consumer_appeal_deposit",
        )
    if forum == Forum.CONSUMER_STATE:
        return Appeal(
            FORUM_LABEL[Forum.CONSUMER_NATIONAL],
            "disputes.consumer_state_appeal_days",
            "disputes.consumer_appeal_deposit",
        )
    if forum == Forum.CONSUMER_NATIONAL:
        return Appeal(
            "Supreme Court",
            "disputes.consumer_national_appeal_days",
            "disputes.consumer_appeal_deposit",
        )
    return None


@dataclass(frozen=True)
class Payment:
    on: date
    amount: Decimal


@dataclass(frozen=True)
class OrderIn:
    order_id: str
    ordered_on: date
    kind: OrderKind
    amount: Decimal | None = None
    """A fixed sum. For refund and delay-interest orders, leave empty and Lekhara works it out."""
    comply_by: date | None = None
    received_on: date | None = None
    """When the copy of the order was received; the appeal time runs from then."""


@dataclass(frozen=True)
class CaseIn:
    case_id: str
    forum: Forum
    case_number: str
    relief: Relief
    status: CaseStatus
    complainant: str
    unit_label: str | None = None
    filed_on: date | None = None
    claim_amount: Decimal | None = None
    reply_due_on: date | None = None
    reply_filed_on: date | None = None
    next_hearing_on: date | None = None
    buyer_payments: tuple[Payment, ...] = ()
    """What the buyer paid the developer, with TDS counted as paid."""
    possession_due_on: date | None = None
    possession_on: date | None = None
    orders: tuple[OrderIn, ...] = ()
    paid: tuple[Payment, ...] = ()
    """What the developer has paid under the orders or a settlement."""
    settlement_offered: Decimal | None = None
    settlement_agreed: Decimal | None = None
    appealed_on: date | None = None


@dataclass(frozen=True)
class Estimate:
    principal: Decimal
    """The buyer's own money returned on a refund. The unit comes back to sell again."""
    interest: Decimal
    other: Decimal
    basis: str

    @property
    def total(self) -> Decimal:
        return self.principal + self.interest + self.other


@dataclass(frozen=True)
class OrderDue:
    order: OrderIn
    due: Decimal
    paid: Decimal
    outstanding: Decimal
    overdue: bool
    appeal: Appeal | None
    appeal_by: date | None
    appeal_deposit: Decimal | None


@dataclass(frozen=True)
class Event:
    on: date
    kind: str
    """reply, hearing, comply or appeal."""
    case_id: str
    text: str


@dataclass(frozen=True)
class CasePosition:
    case: CaseIn
    open: bool
    rate: Decimal
    estimate: Estimate
    orders: tuple[OrderDue, ...]
    ordered: Decimal
    owed: Decimal
    paid: Decimal
    at_stake: Decimal
    """What the case could still cost: the unpaid settlement, the unpaid order or the estimate."""
    settlement_saving: Decimal | None
    events: tuple[Event, ...]

    @property
    def next_event(self) -> Event | None:
        return self.events[0] if self.events else None


@dataclass(frozen=True)
class Patterns:
    by_relief: dict[Relief, int]
    by_forum: dict[Forum, int]
    filed_after_possession_due: int
    with_filing_date: int
    units_with_cases: int
    booked_units: int


@dataclass(frozen=True)
class DisputesPosition:
    cases: tuple[CasePosition, ...]
    open_cases: int
    at_stake: Decimal
    owed_under_orders: Decimal
    overdue_orders: int
    events: tuple[Event, ...]
    patterns: Patterns


def interest_rate(on: date, rules: RulesPack) -> Decimal:
    return rules.value("rera.sbi_mclr", on) + rules.value("rera.delay_interest_margin", on)


def _pct(rate: Decimal) -> str:
    return f"{(rate * 100).quantize(Decimal('0.01'))}%"


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def refund_interest(payments: tuple[Payment, ...], *, to: date, rate: Decimal) -> Decimal:
    """Simple interest on each payment, from the day it was paid."""
    return rupees(sum((p.amount * rate * max((to - p.on).days, 0) / 365 for p in payments), ZERO))


def delay_interest(
    payments: tuple[Payment, ...], *, due_on: date, until: date, rate: Decimal
) -> Decimal:
    """Simple interest on each payment, from the promised possession date (or the payment, if
    later) to possession or today."""
    total = ZERO
    for p in payments:
        start = max(p.on, due_on)
        total += p.amount * rate * max((until - start).days, 0) / 365
    return rupees(total)


def _delay_until(c: CaseIn, as_of: date) -> date:
    return min(c.possession_on, as_of) if c.possession_on else as_of


def estimate(c: CaseIn, *, as_of: date, rate: Decimal) -> Estimate:
    """What the case could cost if it is decided against the developer, as of today."""
    paid_by_buyer = sum((p.amount for p in c.buyer_payments), ZERO)
    claim = c.claim_amount or ZERO
    if c.relief == Relief.REFUND:
        return Estimate(
            principal=paid_by_buyer,
            interest=refund_interest(c.buyer_payments, to=as_of, rate=rate),
            other=ZERO,
            basis=(
                f"Everything the buyer paid returned, with interest at {_pct(rate)} a year from "
                "each payment to today."
            ),
        )
    if c.relief in (Relief.DELAY_INTEREST, Relief.POSSESSION):
        until = _delay_until(c, as_of)
        if c.possession_due_on is None or c.possession_due_on >= until:
            return Estimate(
                ZERO, ZERO, claim, "Possession is not late, so no interest for delay is owed yet."
            )
        interest = delay_interest(
            c.buyer_payments, due_on=c.possession_due_on, until=until, rate=rate
        )
        to = "possession" if c.possession_on and c.possession_on <= as_of else "today"
        extra = ", plus the compensation claimed" if claim > 0 else ""
        return Estimate(
            ZERO,
            interest,
            claim,
            f"Interest at {_pct(rate)} a year on each payment, from the promised possession date "
            f"({_fmt(c.possession_due_on)}) to {to}{extra}.",
        )
    if claim > 0:
        return Estimate(ZERO, ZERO, claim, "The amount claimed.")
    return Estimate(ZERO, ZERO, ZERO, "No amount is claimed.")


def _order_due(c: CaseIn, o: OrderIn, *, to: date, rate: Decimal) -> Decimal:
    if o.amount is not None:
        return o.amount
    if o.kind == OrderKind.REFUND:
        principal = sum((p.amount for p in c.buyer_payments), ZERO)
        return principal + refund_interest(c.buyer_payments, to=to, rate=rate)
    if o.kind == OrderKind.DELAY_INTEREST and c.possession_due_on is not None:
        until = min(c.possession_on, to) if c.possession_on else to
        return delay_interest(c.buyer_payments, due_on=c.possession_due_on, until=until, rate=rate)
    return ZERO


def _orders(c: CaseIn, *, as_of: date, rate: Decimal, rules: RulesPack) -> list[OrderDue]:
    """Each order's amount, and how the developer's payments apply to them, oldest first.

    Interest on a running order stops on the day the payments cover it; until then it runs
    to today.
    """
    paid = [p for p in c.paid if p.on <= as_of]
    paid_total = sum((p.amount for p in paid), ZERO)
    orders = sorted(c.orders, key=lambda o: o.ordered_on)
    dues = [_order_due(c, o, to=as_of, rate=rate) for o in orders]
    if paid:
        last_paid = max(p.on for p in paid)
        at_last = [_order_due(c, o, to=last_paid, rate=rate) for o in orders]
        if paid_total >= sum(at_last, ZERO):
            dues = at_last
    out = []
    remaining = paid_total
    for o, due in zip(orders, dues, strict=True):
        applied = min(remaining, due)
        remaining -= applied
        outstanding = due - applied
        route = appeal_route(c.forum, o.kind) if o.kind != OrderKind.DISMISSED else None
        appeal_by = deposit = None
        if route is not None and outstanding > 0:
            start = o.received_on or o.ordered_on
            appeal_by = start + timedelta(days=rules.value(route.days_rule, o.ordered_on))
            if route.deposit_rule:
                deposit = rupees(outstanding * rules.value(route.deposit_rule, o.ordered_on))
        out.append(
            OrderDue(
                order=o,
                due=due,
                paid=applied,
                outstanding=outstanding,
                overdue=(
                    outstanding > 0
                    and o.comply_by is not None
                    and o.comply_by < as_of
                    and c.appealed_on is None
                ),
                appeal=route,
                appeal_by=appeal_by,
                appeal_deposit=deposit,
            )
        )
    return out


def case_position(c: CaseIn, *, as_of: date, rules: RulesPack) -> CasePosition:
    rate = interest_rate(as_of, rules)
    est = estimate(c, as_of=as_of, rate=rate)
    orders = _orders(c, as_of=as_of, rate=rate, rules=rules)
    paid = sum((p.amount for p in c.paid if p.on <= as_of), ZERO)
    ordered = sum((o.due for o in orders), ZERO)
    owed = sum((o.outstanding for o in orders), ZERO)
    is_open = c.status in OPEN
    if not is_open:
        at_stake = ZERO
    elif c.settlement_agreed is not None:
        at_stake = max(c.settlement_agreed - paid, ZERO)
    elif any(o.order.kind != OrderKind.DISMISSED for o in orders):
        at_stake = owed
    else:
        at_stake = est.total
    settlement = c.settlement_agreed if c.settlement_agreed is not None else c.settlement_offered
    saving = None
    if settlement is not None:
        saving = (ordered if orders else est.total) - settlement

    title = f"the case by {c.complainant}"
    events: list[Event] = []
    if is_open:
        if c.reply_due_on and not c.reply_filed_on:
            events.append(Event(c.reply_due_on, "reply", c.case_id, f"Reply due in {title}"))
        if c.next_hearing_on and c.next_hearing_on >= as_of:
            events.append(Event(c.next_hearing_on, "hearing", c.case_id, f"Hearing in {title}"))
        for o in orders:
            if c.appealed_on is not None or o.outstanding <= 0:
                continue
            if o.order.comply_by:
                events.append(
                    Event(
                        o.order.comply_by, "comply", c.case_id, f"Comply with the order in {title}"
                    )
                )
            if o.appeal_by and o.appeal_by >= as_of:
                events.append(
                    Event(
                        o.appeal_by, "appeal", c.case_id, f"Last day to appeal the order in {title}"
                    )
                )
    events = sorted(set(events), key=lambda e: (e.on, e.kind))
    return CasePosition(
        case=c,
        open=is_open,
        rate=rate,
        estimate=est,
        orders=tuple(orders),
        ordered=ordered,
        owed=owed,
        paid=paid,
        at_stake=at_stake,
        settlement_saving=saving,
        events=tuple(events),
    )


def disputes_position(
    cases: list[CaseIn],
    *,
    as_of: date,
    rules: RulesPack,
    possession_due_on: date | None,
    booked_units: int,
) -> DisputesPosition:
    positions = [case_position(c, as_of=as_of, rules=rules) for c in cases]
    positions.sort(key=lambda p: (not p.open, p.next_event.on if p.next_event else date.max))
    open_positions = [p for p in positions if p.open]
    dated = [c for c in cases if c.filed_on is not None]
    return DisputesPosition(
        cases=tuple(positions),
        open_cases=len(open_positions),
        at_stake=sum((p.at_stake for p in open_positions), ZERO),
        owed_under_orders=sum((p.owed for p in open_positions), ZERO),
        overdue_orders=sum(1 for p in open_positions for o in p.orders if o.overdue),
        events=tuple(sorted((e for p in open_positions for e in p.events), key=lambda e: e.on)),
        patterns=Patterns(
            by_relief={r: sum(1 for c in cases if c.relief == r) for r in Relief},
            by_forum={f: sum(1 for c in cases if c.forum == f) for f in Forum},
            filed_after_possession_due=sum(
                1 for c in dated if possession_due_on is not None and c.filed_on > possession_due_on
            ),
            with_filing_date=len(dated),
            units_with_cases=len({c.unit_label for c in cases if c.unit_label}),
            booked_units=booked_units,
        ),
    )
