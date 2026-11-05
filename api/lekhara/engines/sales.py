"""Selling a unit: the cost sheet a buyer is shown, and what a channel partner is owed.

The cost sheet adds up what the buyer pays for the unit (the agreement value: the base rate on
the carpet area, floor rise, preferential location charges, the car park and amenities), the GST
on it at the project's rate, the charges collected at handover, and the stamp duty and fees the
buyer pays at registration. It warns when the price, after any discount, falls more than the
tolerance below the guidance value (s.43CA), with the tax that would cost the firm.

A channel partner's commission is a share of the agreement value, falling due once the buyer
has paid a set share of it. GST is added for a registered partner, and TDS is deducted once the
year's commission to the partner passes the threshold.

Rates come from the rules pack, where each one says how sure it is.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lekhara.engines.handover import RegistrationCost, registration_cost
from lekhara.money import ZERO, rupees
from lekhara.rules import RulesPack

GST_RULE = {
    "affordable_1pc": "gst.rate.affordable",
    "residential_5pc": "gst.rate.residential",
    "commercial_12pc": "gst.rate.commercial",
    "rrep_mixed": "gst.rate.residential",
}


def _rate(value: Decimal) -> str:
    """A rate as it is said aloud: 10,400 or 4.5."""
    return f"{value.normalize():,f}"


def floor_of(label: str) -> int:
    """The floor from a unit number written tower-floor-flat (A-0304 is the third floor);
    0 when the number does not say."""
    m = re.search(r"(\d{2})(\d{2})$", label or "")
    return int(m.group(1)) if m else 0


@dataclass(frozen=True)
class PriceListIn:
    base_rate: Decimal
    """Per square foot of carpet area."""
    floor_rise: Decimal = ZERO
    """Per square foot, for each floor above `floor_rise_from`."""
    floor_rise_from: int = 1
    plc: dict[str, Decimal] = field(default_factory=dict)
    """Preferential location charges, per square foot: corner, park-facing and the like."""
    car_park: Decimal = ZERO
    amenities: Decimal = ZERO
    other_charges: Decimal = ZERO
    """BESCOM and BWSSB deposits, legal and documentation charges, collected at handover."""
    corpus_per_sqft: Decimal = ZERO
    maintenance_per_sqft_month: Decimal = ZERO
    maintenance_months: int = 0


@dataclass(frozen=True)
class Line:
    label: str
    amount: Decimal
    detail: str = ""


@dataclass(frozen=True)
class CostSheet:
    unit_label: str
    carpet_area_sqft: int
    agreement_lines: tuple[Line, ...]
    agreement_value: Decimal
    gst_rate: Decimal
    gst: Decimal
    handover_lines: tuple[Line, ...]
    registration: RegistrationCost
    agreement_stamp_duty: Decimal
    total: Decimal
    rate_per_sqft: Decimal
    tds_rate: Decimal
    tds: Decimal
    guidance_value: Decimal
    below_guidance: bool
    guidance_gap: Decimal
    guidance_tax: Decimal


def cost_sheet(
    *,
    unit_label: str,
    carpet_area_sqft: int,
    guidance_value: Decimal,
    prices: PriceListIn,
    gst_regime: str,
    plc: list[str] = (),
    discount_per_sqft: Decimal = ZERO,
    on: date,
    rules: RulesPack,
) -> CostSheet:
    area = Decimal(carpet_area_sqft)
    floors_above = max(floor_of(unit_label) - prices.floor_rise_from + 1, 0)
    lines = [Line("Basic price", rupees(area * prices.base_rate),
                  f"{carpet_area_sqft} sq ft at {_rate(prices.base_rate)} a sq ft")]  # fmt: skip
    if prices.floor_rise and floors_above:
        rise = rupees(area * prices.floor_rise * floors_above)
        floors = f"{floors_above} floor{'' if floors_above == 1 else 's'}"
        lines.append(Line("Floor rise", rise, f"{floors} at {_rate(prices.floor_rise)} a sq ft"))
    for name in plc:
        if name in prices.plc:
            charge = rupees(area * prices.plc[name])
            lines.append(Line(f"Location: {name}", charge, f"{_rate(prices.plc[name])} a sq ft"))
    if prices.car_park:
        lines.append(Line("Car park", rupees(prices.car_park)))
    if prices.amenities:
        lines.append(Line("Amenities and clubhouse", rupees(prices.amenities)))
    if discount_per_sqft:
        lines.append(Line("Discount", -rupees(area * discount_per_sqft),
                          f"{_rate(discount_per_sqft)} a sq ft"))  # fmt: skip
    agreement_value = sum((line.amount for line in lines), ZERO)
    gst_rate = rules.value(GST_RULE.get(gst_regime, "gst.rate.residential"), on)
    gst = rupees(agreement_value * gst_rate)

    handover = []
    if prices.other_charges:
        handover.append(Line("Electricity, water and legal charges", rupees(prices.other_charges)))
    if prices.corpus_per_sqft:
        handover.append(Line("Corpus fund", rupees(area * prices.corpus_per_sqft),
                             f"{_rate(prices.corpus_per_sqft)} a sq ft"))  # fmt: skip
    if prices.maintenance_per_sqft_month and prices.maintenance_months:
        handover.append(Line(
            "Maintenance in advance",
            rupees(area * prices.maintenance_per_sqft_month * prices.maintenance_months),
            f"{prices.maintenance_months} months at "
            f"{_rate(prices.maintenance_per_sqft_month)} a sq ft",
        ))  # fmt: skip

    registration = registration_cost(agreement_value, guidance_value, on=on, rules=rules)
    agreement_stamp = min(
        rupees(agreement_value * rules.value("reg.agreement_stamp_rate", on)),
        rules.value("reg.agreement_stamp_cap", on),
    )
    handover_total = sum((line.amount for line in handover), ZERO)
    total = agreement_value + gst + handover_total + registration.total + agreement_stamp

    tds_rate = rules.value("it.s194ia.rate", on)
    tds = (
        rupees(agreement_value * tds_rate)
        if agreement_value >= rules.value("it.s194ia.threshold", on)
        else ZERO
    )
    tolerance = rules.value("it.s43ca.tolerance", on)
    below = guidance_value > agreement_value * (1 + tolerance)
    gap = guidance_value - agreement_value if below else ZERO
    return CostSheet(
        unit_label=unit_label,
        carpet_area_sqft=carpet_area_sqft,
        agreement_lines=tuple(lines),
        agreement_value=agreement_value,
        gst_rate=gst_rate,
        gst=gst,
        handover_lines=tuple(handover),
        registration=registration,
        agreement_stamp_duty=agreement_stamp,
        total=total,
        rate_per_sqft=rupees(agreement_value / area) if area else ZERO,
        tds_rate=tds_rate,
        tds=tds,
        guidance_value=guidance_value,
        below_guidance=below,
        guidance_gap=gap,
        guidance_tax=rupees(gap * rules.value("it.assumed_tax_rate", on)) if below else ZERO,
    )


# What a channel partner is owed


@dataclass(frozen=True)
class CommissionIn:
    agreement_value: Decimal
    rate_pct: Decimal
    """A percentage: 2 means 2%."""
    registered_for_gst: bool
    paid_to_partner_this_year: Decimal
    """Commission already paid to the partner in the financial year, before this one."""


@dataclass(frozen=True)
class CommissionOut:
    amount: Decimal
    gst: Decimal
    tds: Decimal
    payable: Decimal


def commission(c: CommissionIn, *, on: date, rules: RulesPack) -> CommissionOut:
    amount = rupees(c.agreement_value * c.rate_pct / 100)
    gst = rupees(amount * rules.value("gst.brokerage_rate", on)) if c.registered_for_gst else ZERO
    threshold = rules.value("it.brokerage_tds_threshold", on)
    over = c.paid_to_partner_this_year + amount > threshold
    tds = rupees(amount * rules.value("it.brokerage_tds_rate", on)) if over else ZERO
    return CommissionOut(amount=amount, gst=gst, tds=tds, payable=amount + gst - tds)


def commission_due(received: Decimal, agreement_value: Decimal, after_share_pct: Decimal) -> bool:
    """Whether the buyer has paid enough of the agreement value for the commission to fall due."""
    return agreement_value > 0 and received >= agreement_value * after_share_pct / 100
