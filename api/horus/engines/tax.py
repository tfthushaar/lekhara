"""Real-estate-specific tax and statutory exposures.

Each function returns both the figure and the inputs behind it, so the product
can explain every number. Rates and thresholds come from the rules pack; several
of them are marked unsettled or unverified there and must be confirmed by the
customer's CA before anyone relies on them.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from horus.engines.money import Category, ProjectPosition
from horus.money import ZERO, percent, rupees
from horus.rules import RuleNotFound, RulesPack


class GstRegime(StrEnum):
    AFFORDABLE_1PC = "affordable_1pc"
    RESIDENTIAL_5PC = "residential_5pc"
    COMMERCIAL_12PC = "commercial_12pc"
    RREP_MIXED = "rrep_mixed"

    @property
    def residential_scheme(self) -> bool:
        """Residential schemes give no input tax credit and carry the 80% test."""
        return self != GstRegime.COMMERCIAL_12PC


def financial_year(on: date) -> tuple[date, date]:
    start_year = on.year if on.month >= 4 else on.year - 1
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


def fy_label(on: date) -> str:
    start, end = financial_year(on)
    return f"{start.year}-{str(end.year)[2:]}"


# The 80% registered-procurement test


@dataclass(frozen=True)
class Purchase:
    amount: Decimal
    on: date
    supplier_registered: bool
    is_cement: bool = False
    excluded: bool = False
    """Development rights, electricity, diesel, petrol and natural gas are outside the test."""
    rcm_paid: bool = False
    """Reverse charge already paid on it (for example security or transport services)."""


@dataclass(frozen=True)
class ProcurementMeter:
    applies: bool
    fy: str
    fy_start: date
    fy_end: date
    total: Decimal
    qualifying: Decimal
    registered_share_pct: Decimal
    min_share_pct: Decimal
    shortfall: Decimal
    rcm_on_shortfall: Decimal
    unregistered_headroom: Decimal
    unregistered_cement: Decimal
    cement_rcm: Decimal
    payment_due_on: date


def procurement_meter(
    purchases: list[Purchase], *, regime: GstRegime, as_of: date, rules: RulesPack
) -> ProcurementMeter:
    fy_start, fy_end = financial_year(as_of)
    min_share = rules.value("gst.procurement.min_registered_share", as_of)
    month, day = rules.value("gst.procurement.payment_due", as_of)
    due = date(fy_end.year, month, day)

    counted = [p for p in purchases if fy_start <= p.on <= min(fy_end, as_of) and not p.excluded]
    total = sum((p.amount for p in counted), ZERO)
    unregistered_cement = sum(
        (p.amount for p in counted if p.is_cement and not p.supplier_registered), ZERO
    )
    qualifying = sum(
        (
            p.amount
            for p in counted
            if p.supplier_registered or p.rcm_paid or (p.is_cement and not p.supplier_registered)
        ),
        ZERO,
    )

    applies = regime.residential_scheme
    shortfall = max(total * min_share - qualifying, ZERO) if applies else ZERO
    headroom = max(qualifying / min_share - total, ZERO) if applies and min_share else ZERO
    return ProcurementMeter(
        applies=applies,
        fy=fy_label(as_of),
        fy_start=fy_start,
        fy_end=fy_end,
        total=total,
        qualifying=qualifying,
        registered_share_pct=percent(qualifying, total),
        min_share_pct=(min_share * 100).quantize(Decimal("0.01")),
        shortfall=rupees(shortfall),
        rcm_on_shortfall=rupees(
            shortfall * rules.value("gst.procurement.shortfall_rcm_rate", as_of)
        ),
        unregistered_headroom=rupees(headroom),
        unregistered_cement=unregistered_cement,
        cement_rcm=rupees(
            unregistered_cement * rules.value("gst.procurement.cement_rcm_rate", as_of)
        )
        if applies
        else ZERO,
        payment_due_on=due,
    )


# GST on development rights for flats unbooked at completion (JDA projects)


@dataclass(frozen=True)
class UnitForTax:
    carpet_area: Decimal
    value: Decimal
    """Agreement value if booked, otherwise current list price."""
    booked: bool
    landowner_share: bool
    residential: bool = True


@dataclass(frozen=True)
class DevelopmentRightsGst:
    applies: bool
    dr_value: Decimal
    total_residential_area: Decimal
    unbooked_area: Decimal
    unbooked_value: Decimal
    unbooked_units: int
    gst_on_unbooked_share: Decimal
    cap: Decimal
    liability: Decimal
    capped: bool
    saving_per_unit_sold: Decimal


def development_rights_gst(
    dr_value: Decimal | None,
    units: list[UnitForTax],
    *,
    regime: GstRegime,
    on: date,
    rules: RulesPack,
) -> DevelopmentRightsGst:
    """Liability if completion were reached today with the current bookings.

    The landowner's own flats are treated as allotted, not unbooked. Only the
    developer's unbooked residential flats create liability. Sources differ on
    details; the rules behind this are marked unsettled.
    """
    residential = [u for u in units if u.residential]
    total_area = sum((u.carpet_area for u in residential), ZERO)
    unbooked = [u for u in residential if not u.booked and not u.landowner_share]
    unbooked_area = sum((u.carpet_area for u in unbooked), ZERO)
    unbooked_value = sum((u.value for u in unbooked), ZERO)

    applies = bool(dr_value) and regime.residential_scheme and total_area > 0
    if not applies:
        return DevelopmentRightsGst(
            applies=False,
            dr_value=dr_value or ZERO,
            total_residential_area=total_area,
            unbooked_area=unbooked_area,
            unbooked_value=unbooked_value,
            unbooked_units=len(unbooked),
            gst_on_unbooked_share=ZERO,
            cap=ZERO,
            liability=ZERO,
            capped=False,
            saving_per_unit_sold=ZERO,
        )

    rate = rules.value("gst.dr.rcm_rate", on)
    cap_key = (
        "gst.dr.cap.affordable" if regime == GstRegime.AFFORDABLE_1PC else "gst.dr.cap.residential"
    )
    cap_rate = rules.value(cap_key, on)

    def liability(area: Decimal, value: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        share = dr_value * rate * area / total_area
        cap = value * cap_rate
        return rupees(share), rupees(cap), rupees(min(share, cap))

    share, cap, owed = liability(unbooked_area, unbooked_value)
    saving = ZERO
    if unbooked:
        n = Decimal(len(unbooked))
        _, _, after = liability(
            unbooked_area - unbooked_area / n, unbooked_value - unbooked_value / n
        )
        saving = owed - after

    return DevelopmentRightsGst(
        applies=True,
        dr_value=dr_value,
        total_residential_area=total_area,
        unbooked_area=unbooked_area,
        unbooked_value=unbooked_value,
        unbooked_units=len(unbooked),
        gst_on_unbooked_share=share,
        cap=cap,
        liability=owed,
        capped=cap < share,
        saving_per_unit_sold=saving,
    )


# Guidance value (s.43CA)


@dataclass(frozen=True)
class Sale:
    unit_label: str
    agreement_value: Decimal
    guidance_value: Decimal
    booked_on: date


@dataclass(frozen=True)
class GuidanceValueFlag:
    sale: Sale
    gap: Decimal
    gap_pct: Decimal
    deemed_income: Decimal
    estimated_tax: Decimal


def guidance_value_flags(
    sales: list[Sale], *, on: date, rules: RulesPack
) -> list[GuidanceValueFlag]:
    """Sales where guidance value exceeds the price by more than the tolerance.

    Read as a cliff: once outside the tolerance, the whole gap is treated as
    income. Some commentators read it otherwise; the rule is marked secondary.
    """
    tolerance = rules.value("it.s43ca.tolerance", on)
    tax_rate = rules.value("it.assumed_tax_rate", on)
    flags = []
    for sale in sales:
        if sale.guidance_value > sale.agreement_value * (1 + tolerance):
            gap = sale.guidance_value - sale.agreement_value
            flags.append(
                GuidanceValueFlag(
                    sale=sale,
                    gap=gap,
                    gap_pct=percent(gap, sale.agreement_value),
                    deemed_income=gap,
                    estimated_tax=rupees(gap * tax_rate),
                )
            )
    return flags


# TDS on payments to landowners (s.194-IC)


@dataclass(frozen=True)
class LandownerPayment:
    landowner: str
    amount: Decimal
    on: date
    tds_deducted: Decimal
    monetary_consideration: bool = True


@dataclass(frozen=True)
class TdsShortfall:
    payment: LandownerPayment
    expected: Decimal
    short: Decimal


def landowner_tds_shortfalls(
    payments: list[LandownerPayment], *, rules: RulesPack
) -> list[TdsShortfall]:
    out = []
    for payment in payments:
        if not payment.monetary_consideration:
            continue
        expected = rupees(payment.amount * rules.value("it.s194ic.rate", payment.on))
        if payment.tds_deducted < expected:
            out.append(
                TdsShortfall(
                    payment=payment, expected=expected, short=expected - payment.tds_deducted
                )
            )
    return out


# MSME 45-day clock


class MsmeCategory(StrEnum):
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    NONE = "none"


@dataclass(frozen=True)
class SupplierBill:
    vendor: str
    bill_no: str
    amount: Decimal
    accepted_on: date
    msme: MsmeCategory
    written_agreement: bool
    paid_on: date | None = None


class MsmeStatus(StrEnum):
    OK = "ok"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    PAID_ON_TIME = "paid_on_time"
    PAID_LATE = "paid_late"


@dataclass(frozen=True)
class MsmeItem:
    bill: SupplierBill
    due_on: date
    status: MsmeStatus
    days_left: int


def msme_clock(bills: list[SupplierBill], *, as_of: date, rules: RulesPack) -> list[MsmeItem]:
    items = []
    for bill in bills:
        if bill.msme not in (MsmeCategory.MICRO, MsmeCategory.SMALL):
            continue
        key = (
            "it.msme.days_with_agreement"
            if bill.written_agreement
            else "it.msme.days_without_agreement"
        )
        try:
            days = rules.value(key, bill.accepted_on)
        except RuleNotFound:
            continue  # the rule did not apply when the bill was accepted
        due = bill.accepted_on + timedelta(days=days)
        warning = rules.value("it.msme.warning_days", as_of)
        if bill.paid_on is not None:
            status = MsmeStatus.PAID_ON_TIME if bill.paid_on <= due else MsmeStatus.PAID_LATE
        elif as_of > due:
            status = MsmeStatus.OVERDUE
        elif (due - as_of).days <= warning:
            status = MsmeStatus.DUE_SOON
        else:
            status = MsmeStatus.OK
        items.append(MsmeItem(bill=bill, due_on=due, status=status, days_left=(due - as_of).days))
    return items


# BOCW labour cess


@dataclass(frozen=True)
class CessPosition:
    construction_estimate: Decimal
    construction_incurred: Decimal
    cess_on_estimate: Decimal
    cess_due_to_date: Decimal
    cess_paid: Decimal
    balance_due: Decimal


def bocw_cess(
    money: ProjectPosition, cess_paid: Decimal, *, as_of: date, rules: RulesPack
) -> CessPosition:
    rate = rules.value("labour.bocw_cess_rate", as_of)
    lines = [p for p in money.lines if p.line.category == Category.CONSTRUCTION]
    estimate = sum((p.anticipated_final_cost for p in lines), ZERO)
    incurred = sum((p.incurred for p in lines), ZERO)
    due = rupees(incurred * rate)
    return CessPosition(
        construction_estimate=estimate,
        construction_incurred=incurred,
        cess_on_estimate=rupees(estimate * rate),
        cess_due_to_date=due,
        cess_paid=cess_paid,
        balance_due=max(due - cess_paid, ZERO),
    )


# Delay interest owed to buyers (RERA s.18)


@dataclass(frozen=True)
class DelayExposure:
    possession_due_on: date | None
    as_of: date
    days_late: int
    days_to_possession: int | None
    annual_rate: Decimal
    buyer_money: Decimal
    accrued: Decimal
    per_month: Decimal


def delay_interest(
    buyer_money: Decimal, possession_due_on: date | None, *, as_of: date, rules: RulesPack
) -> DelayExposure:
    """Simple interest on what buyers have paid, from the committed possession date.

    Uses buyer money received to date as the base; per-receipt timing is a
    refinement for later.
    """
    rate = rules.value("rera.sbi_mclr", as_of) + rules.value("rera.delay_interest_margin", as_of)
    per_month = rupees(buyer_money * rate / 12)
    if possession_due_on is None:
        return DelayExposure(None, as_of, 0, None, rate, buyer_money, ZERO, per_month)
    days_late = max((as_of - possession_due_on).days, 0)
    accrued = rupees(buyer_money * rate * days_late / 365)
    days_to = (possession_due_on - as_of).days if as_of <= possession_due_on else None
    return DelayExposure(
        possession_due_on, as_of, days_late, days_to, rate, buyer_money, accrued, per_month
    )
