from datetime import date
from decimal import Decimal as D

import pytest

from horus.engines.money import (
    Category,
    CostLine,
    Entry,
    EntryKind,
    ReraHead,
    project_position,
)
from horus.rules import KARNATAKA

TODAY = date(2026, 10, 17)


def line(
    id: str,
    budget: str,
    category: Category = Category.CONSTRUCTION,
    head: ReraHead = ReraHead.DEVELOPMENT,
) -> CostLine:
    return CostLine(
        id=id,
        code=id.upper(),
        name=id.title(),
        category=category,
        rera_head=head,
        original_budget=D(budget),
        revised_budget=D(budget),
    )


def entry(line_id: str, kind: EntryKind, amount: str, on: date = date(2026, 6, 1)) -> Entry:
    return Entry(cost_line_id=line_id, kind=kind, amount=D(amount), on=on)


def position(lines, entries, progress=None, as_of=TODAY):
    return project_position(
        lines, entries, as_of=as_of, certified_progress_pct=progress, rules=KARNATAKA
    )


def test_line_stages_and_forecast() -> None:
    p = position(
        [line("civil", "1000")],
        [
            entry("civil", EntryKind.COMMITMENT, "900"),
            entry("civil", EntryKind.INCURRED, "400"),
            entry("civil", EntryKind.PAID, "360"),
            entry("civil", EntryKind.RETENTION_HELD, "40"),
            entry("civil", EntryKind.ADVANCE_PAID, "100"),
            entry("civil", EntryKind.ADVANCE_RECOVERED, "30"),
        ],
    )
    civil = p.lines[0]
    assert civil.committed == D("900")
    assert civil.incurred == D("400")
    assert civil.paid == D("360")
    assert civil.retained == D("40")
    assert civil.advance_outstanding == D("70")
    assert civil.anticipated_final_cost == D("1000")
    assert civil.cost_to_complete == D("600")
    assert civil.overrun == D("0")


def test_cancellation_is_a_reversing_entry() -> None:
    p = position(
        [line("civil", "1000")],
        [
            entry("civil", EntryKind.COMMITMENT, "1200"),
            entry("civil", EntryKind.COMMITMENT, "-300"),
        ],
    )
    assert p.lines[0].committed == D("900")
    assert p.lines[0].anticipated_final_cost == D("1000")


def test_commitment_above_budget_raises_forecast_and_alerts() -> None:
    p = position([line("mep", "500")], [entry("mep", EntryKind.COMMITMENT, "650")])
    mep = p.lines[0]
    assert mep.anticipated_final_cost == D("650")
    assert mep.overrun == D("150")
    codes = [a.code for a in p.alerts]
    assert "over_committed" in codes
    assert "overrun_beyond_contingency" in codes


def test_contingency_absorbs_overruns() -> None:
    lines = [line("mep", "500"), line("cont", "100", category=Category.CONTINGENCY)]
    p = position(lines, [entry("mep", EntryKind.COMMITMENT, "560")])
    assert p.contingency_budget == D("100")
    assert p.contingency_used == D("60")
    assert p.contingency_remaining == D("40")
    assert p.overrun_beyond_contingency == D("0")
    # Budget 600 total; forecast is 560 + the 40 of contingency still assumed spent.
    assert p.anticipated_final_cost == D("600")
    assert "overrun_beyond_contingency" not in [a.code for a in p.alerts]


def test_overrun_beyond_contingency() -> None:
    lines = [line("mep", "500"), line("cont", "100", category=Category.CONTINGENCY)]
    p = position(lines, [entry("mep", EntryKind.COMMITMENT, "650")])
    assert p.contingency_remaining == D("0")
    assert p.overrun_beyond_contingency == D("50")
    assert p.anticipated_final_cost == D("650")


def test_contingency_low_alert() -> None:
    lines = [line("mep", "500"), line("cont", "100", category=Category.CONTINGENCY)]
    p = position(lines, [entry("mep", EntryKind.COMMITMENT, "580")])
    assert p.contingency_remaining == D("20")
    assert "contingency_low" in [a.code for a in p.alerts]


def test_land_and_development_heads() -> None:
    lines = [
        line("land", "3000", category=Category.LAND, head=ReraHead.LAND),
        line("civil", "7000"),
    ]
    p = position(
        lines,
        [
            entry("land", EntryKind.INCURRED, "3000"),
            entry("land", EntryKind.PAID, "3000"),
            entry("civil", EntryKind.INCURRED, "2100"),
            entry("civil", EntryKind.PAID, "2000"),
        ],
    )
    assert p.land.estimated_cost == D("3000")
    assert p.land.incurred == D("3000")
    assert p.development.estimated_cost == D("7000")
    assert p.development.incurred == D("2100")
    assert p.development.paid == D("2000")
    assert p.development_incurred_pct == D("30.00")
    assert p.anticipated_final_cost == D("10000")
    assert p.cost_to_complete == D("4900")


def test_cost_ahead_of_progress_alert() -> None:
    lines = [line("civil", "1000")]
    entries = [entry("civil", EntryKind.INCURRED, "450")]
    assert "cost_ahead_of_progress" in [a.code for a in position(lines, entries, D("30")).alerts]
    assert "cost_ahead_of_progress" not in [
        a.code for a in position(lines, entries, D("40")).alerts
    ]
    assert "cost_ahead_of_progress" not in [a.code for a in position(lines, entries, None).alerts]


def test_point_in_time() -> None:
    lines = [line("civil", "1000")]
    entries = [
        entry("civil", EntryKind.INCURRED, "100", on=date(2026, 3, 31)),
        entry("civil", EntryKind.INCURRED, "200", on=date(2026, 6, 30)),
    ]
    assert position(lines, entries, as_of=date(2026, 3, 31)).incurred == D("100")
    assert position(lines, entries, as_of=date(2026, 6, 30)).incurred == D("300")


def test_unknown_line_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown cost line"):
        position([line("civil", "1000")], [entry("ghost", EntryKind.INCURRED, "1")])
