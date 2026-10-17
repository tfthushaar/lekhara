"""Karnataka rules pack, version 1.

Every entry states its legal basis and source quality. Entries marked unverified
or unsettled must be confirmed by the customer's CA or lawyer before Horus
figures based on them are relied on.
"""

from datetime import date
from decimal import Decimal

from horus.rules.pack import Rule, RulesPack, SourceQuality

RERA_IN_FORCE = date(2017, 5, 1)
GST_SCHEME_2019 = date(2019, 4, 1)
LABOUR_CODES = date(2025, 11, 21)
ALWAYS = date(2000, 1, 1)
"""Horus settings are not law; they apply on any date."""

_RERA_ACT = "Real Estate (Regulation and Development) Act, 2016"
_KRERA_RULES = "Karnataka Real Estate (Regulation and Development) Rules"
_NOTIF_03_2019 = "Notification 03/2019-Central Tax (Rate)"
_JDA_NOTIFS = "Notifications 04/2019, 05/2019 and 06/2019-Central Tax (Rate)"

_rules = (
    # Escrow: the designated account and withdrawals
    Rule(
        key="escrow.deposit_share",
        value=Decimal("0.70"),
        title="Share of buyer receipts to deposit in the designated account",
        basis=f"{_RERA_ACT}, s.4(2)(l)(D)",
        source_quality=SourceQuality.OFFICIAL,
        confirm_against=_KRERA_RULES,
        effective_from=RERA_IN_FORCE,
    ),
    Rule(
        key="escrow.withdrawal_cost_basis",
        value="incurred_and_paid",
        title="Cost used to work out how much can be withdrawn",
        basis="State withdrawal certificate formats (CA certificate)",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="K-RERA withdrawal certificate format",
        effective_from=RERA_IN_FORCE,
        note=(
            "Some states use cost incurred, others cost incurred and paid. Horus uses the "
            "stricter of the two until the K-RERA format is confirmed."
        ),
    ),
    Rule(
        key="escrow.ongoing_ratio_threshold",
        value=Decimal("1"),
        title="Receivables-to-balance-cost ratio above which 70% (not 100%) must be deposited",
        basis="State withdrawal certificate formats for ongoing projects",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="K-RERA rules for ongoing projects",
        effective_from=RERA_IN_FORCE,
    ),
    Rule(
        key="escrow.cycle_days",
        value=90,
        title="Days after which withdrawal certificates are usually renewed",
        basis="ICAI guidance on RERA withdrawal certificates",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="K-RERA rules and the escrow bank's practice",
        effective_from=RERA_IN_FORCE,
        note="Certificates are renewed when the previous limit is used up, or about every 90 days.",
    ),
    Rule(
        key="escrow.figure_tolerance",
        value=Decimal("0.005"),
        title="How far certificate figures may differ from the books before Horus flags them",
        basis="Horus setting",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Not a legal rule",
        effective_from=ALWAYS,
    ),
    Rule(
        key="escrow.progress_gap_points",
        value=Decimal("10"),
        title="Gap between cost incurred and certified progress that Horus flags",
        basis="Horus setting, mirroring the K-RERA audit cross-check",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Not a legal rule",
        effective_from=ALWAYS,
    ),
    Rule(
        key="escrow.certificate_window_days",
        value=30,
        title="Maximum days between the three certificates in one withdrawal",
        basis="Horus setting",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="The escrow bank's practice",
        effective_from=ALWAYS,
    ),
    Rule(
        key="escrow.min_suggested_withdrawal",
        value=Decimal("1000000"),
        title="Drawable amount at which Horus suggests starting a withdrawal",
        basis="Horus setting",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Not a legal rule",
        effective_from=ALWAYS,
    ),
    # K-RERA
    Rule(
        key="krera.qpr_due_days",
        value=15,
        title="Days after quarter end by which the quarterly progress report is due",
        basis="Common state practice",
        source_quality=SourceQuality.UNVERIFIED,
        confirm_against="K-RERA regulations on quarterly updates",
        effective_from=RERA_IN_FORCE,
    ),
    Rule(
        key="krera.qpr_late_fee_per_quarter",
        value=Decimal("25000"),
        title="Base penalty for a late or missing quarterly progress report",
        basis="K-RERA circular of 20 January 2026 (as reported)",
        source_quality=SourceQuality.UNVERIFIED,
        confirm_against="The K-RERA circular of 20 January 2026",
        effective_from=date(2026, 1, 20),
    ),
    Rule(
        key="krera.qpr_max_penalty_share",
        value=Decimal("0.05"),
        title="Maximum penalty for serious or repeated non-compliance, as a share of project cost",
        basis="K-RERA circular of 20 January 2026 (as reported)",
        source_quality=SourceQuality.UNVERIFIED,
        confirm_against="The K-RERA circular of 20 January 2026",
        effective_from=date(2026, 1, 20),
    ),
    Rule(
        key="krera.annual_audit_months",
        value=6,
        title="Months after financial year end by which project accounts must be audited",
        basis=f"{_RERA_ACT}, s.4(2)(l)(D)",
        source_quality=SourceQuality.OFFICIAL,
        confirm_against=_KRERA_RULES,
        effective_from=RERA_IN_FORCE,
    ),
    Rule(
        key="rera.delay_interest_margin",
        value=Decimal("0.02"),
        title="Margin over the SBI rate for interest owed to buyers on delayed possession",
        basis=f"{_RERA_ACT}, s.18; {_KRERA_RULES}",
        source_quality=SourceQuality.SECONDARY,
        confirm_against=_KRERA_RULES,
        effective_from=RERA_IN_FORCE,
    ),
    Rule(
        key="rera.sbi_mclr",
        value=Decimal("0.0895"),
        title="SBI marginal cost of lending rate used for delay interest",
        basis="Reported SBI MCLR; sources differ between 8.15% and 8.95%",
        source_quality=SourceQuality.UNVERIFIED,
        confirm_against="SBI's published MCLR on the relevant date",
        effective_from=date(2026, 1, 1),
        note="Set from SBI's published rate before relying on delay interest figures.",
    ),
    # GST on residential real estate
    Rule(
        key="gst.rate.affordable",
        value=Decimal("0.01"),
        title="GST on affordable housing, without input tax credit",
        basis="GST rate notifications for residential real estate",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="Current CBIC rate notifications",
        effective_from=GST_SCHEME_2019,
    ),
    Rule(
        key="gst.rate.residential",
        value=Decimal("0.05"),
        title="GST on other residential housing, without input tax credit",
        basis="GST rate notifications for residential real estate",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="Current CBIC rate notifications",
        effective_from=GST_SCHEME_2019,
    ),
    Rule(
        key="gst.rate.commercial",
        value=Decimal("0.12"),
        title="GST on commercial property outside a residential project, with input tax credit",
        basis="GST rate notifications for real estate",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="Current CBIC rate notifications",
        effective_from=GST_SCHEME_2019,
    ),
    Rule(
        key="gst.procurement.min_registered_share",
        value=Decimal("0.80"),
        title="Minimum share of inputs to buy from GST-registered suppliers, per project per year",
        basis=_NOTIF_03_2019,
        source_quality=SourceQuality.OFFICIAL,
        confirm_against="The current text of the notification",
        effective_from=GST_SCHEME_2019,
    ),
    Rule(
        key="gst.procurement.shortfall_rcm_rate",
        value=Decimal("0.18"),
        title="Reverse charge on the shortfall below the registered-supplier minimum",
        basis=_NOTIF_03_2019,
        source_quality=SourceQuality.OFFICIAL,
        confirm_against="The current text of the notification",
        effective_from=GST_SCHEME_2019,
    ),
    Rule(
        key="gst.procurement.cement_rcm_rate",
        value=Decimal("0.28"),
        title="Reverse charge on cement bought from unregistered suppliers",
        basis=_NOTIF_03_2019,
        source_quality=SourceQuality.UNSETTLED,
        confirm_against="Current cement GST rate and reverse charge notifications",
        effective_from=GST_SCHEME_2019,
        note=(
            "Cement was reported to move from 28% to 18% in the 22 September 2025 rate "
            "rationalisation. Confirm which rate applies to reverse charge on unregistered cement."
        ),
    ),
    Rule(
        key="gst.procurement.payment_due",
        value=(6, 30),
        title="Month and day of the following financial year by which the shortfall tax is paid",
        basis="CBIC clarification on paying the shortfall through DRC-03",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="The CBIC circular",
        effective_from=GST_SCHEME_2019,
    ),
    Rule(
        key="gst.dr.rcm_rate",
        value=Decimal("0.18"),
        title="GST on development rights attributable to flats unbooked at completion",
        basis=_JDA_NOTIFS,
        source_quality=SourceQuality.UNSETTLED,
        confirm_against="The notifications and your CA",
        effective_from=GST_SCHEME_2019,
    ),
    Rule(
        key="gst.dr.cap.affordable",
        value=Decimal("0.01"),
        title="Cap on GST on development rights, as a share of unbooked affordable flats' value",
        basis=_JDA_NOTIFS,
        source_quality=SourceQuality.UNSETTLED,
        confirm_against="The notifications and your CA",
        effective_from=GST_SCHEME_2019,
    ),
    Rule(
        key="gst.dr.cap.residential",
        value=Decimal("0.05"),
        title="Cap on GST on development rights, as a share of unbooked flats' value",
        basis=_JDA_NOTIFS,
        source_quality=SourceQuality.UNSETTLED,
        confirm_against="The notifications and your CA",
        effective_from=GST_SCHEME_2019,
        note=(
            "Liability is the lower of GST on the unbooked share of development rights and "
            "1% or 5% of the unbooked flats' value. Sources differ on details."
        ),
    ),
    # Income tax
    Rule(
        key="it.s43ca.tolerance",
        value=Decimal("0.10"),
        title="How far guidance value may exceed the sale price before the gap is taxed",
        basis="Income-tax Act, s.43CA (stamp duty value of stock-in-trade)",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="Income-tax Act 2025 text",
        effective_from=date(2021, 4, 1),
    ),
    Rule(
        key="it.assumed_tax_rate",
        value=Decimal("0.2517"),
        title="Tax rate used only to estimate tax on deemed income",
        basis="Horus setting",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Your company's actual tax rate",
        effective_from=ALWAYS,
    ),
    Rule(
        key="it.s194ic.rate",
        value=Decimal("0.10"),
        title="TDS on money paid to a resident landowner under a joint development agreement",
        basis="Income-tax Act, s.194-IC",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="Income-tax Act 2025 text",
        effective_from=date(2017, 4, 1),
    ),
    Rule(
        key="it.s194ia.rate",
        value=Decimal("0.01"),
        title="TDS deducted by buyers on property purchases above the threshold",
        basis="Income-tax Act, s.194IA",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="Income-tax Act 2025 text",
        effective_from=date(2013, 6, 1),
    ),
    Rule(
        key="it.s194ia.threshold",
        value=Decimal("5000000"),
        title="Sale value above which buyers deduct TDS",
        basis="Income-tax Act, s.194IA",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="Income-tax Act 2025 text",
        effective_from=date(2013, 6, 1),
    ),
    Rule(
        key="it.msme.days_with_agreement",
        value=45,
        title="Days to pay a micro or small supplier when there is a written agreement",
        basis="Income-tax Act s.43B(h), now s.37(2)(g) of the Income-tax Act 2025; MSMED Act s.15",
        source_quality=SourceQuality.OFFICIAL,
        confirm_against="The statute and CBDT guidance",
        effective_from=date(2024, 4, 1),
    ),
    Rule(
        key="it.msme.days_without_agreement",
        value=15,
        title="Days to pay a micro or small supplier when there is no written agreement",
        basis="Income-tax Act s.43B(h), now s.37(2)(g) of the Income-tax Act 2025; MSMED Act s.15",
        source_quality=SourceQuality.OFFICIAL,
        confirm_against="The statute and CBDT guidance",
        effective_from=date(2024, 4, 1),
    ),
    Rule(
        key="it.msme.warning_days",
        value=7,
        title="Days before the MSME deadline when Horus warns",
        basis="Horus setting",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Not a legal rule",
        effective_from=ALWAYS,
    ),
    # Labour
    Rule(
        key="labour.bocw_cess_rate",
        value=Decimal("0.01"),
        title="Building and other construction workers' welfare cess on construction cost",
        basis="Building and Other Construction Workers' Welfare Cess Act, 1996",
        source_quality=SourceQuality.SECONDARY,
        confirm_against="Karnataka Building and Other Construction Workers' Welfare Board",
        effective_from=date(1996, 8, 19),
    ),
    # Money engine settings
    Rule(
        key="money.cost_ahead_points",
        value=Decimal("10"),
        title="Points by which cost incurred may lead certified progress before Horus warns",
        basis="Horus setting, mirroring the K-RERA audit cross-check",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Not a legal rule",
        effective_from=ALWAYS,
    ),
    Rule(
        key="obligations.due_soon_days",
        value=14,
        title="Days before a deadline when Horus marks it as due soon",
        basis="Horus setting",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Not a legal rule",
        effective_from=ALWAYS,
    ),
    Rule(
        key="obligations.headroom_warning_points",
        value=Decimal("5"),
        title="Points above the 80% minimum at which Horus starts showing purchase headroom",
        basis="Horus setting",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Not a legal rule",
        effective_from=ALWAYS,
    ),
    Rule(
        key="money.contingency_low_share",
        value=Decimal("0.25"),
        title="Remaining share of contingency below which Horus warns",
        basis="Horus setting",
        source_quality=SourceQuality.HORUS_DEFAULT,
        confirm_against="Not a legal rule",
        effective_from=ALWAYS,
    ),
)

KARNATAKA = RulesPack(state="KA", version="2026-10-17", rules=_rules)
