"""Loads a project from the database and runs the engines for a date.

Also holds the withdrawal workflow: create a request with drafted certificates,
let each certifier review and sign, submit to the bank, record the release.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horus.engines.collections import (
    BookedUnit,
    CollectionsPosition,
    Milestone,
    Payment,
    Trigger,
    collections_position,
    new_demand,
)
from horus.engines.collections import Demand as DemandIn
from horus.engines.disputes import OPEN as DISPUTE_OPEN
from horus.engines.disputes import (
    RUNNING,
    CaseIn,
    CasePosition,
    CaseStatus,
    DisputesPosition,
    Forum,
    OrderIn,
    OrderKind,
    Relief,
    case_position,
    disputes_position,
)
from horus.engines.disputes import Payment as DisputePaymentIn
from horus.engines.escrow import (
    ROLE_ORDER,
    AccountTxn,
    Certificate,
    CertifierRole,
    Check,
    CheckStatus,
    EscrowPosition,
    RequestStatus,
    TxnKind,
    can_submit,
    check_request,
    draft_certificates,
    escrow_position,
    request_status,
)
from horus.engines.handover import HandoverPosition, UnitHandoverIn, handover_position
from horus.engines.money import Category, CostLine, Entry, EntryKind, ProjectPosition, ReraHead
from horus.engines.money import project_position as money_position
from horus.engines.obligations import Obligation, ProjectFacts, project_obligations
from horus.engines.tax import (
    CessPosition,
    DelayExposure,
    DevelopmentRightsGst,
    GstRegime,
    GuidanceValueFlag,
    LandownerPayment,
    MsmeCategory,
    MsmeItem,
    ProcurementMeter,
    Purchase,
    Sale,
    SupplierBill,
    TdsShortfall,
    UnitForTax,
    bocw_cess,
    delay_interest,
    development_rights_gst,
    guidance_value_flags,
    landowner_tds_shortfalls,
    msme_clock,
    procurement_meter,
)
from horus.models import (
    Bill,
    CostLineRow,
    DemandRow,
    DisputeCase,
    DisputeHearing,
    DisputeOrder,
    DisputePayment,
    EscrowTxn,
    Filing,
    Landowner,
    LandownerPaymentRow,
    LedgerEntry,
    Organization,
    PaymentMilestone,
    ProgressCertificate,
    Project,
    Receipt,
    Unit,
    UnitHandover,
    WithdrawalCertificate,
    WithdrawalRequest,
)
from horus.money import ZERO
from horus.rules import KARNATAKA, RulesPack


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ProjectSnapshot:
    project: Project
    as_of: date
    money: ProjectPosition
    escrow: EscrowPosition
    procurement: ProcurementMeter
    development_rights: DevelopmentRightsGst
    guidance_flags: list[GuidanceValueFlag]
    landowner_tds: list[TdsShortfall]
    msme: list[MsmeItem]
    cess: CessPosition
    delay: DelayExposure
    obligations: list[Obligation]
    open_request: WithdrawalRequest | None
    collections: CollectionsPosition
    handover: HandoverPosition


def organization(session: Session) -> Organization:
    org = session.scalars(select(Organization).order_by(Organization.name)).first()
    if org is None:
        raise ServiceError("No organisation has been set up yet.", 404)
    return org


def projects(session: Session) -> list[Project]:
    org = organization(session)
    return list(
        session.scalars(
            select(Project).where(Project.organization_id == org.id).order_by(Project.name)
        )
    )


def visible_projects(
    session: Session, organization_ids: set[str], project_ids: set[str]
) -> list[Project]:
    """Projects of the person's own organisations, plus projects they certify."""
    if not organization_ids and not project_ids:
        return []
    clauses = []
    if organization_ids:
        clauses.append(Project.organization_id.in_(organization_ids))
    if project_ids:
        clauses.append(Project.id.in_(project_ids))
    return list(session.scalars(select(Project).where(or_(*clauses)).order_by(Project.name)))


def get_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ServiceError("Project not found.", 404)
    return project


def _money(session: Session, project: Project, as_of: date, rules: RulesPack) -> ProjectPosition:
    lines = [
        CostLine(
            id=row.id,
            code=row.code,
            name=row.name,
            category=Category(row.category),
            rera_head=ReraHead(row.rera_head),
            original_budget=row.original_budget,
            revised_budget=row.revised_budget,
        )
        for row in session.scalars(
            select(CostLineRow)
            .where(CostLineRow.project_id == project.id)
            .order_by(CostLineRow.position)
        )
    ]
    entries = [
        Entry(row.cost_line_id, EntryKind(row.kind), row.amount, row.entry_date)
        for row in session.scalars(select(LedgerEntry).where(LedgerEntry.project_id == project.id))
    ]
    progress = session.scalars(
        select(ProgressCertificate)
        .where(ProgressCertificate.project_id == project.id, ProgressCertificate.as_of <= as_of)
        .order_by(ProgressCertificate.as_of.desc())
    ).first()
    return money_position(
        lines,
        entries,
        as_of=as_of,
        certified_progress_pct=progress.completion_pct if progress else None,
        rules=rules,
    )


def _escrow(
    session: Session, project: Project, money: ProjectPosition, as_of: date, rules: RulesPack
) -> EscrowPosition:
    txns = [
        AccountTxn(TxnKind(t.kind), t.amount, t.txn_date)
        for t in session.scalars(select(EscrowTxn).where(EscrowTxn.project_id == project.id))
    ]
    receipts = sum(
        (
            r.amount
            for r in session.scalars(
                select(Receipt).where(
                    Receipt.project_id == project.id, Receipt.received_on <= as_of
                )
            )
        ),
        ZERO,
    )
    return escrow_position(money, txns, receipts, as_of=as_of, rules=rules)


def open_request(session: Session, project: Project) -> WithdrawalRequest | None:
    return session.scalars(
        select(WithdrawalRequest).where(
            WithdrawalRequest.project_id == project.id,
            WithdrawalRequest.released_on.is_(None),
            WithdrawalRequest.rejected_on.is_(None),
        )
    ).first()


def snapshot(
    session: Session, project: Project, as_of: date, rules: RulesPack = KARNATAKA
) -> ProjectSnapshot:
    regime = GstRegime(project.gst_regime)
    money = _money(session, project, as_of, rules)
    escrow = _escrow(session, project, money, as_of, rules)

    bills = list(
        session.scalars(
            select(Bill).where(Bill.project_id == project.id).order_by(Bill.accepted_on)
        )
    )
    procurement = procurement_meter(
        [
            Purchase(
                amount=b.taxable_value,
                on=b.bill_date,
                supplier_registered=b.vendor.registered,
                is_cement=b.is_cement,
                excluded=b.excluded,
                rcm_paid=b.rcm_paid,
            )
            for b in bills
        ],
        regime=regime,
        as_of=as_of,
        rules=rules,
    )
    msme = msme_clock(
        [
            SupplierBill(
                vendor=b.vendor.name,
                bill_no=b.bill_no,
                amount=b.taxable_value,
                accepted_on=b.accepted_on,
                msme=MsmeCategory(b.vendor.msme_category),
                written_agreement=b.vendor.written_agreement,
                paid_on=b.paid_on if b.paid_on and b.paid_on <= as_of else None,
            )
            for b in bills
            if b.accepted_on <= as_of
        ],
        as_of=as_of,
        rules=rules,
    )

    units = list(session.scalars(select(Unit).where(Unit.project_id == project.id)))
    booked = [u for u in units if u.booked and u.booked_on and u.booked_on <= as_of]
    booked_ids = {u.id for u in booked}
    development_rights = development_rights_gst(
        project.development_rights_value,
        [
            UnitForTax(
                carpet_area=Decimal(u.carpet_area_sqft),
                value=u.agreement_value
                if u.id in booked_ids and u.agreement_value
                else u.list_price,
                booked=u.id in booked_ids,
                landowner_share=u.owner_share == "landowner",
            )
            for u in units
        ],
        regime=regime,
        on=as_of,
        rules=rules,
    )
    flags = guidance_value_flags(
        [
            Sale(u.label, u.agreement_value, u.guidance_value, u.booked_on)
            for u in booked
            if u.agreement_value is not None and u.booked_on is not None
        ],
        on=as_of,
        rules=rules,
    )

    payments = [
        LandownerPayment(
            landowner=p.landowner.name,
            amount=p.amount,
            on=p.paid_on,
            tds_deducted=p.tds_deducted,
            monetary_consideration=p.monetary_consideration,
        )
        for p in session.scalars(
            select(LandownerPaymentRow)
            .join(Landowner)
            .where(Landowner.project_id == project.id, LandownerPaymentRow.paid_on <= as_of)
        )
    ]
    tds = landowner_tds_shortfalls(payments, rules=rules)
    cess = bocw_cess(money, project.cess_paid, as_of=as_of, rules=rules)
    delay = delay_interest(
        escrow.receipts_from_buyers, project.possession_due_on, as_of=as_of, rules=rules
    )

    filings = list(
        session.scalars(
            select(Filing).where(Filing.project_id == project.id, Filing.filed_on <= as_of)
        )
    )
    collections = collections_for(session, project, as_of, rules)
    handover = handover_for(session, project, as_of, collections, rules)
    disputes = disputes_for(session, project, as_of, rules)
    request = open_request(session, project)
    waiting_on = None
    if request is not None:
        _, _, _, waiting_on = _request_state(request, money, escrow, project, as_of, rules)

    facts = ProjectFacts(
        project_id=project.id,
        project_name=project.name,
        as_of=as_of,
        registered_on=project.registered_on,
        estimated_cost=money.anticipated_final_cost,
        escrow=escrow,
        procurement=procurement,
        development_rights=development_rights,
        msme=msme,
        delay=delay,
        guidance_flags=flags,
        landowner_tds=tds,
        cess=cess,
        qpr_filed={f.period_end for f in filings if f.kind == "qpr"},
        audits_done={f.period_end.year - 1 for f in filings if f.kind == "annual_audit"},
        open_withdrawal_amount=request.amount if request else None,
        open_withdrawal_waiting_on=waiting_on,
        collections=collections,
        handover=handover,
        disputes=disputes,
    )
    return ProjectSnapshot(
        project=project,
        as_of=as_of,
        money=money,
        escrow=escrow,
        procurement=procurement,
        development_rights=development_rights,
        guidance_flags=flags,
        landowner_tds=tds,
        msme=msme,
        cess=cess,
        delay=delay,
        obligations=project_obligations(facts, rules=rules),
        open_request=request,
        collections=collections,
        handover=handover,
    )


# Collections


def sale_gst_rate(project: Project, as_of: date, rules: RulesPack) -> Decimal:
    regime = GstRegime(project.gst_regime)
    if regime == GstRegime.AFFORDABLE_1PC:
        return rules.value("gst.rate.affordable", as_of)
    if regime == GstRegime.COMMERCIAL_12PC:
        return rules.value("gst.rate.commercial", as_of)
    return rules.value("gst.rate.residential", as_of)


def _milestones(session: Session, project: Project) -> list[PaymentMilestone]:
    return list(
        session.scalars(
            select(PaymentMilestone)
            .where(PaymentMilestone.project_id == project.id)
            .order_by(PaymentMilestone.sequence)
        )
    )


def _latest_progress(session: Session, project: Project, as_of: date) -> ProgressCertificate | None:
    return session.scalars(
        select(ProgressCertificate)
        .where(ProgressCertificate.project_id == project.id, ProgressCertificate.as_of <= as_of)
        .order_by(ProgressCertificate.as_of.desc())
    ).first()


def _milestone_in(row: PaymentMilestone) -> Milestone:
    return Milestone(
        id=row.id,
        sequence=row.sequence,
        name=row.name,
        share_pct=row.share_pct,
        trigger=Trigger(row.trigger),
        progress_pct=row.progress_pct,
        due_days=row.due_days,
    )


def _booked_units(session: Session, project: Project, as_of: date) -> list[BookedUnit]:
    return [
        BookedUnit(u.id, u.label, u.buyer_name, u.agreement_value, u.booked_on)
        for u in session.scalars(
            select(Unit)
            .where(Unit.project_id == project.id, Unit.booked.is_(True))
            .order_by(Unit.label)
        )
        if u.agreement_value is not None and u.booked_on is not None and u.booked_on <= as_of
    ]


def collections_for(
    session: Session, project: Project, as_of: date, rules: RulesPack = KARNATAKA
) -> CollectionsPosition:
    progress = _latest_progress(session, project, as_of)
    demands = [
        DemandIn(d.id, d.unit_id, d.milestone_id, d.amount, d.gst, d.raised_on, d.due_on)
        for d in session.scalars(select(DemandRow).where(DemandRow.project_id == project.id))
    ]
    payments = [
        Payment(r.unit_id, r.amount, r.received_on, r.tds_deducted)
        for r in session.scalars(select(Receipt).where(Receipt.project_id == project.id))
    ]
    deposits = [
        (t.txn_date, t.amount)
        for t in session.scalars(
            select(EscrowTxn).where(
                EscrowTxn.project_id == project.id, EscrowTxn.kind == TxnKind.DEPOSIT.value
            )
        )
    ]
    return collections_position(
        milestones=[_milestone_in(m) for m in _milestones(session, project)],
        units=_booked_units(session, project, as_of),
        demands=demands,
        payments=payments,
        deposits=deposits,
        certified_progress_pct=progress.completion_pct if progress else None,
        certified_on=progress.as_of if progress else None,
        possession_given=oc_received(project, as_of),
        gst_rate_on_sale=sale_gst_rate(project, as_of, rules),
        as_of=as_of,
        rules=rules,
    )


def raise_demands(
    session: Session,
    project: Project,
    milestone_id: str,
    as_of: date,
    *,
    user_id: str | None = None,
    rules: RulesPack = KARNATAKA,
) -> int:
    """Raise this milestone's demand on every booked unit that does not have it yet."""
    position = collections_for(session, project, as_of, rules)
    ready = next((r for r in position.ready if r.milestone.id == milestone_id), None)
    if ready is None:
        raise ServiceError("This milestone is not ready to raise, or is already raised.", 409)
    units = {u.id: u for u in _booked_units(session, project, as_of)}
    rate = sale_gst_rate(project, as_of, rules)
    progress = _latest_progress(session, project, as_of)
    for unit_id in ready.unit_ids:
        amount, gst, due_on = new_demand(
            units[unit_id], ready.milestone, gst_rate_on_sale=rate, raised_on=as_of
        )
        session.add(
            DemandRow(
                project_id=project.id,
                unit_id=unit_id,
                milestone_id=milestone_id,
                amount=amount,
                gst=gst,
                raised_on=as_of,
                due_on=due_on,
                certified_progress_pct=progress.completion_pct
                if progress and ready.milestone.trigger == Trigger.PROGRESS
                else None,
                created_by_user_id=user_id,
            )
        )
    session.commit()
    return len(ready.unit_ids)


def get_demand(session: Session, demand_id: str) -> DemandRow:
    demand = session.get(DemandRow, demand_id)
    if demand is None:
        raise ServiceError("Demand not found.", 404)
    return demand


# Registration and handover


def oc_received(project: Project, as_of: date) -> bool:
    return (
        project.oc_status in ("partial", "received")
        and project.oc_received_on is not None
        and project.oc_received_on <= as_of
    )


def handover_for(
    session: Session,
    project: Project,
    as_of: date,
    collections: CollectionsPosition | None = None,
    rules: RulesPack = KARNATAKA,
) -> HandoverPosition:
    collections = collections or collections_for(session, project, as_of, rules)
    rate = sale_gst_rate(project, as_of, rules)
    possession = next(
        (m.id for m in _milestones(session, project) if m.trigger == Trigger.POSSESSION.value),
        None,
    )
    final_raised = {
        d.unit_id
        for d in session.scalars(
            select(DemandRow).where(
                DemandRow.project_id == project.id,
                DemandRow.milestone_id == possession,
                DemandRow.raised_on <= as_of,
            )
        )
    }
    records = {
        h.unit_id: h
        for h in session.scalars(
            select(UnitHandover).join(Unit).where(Unit.project_id == project.id)
        )
    }
    units = {u.id: u for u in session.scalars(select(Unit).where(Unit.project_id == project.id))}
    inputs = []
    for account in collections.accounts:
        unit = units[account.unit.id]
        record = records.get(unit.id)
        total_value = unit.agreement_value + unit.agreement_value * rate
        balance = max(total_value - account.received - account.tds, ZERO).quantize(Decimal("0.01"))
        inputs.append(
            UnitHandoverIn(
                unit_id=unit.id,
                label=unit.label,
                buyer=unit.buyer_name,
                agreement_value=unit.agreement_value,
                guidance_value=unit.guidance_value,
                ekhata_status=record.ekhata_status if record else "none",
                khata_type=record.khata_type if record else None,
                final_demand_raised=unit.id in final_raised,
                balance_due=balance,
                deed_drafted_on=record.deed_drafted_on if record else None,
                appointment_on=record.appointment_on if record else None,
                registered_on=record.registered_on if record else None,
                document_no=record.document_no if record else None,
                possession_on=record.possession_on if record else None,
            )
        )
    return handover_position(
        inputs,
        oc_received_on=project.oc_received_on if oc_received(project, as_of) else None,
        common_areas_conveyed_on=project.common_areas_conveyed_on,
        on=as_of,
        rules=rules,
    )


HANDOVER_FIELDS = {
    "ekhata_status",
    "khata_type",
    "deed_drafted_on",
    "appointment_on",
    "registered_on",
    "document_no",
    "possession_on",
}


def get_unit(session: Session, unit_id: str) -> Unit:
    unit = session.get(Unit, unit_id)
    if unit is None:
        raise ServiceError("Unit not found.", 404)
    return unit


def update_handover(
    session: Session, unit: Unit, fields: dict, *, user_id: str | None = None
) -> UnitHandover:
    if not unit.booked:
        raise ServiceError("Only a booked unit can be registered.")
    unknown = set(fields) - HANDOVER_FIELDS
    if unknown:
        raise ServiceError(f"Unknown field: {sorted(unknown)[0]}.")
    if fields.get("ekhata_status") not in (None, "none", "applied", "draft", "final"):
        raise ServiceError("The e-Khata status must be none, applied, draft or final.")
    if fields.get("khata_type") not in (None, "A", "B"):
        raise ServiceError("The khata type must be A or B.")
    record = session.scalars(select(UnitHandover).where(UnitHandover.unit_id == unit.id)).first()
    if record is None:
        record = UnitHandover(unit_id=unit.id)
        session.add(record)
    if fields.get("registered_on") and not (fields.get("document_no") or record.document_no):
        raise ServiceError("Enter the registered document number with the registration date.")
    for key, value in fields.items():
        setattr(record, key, value)
    record.updated_by_user_id = user_id
    session.commit()
    return record


# Disputes and orders


def _choice(value: str | None, enum: type, what: str) -> str:
    try:
        return enum(value).value
    except ValueError:
        raise ServiceError(f"Choose the {what} from the list.") from None


def _money_in(fields: dict, key: str) -> None:
    value = fields.get(key)
    if value is not None and Decimal(value) < 0:
        raise ServiceError("Amounts cannot be negative.")


def _case_in(
    row: DisputeCase,
    project: Project,
    as_of: date,
    units: dict[str, Unit],
    receipts: dict[str, list[DisputePaymentIn]],
    possession: dict[str, date],
) -> CaseIn:
    unit = units.get(row.unit_id) if row.unit_id else None
    return CaseIn(
        case_id=row.id,
        forum=Forum(row.forum),
        case_number=row.case_number,
        relief=Relief(row.relief),
        status=CaseStatus(row.status),
        complainant=row.complainant,
        unit_label=unit.label if unit else None,
        filed_on=row.filed_on,
        claim_amount=row.claim_amount,
        reply_due_on=row.reply_due_on,
        reply_filed_on=row.reply_filed_on,
        next_hearing_on=row.next_hearing_on,
        buyer_payments=tuple(sorted(receipts.get(row.unit_id, []), key=lambda p: p.on)),
        possession_due_on=project.possession_due_on,
        possession_on=possession.get(row.unit_id) if row.unit_id else None,
        orders=tuple(
            OrderIn(
                order_id=o.id,
                ordered_on=o.ordered_on,
                kind=OrderKind(o.kind),
                amount=o.amount,
                comply_by=o.comply_by,
                received_on=o.received_on,
            )
            for o in row.orders
            if o.ordered_on <= as_of
        ),
        paid=tuple(DisputePaymentIn(p.paid_on, p.amount) for p in row.payments),
        settlement_offered=row.settlement_offered,
        settlement_agreed=row.settlement_agreed,
        appealed_on=row.appealed_on,
    )


def _case_inputs(
    session: Session, project: Project, rows: list[DisputeCase], as_of: date
) -> list[CaseIn]:
    unit_ids = {r.unit_id for r in rows if r.unit_id}
    units = {u.id: u for u in session.scalars(select(Unit).where(Unit.id.in_(unit_ids)))}
    receipts: dict[str, list[DisputePaymentIn]] = {}
    for r in session.scalars(
        select(Receipt).where(Receipt.unit_id.in_(unit_ids), Receipt.received_on <= as_of)
    ):
        receipts.setdefault(r.unit_id, []).append(
            DisputePaymentIn(r.received_on, r.amount + r.tds_deducted)
        )
    possession = {
        h.unit_id: h.possession_on
        for h in session.scalars(select(UnitHandover).where(UnitHandover.unit_id.in_(unit_ids)))
        if h.possession_on and h.possession_on <= as_of
    }
    return [_case_in(r, project, as_of, units, receipts, possession) for r in rows]


def booked_units(session: Session, project: Project, as_of: date) -> list[Unit]:
    return [
        u
        for u in session.scalars(
            select(Unit)
            .where(Unit.project_id == project.id, Unit.booked.is_(True))
            .order_by(Unit.label)
        )
        if u.booked_on is None or u.booked_on <= as_of
    ]


def disputes_for(
    session: Session, project: Project, as_of: date, rules: RulesPack = KARNATAKA
) -> DisputesPosition:
    rows = list(
        session.scalars(
            select(DisputeCase).where(
                DisputeCase.project_id == project.id,
                or_(DisputeCase.filed_on.is_(None), DisputeCase.filed_on <= as_of),
            )
        )
    )
    return disputes_position(
        _case_inputs(session, project, rows, as_of),
        as_of=as_of,
        rules=rules,
        possession_due_on=project.possession_due_on,
        booked_units=len(booked_units(session, project, as_of)),
    )


def get_case(session: Session, case_id: str) -> DisputeCase:
    row = session.get(DisputeCase, case_id)
    if row is None:
        raise ServiceError("Case not found.", 404)
    return row


def case_position_for(
    session: Session, row: DisputeCase, project: Project, as_of: date, rules: RulesPack = KARNATAKA
) -> CasePosition:
    (case,) = _case_inputs(session, project, [row], as_of)
    return case_position(case, as_of=as_of, rules=rules)


def create_case(
    session: Session, project: Project, fields: dict, *, as_of: date, user_id: str | None = None
) -> DisputeCase:
    number = (fields.get("case_number") or "").strip()
    if not number:
        raise ServiceError("Enter the case number.")
    unit = None
    label = (fields.get("unit") or "").strip()
    if label:
        unit = session.scalars(
            select(Unit).where(Unit.project_id == project.id, Unit.label == label)
        ).first()
        if unit is None or not unit.booked:
            raise ServiceError(f"No booked unit {label} in this project.")
    complainant = (fields.get("complainant") or "").strip() or (unit.buyer_name if unit else "")
    if not complainant:
        raise ServiceError("Enter who brought the case, or the unit it is about.")
    _money_in(fields, "claim_amount")
    row = DisputeCase(
        project_id=project.id,
        unit_id=unit.id if unit else None,
        forum=_choice(fields.get("forum"), Forum, "forum"),
        case_number=number,
        relief=_choice(fields.get("relief"), Relief, "relief sought"),
        complainant=complainant,
        summary=(fields.get("summary") or "").strip() or None,
        claim_amount=fields.get("claim_amount"),
        filed_on=fields.get("filed_on"),
        notice_received_on=fields.get("notice_received_on") or as_of,
        reply_due_on=fields.get("reply_due_on"),
        next_hearing_on=fields.get("next_hearing_on"),
        lawyer=(fields.get("lawyer") or "").strip() or None,
        status=CaseStatus.HEARING.value if fields.get("next_hearing_on") else "notice",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    session.add(row)
    session.commit()
    return row


CASE_FIELDS = {
    "status",
    "lawyer",
    "summary",
    "claim_amount",
    "reply_due_on",
    "reply_filed_on",
    "next_hearing_on",
    "settlement_offered",
    "settlement_agreed",
    "appealed_on",
}


def _close_if_done(row: DisputeCase, as_of: date) -> None:
    if CaseStatus(row.status) in DISPUTE_OPEN:
        row.closed_on = None
    elif row.closed_on is None:
        row.closed_on = as_of


def update_case(
    session: Session, row: DisputeCase, fields: dict, *, as_of: date, user_id: str | None = None
) -> DisputeCase:
    unknown = set(fields) - CASE_FIELDS
    if unknown:
        raise ServiceError(f"Unknown field: {sorted(unknown)[0]}.")
    for key in ("claim_amount", "settlement_offered", "settlement_agreed"):
        _money_in(fields, key)
    if "status" in fields:
        fields["status"] = _choice(fields["status"], CaseStatus, "status")
    status_changed = fields.get("status", row.status) != row.status
    for key, value in fields.items():
        if isinstance(value, str) and key != "status":
            value = value.strip() or None
        setattr(row, key, value)
    if not status_changed:
        if fields.get("appealed_on"):
            row.status = CaseStatus.APPEALED.value
        elif fields.get("settlement_agreed") is not None and CaseStatus(row.status) in DISPUTE_OPEN:
            row.status = CaseStatus.SETTLING.value
    _close_if_done(row, as_of)
    row.updated_by_user_id = user_id
    session.commit()
    return row


def add_hearing(
    session: Session, row: DisputeCase, fields: dict, *, as_of: date, user_id: str | None = None
) -> DisputeHearing:
    held_on = fields.get("held_on")
    if held_on is None:
        raise ServiceError("Enter the date of the hearing.")
    if held_on > as_of:
        raise ServiceError(
            "Record a hearing once it has happened. Set the next hearing date instead."
        )
    hearing = DisputeHearing(
        case_id=row.id,
        held_on=held_on,
        purpose=(fields.get("purpose") or "").strip() or "Hearing",
        outcome=(fields.get("outcome") or "").strip() or None,
        recorded_by_user_id=user_id,
    )
    session.add(hearing)
    next_on = fields.get("next_hearing_on")
    if next_on is not None and next_on <= held_on:
        raise ServiceError("The next hearing must be after this one.")
    row.next_hearing_on = next_on
    if fields.get("order_reserved"):
        row.status = CaseStatus.RESERVED.value
    elif row.status == CaseStatus.NOTICE.value:
        row.status = CaseStatus.HEARING.value
    row.updated_by_user_id = user_id
    session.commit()
    return hearing


def add_order(
    session: Session, row: DisputeCase, fields: dict, *, as_of: date, user_id: str | None = None
) -> DisputeOrder:
    ordered_on = fields.get("ordered_on")
    if ordered_on is None or ordered_on > as_of:
        raise ServiceError("Enter the date of the order; it cannot be in the future.")
    kind = OrderKind(_choice(fields.get("kind"), OrderKind, "kind of order"))
    _money_in(fields, "amount")
    amount = fields.get("amount")
    if (
        amount is None
        and kind not in RUNNING
        and kind
        not in (
            OrderKind.POSSESSION,
            OrderKind.DISMISSED,
            OrderKind.OTHER,
        )
    ):
        raise ServiceError("Enter the amount the order directs.")
    if amount is None and kind in RUNNING and row.unit_id is None:
        raise ServiceError(
            "Enter the amount. Horus works out refunds and interest only for a buyer's unit."
        )
    order = DisputeOrder(
        case_id=row.id,
        ordered_on=ordered_on,
        received_on=fields.get("received_on"),
        kind=kind.value,
        amount=amount,
        comply_by=fields.get("comply_by"),
        summary=(fields.get("summary") or "").strip() or None,
        recorded_by_user_id=user_id,
    )
    session.add(order)
    if kind == OrderKind.DISMISSED:
        row.status = CaseStatus.DISMISSED.value
    elif row.status != CaseStatus.APPEALED.value:
        row.status = CaseStatus.ORDERED.value
    row.next_hearing_on = None
    _close_if_done(row, as_of)
    row.updated_by_user_id = user_id
    session.commit()
    return order


def add_payment(
    session: Session,
    row: DisputeCase,
    project: Project,
    fields: dict,
    *,
    as_of: date,
    user_id: str | None = None,
    rules: RulesPack = KARNATAKA,
) -> DisputePayment:
    paid_on = fields.get("paid_on")
    amount = fields.get("amount")
    if paid_on is None or paid_on > as_of:
        raise ServiceError("Enter the date of the payment; it cannot be in the future.")
    if amount is None or Decimal(amount) <= 0:
        raise ServiceError("Enter the amount paid.")
    payment = DisputePayment(
        case_id=row.id,
        paid_on=paid_on,
        amount=amount,
        reference=(fields.get("reference") or "").strip() or None,
        recorded_by_user_id=user_id,
    )
    session.add(payment)
    session.flush()
    session.refresh(row)
    position = case_position_for(session, row, project, as_of, rules)
    if row.settlement_agreed is not None and position.paid >= row.settlement_agreed:
        row.status = CaseStatus.SETTLED.value
    elif position.orders and position.owed <= 0 and row.status == CaseStatus.ORDERED.value:
        row.status = CaseStatus.COMPLIED.value
    _close_if_done(row, as_of)
    row.updated_by_user_id = user_id
    session.commit()
    return payment


# Withdrawal workflow

ROLE_WAITING = {
    CertifierRole.ARCHITECT: "the architect",
    CertifierRole.ENGINEER: "the engineer",
    CertifierRole.CA: "the CA",
}


def certificates_for(request: WithdrawalRequest) -> dict[CertifierRole, Certificate]:
    out = {}
    for row in request.certificates:
        role = CertifierRole(row.role)
        out[role] = Certificate(
            role=role,
            signed=row.signed,
            signer_name=row.signer_name,
            signer_firm=row.signer_firm,
            issued_on=row.issued_on,
            completion_pct=row.completion_pct,
            development_cost_incurred=row.development_cost_incurred,
            total_cost_incurred=row.total_cost_incurred,
            withdrawable_amount=row.withdrawable_amount,
        )
    return out


def _request_state(
    request: WithdrawalRequest,
    money: ProjectPosition,
    escrow: EscrowPosition,
    project: Project,
    as_of: date,
    rules: RulesPack,
) -> tuple[dict[CertifierRole, Certificate], list[Check], RequestStatus, str | None]:
    certificates = certificates_for(request)
    checks = check_request(
        request.amount,
        certificates,
        escrow,
        money,
        statutory_auditor_firm=project.statutory_auditor_firm,
        as_of=as_of,
        rules=rules,
    )
    if request.submitted_on is not None:
        # Once submitted, the figures are frozen; later ledger movement does not reopen checks.
        checks = [c for c in checks if c.code == "all_signed"]
    status = request_status(
        checks,
        submitted=request.submitted_on is not None,
        released=request.released_on is not None,
        rejected=request.rejected_on is not None,
    )
    waiting_on: str | None
    if status in (RequestStatus.RELEASED, RequestStatus.REJECTED):
        waiting_on = None
    elif status == RequestStatus.SUBMITTED:
        waiting_on = "the bank"
    else:
        unsigned = [r for r in ROLE_ORDER if not certificates.get(r) or not certificates[r].signed]
        if unsigned:
            waiting_on = ROLE_WAITING[unsigned[0]]
        elif any(c.status == CheckStatus.FAIL for c in checks):
            waiting_on = "corrected figures"
        else:
            waiting_on = "submission to the bank"
    return certificates, checks, status, waiting_on


@dataclass(frozen=True)
class RequestState:
    request: WithdrawalRequest
    snapshot: ProjectSnapshot
    certificates: dict[CertifierRole, Certificate]
    checks: list[Check]
    status: RequestStatus
    waiting_on: str | None


def request_state(session: Session, request: WithdrawalRequest, as_of: date) -> RequestState:
    project = get_project(session, request.project_id)
    snap = snapshot(session, project, as_of)
    certificates, checks, status, waiting_on = _request_state(
        request, snap.money, snap.escrow, project, as_of, KARNATAKA
    )
    return RequestState(request, snap, certificates, checks, status, waiting_on)


def get_request(session: Session, request_id: str) -> WithdrawalRequest:
    request = session.get(WithdrawalRequest, request_id)
    if request is None:
        raise ServiceError("Withdrawal request not found.", 404)
    return request


def create_withdrawal(
    session: Session,
    project: Project,
    amount: Decimal | None,
    as_of: date,
    *,
    user_id: str | None = None,
) -> WithdrawalRequest:
    if open_request(session, project) is not None:
        raise ServiceError("A withdrawal for this project is already under way.", 409)
    snap = snapshot(session, project, as_of)
    amount = snap.escrow.drawable_now if amount is None else amount
    if amount <= 0:
        raise ServiceError("Nothing can be withdrawn at the moment.")
    if amount > snap.escrow.drawable_now:
        raise ServiceError("The amount is more than can be withdrawn now.")

    drafts = draft_certificates(snap.escrow, snap.money)
    request = WithdrawalRequest(
        project_id=project.id, amount=amount, created_on=as_of, created_by_user_id=user_id
    )
    for role in ROLE_ORDER:
        draft = drafts[role]
        if role == CertifierRole.CA:
            draft = replace(draft, withdrawable_amount=amount)
        request.certificates.append(
            WithdrawalCertificate(
                role=role.value,
                completion_pct=draft.completion_pct,
                development_cost_incurred=draft.development_cost_incurred,
                total_cost_incurred=draft.total_cost_incurred,
                withdrawable_amount=draft.withdrawable_amount,
            )
        )
    session.add(request)
    session.commit()
    return request


def _certificate(request: WithdrawalRequest, role: CertifierRole) -> WithdrawalCertificate:
    for row in request.certificates:
        if row.role == role.value:
            return row
    raise ServiceError("Certificate not found.", 404)


def _require_editable(request: WithdrawalRequest) -> None:
    if not request.is_open or request.submitted_on is not None:
        raise ServiceError("This request has been submitted and can no longer change.", 409)


FIGURE_FIELDS = {
    CertifierRole.ARCHITECT: {"completion_pct"},
    CertifierRole.ENGINEER: {"development_cost_incurred"},
    CertifierRole.CA: {"total_cost_incurred", "withdrawable_amount"},
}


def update_certificate(
    session: Session, request: WithdrawalRequest, role: CertifierRole, figures: dict
) -> None:
    _require_editable(request)
    row = _certificate(request, role)
    if row.signed:
        raise ServiceError("This certificate is signed. Ask the signer to withdraw it first.", 409)
    for key, value in figures.items():
        if key not in FIGURE_FIELDS[role]:
            raise ServiceError(f"The {role.value} does not certify {key}.")
        setattr(row, key, value)
    session.commit()


def sign_certificate(
    session: Session,
    request: WithdrawalRequest,
    role: CertifierRole,
    *,
    signer_name: str,
    signer_firm: str | None,
    issued_on: date,
    user_id: str | None = None,
) -> None:
    _require_editable(request)
    if not signer_name.strip():
        raise ServiceError("The signer's name is missing.")
    if not signer_firm or not signer_firm.strip():
        raise ServiceError("Add your firm's name to your profile before signing.")
    row = _certificate(request, role)
    if row.signed:
        raise ServiceError("This certificate is already signed.", 409)
    row.signed = True
    row.signer_name = signer_name.strip()
    row.signer_firm = signer_firm.strip()
    row.issued_on = issued_on
    row.signed_by_user_id = user_id
    session.commit()


def submit_request(
    session: Session, request: WithdrawalRequest, as_of: date, *, user_id: str | None = None
) -> None:
    _require_editable(request)
    state = request_state(session, request, as_of)
    if not can_submit(state.checks):
        raise ServiceError("Every check must pass and all three certificates must be signed.")
    request.submitted_on = as_of
    request.submitted_by_user_id = user_id
    session.commit()


def release_request(
    session: Session,
    request: WithdrawalRequest,
    *,
    amount: Decimal | None,
    bank_reference: str | None,
    released_on: date,
    user_id: str | None = None,
) -> None:
    if request.submitted_on is None or not request.is_open:
        raise ServiceError("Only a submitted request can be released.", 409)
    released = request.amount if amount is None else amount
    if released <= 0 or released > request.amount:
        raise ServiceError("The released amount must be above zero and no more than requested.")
    request.released_on = released_on
    request.released_amount = released
    request.bank_reference = bank_reference
    request.released_by_user_id = user_id
    session.add(
        EscrowTxn(
            project_id=request.project_id,
            kind=TxnKind.WITHDRAWAL.value,
            amount=released,
            txn_date=released_on,
            reference=bank_reference or f"Withdrawal {request.id[:8]}",
        )
    )
    session.commit()


def reject_request(
    session: Session, request: WithdrawalRequest, *, reason: str, rejected_on: date
) -> None:
    if not request.is_open:
        raise ServiceError("This request is already closed.", 409)
    request.rejected_on = rejected_on
    request.rejection_reason = reason.strip() or None
    session.commit()


def project_requests(session: Session, project: Project) -> list[WithdrawalRequest]:
    return list(
        session.scalars(
            select(WithdrawalRequest)
            .where(WithdrawalRequest.project_id == project.id)
            .order_by(WithdrawalRequest.created_on.desc())
        )
    )


def landowners(session: Session, project: Project) -> list[Landowner]:
    return list(
        session.scalars(
            select(Landowner).where(Landowner.project_id == project.id).order_by(Landowner.name)
        )
    )


def project_units(session: Session, project: Project) -> list[Unit]:
    return list(
        session.scalars(select(Unit).where(Unit.project_id == project.id).order_by(Unit.label))
    )
