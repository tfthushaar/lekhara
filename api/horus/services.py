"""Loads a project from the database and runs the engines for a date.

Also holds the withdrawal workflow: create a request with drafted certificates,
let each certifier review and sign, submit to the bank, record the release.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

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
    EscrowTxn,
    Filing,
    Landowner,
    LandownerPaymentRow,
    LedgerEntry,
    Organization,
    ProgressCertificate,
    Project,
    Receipt,
    Unit,
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
    )


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
