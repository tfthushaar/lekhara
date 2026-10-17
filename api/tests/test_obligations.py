from datetime import date
from decimal import Decimal as D

from lekhara.engines.escrow import AccountTxn, TxnKind, escrow_position
from lekhara.engines.money import Category, CostLine, Entry, EntryKind, ReraHead, project_position
from lekhara.engines.obligations import ObligationStatus, ProjectFacts, project_obligations
from lekhara.engines.tax import (
    GstRegime,
    Purchase,
    bocw_cess,
    delay_interest,
    development_rights_gst,
    procurement_meter,
)
from lekhara.rules import KARNATAKA

TODAY = date(2026, 10, 17)


def facts(
    *,
    deposits="90000000",
    withdrawn="20000000",
    receipts="100000000",
    possession=date(2027, 12, 31),
    qpr_filed=None,
    audits_done=None,
    purchases=None,
    cess_paid="400000",
) -> ProjectFacts:
    lines = [
        CostLine("land", "L", "Land", Category.LAND, ReraHead.LAND, D("30000000"), D("30000000")),
        CostLine(
            "civil",
            "C",
            "Civil",
            Category.CONSTRUCTION,
            ReraHead.DEVELOPMENT,
            D("70000000"),
            D("70000000"),
        ),
    ]
    entries = [
        Entry("land", EntryKind.INCURRED, D("30000000"), date(2024, 5, 1)),
        Entry("land", EntryKind.PAID, D("30000000"), date(2024, 5, 1)),
        Entry("civil", EntryKind.INCURRED, D("40000000"), date(2026, 9, 1)),
        Entry("civil", EntryKind.PAID, D("40000000"), date(2026, 9, 1)),
    ]
    money = project_position(
        lines, entries, as_of=TODAY, certified_progress_pct=D("57"), rules=KARNATAKA
    )
    txns = [
        AccountTxn(TxnKind.DEPOSIT, D(deposits), date(2026, 1, 1)),
        AccountTxn(TxnKind.WITHDRAWAL, D(withdrawn), date(2026, 8, 1)),
    ]
    escrow = escrow_position(money, txns, D(receipts), as_of=TODAY, rules=KARNATAKA)
    procurement = procurement_meter(
        purchases or [Purchase(D("100"), date(2026, 6, 1), True)],
        regime=GstRegime.RESIDENTIAL_5PC,
        as_of=TODAY,
        rules=KARNATAKA,
    )
    quarters = {date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31)}
    return ProjectFacts(
        project_id="p1",
        project_name="Test Towers",
        as_of=TODAY,
        registered_on=date(2025, 4, 1),
        estimated_cost=money.anticipated_final_cost,
        escrow=escrow,
        procurement=procurement,
        development_rights=development_rights_gst(
            None, [], regime=GstRegime.RESIDENTIAL_5PC, on=TODAY, rules=KARNATAKA
        ),
        msme=[],
        delay=delay_interest(D(receipts), possession, as_of=TODAY, rules=KARNATAKA),
        guidance_flags=[],
        landowner_tds=[],
        cess=bocw_cess(money, D(cess_paid), as_of=TODAY, rules=KARNATAKA),
        qpr_filed=quarters if qpr_filed is None else qpr_filed,
        audits_done={2025} if audits_done is None else audits_done,
    )


def by_key(f: ProjectFacts):
    return {o.key: o for o in project_obligations(f, rules=KARNATAKA)}


def test_withdrawal_opportunity() -> None:
    o = by_key(facts())["escrow:withdraw"]
    # Cost incurred and paid 7 crore, withdrawn 2 crore, balance 7 crore: 5 crore drawable.
    assert o.status == ObligationStatus.OPPORTUNITY
    assert o.amount == D("50000000")


def test_deposit_shortfall_is_overdue() -> None:
    o = by_key(facts(deposits="60000000"))["escrow:deposit"]
    assert o.status == ObligationStatus.OVERDUE
    assert o.amount == D("10000000.00")


def test_late_qpr_and_next_qpr() -> None:
    obligations = by_key(facts())
    late = obligations["qpr:2026-06-30"]
    assert late.status == ObligationStatus.OVERDUE
    assert late.due_on == date(2026, 7, 15)
    assert late.amount == D("25000")
    # Quarter ending 30 September 2026 was due on 15 October: also late.
    assert obligations["qpr:2026-09-30"].status == ObligationStatus.OVERDUE
    nxt = obligations["qpr:2026-12-31"]
    assert nxt.status == ObligationStatus.UPCOMING
    assert nxt.due_on == date(2027, 1, 15)


def test_filed_qprs_are_not_listed() -> None:
    filed = {
        date(2025, 6, 30),
        date(2025, 9, 30),
        date(2025, 12, 31),
        date(2026, 3, 31),
        date(2026, 6, 30),
        date(2026, 9, 30),
    }
    keys = by_key(facts(qpr_filed=filed))
    assert not [k for k in keys if k.startswith("qpr:2026-0")]
    assert "qpr:2026-12-31" in keys


def test_annual_audit_overdue() -> None:
    o = by_key(facts(audits_done=set()))["audit:2025"]
    assert o.due_on == date(2026, 9, 30)
    assert o.status == ObligationStatus.OVERDUE
    assert "audit:2025" not in by_key(facts())


def test_delay_interest_when_possession_is_late() -> None:
    o = by_key(facts(possession=date(2026, 8, 18)))["rera:delay"]
    assert o.status == ObligationStatus.OVERDUE
    assert o.amount > 0


def test_possession_soon_is_at_risk() -> None:
    o = by_key(facts(possession=date(2026, 12, 31)))["rera:possession"]
    assert o.status == ObligationStatus.AT_RISK


def test_gst_shortfall_is_at_risk() -> None:
    purchases = [
        Purchase(D("70"), date(2026, 6, 1), True),
        Purchase(D("30"), date(2026, 6, 1), False),
    ]
    o = by_key(facts(purchases=purchases))["gst80:2026-27"]
    assert o.status == ObligationStatus.AT_RISK
    assert o.amount == D("1.80")


def test_cess_balance() -> None:
    o = by_key(facts(cess_paid="100000"))["bocw:cess"]
    assert o.amount == D("300000.00")
    assert "bocw:cess" not in by_key(facts(cess_paid="400000"))


def test_most_urgent_first() -> None:
    statuses = [o.status for o in project_obligations(facts(), rules=KARNATAKA)]
    order = list(ObligationStatus)
    assert statuses == sorted(statuses, key=order.index)
