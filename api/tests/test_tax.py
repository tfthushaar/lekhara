from datetime import date
from decimal import Decimal as D

from horus.engines.money import Category, CostLine, Entry, EntryKind, ReraHead, project_position
from horus.engines.tax import (
    GstRegime,
    LandownerPayment,
    MsmeCategory,
    MsmeStatus,
    Purchase,
    Sale,
    SupplierBill,
    UnitForTax,
    bocw_cess,
    delay_interest,
    development_rights_gst,
    financial_year,
    fy_label,
    guidance_value_flags,
    landowner_tds_shortfalls,
    msme_clock,
    procurement_meter,
)
from horus.rules import KARNATAKA

TODAY = date(2026, 10, 17)


def test_financial_year() -> None:
    assert financial_year(date(2026, 10, 17)) == (date(2026, 4, 1), date(2027, 3, 31))
    assert financial_year(date(2027, 2, 1)) == (date(2026, 4, 1), date(2027, 3, 31))
    assert fy_label(date(2026, 4, 1)) == "2026-27"


def buy(amount: str, registered: bool, **kw) -> Purchase:
    return Purchase(
        amount=D(amount), on=kw.pop("on", date(2026, 6, 1)), supplier_registered=registered, **kw
    )


def meter(purchases, regime=GstRegime.RESIDENTIAL_5PC):
    return procurement_meter(purchases, regime=regime, as_of=TODAY, rules=KARNATAKA)


def test_meter_shortfall() -> None:
    m = meter([buy("70", True), buy("30", False)])
    assert m.total == D("100")
    assert m.registered_share_pct == D("70.00")
    assert m.shortfall == D("10.00")
    assert m.rcm_on_shortfall == D("1.80")
    assert m.unregistered_headroom == D("0.00")
    assert m.payment_due_on == date(2027, 6, 30)


def test_meter_headroom() -> None:
    m = meter([buy("90", True), buy("10", False)])
    assert m.shortfall == D("0.00")
    # 90 qualifying supports 112.5 of total purchases at 80%: 12.5 more may be unregistered.
    assert m.unregistered_headroom == D("12.50")


def test_meter_exclusions_cement_and_rcm_services() -> None:
    m = meter(
        [
            buy("60", True),
            buy("50", False, excluded=True),  # electricity: outside the test
            buy("10", False, is_cement=True),  # unregistered cement: reverse charge paid separately
            buy("10", False, rcm_paid=True),  # security services on reverse charge
            buy("20", False),
        ]
    )
    assert m.total == D("100")
    assert m.qualifying == D("80")
    assert m.shortfall == D("0.00")
    assert m.cement_rcm == D("2.80")


def test_meter_counts_only_this_year_to_date() -> None:
    m = meter(
        [
            buy("100", False, on=date(2026, 3, 31)),  # last financial year
            buy("100", False, on=date(2026, 11, 1)),  # after today
            buy("50", True),
        ]
    )
    assert m.total == D("50")
    assert m.shortfall == D("0.00")


def test_meter_does_not_apply_to_commercial() -> None:
    m = meter([buy("10", True), buy("90", False)], regime=GstRegime.COMMERCIAL_12PC)
    assert not m.applies
    assert m.shortfall == D("0")


def flats():
    units = [UnitForTax(D("100"), D("50"), booked=False, landowner_share=True) for _ in range(4)]
    units += [UnitForTax(D("100"), D("50"), booked=True, landowner_share=False) for _ in range(3)]
    units += [UnitForTax(D("100"), D("50"), booked=False, landowner_share=False) for _ in range(3)]
    return units


def test_development_rights_gst_capped() -> None:
    r = development_rights_gst(
        D("1000"), flats(), regime=GstRegime.RESIDENTIAL_5PC, on=TODAY, rules=KARNATAKA
    )
    assert r.applies
    assert r.unbooked_units == 3
    assert r.unbooked_area == D("300")
    assert r.gst_on_unbooked_share == D("54.00")
    assert r.cap == D("7.50")
    assert r.liability == D("7.50")
    assert r.capped
    assert r.saving_per_unit_sold == D("2.50")


def test_development_rights_gst_not_applicable_without_jda() -> None:
    r = development_rights_gst(
        None, flats(), regime=GstRegime.RESIDENTIAL_5PC, on=TODAY, rules=KARNATAKA
    )
    assert not r.applies
    assert r.liability == D("0")


def test_guidance_value_flags() -> None:
    sales = [
        Sale("A-101", D("100"), D("111"), date(2026, 9, 1)),
        Sale("A-102", D("100"), D("110"), date(2026, 9, 1)),
    ]
    flags = guidance_value_flags(sales, on=TODAY, rules=KARNATAKA)
    assert [f.sale.unit_label for f in flags] == ["A-101"]
    assert flags[0].gap == D("11")
    assert flags[0].estimated_tax == D("2.77")


def test_landowner_tds() -> None:
    payments = [
        LandownerPayment("Ravi", D("1000"), date(2026, 8, 1), D("50")),
        LandownerPayment("Ravi", D("1000"), date(2026, 9, 1), D("100")),
        LandownerPayment("Ravi", D("1000"), date(2026, 9, 1), D("0"), monetary_consideration=False),
    ]
    shortfalls = landowner_tds_shortfalls(payments, rules=KARNATAKA)
    assert len(shortfalls) == 1
    assert shortfalls[0].expected == D("100.00")
    assert shortfalls[0].short == D("50.00")


def bill(no: str, accepted: date, msme=MsmeCategory.MICRO, agreement=True, paid=None):
    return SupplierBill("Supplier", no, D("100"), accepted, msme, agreement, paid)


def test_msme_clock() -> None:
    items = msme_clock(
        [
            bill("1", date(2026, 10, 1)),  # due 15 Nov
            bill("2", date(2026, 9, 1)),  # due 16 Oct: overdue
            bill("3", date(2026, 9, 5)),  # due 20 Oct: due soon
            bill("4", date(2026, 10, 10), agreement=False),  # due 25 Oct
            bill("5", date(2026, 9, 1), msme=MsmeCategory.MEDIUM),  # not covered
            bill("6", date(2024, 1, 1)),  # before the rule applied
            bill("7", date(2026, 8, 1), paid=date(2026, 9, 30)),  # due 15 Sep: paid late
        ],
        as_of=TODAY,
        rules=KARNATAKA,
    )
    by_no = {i.bill.bill_no: i for i in items}
    assert set(by_no) == {"1", "2", "3", "4", "7"}
    assert by_no["1"].status == MsmeStatus.OK
    assert by_no["1"].due_on == date(2026, 11, 15)
    assert by_no["2"].status == MsmeStatus.OVERDUE
    assert by_no["3"].status == MsmeStatus.DUE_SOON
    assert by_no["4"].due_on == date(2026, 10, 25)
    assert by_no["4"].status == MsmeStatus.OK
    assert by_no["7"].status == MsmeStatus.PAID_LATE


def test_bocw_cess() -> None:
    lines = [
        CostLine("land", "L", "Land", Category.LAND, ReraHead.LAND, D("3000"), D("3000")),
        CostLine(
            "civil", "C", "Civil", Category.CONSTRUCTION, ReraHead.DEVELOPMENT, D("7000"), D("7000")
        ),
    ]
    entries = [
        Entry("land", EntryKind.INCURRED, D("3000"), date(2025, 1, 1)),
        Entry("civil", EntryKind.INCURRED, D("4000"), date(2026, 9, 1)),
    ]
    money = project_position(
        lines, entries, as_of=TODAY, certified_progress_pct=None, rules=KARNATAKA
    )
    c = bocw_cess(money, D("25"), as_of=TODAY, rules=KARNATAKA)
    assert c.cess_on_estimate == D("70.00")
    assert c.cess_due_to_date == D("40.00")
    assert c.balance_due == D("15.00")


def test_delay_interest() -> None:
    late = delay_interest(D("1200000"), date(2026, 8, 18), as_of=TODAY, rules=KARNATAKA)
    assert late.annual_rate == D("0.1095")
    assert late.days_late == 60
    assert late.accrued == D("21600.00")
    assert late.per_month == D("10950.00")
    assert late.days_to_possession is None

    early = delay_interest(D("1200000"), date(2026, 12, 16), as_of=TODAY, rules=KARNATAKA)
    assert early.days_late == 0
    assert early.accrued == D("0.00")
    assert early.days_to_possession == 60
