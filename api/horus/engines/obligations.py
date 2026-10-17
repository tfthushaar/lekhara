"""Obligations engine: everything a project owes outside parties, as one dated list.

Each obligation says what is owed, to whom, by when, what is at stake and which
rule it comes from, in plain words. The Today screen is this list across all
projects, most urgent first.
"""

from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from horus.engines.escrow import EscrowPosition
from horus.engines.tax import (
    CessPosition,
    DelayExposure,
    DevelopmentRightsGst,
    GuidanceValueFlag,
    MsmeItem,
    MsmeStatus,
    ProcurementMeter,
    TdsShortfall,
    financial_year,
)
from horus.money import ZERO
from horus.rules import RuleNotFound, RulesPack


class ObligationStatus(StrEnum):
    OVERDUE = "overdue"
    DUE_SOON = "due_soon"
    AT_RISK = "at_risk"
    OPPORTUNITY = "opportunity"
    UPCOMING = "upcoming"
    DONE = "done"


STATUS_ORDER = {status: i for i, status in enumerate(ObligationStatus)}


class Area(StrEnum):
    """The part of the product where the obligation is handled."""

    ESCROW = "escrow"
    KRERA = "krera"
    TAX = "tax"
    UNITS = "units"


@dataclass(frozen=True)
class Obligation:
    key: str
    project_id: str
    project_name: str
    title: str
    detail: str
    owed_to: str
    status: ObligationStatus
    area: Area
    due_on: date | None = None
    amount: Decimal | None = None
    rule_key: str | None = None
    action: str | None = None


@dataclass(frozen=True)
class ProjectFacts:
    project_id: str
    project_name: str
    as_of: date
    registered_on: date
    estimated_cost: Decimal
    escrow: EscrowPosition
    procurement: ProcurementMeter
    development_rights: DevelopmentRightsGst
    msme: list[MsmeItem]
    delay: DelayExposure
    guidance_flags: list[GuidanceValueFlag]
    landowner_tds: list[TdsShortfall]
    cess: CessPosition
    qpr_filed: set[date] = field(default_factory=set)
    """Quarter-end dates for which the quarterly progress report has been filed."""
    audits_done: set[int] = field(default_factory=set)
    """Start years of financial years whose annual project audit is done."""


def _quarter_ends(start: date, end: date) -> list[date]:
    ends = []
    year = start.year
    while True:
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qe = date(year, month, day)
            if qe > end:
                return ends
            if qe >= start:
                ends.append(qe)
        year += 1


def _dated_status(due: date, as_of: date, soon_days: int) -> ObligationStatus:
    if due < as_of:
        return ObligationStatus.OVERDUE
    if (due - as_of).days <= soon_days:
        return ObligationStatus.DUE_SOON
    return ObligationStatus.UPCOMING


def _month_end_after(d: date, months: int) -> date:
    """Last day of the month that is `months` after the month of `d`."""
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    first_of_next = date(year + month // 12, month % 12 + 1, 1)
    return first_of_next - timedelta(days=1)


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def project_obligations(f: ProjectFacts, *, rules: RulesPack) -> list[Obligation]:
    soon = rules.value("obligations.due_soon_days", f.as_of)
    out: list[Obligation] = []

    def add(**kwargs) -> None:
        out.append(Obligation(project_id=f.project_id, project_name=f.project_name, **kwargs))

    # Escrow
    e = f.escrow
    if e.suggest_withdrawal:
        add(
            key="escrow:withdraw",
            title="Money is waiting in the RERA account",
            detail=(
                "Cost incurred allows a withdrawal now. Horus has prepared the three "
                "certificates for your architect, engineer and CA."
            ),
            owed_to="Escrow bank",
            status=ObligationStatus.OPPORTUNITY,
            area=Area.ESCROW,
            due_on=f.as_of,
            amount=e.drawable_now,
            rule_key="escrow.withdrawal_cost_basis",
            action="Start a withdrawal",
        )
    elif e.next_cycle_due_on and (e.next_cycle_due_on - f.as_of).days <= 30:
        add(
            key="escrow:cycle",
            title="Withdrawal certificates are due for renewal",
            detail="The last certificates will be about 90 days old. Plan the next cycle.",
            owed_to="Escrow bank",
            status=_dated_status(e.next_cycle_due_on, f.as_of, soon),
            area=Area.ESCROW,
            due_on=e.next_cycle_due_on,
            rule_key="escrow.cycle_days",
            action="Open escrow",
        )
    if e.deposit_shortfall > 0:
        add(
            key="escrow:deposit",
            title="Deposits into the RERA account are short",
            detail=(
                "70% of buyer receipts must go into the designated account. "
                "Deposit the difference to stay compliant."
            ),
            owed_to="K-RERA",
            status=ObligationStatus.OVERDUE,
            area=Area.ESCROW,
            amount=e.deposit_shortfall,
            rule_key="escrow.deposit_share",
            action="Open escrow",
        )

    # Quarterly progress reports
    late_fee = None
    with suppress(RuleNotFound):
        late_fee = rules.value("krera.qpr_late_fee_per_quarter", f.as_of)
    due_days = rules.value("krera.qpr_due_days", f.as_of)
    horizon = f.as_of + timedelta(days=100)
    for qe in _quarter_ends(f.registered_on, horizon):
        if qe in f.qpr_filed:
            continue
        due = qe + timedelta(days=due_days)
        label = f"quarter ending {_fmt(qe)}"
        if due < f.as_of:
            add(
                key=f"qpr:{qe.isoformat()}",
                title="Quarterly progress report is late",
                detail=f"The K-RERA report for the {label} was due on {_fmt(due)}.",
                owed_to="K-RERA",
                status=ObligationStatus.OVERDUE,
                area=Area.KRERA,
                due_on=due,
                amount=late_fee,
                rule_key="krera.qpr_due_days",
                action="Prepare the report",
            )
            continue
        add(
            key=f"qpr:{qe.isoformat()}",
            title="Quarterly progress report",
            detail=f"The K-RERA report for the {label} is due on {_fmt(due)}.",
            owed_to="K-RERA",
            status=_dated_status(due, f.as_of, soon),
            area=Area.KRERA,
            due_on=due,
            rule_key="krera.qpr_due_days",
            action="Prepare the report",
        )
        break

    # Annual project audit
    months = rules.value("krera.annual_audit_months", f.as_of)
    fy_start, _ = financial_year(f.as_of)
    previous_fy_end = fy_start - timedelta(days=1)
    if previous_fy_end > f.registered_on and (fy_start.year - 1) not in f.audits_done:
        due = _month_end_after(previous_fy_end, months)
        status = _dated_status(due, f.as_of, soon)
        if status != ObligationStatus.UPCOMING or (due - f.as_of).days <= 60:
            add(
                key=f"audit:{fy_start.year - 1}",
                title="Annual project audit",
                detail=(
                    f"Project accounts for {fy_start.year - 1}-{str(fy_start.year)[2:]} must be "
                    f"audited by a CA by {_fmt(due)}."
                ),
                owed_to="K-RERA",
                status=status,
                area=Area.KRERA,
                due_on=due,
                rule_key="krera.annual_audit_months",
                action="Prepare the audit pack",
            )

    # Delay interest and the possession date
    d = f.delay
    if d.possession_due_on is not None:
        if d.days_late > 0:
            add(
                key="rera:delay",
                title="Possession is late; delay interest is building up",
                detail=(
                    f"Possession was due on {_fmt(d.possession_due_on)}, {d.days_late} days ago. "
                    "Each month of delay adds interest owed to buyers."
                ),
                owed_to="Buyers",
                status=ObligationStatus.OVERDUE,
                area=Area.KRERA,
                due_on=d.possession_due_on,
                amount=d.accrued,
                rule_key="rera.delay_interest_margin",
                action="See the exposure",
            )
        elif d.days_to_possession is not None and d.days_to_possession <= 120:
            add(
                key="rera:possession",
                title=f"Possession is due in {d.days_to_possession} days",
                detail=(
                    "If possession slips, delay interest owed to buyers starts at this amount "
                    "a month."
                ),
                owed_to="Buyers",
                status=ObligationStatus.AT_RISK,
                area=Area.KRERA,
                due_on=d.possession_due_on,
                amount=d.per_month,
                rule_key="rera.delay_interest_margin",
                action="See the exposure",
            )

    # GST: the 80% registered-procurement test
    p = f.procurement
    if p.applies and p.total > 0:
        if p.shortfall > 0:
            add(
                key=f"gst80:{p.fy}",
                title="Purchases from registered suppliers are below 80% this year",
                detail=(
                    f"{p.registered_share_pct}% of this year's inputs are from registered "
                    "suppliers. Reverse charge on the shortfall is due by "
                    f"{_fmt(p.payment_due_on)} unless more is bought from registered suppliers."
                ),
                owed_to="GST",
                status=ObligationStatus.AT_RISK,
                area=Area.TAX,
                due_on=p.payment_due_on,
                amount=p.rcm_on_shortfall,
                rule_key="gst.procurement.min_registered_share",
                action="See the meter",
            )
        elif p.registered_share_pct - p.min_share_pct < rules.value(
            "obligations.headroom_warning_points", f.as_of
        ):
            add(
                key=f"gst80:{p.fy}",
                title="Close to the 80% registered-supplier limit",
                detail=(
                    "Only this much more can be bought from unregistered suppliers this year "
                    "before reverse charge applies."
                ),
                owed_to="GST",
                status=ObligationStatus.UPCOMING,
                area=Area.TAX,
                due_on=p.payment_due_on,
                amount=p.unregistered_headroom,
                rule_key="gst.procurement.min_registered_share",
                action="See the meter",
            )

    # GST on development rights at completion
    dr = f.development_rights
    if dr.applies and dr.liability > 0:
        add(
            key="gst:dr",
            title="GST on development rights falls due at completion",
            detail=(
                f"{dr.unbooked_units} of your flats are unbooked. If they are still unbooked at "
                "completion, this is payable in cash. Each flat sold before then lowers it."
            ),
            owed_to="GST",
            status=ObligationStatus.AT_RISK,
            area=Area.TAX,
            due_on=f.delay.possession_due_on,
            amount=dr.liability,
            rule_key="gst.dr.rcm_rate",
            action="See the forecast",
        )

    # Guidance value
    for flag in f.guidance_flags:
        add(
            key=f"s43ca:{flag.sale.unit_label}",
            title=f"Unit {flag.sale.unit_label} is sold well below guidance value",
            detail=(
                f"The price is {flag.gap_pct}% below guidance value. The gap may be taxed as "
                "income; the amount shown is the estimated tax."
            ),
            owed_to="Income tax",
            status=ObligationStatus.AT_RISK,
            area=Area.TAX,
            due_on=flag.sale.booked_on,
            amount=flag.estimated_tax,
            rule_key="it.s43ca.tolerance",
            action="See the sale",
        )

    # TDS to landowners
    for s in f.landowner_tds:
        add(
            key=f"s194ic:{s.payment.landowner}:{s.payment.on.isoformat()}",
            title=f"TDS short on a payment to {s.payment.landowner}",
            detail=f"10% TDS applies to money paid under the JDA. Paid on {_fmt(s.payment.on)}.",
            owed_to="Income tax",
            status=ObligationStatus.OVERDUE,
            area=Area.UNITS,
            due_on=s.payment.on,
            amount=s.short,
            rule_key="it.s194ic.rate",
            action="See landowner payments",
        )

    # MSME payments
    for item in f.msme:
        if item.status not in (MsmeStatus.DUE_SOON, MsmeStatus.OVERDUE):
            continue
        overdue = item.status == MsmeStatus.OVERDUE
        add(
            key=f"msme:{item.bill.vendor}:{item.bill.bill_no}",
            title=f"{'Pay' if not overdue else 'Overdue to'} {item.bill.vendor}, an MSME supplier",
            detail=(
                f"Bill {item.bill.bill_no} must be paid by {_fmt(item.due_on)} to keep the tax "
                "deduction this year."
            ),
            owed_to="Income tax",
            status=ObligationStatus.OVERDUE if overdue else ObligationStatus.DUE_SOON,
            area=Area.TAX,
            due_on=item.due_on,
            amount=item.bill.amount,
            rule_key="it.msme.days_with_agreement"
            if item.bill.written_agreement
            else "it.msme.days_without_agreement",
            action="See MSME bills",
        )

    # BOCW labour cess
    if f.cess.balance_due > 0:
        add(
            key="bocw:cess",
            title="Labour cess not yet paid on construction to date",
            detail="1% cess applies to the cost of construction.",
            owed_to="Labour welfare board",
            status=ObligationStatus.AT_RISK,
            area=Area.TAX,
            amount=f.cess.balance_due,
            rule_key="labour.bocw_cess_rate",
            action="See the cess",
        )

    return sort_obligations(out)


def sort_obligations(items: list[Obligation]) -> list[Obligation]:
    return sorted(
        items,
        key=lambda o: (
            STATUS_ORDER[o.status],
            o.due_on or date.max,
            -(o.amount or ZERO),
        ),
    )
