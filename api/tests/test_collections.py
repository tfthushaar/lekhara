from datetime import date
from decimal import Decimal as D

from horus.engines.collections import (
    BookedUnit,
    Demand,
    Milestone,
    Payment,
    Trigger,
    collections_position,
    milestone_reached,
    new_demand,
)
from horus.rules import KARNATAKA

TODAY = date(2026, 10, 17)
RATE = D("0.1095")  # SBI MCLR 8.95% + 2%, from the rules pack

BOOKING = Milestone("m1", 1, "On booking", D("10"), Trigger.BOOKING, due_days=7)
SLAB = Milestone("m2", 2, "On the 8th floor slab", D("10"), Trigger.PROGRESS, D("50"))
TERRACE = Milestone("m3", 3, "On the terrace slab", D("10"), Trigger.PROGRESS, D("65"))
POSSESSION = Milestone("m4", 4, "On possession", D("10"), Trigger.POSSESSION)
UNIT = BookedUnit("u1", "A-0101", "Buyer 001", D("10000000"), date(2026, 1, 10))


def position(demands, payments, progress=D("56"), deposits=(), units=(UNIT,)):
    return collections_position(
        milestones=[BOOKING, SLAB, TERRACE, POSSESSION],
        units=list(units),
        demands=demands,
        payments=payments,
        deposits=list(deposits),
        certified_progress_pct=progress,
        certified_on=date(2026, 9, 29),
        possession_given=False,
        gst_rate_on_sale=D("0.05"),
        as_of=TODAY,
        rules=KARNATAKA,
    )


def demand(id, milestone, raised, due, amount="1000000", gst="50000"):
    return Demand(id, "u1", milestone, D(amount), D(gst), raised, due)


def test_which_milestones_are_reached() -> None:
    kw = {"certified_progress_pct": D("56"), "possession_given": False}
    assert milestone_reached(BOOKING, **kw)
    assert milestone_reached(SLAB, **kw)
    assert not milestone_reached(TERRACE, **kw)
    assert not milestone_reached(POSSESSION, **kw)
    assert not milestone_reached(SLAB, certified_progress_pct=None, possession_given=False)


def test_payments_are_matched_in_order_and_overdue_accrues_interest() -> None:
    demands = [
        demand("d1", "m1", date(2026, 1, 10), date(2026, 1, 17)),
        demand("d2", "m2", date(2026, 9, 1), date(2026, 9, 16)),
    ]
    payments = [
        Payment("u1", D("1050000"), date(2026, 1, 15)),
        Payment("u1", D("550000"), date(2026, 9, 10)),
    ]
    p = position(demands, payments)
    account = p.accounts[0]
    first, second = account.demands
    assert first.outstanding == D("0")
    assert second.paid == D("550000")
    assert second.outstanding == D("500000")
    assert second.overdue and second.days_overdue == 31
    assert second.interest == (D("500000") * RATE * 31 / 365).quantize(D("0.01"))
    assert account.overdue == D("500000")
    assert p.overdue_buyers == 1


def test_tds_deducted_by_the_buyer_counts_as_paid() -> None:
    demands = [demand("d1", "m1", date(2026, 1, 10), date(2026, 1, 17))]
    payments = [Payment("u1", D("1040000"), date(2026, 1, 15), tds=D("10000"))]
    account = position(demands, payments).accounts[0]
    assert account.outstanding == D("0")
    assert account.tds == D("10000")


def test_certified_progress_makes_demands_ready_to_raise() -> None:
    demands = [demand("d1", "m1", date(2026, 1, 10), date(2026, 1, 17))]
    p = position(demands, [Payment("u1", D("1050000"), date(2026, 1, 15))])
    assert [r.milestone.id for r in p.ready] == ["m2"]
    ready = p.ready[0]
    assert ready.unit_ids == ("u1",)
    assert ready.amount == D("1000000.00")
    assert ready.gst == D("50000.00")
    assert "certified 56%" in ready.reason
    # Below the milestone's level, nothing is ready.
    assert [r.milestone.id for r in position(demands, [], progress=D("40")).ready] == []


def test_new_demand_amount_gst_and_due_date() -> None:
    amount, gst, due = new_demand(UNIT, SLAB, gst_rate_on_sale=D("0.05"), raised_on=TODAY)
    assert (amount, gst, due) == (D("1000000.00"), D("50000.00"), date(2026, 11, 1))


def test_month_end_deposit_check() -> None:
    payments = [
        Payment("u1", D("1000"), date(2026, 8, 20)),
        Payment("u1", D("1000"), date(2026, 9, 5)),
    ]
    deposits = [(date(2026, 8, 31), D("700")), (date(2026, 9, 30), D("500"))]
    checks = {c.month_end: c for c in position([], payments, deposits=deposits).deposit_checks}
    assert checks[date(2026, 8, 31)].shortfall == D("0")
    september = checks[date(2026, 9, 30)]
    assert september.required == D("1400.00")
    assert september.deposits == D("1200")
    assert september.shortfall == D("200.00")
