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

from lekhara.engines.collections import CollectionsPosition
from lekhara.engines.disputes import (
    FORUM_LABEL,
    RELIEF_LABEL,
    RUNNING,
    DisputesPosition,
    Forum,
)
from lekhara.engines.documents import OWED_TO as DOCUMENT_OWED_TO
from lekhara.engines.documents import Expiring
from lekhara.engines.escrow import EscrowPosition
from lekhara.engines.handover import BLOCKER_TEXT, HandoverPosition, Stage
from lekhara.engines.tax import (
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
from lekhara.money import ZERO
from lekhara.rules import RuleNotFound, RulesPack


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
    COLLECTIONS = "collections"
    HANDOVER = "handover"
    DISPUTES = "disputes"
    DOCUMENTS = "documents"
    APPROVALS = "approvals"
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
    amount_label: str | None = None
    """What the amount is, in plain words: 'Reverse charge', 'Bill', 'Can be drawn now'."""
    exposure: bool = False
    """True when the amount is money at risk (a penalty, tax or shortfall), not a bill or an
    opportunity. Only exposures are added up as money at stake."""
    ref: str | None = None
    """The record the obligation is about, when it has its own page (a case)."""


@dataclass(frozen=True)
class LapsingApproval:
    approval_id: str
    name: str
    authority: str | None
    valid_until: date


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
    open_withdrawal_amount: Decimal | None = None
    open_withdrawal_waiting_on: str | None = None
    """Who the open withdrawal request is waiting for, for example "the CA" or "the bank"."""
    collections: CollectionsPosition | None = None
    handover: HandoverPosition | None = None
    disputes: DisputesPosition | None = None
    expiring_documents: list[Expiring] = field(default_factory=list)
    lapsing_approvals: list[LapsingApproval] = field(default_factory=list)


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
    if f.open_withdrawal_waiting_on is not None:
        add(
            key="escrow:open",
            amount_label="Requested",
            exposure=False,
            title=f"Withdrawal is waiting for {f.open_withdrawal_waiting_on}",
            detail="A withdrawal request is under way. Follow it through to release.",
            owed_to="Escrow bank",
            status=ObligationStatus.OPPORTUNITY,
            area=Area.ESCROW,
            due_on=f.as_of,
            amount=f.open_withdrawal_amount,
            rule_key="escrow.withdrawal_cost_basis",
            action="Open the request",
        )
    elif e.suggest_withdrawal:
        add(
            key="escrow:withdraw",
            amount_label="Can be drawn now",
            exposure=False,
            title="Money is waiting in the RERA account",
            detail=(
                "Cost incurred allows a withdrawal now. Lekhara has prepared the three "
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
            amount_label="To deposit",
            exposure=True,
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

    # Collections: demands a certified stage has unlocked, and buyers past their due date
    c = f.collections
    if c is not None:
        for ready in c.ready:
            add(
                key=f"demand:{ready.milestone.id}",
                title="Demands are ready to raise",
                detail=(
                    f"{ready.milestone.name}, for {len(ready.unit_ids)} booked units. "
                    f"{ready.reason}"
                ),
                owed_to="Buyers",
                status=ObligationStatus.OPPORTUNITY,
                area=Area.COLLECTIONS,
                due_on=f.as_of,
                amount=ready.amount + ready.gst,
                amount_label="Ready to bill",
                exposure=False,
                action="Raise the demands",
            )
        if c.overdue > 0:
            add(
                key="collections:overdue",
                title=f"{c.overdue_buyers} buyers are past their due date",
                detail="Their instalments are overdue; interest at the agreed rate is running.",
                owed_to="Buyers",
                status=ObligationStatus.OPPORTUNITY,
                area=Area.COLLECTIONS,
                amount=c.overdue,
                amount_label="Overdue from buyers",
                exposure=False,
                rule_key="rera.buyer_late_interest_basis",
                action="See who owes",
            )

    # Registration and handover, once the occupancy certificate is in
    h = f.handover
    if h is not None and h.oc_received:
        waiting = [r for r in h.units if r.blocker not in (Stage.POSSESSION, Stage.DONE)]
        if waiting and h.money_waiting > 0:
            top = max(
                (s for s in h.by_blocker if s not in (Stage.POSSESSION, Stage.DONE)),
                key=lambda s: h.by_blocker[s],
            )
            add(
                key="handover:registration",
                title=f"{len(waiting)} units are not yet registered",
                detail=(
                    f"Most are held up at one step: {BLOCKER_TEXT[top].lower()} "
                    f"({h.by_blocker[top]} units). Final payments come in at registration."
                ),
                owed_to="Buyers",
                status=ObligationStatus.OPPORTUNITY,
                area=Area.HANDOVER,
                amount=h.money_waiting,
                amount_label="Waiting on registration",
                exposure=False,
                action="Open handover",
            )
        if h.conveyance_due_on and h.common_areas_conveyed_on is None:
            add(
                key="handover:conveyance",
                title="Convey the common areas to the association",
                detail=(
                    "RERA asks for conveyance within three months of the occupancy certificate, "
                    "where no local law says otherwise. Confirm the Karnataka position."
                ),
                owed_to="Association",
                status=_dated_status(h.conveyance_due_on, f.as_of, soon),
                area=Area.HANDOVER,
                due_on=h.conveyance_due_on,
                rule_key="rera.s17_conveyance_months",
                action="Open handover",
            )

    # Disputes and orders
    dp = f.disputes
    if dp is not None:
        hearing_days = rules.value("disputes.hearing_notice_days", f.as_of)
        for cp in dp.cases:
            if not cp.open:
                continue
            c = cp.case
            who = f"the case by {c.complainant}"
            forum = FORUM_LABEL[c.forum]
            where = f"{forum}, {c.case_number}."
            could_cost = cp.at_stake if cp.at_stake > 0 else None
            if c.reply_due_on and not c.reply_filed_on:
                add(
                    key=f"case:{c.case_id}:reply",
                    title=f"File the reply in {who}",
                    detail=f"{where} {RELIEF_LABEL[c.relief]} is sought.",
                    owed_to=forum,
                    status=_dated_status(c.reply_due_on, f.as_of, soon),
                    area=Area.DISPUTES,
                    due_on=c.reply_due_on,
                    amount=could_cost,
                    amount_label="Could cost",
                    exposure=False,
                    action="Open the case",
                    ref=c.case_id,
                )
            if (
                c.next_hearing_on
                and c.next_hearing_on >= f.as_of
                and (c.next_hearing_on - f.as_of).days <= hearing_days
            ):
                add(
                    key=f"case:{c.case_id}:hearing",
                    title=f"Hearing in {who}",
                    detail=f"{where} Brief your lawyer and send the documents they need.",
                    owed_to=forum,
                    status=_dated_status(c.next_hearing_on, f.as_of, soon),
                    area=Area.DISPUTES,
                    due_on=c.next_hearing_on,
                    amount=could_cost,
                    amount_label="Could cost",
                    exposure=False,
                    action="Open the case",
                    ref=c.case_id,
                )
            unpaid = [o for o in cp.orders if o.outstanding > 0]
            if unpaid and c.appealed_on is None and c.settlement_agreed is None:
                comply = min((o.order.comply_by for o in unpaid if o.order.comply_by), default=None)
                overdue = any(o.overdue for o in unpaid)
                running = any(o.order.amount is None and o.order.kind in RUNNING for o in unpaid)
                notes = []
                if running:
                    notes.append("Interest keeps running until it is paid.")
                if overdue and c.forum in (Forum.KRERA, Forum.ADJUDICATING_OFFICER):
                    notes.append("K-RERA can recover an unpaid amount as arrears of land revenue.")
                add(
                    key=f"case:{c.case_id}:order",
                    title=(
                        f"The order in {who} is past its date"
                        if overdue
                        else f"Pay what was ordered in {who}"
                    ),
                    detail=" ".join([where, *notes]),
                    owed_to=c.complainant,
                    status=ObligationStatus.OVERDUE
                    if overdue
                    else _dated_status(comply, f.as_of, soon)
                    if comply
                    else ObligationStatus.DUE_SOON,
                    area=Area.DISPUTES,
                    due_on=comply,
                    amount=sum((o.outstanding for o in unpaid), ZERO),
                    amount_label="Ordered to pay",
                    exposure=True,
                    rule_key="rera.delay_interest_margin" if running else None,
                    action="Open the case",
                    ref=c.case_id,
                )
                open_appeals = [o for o in unpaid if o.appeal_by and o.appeal_by >= f.as_of]
                if open_appeals:
                    first = min(open_appeals, key=lambda o: o.appeal_by)
                    deposit = sum((o.appeal_deposit or ZERO for o in open_appeals), ZERO)
                    add(
                        key=f"case:{c.case_id}:appeal",
                        title=f"Decide whether to appeal the order in {who}",
                        detail=(
                            f"An appeal to the {first.appeal.to} must be filed by "
                            f"{_fmt(first.appeal_by)}"
                            + (", with the amount shown deposited first." if deposit else ".")
                        ),
                        owed_to=first.appeal.to,
                        status=_dated_status(first.appeal_by, f.as_of, soon),
                        area=Area.DISPUTES,
                        due_on=first.appeal_by,
                        amount=deposit or None,
                        amount_label="Deposit to appeal",
                        exposure=False,
                        rule_key=first.appeal.days_rule,
                        action="Open the case",
                        ref=c.case_id,
                    )
            if c.settlement_agreed is not None and cp.at_stake > 0:
                add(
                    key=f"case:{c.case_id}:settlement",
                    title=f"Pay the settlement agreed in {who}",
                    detail=f"{where} File the settlement terms once it is paid.",
                    owed_to=c.complainant,
                    status=ObligationStatus.DUE_SOON,
                    area=Area.DISPUTES,
                    amount=cp.at_stake,
                    amount_label="Agreed settlement",
                    exposure=False,
                    action="Open the case",
                    ref=c.case_id,
                )

    # Documents about to lapse
    for e in f.expiring_documents:
        add(
            key=f"doc:{e.document_id}:expiry",
            title=f"{e.title} has expired" if e.expired else f"{e.title} is about to expire",
            detail=(
                f"It runs out on {_fmt(e.expires_on)}. Renew it and add the new copy to the vault."
            ),
            owed_to=DOCUMENT_OWED_TO.get(e.category, "Your records"),
            status=_dated_status(e.expires_on, f.as_of, soon),
            area=Area.DOCUMENTS,
            due_on=e.expires_on,
            action="Open the document",
            ref=e.document_id,
        )

    # Approvals about to lapse
    for a in f.lapsing_approvals:
        lapsed = a.valid_until < f.as_of
        add(
            key=f"approval:{a.approval_id}",
            title=f"{a.name} has lapsed" if lapsed else f"Renew {a.name}",
            detail=(
                f"It {'lapsed' if lapsed else 'lapses'} on {_fmt(a.valid_until)}. Apply for the "
                "renewal and record the new validity in the approvals list."
            ),
            owed_to=a.authority or "The authority",
            status=_dated_status(a.valid_until, f.as_of, soon),
            area=Area.APPROVALS,
            due_on=a.valid_until,
            rule_key="approvals.renewal_notice_days",
            action="Open the approvals",
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
                amount_label="Late fee from",
                exposure=True,
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

    # Annual project audit, for every financial year ended since registration
    months = rules.value("krera.annual_audit_months", f.as_of)
    fy_start, _ = financial_year(f.as_of)
    fy_end = fy_start - timedelta(days=1)
    while fy_end > f.registered_on:
        year = fy_end.year - 1
        if year not in f.audits_done:
            due = _month_end_after(fy_end, months)
            status = _dated_status(due, f.as_of, soon)
            if status != ObligationStatus.UPCOMING or (due - f.as_of).days <= 60:
                add(
                    key=f"audit:{year}",
                    title="Annual project audit",
                    detail=(
                        f"Project accounts for {year}-{str(year + 1)[2:]} must be audited by a CA "
                        f"by {_fmt(due)}."
                    ),
                    owed_to="K-RERA",
                    status=status,
                    area=Area.KRERA,
                    due_on=due,
                    rule_key="krera.annual_audit_months",
                    action="Prepare the audit pack",
                )
        fy_end = date(fy_end.year - 1, 3, 31)

    # Delay interest and the possession date
    d = f.delay
    if d.possession_due_on is not None:
        if d.days_late > 0:
            add(
                key="rera:delay",
                amount_label="Interest so far",
                exposure=True,
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
                amount_label="Per month if late",
                exposure=False,
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
                amount_label="Reverse charge",
                exposure=True,
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
                amount_label="Still allowed unregistered",
                exposure=False,
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
            amount_label="Payable at completion",
            exposure=True,
            title="GST on development rights falls due at completion",
            detail=(
                f"{dr.unbooked_units} of your flats are unbooked. If they are still unbooked at "
                "completion, this is payable in cash. Each flat sold before then lowers it."
            ),
            owed_to="GST",
            status=ObligationStatus.AT_RISK,
            area=Area.TAX,
            due_on=f.delay.possession_due_on if f.delay.days_late == 0 else None,
            amount=dr.liability,
            rule_key="gst.dr.rcm_rate",
            action="See the forecast",
        )

    # Guidance value
    for flag in f.guidance_flags:
        add(
            key=f"s43ca:{flag.sale.unit_label}",
            amount_label="Estimated tax",
            exposure=True,
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
            amount_label="TDS short",
            exposure=True,
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
            amount_label="Bill",
            exposure=False,
            title=(
                f"Payment to {item.bill.vendor} is past the MSME limit"
                if overdue
                else f"Pay {item.bill.vendor} before the MSME limit"
            ),
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
            amount_label="Cess due",
            exposure=True,
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
