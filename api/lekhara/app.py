import base64
import hmac
import json
import re
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Header, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lekhara import (
    accounts,
    auth,
    connectors,
    export,
    imports,
    inbound,
    jobs,
    legal,
    packs,
    purchases,
    record_views,
    registers,
    review,
    services,
    statutory,
    views,
)
from lekhara.bank import service as bank
from lekhara.config import Settings, get_settings
from lekhara.db import make_engine, make_sessionmaker
from lekhara.engines.escrow import ROLE_ORDER, CertifierRole, RequestStatus
from lekhara.engines.obligations import ObligationStatus, sort_obligations
from lekhara.gst import service as gst
from lekhara.migrate import upgrade
from lekhara.models import (
    Approval,
    Bill,
    Commitment,
    Connector,
    CostLineRow,
    Filing,
    InboundItem,
    InboundMessage,
    Landowner,
    LandownerPaymentRow,
    Membership,
    Organization,
    PaymentMilestone,
    Project,
    Receipt,
    StatementPassword,
    TrustedSender,
    Unit,
    User,
    Vendor,
)
from lekhara.money import ZERO
from lekhara.records import (
    APPROVALS,
    BILLS,
    COMMITMENTS,
    FILINGS,
    LANDOWNER_PAYMENTS,
    RECEIPTS,
    SUPPLIERS,
)
from lekhara.rules import KARNATAKA
from lekhara.secretbox import seal
from lekhara.services import ServiceError
from lekhara.storage import LocalStorage
from lekhara.tally import service as tally
from lekhara.tally.plan import UnitRef

DEMO_PASSWORD = "lekhara-demo"


class UnitBody(BaseModel):
    label: str | None = None
    tower: str | None = None
    carpet_area_sqft: str | None = None
    owner_share: str | None = None
    list_price: str | None = None
    guidance_value: str | None = None
    buyer_name: str | None = None
    buyer_phone: str | None = None
    buyer_email: str | None = None
    booked_on: str | None = None
    agreement_value: str | None = None


class TallyOptions(BaseModel):
    cost_centre: str | None = None
    links: dict[str, str | dict[str, str | None]] = {}


class ProjectBody(BaseModel):
    name: str | None = None
    krera_registration: str | None = None
    registered_on: str | None = None
    possession_due_on: str | None = None
    locality: str | None = None
    city: str | None = None
    spv_name: str | None = None
    land_structure: str | None = None
    gst_regime: str | None = None
    escrow_bank: str | None = None
    statutory_auditor_firm: str | None = None
    development_rights_value: str | None = None
    cess_paid: str | None = None
    oc_status: str | None = None
    oc_received_on: str | None = None
    oc_reference: str | None = None
    association_formed_on: str | None = None
    common_areas_conveyed_on: str | None = None


class ProgressBody(BaseModel):
    as_of: str | None = None
    completion_pct: str | None = None
    certified_by: str | None = None


class BillBody(BaseModel):
    supplier: str | None = None
    bill_no: str | None = None
    bill_date: str | None = None
    taxable_value: str | None = None
    gst_amount: str | None = None
    accepted_on: str | None = None
    paid_on: str | None = None
    cost_line: str | None = None
    is_cement: str | None = None
    rcm_paid: str | None = None
    excluded: str | None = None
    clear: list[str] | None = None


class SupplierBody(BaseModel):
    name: str | None = None
    gstin: str | None = None
    pan: str | None = None
    state: str | None = None
    msme_category: str | None = None
    udyam_number: str | None = None
    written_agreement: str | None = None
    clear: list[str] | None = None


class CommitmentBody(BaseModel):
    reference: str | None = None
    cost_line: str | None = None
    amount: str | None = None
    committed_on: str | None = None
    supplier: str | None = None
    description: str | None = None


class AllowBody(BaseModel):
    trust: bool = False


class SenderBody(BaseModel):
    address: str = ""


class PasswordBody(BaseModel):
    label: str | None = None
    password: str | None = None


class ConnectorLink(BaseModel):
    code: str = ""
    name: str | None = None


class ConnectorBeat(BaseModel):
    state: str | None = None
    company: str | None = None


class GstOptions(BaseModel):
    add_missing: bool | None = None


class StatementOptions(BaseModel):
    role: str | None = None
    buyers_pay_here: bool | None = None
    lines: dict[str, str | None] | None = None


class PlanBody(BaseModel):
    stages: list[dict] = []


class TemplateBody(BaseModel):
    template: str = ""


class ReceiptBody(BaseModel):
    received_on: str | None = None
    amount: str | None = None
    tds_deducted: str | None = None
    reference: str | None = None


class CostLineBody(BaseModel):
    code: str | None = None
    name: str | None = None
    category: str | None = None
    original_budget: str | None = None
    revised_budget: str | None = None


class LandownerBody(BaseModel):
    name: str | None = None
    share_type: str | None = None
    share_pct: str | None = None
    refundable_deposit: str | None = None
    pan: str | None = None


class LandownerPaymentBody(BaseModel):
    paid_on: str | None = None
    amount: str | None = None
    tds_deducted: str | None = None
    deposit: str | None = None
    reference: str | None = None


class ApprovalBody(BaseModel):
    name: str | None = None
    authority: str | None = None
    reference: str | None = None
    applied_on: str | None = None
    granted_on: str | None = None
    valid_until: str | None = None
    note: str | None = None


class FilingBody(BaseModel):
    kind: str | None = None
    period_end: str | None = None
    filed_on: str | None = None
    reference: str | None = None


class TableBody(BaseModel):
    rows: list[list[str]]


class MappingBody(BaseModel):
    mapping: dict[str, str | None] = {}


class Signup(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None
    firm: str | None = None
    accept_terms: bool | None = None


class TokenBody(BaseModel):
    token: str


class Forgot(BaseModel):
    email: str | None = None


class Reset(BaseModel):
    token: str
    password: str | None = None


class FirmUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    gstin: str | None = None


class NewInvitation(BaseModel):
    email: str | None = None
    role: str | None = None
    project_ids: list[str] = []


class Acceptance(BaseModel):
    name: str | None = None
    password: str | None = None
    firm: str | None = None
    accept_terms: bool | None = None


class PasswordCheck(BaseModel):
    password: str | None = None


class CloseFirm(BaseModel):
    confirm: str | None = None


class RoleChange(BaseModel):
    role: str | None = None


class NewProject(BaseModel):
    name: str | None = None
    krera_registration: str | None = None
    registered_on: date | None = None
    possession_due_on: date | None = None
    locality: str | None = None
    city: str | None = None
    spv_name: str | None = None
    land_structure: str | None = None
    gst_regime: str | None = None
    escrow_bank: str | None = None


class Login(BaseModel):
    email: str
    password: str


class NewCase(BaseModel):
    forum: str
    case_number: str
    relief: str
    complainant: str | None = None
    unit: str | None = None
    filed_on: date | None = None
    notice_received_on: date | None = None
    claim_amount: Decimal | None = None
    reply_due_on: date | None = None
    next_hearing_on: date | None = None
    lawyer: str | None = None
    summary: str | None = None


class CaseUpdate(BaseModel):
    status: str | None = None
    lawyer: str | None = None
    summary: str | None = None
    claim_amount: Decimal | None = None
    reply_due_on: date | None = None
    reply_filed_on: date | None = None
    next_hearing_on: date | None = None
    settlement_offered: Decimal | None = None
    settlement_agreed: Decimal | None = None
    appealed_on: date | None = None


class NewHearing(BaseModel):
    held_on: date
    purpose: str | None = None
    outcome: str | None = None
    next_hearing_on: date | None = None
    order_reserved: bool = False


class NewOrder(BaseModel):
    ordered_on: date
    kind: str
    amount: Decimal | None = None
    comply_by: date | None = None
    received_on: date | None = None
    summary: str | None = None


class NewPayment(BaseModel):
    paid_on: date
    amount: Decimal
    reference: str | None = None


class DocumentUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    document_date: date | None = None
    expires_on: date | None = None
    reference: str | None = None
    notes: str | None = None
    requirement: str | None = None


class Waiver(BaseModel):
    reason: str | None = None


class NewRoom(BaseModel):
    name: str
    audience: str | None = None
    expires_on: date | None = None
    document_ids: list[str] = []


class RoomUpdate(BaseModel):
    name: str | None = None
    audience: str | None = None
    expires_on: date | None = None
    document_ids: list[str] | None = None


class HandoverUpdate(BaseModel):
    ekhata_status: str | None = None
    khata_type: str | None = None
    deed_drafted_on: date | None = None
    appointment_on: date | None = None
    registered_on: date | None = None
    document_no: str | None = None
    possession_on: date | None = None


class NewWithdrawal(BaseModel):
    amount: Decimal | None = None


class CertificateFigures(BaseModel):
    completion_pct: Decimal | None = None
    development_cost_incurred: Decimal | None = None
    total_cost_incurred: Decimal | None = None
    withdrawable_amount: Decimal | None = None


class SignCertificate(BaseModel):
    issued_on: date | None = None


class ReleaseWithdrawal(BaseModel):
    amount: Decimal | None = None
    bank_reference: str | None = None
    released_on: date | None = None


class RejectWithdrawal(BaseModel):
    reason: str = ""


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _withdrawal_permissions(
    principal: auth.Principal, project: Project, state: services.RequestState
) -> dict:
    editable = state.request.is_open and state.request.submitted_on is None
    unsigned = [
        role.value
        for role in ROLE_ORDER
        if principal.certifies(project, role)
        and not (state.certificates.get(role) and state.certificates[role].signed)
    ]
    return {
        "edit_roles": unsigned if editable else [],
        "sign_roles": unsigned if editable else [],
        "can_submit": principal.can_prepare(project) and state.status == RequestStatus.READY,
        "can_release": principal.can_release(project) and state.status == RequestStatus.SUBMITTED,
    }


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or make_engine(settings.database_url)
    if settings.auto_migrate:
        upgrade(engine)
    session_factory = make_sessionmaker(engine)
    throttle = auth.LoginThrottle()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker = None
        if settings.worker:
            worker = jobs.Worker(session_factory, app.state.storage, settings)
            worker.start()
        yield
        if worker is not None:
            worker.stop()

    app = FastAPI(title="Lekhara API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.storage = LocalStorage(settings.storage_dir)

    def get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    def as_of() -> date:
        return settings.as_of()

    def client(request: Request) -> tuple[str | None, str | None]:
        forwarded = (
            request.headers.get("x-lekhara-client-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        )
        ip = forwarded or (request.client.host if request.client else None)
        agent = request.headers.get("x-lekhara-user-agent") or request.headers.get("user-agent")
        return ip, agent

    def log(session: Session, request: Request, action: str, *, me=None, user=None,
            organization_id=None, detail=None) -> None:  # fmt: skip
        ip, agent = client(request)
        if user is None and me is not None:
            user = session.get(User, me.user_id)
        if organization_id is None and me is not None and me.org_roles:
            organization_id = next(iter(me.org_roles))
        legal.record(
            session, action, user=user, organization_id=organization_id, detail=detail, ip=ip,
            user_agent=agent,
        )  # fmt: skip

    SessionDep = Annotated[Session, Depends(get_session)]
    AsOf = Annotated[date, Depends(as_of)]

    def current_principal(
        session: SessionDep, authorization: Annotated[str | None, Header()] = None
    ) -> auth.Principal:
        token = _bearer(authorization)
        if token is None:
            raise ServiceError("Sign in to continue.", 401)
        principal = auth.principal_for(session, token, settings.as_of())
        if principal is None:
            raise ServiceError("Your session has ended. Sign in again.", 401)
        return principal

    Me = Annotated[auth.Principal, Depends(current_principal)]

    def visible(session: Session, me: auth.Principal) -> list[Project]:
        return services.visible_projects(session, set(me.org_roles), set(me.project_roles))

    def viewable_project(session: Session, me: auth.Principal, project_id: str) -> Project:
        project = services.get_project(session, project_id)
        auth.require_view(me, project)
        return project

    @app.exception_handler(ServiceError)
    def service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Sign-in

    @app.post("/auth/login")
    def login(body: Login, session: SessionDep, request: Request) -> dict:
        try:
            token, user = auth.login(session, body.email, body.password, throttle)
        except ServiceError:
            session.rollback()
            log(session, request, "sign_in_failed", detail=(body.email or "")[:200])
            raise
        orgs = list(
            session.scalars(select(Membership.organization_id).where(Membership.user_id == user.id))
        )
        log(session, request, "sign_in", user=user, organization_id=orgs[0] if orgs else None)
        return {"token": token, "user": {"id": user.id, "name": user.name, "email": user.email}}

    @app.post("/auth/logout", status_code=204)
    def logout(
        session: SessionDep, authorization: Annotated[str | None, Header()] = None
    ) -> Response:
        token = _bearer(authorization)
        if token:
            auth.logout(session, token)
        return Response(status_code=204)

    @app.get("/auth/me")
    def me(session: SessionDep, me: Me, on: AsOf) -> dict:
        organizations = [
            org.name
            for org in session.scalars(
                select(Organization).where(Organization.id.in_(set(me.org_roles)))
            )
        ]
        user = session.get(User, me.user_id)
        firm = None
        if me.org_roles:
            org = accounts.current_org(session, me)
            role = me.org_roles[org.id]
            firm = {
                "id": org.id,
                "name": org.name,
                "access": services.access_state(org, on),
                "trial_ends_on": views.d(org.trial_ends_on),
                "days_left": services.trial_days_left(org, on),
                "is_sample": org.is_sample,
                "delete_after": views.d(org.delete_after),
                "can_add_projects": role
                in (auth.OrgRole.OWNER, auth.OrgRole.FINANCE, auth.OrgRole.ACCOUNTS),
            }
        return {
            "user": {"id": me.user_id, "name": me.name, "email": me.email, "firm": me.firm},
            "role_label": me.describe(),
            "kind": "certifier" if me.is_certifier_only else "team",
            "organizations": organizations,
            "organization": firm,
            "email_verified": user.email_verified_at is not None,
            "terms_accepted": legal.accepted(session, me.user_id),
        }

    @app.get("/auth/demo")
    def demo_accounts(session: SessionDep) -> dict:
        if not settings.demo:
            raise ServiceError("Not found.", 404)
        from lekhara.seed import DEMO_ACCOUNTS

        return {
            "password": DEMO_PASSWORD,
            "accounts": [
                {"email": a.email, "name": a.name, "label": a.label} for a in DEMO_ACCOUNTS
            ],
        }

    # Sign-up, email checks and passwords

    @app.post("/auth/signup", status_code=201)
    def signup(body: Signup, session: SessionDep, on: AsOf, request: Request) -> dict:
        legal.require_acceptance(body.accept_terms)
        token, user = accounts.signup(
            session,
            settings,
            name=body.name,
            email=body.email,
            password=body.password,
            firm=body.firm,
            as_of=on,
        )
        org_id = session.scalars(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        ).first()
        legal.accept(session, user, organization_id=org_id, ip=client(request)[0], manager=True)
        session.commit()
        log(session, request, "signed_up", user=user, organization_id=org_id)
        return {"token": token, "user": {"id": user.id, "name": user.name, "email": user.email}}

    @app.post("/auth/verify")
    def verify(body: TokenBody, session: SessionDep) -> dict:
        user = accounts.verify_email(session, body.token)
        return {"email": user.email}

    @app.post("/auth/verify/resend")
    def resend_verification(session: SessionDep, me: Me) -> dict:
        user = session.get(User, me.user_id)
        if user.email_verified_at is None:
            accounts.send_verification(session, settings, user)
            session.commit()
        return {"ok": True}

    @app.post("/auth/forgot")
    def forgot(body: Forgot, session: SessionDep) -> dict:
        key = f"forgot:{(body.email or '').strip().casefold()}"
        throttle.check(key)
        throttle.failed(key)  # counts every request, so the form cannot be used to flood a mailbox
        accounts.forgot_password(session, settings, body.email)
        return {"ok": True}

    @app.post("/auth/reset")
    def reset(body: Reset, session: SessionDep, request: Request) -> dict:
        accounts.reset_password(session, body.token, body.password)
        log(session, request, "password_reset")
        return {"ok": True}

    # The law: terms accepted, the access log, deleting an account, closing a firm

    @app.get("/legal")
    def legal_info() -> dict:
        return legal.public_info(settings)

    @app.post("/auth/accept-terms")
    def accept_terms(session: SessionDep, me: Me, request: Request) -> dict:
        user = session.get(User, me.user_id)
        org_id = next(iter(me.org_roles), None)
        manager = me.org_roles.get(org_id) in (auth.OrgRole.OWNER, auth.OrgRole.FINANCE)
        legal.accept(session, user, organization_id=org_id, ip=client(request)[0], manager=manager)
        session.commit()
        log(session, request, "terms_accepted", user=user, organization_id=org_id,
            detail=legal.VERSION)  # fmt: skip
        return {"ok": True}

    @app.post("/auth/delete-account")
    def delete_account(body: PasswordCheck, session: SessionDep, me: Me, request: Request) -> dict:
        user = session.get(User, me.user_id)
        if not auth.verify_password(body.password or "", user.password_hash):
            raise ServiceError("That password is not right.", 400)
        legal.delete_account(session, user, ip=client(request)[0])
        return {"ok": True}

    @app.get("/organization/access-log")
    def access_log(session: SessionDep, me: Me) -> dict:
        org = accounts.current_org(session, me)
        accounts.require_manager(me, org)
        return {
            "keep_days": legal.LOG_DAYS,
            "events": [
                {
                    "at": e.at.replace(microsecond=0).isoformat(),
                    "who": e.who,
                    "action": e.action,
                    "detail": e.detail,
                    "ip": e.ip,
                }
                for e in legal.events_for(session, org.id)
            ],
        }

    @app.post("/organization/close")
    def close_firm(
        body: CloseFirm, session: SessionDep, me: Me, on: AsOf, request: Request
    ) -> dict:
        org = accounts.current_org(session, me)
        accounts.require_manager(me, org, owner=True)
        legal.close_firm(
            session, org, confirm=body.confirm or "", as_of=on, user=session.get(User, me.user_id),
            ip=client(request)[0],
        )  # fmt: skip
        return firm_view(session, me, org, on)

    @app.post("/organization/keep")
    def keep_firm(session: SessionDep, me: Me, on: AsOf, request: Request) -> dict:
        org = accounts.current_org(session, me)
        accounts.require_manager(me, org, owner=True)
        legal.keep_firm(session, org, user=session.get(User, me.user_id), ip=client(request)[0])
        return firm_view(session, me, org, on)

    # The firm, its team and its subscription

    def firm_view(session: Session, me: auth.Principal, org: Organization, on: date) -> dict:
        role = me.org_roles[org.id]
        projects = list(
            session.scalars(
                select(Project).where(Project.organization_id == org.id).order_by(Project.name)
            )
        )
        return {
            "id": org.id,
            "name": org.name,
            "legal_name": org.legal_name,
            "gstin": org.gstin,
            "state": accounts.GSTIN_STATE.get((org.gstin or "")[:2]) if org.gstin else None,
            "access": services.access_state(org, on),
            "trial_ends_on": views.d(org.trial_ends_on),
            "days_left": services.trial_days_left(org, on),
            "is_sample": org.is_sample,
            "closing_on": views.d(org.closing_on),
            "delete_after": views.d(org.delete_after),
            "role": role.value,
            "can_manage": role in (auth.OrgRole.OWNER, auth.OrgRole.FINANCE),
            "is_owner": role == auth.OrgRole.OWNER,
            "members": [
                {
                    "user_id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "role": r,
                    "role_label": accounts.ROLE_LABEL[r],
                    "you": u.id == me.user_id,
                }
                for u, r in accounts.team(session, org)
            ],
            "certifiers": [
                {
                    "user_id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "firm": u.firm,
                    "role_label": accounts.ROLE_LABEL[r],
                    "projects": [p.name for p in ps],
                }
                for u, r, ps in accounts.certifiers(session, org)
            ],
            "invitations": [
                {
                    "id": i.id,
                    "email": i.email,
                    "role_label": accounts.ROLE_LABEL[i.org_role or i.certifier_role],
                    "expires_on": views.d(i.expires_at.date()),
                }
                for i in accounts.pending_invitations(session, org)
            ],
            "projects": [{"id": p.id, "name": p.name} for p in projects],
            "roles": [
                {"value": value, "label": label} for value, label in accounts.ROLE_LABEL.items()
            ],
        }

    @app.get("/organization")
    def get_firm(session: SessionDep, me: Me, on: AsOf) -> dict:
        return firm_view(session, me, accounts.current_org(session, me), on)

    @app.put("/organization")
    def update_firm(body: FirmUpdate, session: SessionDep, me: Me, on: AsOf) -> dict:
        org = accounts.current_org(session, me)
        accounts.require_manager(me, org, owner=True)
        accounts.update_org(session, org, body.model_dump(exclude_unset=True))
        return firm_view(session, me, org, on)

    @app.get("/organization/export")
    def export_workspace(
        session: SessionDep, me: Me, on: AsOf, request: Request
    ) -> StreamingResponse:
        """Everything the firm has, at any time, even when the workspace is read-only."""
        org = accounts.current_org(session, me)
        accounts.require_manager(me, org)
        done = export.workspace(session, app.state.storage, org, as_of=on, user_id=me.user_id)
        log(session, request, "workspace_exported", me=me, organization_id=org.id)
        ascii_name = done.filename.encode("ascii", "replace").decode().replace("?", "-")
        return StreamingResponse(
            done.chunks(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(done.filename)}",
                "Cache-Control": "private, no-store",
            },
        )

    @app.post("/organization/invitations", status_code=201)
    def invite(body: NewInvitation, session: SessionDep, me: Me, request: Request) -> dict:
        org = accounts.current_org(session, me)
        row, link = accounts.invite(
            session,
            settings,
            org,
            me,
            email=body.email,
            role=body.role,
            project_ids=body.project_ids,
        )
        log(session, request, "invitation_sent", me=me, organization_id=org.id,
            detail=f"{body.email} as {body.role}")  # fmt: skip
        return {"id": row.id, "link": link}

    @app.post("/organization/invitations/{invitation_id}/cancel")
    def cancel_invitation(invitation_id: str, session: SessionDep, me: Me) -> dict:
        accounts.cancel_invitation(session, accounts.current_org(session, me), me, invitation_id)
        return {"ok": True}

    @app.put("/organization/members/{user_id}")
    def change_role(
        user_id: str, body: RoleChange, session: SessionDep, me: Me, request: Request
    ) -> dict:
        accounts.change_role(session, accounts.current_org(session, me), me, user_id, body.role)
        person = session.get(User, user_id)
        log(session, request, "role_changed", me=me,
            detail=f"{person.email if person else user_id} to {body.role}")  # fmt: skip
        return {"ok": True}

    @app.post("/organization/members/{user_id}/remove")
    def remove_member(user_id: str, session: SessionDep, me: Me, request: Request) -> dict:
        person = session.get(User, user_id)
        email = person.email if person else user_id
        accounts.remove_member(session, accounts.current_org(session, me), me, user_id)
        log(session, request, "member_removed", me=me, detail=email)
        return {"ok": True}

    @app.get("/invitations/{token}")
    def get_invitation(token: str, session: SessionDep) -> dict:
        row = accounts.invitation_by_token(session, token)
        org = session.get(Organization, row.organization_id)
        return {
            "firm": org.name,
            "email": row.email,
            "role": row.org_role or row.certifier_role,
            "role_label": accounts.ROLE_LABEL[row.org_role or row.certifier_role],
            "certifier": row.certifier_role is not None,
            "projects": [p.name for p in accounts.invitation_projects(session, row)],
            "has_account": session.scalars(select(User).where(User.email == row.email)).first()
            is not None,
        }

    @app.post("/invitations/{token}/accept")
    def accept_invitation(
        token: str, body: Acceptance, session: SessionDep, request: Request
    ) -> dict:
        invitation = accounts.invitation_by_token(session, token)
        new_account = (
            session.scalars(select(User).where(User.email == invitation.email)).first() is None
        )
        if new_account:
            legal.require_acceptance(body.accept_terms)
        session_token = accounts.accept_invitation(
            session, settings, token, name=body.name, password=body.password, firm=body.firm
        )
        principal = auth.principal_for(session, session_token, settings.as_of())
        user = session.get(User, principal.user_id)
        if new_account or body.accept_terms:
            manager = invitation.org_role in (auth.OrgRole.OWNER.value, auth.OrgRole.FINANCE.value)
            legal.accept(
                session, user, organization_id=invitation.organization_id,
                ip=client(request)[0], manager=manager,
            )  # fmt: skip
            session.commit()
        log(session, request, "invitation_accepted", user=user,
            organization_id=invitation.organization_id)  # fmt: skip
        return {"token": session_token}

    @app.post("/projects", status_code=201)
    def create_project(body: NewProject, session: SessionDep, me: Me, on: AsOf) -> dict:
        org = accounts.current_org(session, me)
        if services.access_state(org, on) == "read_only":
            raise ServiceError(auth.READ_ONLY, 402)
        project = accounts.create_project(session, org, me, body.model_dump())
        return {"id": project.id}

    # Units and buyers: add, edit, delete, with history

    def unit_for(session: Session, me: auth.Principal, unit_id: str, *, edit=False):
        unit = services.get_unit(session, unit_id)
        p = services.get_project(session, unit.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return unit, p

    def unit_view(session: Session, me: auth.Principal, unit, p: Project) -> dict:
        changes = registers.history(session, "unit", unit.id)
        ids = {c.user_id for c in changes if c.user_id}
        names = {u.id: u.name for u in session.scalars(select(User).where(User.id.in_(ids)))}
        return views.unit_detail(
            unit,
            p,
            changes,
            names,
            can_edit=me.can_prepare(p) and not me.views_as_sample(p),
            dependents=registers.unit_dependents(session, unit),
            receipts=registers.unit_receipts(session, unit),
        )

    @app.post("/projects/{project_id}/units", status_code=201)
    def create_unit(project_id: str, body: UnitBody, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        values = registers.parse_unit_form(body.model_dump(exclude_unset=True))
        unit = registers.create_unit(session, p, values, user_id=me.user_id)
        session.commit()
        return {"id": unit.id}

    @app.get("/units/{unit_id}")
    def get_unit(unit_id: str, session: SessionDep, me: Me) -> dict:
        unit, p = unit_for(session, me, unit_id)
        return unit_view(session, me, unit, p)

    @app.put("/units/{unit_id}")
    def update_unit(unit_id: str, body: UnitBody, session: SessionDep, me: Me) -> dict:
        unit, p = unit_for(session, me, unit_id, edit=True)
        values = registers.parse_unit_form(body.model_dump(exclude_unset=True))
        registers.update_unit(session, p, unit, values, user_id=me.user_id)
        session.commit()
        return unit_view(session, me, unit, p)

    @app.post("/units/{unit_id}/unsold")
    def unit_unsold(unit_id: str, session: SessionDep, me: Me) -> dict:
        unit, p = unit_for(session, me, unit_id, edit=True)
        registers.clear_buyer(session, p, unit, user_id=me.user_id)
        session.commit()
        return unit_view(session, me, unit, p)

    @app.post("/units/{unit_id}/delete")
    def delete_unit(unit_id: str, session: SessionDep, me: Me) -> dict:
        unit, p = unit_for(session, me, unit_id, edit=True)
        registers.delete_unit(session, p, unit, user_id=me.user_id)
        session.commit()
        return {"project_id": p.id}

    # The Import centre, templates and exports

    def file_download(data: bytes, filename: str) -> Response:
        media = (
            "text/csv; charset=utf-8"
            if filename.endswith(".csv")
            else "application/pdf"
            if filename.endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        return Response(
            content=data,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
            },
        )

    def split_name(name: str) -> tuple[str, str]:
        kind, _, fmt = name.partition(".")
        if fmt not in ("xlsx", "csv"):
            raise ServiceError("Not found.", 404)
        imports.record_type(kind)
        return kind, fmt

    @app.get("/imports/templates/{name}")
    def import_template(name: str, me: Me) -> Response:
        kind, fmt = split_name(name)
        return file_download(imports.template(kind, fmt), f"lekhara-{kind}-template.{fmt}")

    @app.get("/projects/{project_id}/exports/{name}")
    def export_records(
        project_id: str, name: str, session: SessionDep, me: Me, on: AsOf
    ) -> Response:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        kind, fmt = split_name(name)
        data = imports.export(session, p, kind, fmt)
        return file_download(data, f"{p.name} {kind} {on.isoformat()}.{fmt}".replace(" ", "-"))

    @app.post("/projects/{project_id}/imports/{kind}", status_code=201)
    def start_import(
        project_id: str, kind: str, session: SessionDep, me: Me, file: UploadFile
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        data = file.file.read(settings.max_upload_mb * 1_000_000 + 1)
        if len(data) > settings.max_upload_mb * 1_000_000:
            raise ServiceError(f"Files can be up to {settings.max_upload_mb} MB.")
        batch = imports.start(
            session, p, kind, filename=file.filename or "import", data=data, user_id=me.user_id
        )
        return {"id": batch.id}

    @app.get("/projects/{project_id}/imports")
    def list_imports(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return {
            "can_import": me.can_prepare(p) and not me.views_as_sample(p),
            "imports": [views.batch_row(b) for b in imports.project_batches(session, p)],
        }

    def batch_for(session: Session, me: auth.Principal, batch_id: str, *, edit=False):
        batch = imports.get_batch(session, batch_id)
        p = services.get_project(session, batch.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return batch, p

    def batch_view(session: Session, me: auth.Principal, batch, p: Project) -> dict:
        on = settings.as_of()
        rows = imports.evaluate(session, batch, as_of=on) if batch.status == "preview" else None
        editable = me.can_prepare(p) and not me.views_as_sample(p)
        return views.import_batch(
            batch, rows, p, can_edit=editable, can_undo=editable and imports.can_undo(batch)
        )

    @app.get("/imports/{batch_id}")
    def get_import(batch_id: str, session: SessionDep, me: Me) -> dict:
        batch, p = batch_for(session, me, batch_id)
        return batch_view(session, me, batch, p)

    @app.put("/imports/{batch_id}/mapping")
    def map_import(batch_id: str, body: MappingBody, session: SessionDep, me: Me) -> dict:
        batch, p = batch_for(session, me, batch_id, edit=True)
        imports.set_mapping(session, batch, body.mapping)
        return batch_view(session, me, batch, p)

    @app.post("/imports/{batch_id}/apply")
    def apply_import(batch_id: str, session: SessionDep, me: Me) -> dict:
        batch, p = batch_for(session, me, batch_id, edit=True)
        imports.apply(session, batch, user_id=me.user_id, as_of=settings.as_of())
        return batch_view(session, me, batch, p)

    @app.post("/imports/{batch_id}/undo")
    def undo_import(batch_id: str, session: SessionDep, me: Me) -> dict:
        batch, p = batch_for(session, me, batch_id, edit=True)
        imports.undo(session, batch, user_id=me.user_id)
        return batch_view(session, me, batch, p)

    # Project set-up

    def readiness_view(session: Session, me: auth.Principal, p: Project, on: date) -> dict:
        from lekhara.readiness import readiness

        return views.readiness(
            readiness(session, p, on), p, can_edit=me.can_prepare(p) and not me.views_as_sample(p)
        )

    @app.get("/projects/{project_id}/setup")
    def project_setup(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return readiness_view(session, me, p, on)

    @app.put("/projects/{project_id}")
    def update_project(
        project_id: str, body: ProjectBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        registers.update_project(
            session, p, body.model_dump(exclude_unset=True), user_id=me.user_id
        )
        session.commit()
        return readiness_view(session, me, p, on)

    @app.post("/projects/{project_id}/progress", status_code=201)
    def record_progress(
        project_id: str, body: ProgressBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_view(me, p)
        if not (
            me.can_prepare(p)
            or me.certifies(p, CertifierRole.ARCHITECT)
            or me.certifies(p, CertifierRole.ENGINEER)
        ):
            raise ServiceError(
                "Only the team, or the project's architect or engineer, can record progress.",
                403,
            )
        auth.require_writable(me, p)
        certified_by = body.certified_by or me.firm or me.name
        registers.record_progress(
            session, p, body.model_dump(), as_of=on, certified_by=certified_by, user_id=me.user_id
        )
        session.commit()
        return readiness_view(session, me, p, on) if me.is_team(p) else {"ok": True}

    # Payment plans and buyer payments

    @app.get("/projects/{project_id}/payment-plan")
    def get_payment_plan(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return views.payment_plan(
            registers.payment_plan(session, p),
            registers.demands_by_milestone(session, p),
            can_edit=me.can_prepare(p) and not me.views_as_sample(p),
        )

    @app.put("/projects/{project_id}/payment-plan")
    def put_payment_plan(project_id: str, body: PlanBody, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        registers.replace_plan(session, p, body.stages, user_id=me.user_id)
        session.commit()
        return get_payment_plan(project_id, session, me)

    @app.post("/projects/{project_id}/payment-plan/template")
    def plan_template(project_id: str, body: TemplateBody, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        registers.apply_template(session, p, body.template, user_id=me.user_id)
        session.commit()
        return get_payment_plan(project_id, session, me)

    @app.post("/units/{unit_id}/receipts", status_code=201)
    def record_receipt(unit_id: str, body: ReceiptBody, session: SessionDep, me: Me) -> dict:
        unit, p = unit_for(session, me, unit_id, edit=True)
        values, problems = registers.parse_row(
            RECEIPTS, {k: v for k, v in body.model_dump().items() if v not in (None, "")}
        )
        if problems:
            raise ServiceError(" ".join(problems))
        receipt = registers.create_receipt(session, p, unit, values, user_id=me.user_id)
        session.commit()
        return {"id": receipt.id}

    @app.post("/receipts/{receipt_id}/delete")
    def delete_receipt(receipt_id: str, session: SessionDep, me: Me) -> dict:
        receipt = session.get(Receipt, receipt_id)
        if receipt is None:
            raise ServiceError("Payment not found.", 404)
        p = services.get_project(session, receipt.project_id)
        auth.require_prepare(me, p)
        unit_id = receipt.unit_id
        registers.delete_receipt(session, p, receipt, user_id=me.user_id)
        session.commit()
        return {"unit_id": unit_id}

    # Cost lines and landowners

    @app.get("/projects/{project_id}/cost-lines")
    def get_cost_lines(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return views.cost_lines(
            registers.cost_lines(session, p),
            services.snapshot(session, p, on),
            can_edit=me.can_prepare(p) and not me.views_as_sample(p),
        )

    @app.post("/projects/{project_id}/cost-lines/standard")
    def standard_cost_lines(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        added = registers.add_standard_lines(session, p, user_id=me.user_id)
        session.commit()
        return {"added": added}

    @app.post("/projects/{project_id}/cost-lines", status_code=201)
    def create_cost_line(project_id: str, body: CostLineBody, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        line = registers.create_cost_line(
            session, p, body.model_dump(exclude_unset=True), user_id=me.user_id
        )
        session.commit()
        return {"id": line.id}

    def cost_line_for(session: Session, me: auth.Principal, line_id: str):
        line = session.get(CostLineRow, line_id)
        if line is None:
            raise ServiceError("Cost line not found.", 404)
        p = services.get_project(session, line.project_id)
        auth.require_prepare(me, p)
        return line, p

    @app.put("/cost-lines/{line_id}")
    def update_cost_line(line_id: str, body: CostLineBody, session: SessionDep, me: Me) -> dict:
        line, p = cost_line_for(session, me, line_id)
        registers.update_cost_line(
            session, p, line, body.model_dump(exclude_unset=True), user_id=me.user_id
        )
        session.commit()
        return {"ok": True}

    @app.post("/cost-lines/{line_id}/delete")
    def delete_cost_line(line_id: str, session: SessionDep, me: Me) -> dict:
        line, p = cost_line_for(session, me, line_id)
        registers.delete_cost_line(session, p, line, user_id=me.user_id)
        session.commit()
        return {"project_id": p.id}

    @app.post("/projects/{project_id}/landowners", status_code=201)
    def create_landowner(project_id: str, body: LandownerBody, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        owner = registers.create_landowner(
            session, p, body.model_dump(exclude_unset=True), user_id=me.user_id
        )
        session.commit()
        return {"id": owner.id}

    @app.put("/landowners/{owner_id}")
    def update_landowner(owner_id: str, body: LandownerBody, session: SessionDep, me: Me) -> dict:
        owner = session.get(Landowner, owner_id)
        if owner is None:
            raise ServiceError("Landowner not found.", 404)
        p = services.get_project(session, owner.project_id)
        auth.require_prepare(me, p)
        registers.update_landowner(
            session, p, owner, body.model_dump(exclude_unset=True), user_id=me.user_id
        )
        session.commit()
        return {"ok": True}

    # Landowners and their payments

    def landowner_for(session: Session, me: auth.Principal, owner_id: str, *, edit=False):
        owner = session.get(Landowner, owner_id)
        if owner is None:
            raise ServiceError("Landowner not found.", 404)
        p = services.get_project(session, owner.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return owner, p

    def landowner_view(session: Session, me: auth.Principal, owner, p: Project) -> dict:
        session.refresh(owner)
        changes = registers.landowner_history(session, owner)
        return record_views.landowner_detail(
            session,
            owner,
            p,
            names_for(session, changes),
            can_edit=me.can_prepare(p) and not me.views_as_sample(p),
        )

    @app.get("/landowners/{owner_id}")
    def get_landowner(owner_id: str, session: SessionDep, me: Me) -> dict:
        owner, p = landowner_for(session, me, owner_id)
        return landowner_view(session, me, owner, p)

    @app.post("/landowners/{owner_id}/payments", status_code=201)
    def add_landowner_payment(
        owner_id: str, body: LandownerPaymentBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        owner, p = landowner_for(session, me, owner_id, edit=True)
        values, _ = form_values(LANDOWNER_PAYMENTS, body)
        registers.create_landowner_payment(session, p, owner, values, as_of=on, user_id=me.user_id)
        session.commit()
        return landowner_view(session, me, owner, p)

    def landowner_payment_for(session: Session, me: auth.Principal, payment_id: str):
        payment = session.get(LandownerPaymentRow, payment_id)
        if payment is None:
            raise ServiceError("Payment not found.", 404)
        owner, p = landowner_for(session, me, payment.landowner_id, edit=True)
        return payment, owner, p

    @app.put("/landowner-payments/{payment_id}")
    def update_landowner_payment(
        payment_id: str, body: LandownerPaymentBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        payment, owner, p = landowner_payment_for(session, me, payment_id)
        values, _ = form_values(LANDOWNER_PAYMENTS, body)
        if "reference" in body.model_fields_set and not body.reference:
            values["reference"] = None
        if "tds_deducted" in body.model_fields_set and not body.tds_deducted:
            values["tds_deducted"] = ZERO
        registers.update_landowner_payment(
            session, p, payment, values, as_of=on, user_id=me.user_id
        )
        session.commit()
        return landowner_view(session, me, owner, p)

    @app.post("/landowner-payments/{payment_id}/delete")
    def delete_landowner_payment(payment_id: str, session: SessionDep, me: Me) -> dict:
        payment, owner, p = landowner_payment_for(session, me, payment_id)
        registers.delete_landowner_payment(session, p, payment, user_id=me.user_id)
        session.commit()
        return landowner_view(session, me, owner, p)

    # Approvals

    def approvals_for(session: Session, me: auth.Principal, p: Project, on: date) -> dict:
        return record_views.approvals_view(
            session,
            p,
            lambda changes: names_for(session, changes),
            can_edit=me.can_prepare(p) and not me.views_as_sample(p),
            as_of=on,
        )

    @app.get("/projects/{project_id}/approvals")
    def project_approvals(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return approvals_for(session, me, p, on)

    @app.post("/projects/{project_id}/approvals", status_code=201)
    def create_approval(
        project_id: str, body: ApprovalBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        values, _ = form_values(APPROVALS, body)
        statutory.create_approval(session, p, values, as_of=on, user_id=me.user_id)
        session.commit()
        return approvals_for(session, me, p, on)

    @app.post("/projects/{project_id}/approvals/standard")
    def standard_approvals(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        statutory.add_standard_approvals(session, p, as_of=on, user_id=me.user_id)
        session.commit()
        return approvals_for(session, me, p, on)

    def approval_for(session: Session, me: auth.Principal, approval_id: str):
        a = session.get(Approval, approval_id)
        if a is None:
            raise ServiceError("Approval not found.", 404)
        p = services.get_project(session, a.project_id)
        auth.require_prepare(me, p)
        return a, p

    @app.put("/approvals/{approval_id}")
    def update_approval(
        approval_id: str, body: ApprovalBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        a, p = approval_for(session, me, approval_id)
        values, _ = form_values(APPROVALS, body)
        clear = tuple(
            k
            for k in ("authority", "reference", "applied_on", "granted_on", "valid_until", "note")
            if k in body.model_fields_set and not getattr(body, k)
        )
        statutory.update_approval(session, p, a, values, as_of=on, user_id=me.user_id, clear=clear)
        session.commit()
        return approvals_for(session, me, p, on)

    @app.post("/approvals/{approval_id}/delete")
    def delete_approval(approval_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        a, p = approval_for(session, me, approval_id)
        statutory.delete_approval(session, p, a, user_id=me.user_id)
        session.commit()
        return approvals_for(session, me, p, on)

    # K-RERA filings

    def krera_for(session: Session, me: auth.Principal, p: Project, on: date) -> dict:
        return record_views.krera_view(
            session,
            p,
            lambda changes: names_for(session, changes),
            can_edit=me.can_prepare(p) and not me.views_as_sample(p),
            as_of=on,
        )

    @app.get("/projects/{project_id}/krera")
    def project_krera(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return krera_for(session, me, p, on)

    @app.post("/projects/{project_id}/filings", status_code=201)
    def create_filing(
        project_id: str, body: FilingBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        values, _ = form_values(FILINGS, body)
        statutory.create_filing(session, p, values, as_of=on, user_id=me.user_id)
        session.commit()
        return krera_for(session, me, p, on)

    def filing_for(session: Session, me: auth.Principal, filing_id: str):
        f = session.get(Filing, filing_id)
        if f is None:
            raise ServiceError("Filing not found.", 404)
        p = services.get_project(session, f.project_id)
        auth.require_prepare(me, p)
        return f, p

    @app.put("/filings/{filing_id}")
    def update_filing(
        filing_id: str, body: FilingBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        f, p = filing_for(session, me, filing_id)
        values, _ = form_values(FILINGS, body)
        if "reference" in body.model_fields_set and not body.reference:
            values["reference"] = None
        statutory.update_filing(session, p, f, values, as_of=on, user_id=me.user_id)
        session.commit()
        return krera_for(session, me, p, on)

    @app.post("/filings/{filing_id}/delete")
    def delete_filing(filing_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        f, p = filing_for(session, me, filing_id)
        statutory.delete_filing(session, p, f, user_id=me.user_id)
        session.commit()
        return krera_for(session, me, p, on)

    # Records edited as a table

    def table_kind(kind: str) -> str:
        if kind not in imports.EDITABLE_AS_TABLE:
            raise ServiceError("These records cannot be edited as a table.", 404)
        return kind

    @app.get("/projects/{project_id}/table/{kind}")
    def get_table(project_id: str, kind: str, session: SessionDep, me: Me, page: int = 1) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        return record_views.table_view(session, p, table_kind(kind), page=page)

    @app.post("/projects/{project_id}/table/{kind}", status_code=201)
    def save_table(
        project_id: str, kind: str, body: TableBody, session: SessionDep, me: Me
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        record = imports.record_type(table_kind(kind))
        header = [f.label for f in record.fields]
        if any(len(row) != len(header) for row in body.rows):
            raise ServiceError("Every row needs a value for each column.")
        batch = imports.start_rows(
            session,
            p,
            kind,
            filename=f"{record.title}, edited as a table",
            rows=[header, *body.rows],
            user_id=me.user_id,
            origin="table",
        )
        return {"id": batch.id}

    # Tally imports

    def tally_for(session: Session, me: auth.Principal, import_id: str, *, edit=False):
        row = tally.get_import(session, import_id)
        p = services.get_project(session, row.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return row, p

    def tally_view(session: Session, me: auth.Principal, row, p: Project, on: date) -> dict:
        book, plan = tally.review(session, app.state.storage, row, on)
        units = list(
            session.scalars(select(Unit).where(Unit.project_id == p.id).order_by(Unit.label))
        )
        editable = me.can_prepare(p) and not me.views_as_sample(p)
        return views.tally_review(
            row,
            book,
            plan,
            p,
            units,
            can_edit=editable,
            can_undo=editable and tally.can_undo(row),
            lines=registers.cost_lines(session, p),
            owners=services.landowners(session, p),
        )

    @app.post("/projects/{project_id}/tally", status_code=201)
    def upload_tally(project_id: str, session: SessionDep, me: Me, file: UploadFile) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        limit = settings.tally_upload_mb * 1_000_000
        data = file.file.read(limit + 1)
        if len(data) > limit:
            raise ServiceError(
                f"Tally files can be up to {settings.tally_upload_mb} MB. Export a shorter period."
            )
        row = tally.upload(
            session,
            app.state.storage,
            p,
            filename=file.filename or "tally",
            data=data,
            user_id=me.user_id,
        )
        return {"id": row.id}

    @app.get("/projects/{project_id}/tally")
    def list_tally(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return {
            "can_import": me.can_prepare(p) and not me.views_as_sample(p),
            "imports": [views.tally_row(r) for r in tally.project_imports(session, p)],
        }

    @app.get("/tally/{import_id}")
    def get_tally(import_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = tally_for(session, me, import_id)
        return tally_view(session, me, row, p, on)

    @app.put("/tally/{import_id}/options")
    def tally_options(
        import_id: str, body: TallyOptions, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        row, p = tally_for(session, me, import_id, edit=True)
        tally.set_options(session, row, cost_centre=body.cost_centre, links=body.links)
        return tally_view(session, me, row, p, on)

    @app.post("/tally/{import_id}/apply")
    def apply_tally(import_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = tally_for(session, me, import_id, edit=True)
        tally.apply(session, app.state.storage, row, as_of=on, user_id=me.user_id)
        return tally_view(session, me, row, p, on)

    @app.post("/tally/{import_id}/undo")
    def undo_tally(import_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = tally_for(session, me, import_id, edit=True)
        tally.undo(session, row)
        return tally_view(session, me, row, p, on)

    # Bank statements

    def statement_for(session: Session, me: auth.Principal, statement_id: str, *, edit=False):
        row = bank.get_statement(session, statement_id)
        p = services.get_project(session, row.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return row, p

    def statement_view(session: Session, me: auth.Principal, row, p: Project, on: date) -> dict:
        passwords = bank.statement_passwords(session, settings, p.organization_id)
        statement, plan = bank.review(session, app.state.storage, row, on, passwords)
        units = list(
            session.scalars(
                select(Unit).where(Unit.project_id == p.id, Unit.booked).order_by(Unit.label)
            )
        )
        refs = [UnitRef(u.id, u.label, u.buyer_name) for u in units]
        editable = me.can_prepare(p) and not me.views_as_sample(p)
        return views.bank_review(
            row, statement, plan, p, refs, can_edit=editable, can_undo=bank.can_undo(row)
        )

    @app.post("/projects/{project_id}/bank-statements", status_code=201)
    def upload_statement(project_id: str, session: SessionDep, me: Me, file: UploadFile) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        limit = settings.max_upload_mb * 1_000_000
        data = file.file.read(limit + 1)
        if len(data) > limit:
            raise ServiceError(
                f"Statements can be up to {settings.max_upload_mb} MB. Download a shorter period."
            )
        row = bank.upload(
            session,
            app.state.storage,
            p,
            filename=file.filename or "statement",
            data=data,
            user_id=me.user_id,
            passwords=bank.statement_passwords(session, settings, p.organization_id),
        )
        return {"id": row.id}

    @app.get("/projects/{project_id}/bank-statements")
    def list_statements(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return {
            "can_import": me.can_prepare(p) and not me.views_as_sample(p),
            "statements": [
                views.bank_statement_row(r) for r in bank.project_statements(session, p)
            ],
        }

    @app.get("/bank-statements/{statement_id}")
    def get_statement(statement_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = statement_for(session, me, statement_id)
        return statement_view(session, me, row, p, on)

    @app.put("/bank-statements/{statement_id}/options")
    def statement_options(
        statement_id: str, body: StatementOptions, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        row, p = statement_for(session, me, statement_id, edit=True)
        bank.set_options(
            session,
            app.state.storage,
            row,
            body.model_dump(exclude_unset=True),
            as_of=on,
            passwords=bank.statement_passwords(session, settings, p.organization_id),
        )
        return statement_view(session, me, row, p, on)

    @app.post("/bank-statements/{statement_id}/apply")
    def apply_statement(statement_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = statement_for(session, me, statement_id, edit=True)
        bank.apply(
            session,
            app.state.storage,
            row,
            as_of=on,
            user_id=me.user_id,
            passwords=bank.statement_passwords(session, settings, p.organization_id),
        )
        return statement_view(session, me, row, p, on)

    @app.post("/bank-statements/{statement_id}/undo")
    def undo_statement(statement_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = statement_for(session, me, statement_id, edit=True)
        bank.undo(session, row)
        return statement_view(session, me, row, p, on)

    # Suppliers, bills and commitments

    def bill_for(session: Session, me: auth.Principal, bill_id: str, *, edit=False):
        bill = session.get(Bill, bill_id)
        if bill is None:
            raise ServiceError("Bill not found.", 404)
        p = services.get_project(session, bill.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return bill, p

    def vendor_for(session: Session, me: auth.Principal, vendor_id: str, *, edit=False):
        vendor = session.get(Vendor, vendor_id)
        org = session.get(Organization, vendor.organization_id) if vendor else None
        role = me.org_roles.get(vendor.organization_id) if vendor else None
        if vendor is None or (role is None and not org.is_sample):
            raise ServiceError("Supplier not found.", 404)
        if edit:
            if role not in (auth.OrgRole.OWNER, auth.OrgRole.FINANCE, auth.OrgRole.ACCOUNTS):
                raise ServiceError("Your role cannot change suppliers.", 403)
            if services.access_state(org, me.as_of) == "read_only":
                raise ServiceError(auth.READ_ONLY, 402)
        return vendor, org

    def names_for(session: Session, changes) -> dict:
        ids = {c.user_id for c in changes if c.user_id}
        return {u.id: u.name for u in session.scalars(select(User).where(User.id.in_(ids)))}

    def bill_view(session: Session, me: auth.Principal, bill, p: Project) -> dict:
        changes = registers.history(session, "bill", bill.id)
        return views.bill_detail(
            session,
            bill,
            p,
            changes,
            names_for(session, changes),
            can_edit=me.can_prepare(p) and not me.views_as_sample(p),
        )

    def vendor_view(session: Session, me: auth.Principal, vendor, org) -> dict:
        changes = registers.history(session, "vendor", vendor.id)
        role = me.org_roles.get(vendor.organization_id)
        projects = {
            x.id: x.name
            for x in session.scalars(select(Project).where(Project.organization_id == org.id))
        }
        return views.vendor_detail(
            session,
            vendor,
            changes,
            names_for(session, changes),
            can_edit=role in (auth.OrgRole.OWNER, auth.OrgRole.FINANCE, auth.OrgRole.ACCOUNTS),
            projects=projects,
        )

    def form_values(record, body: BaseModel) -> tuple[dict, list[str]]:
        values, problems = purchases.parse_form(record, body.model_dump(exclude_unset=True))
        if problems:
            raise ServiceError(" ".join(problems))
        return values, list(getattr(body, "clear", None) or [])

    @app.get("/projects/{project_id}/purchases")
    def project_purchases(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return views.purchases_view(
            session, p, can_edit=me.can_prepare(p) and not me.views_as_sample(p)
        )

    @app.post("/projects/{project_id}/bills", status_code=201)
    def create_bill(project_id: str, body: BillBody, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        values, _ = form_values(BILLS, body)
        bill = purchases.create_bill(session, p, values, as_of=on, user_id=me.user_id)
        session.commit()
        return {"id": bill.id}

    @app.get("/bills/{bill_id}")
    def get_bill(bill_id: str, session: SessionDep, me: Me) -> dict:
        bill, p = bill_for(session, me, bill_id)
        return bill_view(session, me, bill, p)

    @app.put("/bills/{bill_id}")
    def update_bill(bill_id: str, body: BillBody, session: SessionDep, me: Me, on: AsOf) -> dict:
        bill, p = bill_for(session, me, bill_id, edit=True)
        values, clear = form_values(BILLS, body)
        purchases.update_bill(session, p, bill, values, as_of=on, user_id=me.user_id)
        for key in clear:
            if key not in values:
                purchases.clear_bill_field(session, p, bill, key, user_id=me.user_id)
        session.commit()
        return bill_view(session, me, bill, p)

    @app.post("/bills/{bill_id}/delete")
    def delete_bill(bill_id: str, session: SessionDep, me: Me) -> dict:
        bill, p = bill_for(session, me, bill_id, edit=True)
        purchases.delete_bill(session, p, bill, user_id=me.user_id)
        session.commit()
        return {"project_id": p.id}

    @app.post("/projects/{project_id}/suppliers", status_code=201)
    def create_supplier(project_id: str, body: SupplierBody, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        values, _ = form_values(SUPPLIERS, body)
        vendor = purchases.create_vendor(
            session, p.organization_id, values, project=p, user_id=me.user_id
        )
        session.commit()
        return {"id": vendor.id}

    @app.get("/suppliers/{vendor_id}")
    def get_supplier(vendor_id: str, session: SessionDep, me: Me) -> dict:
        vendor, org = vendor_for(session, me, vendor_id)
        return vendor_view(session, me, vendor, org)

    @app.put("/suppliers/{vendor_id}")
    def update_supplier(vendor_id: str, body: SupplierBody, session: SessionDep, me: Me) -> dict:
        vendor, org = vendor_for(session, me, vendor_id, edit=True)
        values, clear = form_values(SUPPLIERS, body)
        purchases.update_vendor(session, vendor, values, project=None, user_id=me.user_id)
        for key in clear:
            if key not in values:
                purchases.clear_vendor_field(session, vendor, key, user_id=me.user_id)
        session.commit()
        return vendor_view(session, me, vendor, org)

    @app.post("/suppliers/{vendor_id}/delete")
    def delete_supplier(vendor_id: str, session: SessionDep, me: Me) -> dict:
        vendor, _ = vendor_for(session, me, vendor_id, edit=True)
        purchases.delete_vendor(session, vendor, user_id=me.user_id)
        session.commit()
        return {"ok": True}

    @app.get("/projects/{project_id}/commitments")
    def project_commitments(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return views.commitments_view(
            session, p, can_edit=me.can_prepare(p) and not me.views_as_sample(p)
        )

    @app.post("/projects/{project_id}/commitments", status_code=201)
    def create_commitment(
        project_id: str, body: CommitmentBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        values, _ = form_values(COMMITMENTS, body)
        c = purchases.create_commitment(session, p, values, as_of=on, user_id=me.user_id)
        session.commit()
        return {"id": c.id}

    def commitment_for(session: Session, me: auth.Principal, commitment_id: str):
        c = session.get(Commitment, commitment_id)
        if c is None:
            raise ServiceError("Order not found.", 404)
        p = services.get_project(session, c.project_id)
        auth.require_prepare(me, p)
        return c, p

    @app.put("/commitments/{commitment_id}")
    def update_commitment(
        commitment_id: str, body: CommitmentBody, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        c, p = commitment_for(session, me, commitment_id)
        values, _ = form_values(COMMITMENTS, body)
        if "description" in body.model_fields_set and not body.description:
            values["description"] = None
        if "supplier" in body.model_fields_set and not body.supplier:
            values["supplier"] = None
        purchases.update_commitment(session, p, c, values, as_of=on, user_id=me.user_id)
        session.commit()
        return views.commitments_view(session, p, can_edit=True)

    @app.post("/commitments/{commitment_id}/delete")
    def delete_commitment(commitment_id: str, session: SessionDep, me: Me) -> dict:
        c, p = commitment_for(session, me, commitment_id)
        purchases.delete_commitment(session, p, c, user_id=me.user_id)
        session.commit()
        return views.commitments_view(session, p, can_edit=True)

    # The forwarding address

    @app.post("/inbound/email", status_code=202)
    async def inbound_email(request: Request, session: SessionDep) -> dict:
        """Mail posted by the email service: raw MIME as the body, a form field (email,
        body-mime or raw) or JSON {raw: base64, to: [...]}, with the shared secret."""
        if not settings.inbound_secret:
            raise ServiceError("Incoming mail is not set up here.", 404)
        given = request.headers.get("x-lekhara-inbound-secret") or request.query_params.get(
            "secret", ""
        )
        if not hmac.compare_digest(given.encode(), settings.inbound_secret.encode()):
            raise ServiceError("Not allowed.", 403)
        kind = request.headers.get("content-type", "").split(";")[0].strip().casefold()
        envelope: list[str] = []
        if kind in ("multipart/form-data", "application/x-www-form-urlencoded"):
            form = await request.form()
            field = form.get("email") or form.get("body-mime") or form.get("raw")
            raw = await field.read() if hasattr(field, "read") else str(field or "").encode()
            if form.get("envelope"):
                try:
                    envelope = list(json.loads(str(form["envelope"])).get("to", []))
                except (ValueError, AttributeError):
                    envelope = []
            if form.get("recipient"):
                envelope.append(str(form["recipient"]))
        elif kind == "application/json":
            body = await request.json()
            raw = base64.b64decode(body.get("raw", ""))
            envelope = [str(a) for a in body.get("to", [])]
        else:
            raw = await request.body()
        if not raw:
            raise ServiceError("The email is empty.")
        message = inbound.receive(session, app.state.storage, settings, raw, envelope_to=envelope)
        if message is None:
            return {"status": "no_project"}
        return {"id": message.id, "status": message.status}

    def message_for(session: Session, me: auth.Principal, message_id: str):
        msg = session.get(InboundMessage, message_id)
        if msg is None:
            raise ServiceError("Email not found.", 404)
        p = services.get_project(session, msg.project_id)
        auth.require_prepare(me, p)
        return msg, p

    def inbound_payload(session: Session, me: auth.Principal, p: Project) -> dict:
        address = inbound.address_for(session, p, settings)
        return views.inbound_view(
            session,
            p,
            address,
            can_edit=me.can_prepare(p) and not me.views_as_sample(p),
            domain_ready=bool(settings.inbound_secret or settings.inbound_imap_url),
        )

    @app.get("/projects/{project_id}/inbound")
    def project_inbound(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return inbound_payload(session, me, p)

    @app.post("/inbound/{message_id}/allow")
    def allow_inbound(message_id: str, body: AllowBody, session: SessionDep, me: Me) -> dict:
        msg, p = message_for(session, me, message_id)
        inbound.allow(session, p.organization_id, msg, user_id=me.user_id, trust=body.trust)
        jobs.run_pending(session_factory, app.state.storage, settings, limit=5)
        return inbound_payload(session, me, p)

    @app.post("/inbound/{message_id}/reject")
    def reject_inbound(message_id: str, session: SessionDep, me: Me) -> dict:
        msg, p = message_for(session, me, message_id)
        inbound.reject(session, msg, user_id=me.user_id)
        return inbound_payload(session, me, p)

    @app.post("/inbound/items/{item_id}/retry")
    def retry_inbound(item_id: str, session: SessionDep, me: Me) -> dict:
        item = session.get(InboundItem, item_id)
        if item is None:
            raise ServiceError("File not found.", 404)
        msg, p = message_for(session, me, item.message_id)
        inbound.retry(session, app.state.storage, settings, item)
        return inbound_payload(session, me, p)

    def org_manager(session: Session, me: auth.Principal):
        org = accounts.current_org(session, me)
        accounts.require_manager(me, org)
        if services.access_state(org, me.as_of) == "read_only":
            raise ServiceError(auth.READ_ONLY, 402)
        return org

    def senders_payload(session: Session, me: auth.Principal) -> dict:
        org = accounts.current_org(session, me)
        role = me.org_roles.get(org.id)
        return {
            "can_edit": role in (auth.OrgRole.OWNER, auth.OrgRole.FINANCE),
            "senders": [
                {"id": t.id, "address": t.address} for t in inbound.trusted_senders(session, org.id)
            ],
            "passwords": [
                {"id": x.id, "label": x.label, "added_on": x.created_at.date().isoformat()}
                for x in session.scalars(
                    select(StatementPassword)
                    .where(StatementPassword.organization_id == org.id)
                    .order_by(StatementPassword.created_at)
                )
            ],
        }

    @app.get("/organization/inbound")
    def org_inbound(session: SessionDep, me: Me) -> dict:
        return senders_payload(session, me)

    @app.post("/organization/senders", status_code=201)
    def add_sender(body: SenderBody, session: SessionDep, me: Me) -> dict:
        org = org_manager(session, me)
        inbound.add_trusted(session, org.id, body.address, user_id=me.user_id)
        session.commit()
        return senders_payload(session, me)

    @app.post("/organization/senders/{sender_id}/delete")
    def remove_sender(sender_id: str, session: SessionDep, me: Me) -> dict:
        org = org_manager(session, me)
        row = session.get(TrustedSender, sender_id)
        if row is None or row.organization_id != org.id:
            raise ServiceError("Not found.", 404)
        session.delete(row)
        session.commit()
        return senders_payload(session, me)

    @app.post("/organization/statement-passwords", status_code=201)
    def add_password(body: PasswordBody, session: SessionDep, me: Me) -> dict:
        org = org_manager(session, me)
        label, secret = (body.label or "").strip(), body.password or ""
        if not label or not secret:
            raise ServiceError("Give the account or bank it is for, and the password.")
        session.add(
            StatementPassword(
                organization_id=org.id,
                label=label[:200],
                sealed=seal(settings, secret),
                added_by_user_id=me.user_id,
            )
        )
        session.commit()
        return senders_payload(session, me)

    @app.post("/organization/statement-passwords/{password_id}/delete")
    def remove_password(password_id: str, session: SessionDep, me: Me) -> dict:
        org = org_manager(session, me)
        row = session.get(StatementPassword, password_id)
        if row is None or row.organization_id != org.id:
            raise ServiceError("Not found.", 404)
        session.delete(row)
        session.commit()
        return senders_payload(session, me)

    # Connectors on the builder's own computers

    def connector_from(session: Session, key: str | None) -> Connector:
        return connectors.by_key(session, key)

    @app.post("/projects/{project_id}/connectors", status_code=201)
    def new_connector(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        connector, code = connectors.new_code(session, p, user_id=me.user_id)
        return {**views.connector_row(connector), "code": code}

    @app.get("/projects/{project_id}/connectors")
    def list_connectors(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return {
            "can_edit": me.can_prepare(p) and not me.views_as_sample(p),
            "connectors": [views.connector_row(c) for c in connectors.connectors_of(session, p)],
        }

    @app.post("/connectors/{connector_id}/unlink")
    def unlink_connector(connector_id: str, session: SessionDep, me: Me) -> dict:
        c = session.get(Connector, connector_id)
        if c is None:
            raise ServiceError("Not found.", 404)
        p = services.get_project(session, c.project_id)
        auth.require_prepare(me, p)
        connectors.unlink(session, c)
        return {"ok": True}

    @app.post("/connector/link")
    def connector_link(body: ConnectorLink, session: SessionDep) -> dict:
        c, key = connectors.link(session, body.code, body.name)
        p = session.get(Project, c.project_id)
        return {"key": key, "connector_id": c.id, **connectors.config(c, p)}

    @app.get("/connector/config")
    def connector_config(
        session: SessionDep, x_lekhara_connector: Annotated[str | None, Header()] = None
    ) -> dict:
        c = connector_from(session, x_lekhara_connector)
        return connectors.config(c, session.get(Project, c.project_id))

    @app.post("/connector/heartbeat")
    def connector_heartbeat(
        body: ConnectorBeat,
        session: SessionDep,
        x_lekhara_connector: Annotated[str | None, Header()] = None,
    ) -> dict:
        c = connector_from(session, x_lekhara_connector)
        connectors.heartbeat(session, c, body.state, body.company)
        return {"ok": True}

    @app.post("/connector/tally")
    async def connector_tally(
        request: Request,
        session: SessionDep,
        x_lekhara_connector: Annotated[str | None, Header()] = None,
    ) -> dict:
        c = connector_from(session, x_lekhara_connector)
        form = await request.form()
        limit = settings.tally_upload_mb * 1_000_000

        async def part(name: str) -> bytes | None:
            field = form.get(name)
            if field is None or not hasattr(field, "read"):
                return None
            data = await field.read(limit + 1)
            if len(data) > limit:
                raise ServiceError(
                    f"Tally data over {settings.tally_upload_mb} MB; sync a shorter period."
                )
            return data or None

        return connectors.sync(
            session,
            app.state.storage,
            settings,
            c,
            masters=await part("masters"),
            vouchers=await part("vouchers"),
            company=str(form.get("company") or "") or None,
        )

    # GSTR-2B from the GST portal

    def gst_for(session: Session, me: auth.Principal, import_id: str, *, edit=False):
        row = gst.get_import(session, import_id)
        p = services.get_project(session, row.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return row, p

    def gst_view(session: Session, me: auth.Principal, row, p: Project) -> dict:
        ret, plan = gst.review(session, app.state.storage, row)
        editable = me.can_prepare(p) and not me.views_as_sample(p)
        return views.gst_review(row, ret, plan, p, can_edit=editable, can_undo=gst.can_undo(row))

    @app.post("/projects/{project_id}/gst", status_code=201)
    def upload_gst(project_id: str, session: SessionDep, me: Me, file: UploadFile) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        data = file.file.read(settings.max_upload_mb * 1_000_000 + 1)
        if len(data) > settings.max_upload_mb * 1_000_000:
            raise ServiceError(f"Files can be up to {settings.max_upload_mb} MB.")
        row = gst.upload(
            session, app.state.storage, p, filename=file.filename or "gstr2b", data=data,
            user_id=me.user_id,
        )  # fmt: skip
        return {"id": row.id}

    @app.get("/projects/{project_id}/gst")
    def list_gst(project_id: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return {
            "can_import": me.can_prepare(p) and not me.views_as_sample(p),
            "imports": [views.gst_row(r) for r in gst.project_imports(session, p)],
        }

    @app.get("/gst/{import_id}")
    def get_gst(import_id: str, session: SessionDep, me: Me) -> dict:
        row, p = gst_for(session, me, import_id)
        return gst_view(session, me, row, p)

    @app.put("/gst/{import_id}/options")
    def gst_options(import_id: str, body: GstOptions, session: SessionDep, me: Me) -> dict:
        row, p = gst_for(session, me, import_id, edit=True)
        gst.set_options(session, row, body.model_dump(exclude_unset=True))
        return gst_view(session, me, row, p)

    @app.post("/gst/{import_id}/apply")
    def apply_gst(import_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = gst_for(session, me, import_id, edit=True)
        gst.apply(session, app.state.storage, row, as_of=on, user_id=me.user_id)
        return gst_view(session, me, row, p)

    @app.post("/gst/{import_id}/undo")
    def undo_gst(import_id: str, session: SessionDep, me: Me) -> dict:
        row, p = gst_for(session, me, import_id, edit=True)
        gst.undo(session, row, user_id=me.user_id)
        return gst_view(session, me, row, p)

    # Today

    def reviewable(session: Session, me: auth.Principal) -> list[Project]:
        return [
            p
            for p in visible(session, me)
            if me.can_prepare(p) and me.is_team_member(p) and not me.views_as_sample(p)
        ]

    @app.get("/review")
    def review_queue(session: SessionDep, me: Me) -> dict:
        entries = review.waiting(session, app.state.storage, settings, reviewable(session, me))
        return {
            "count": len(entries),
            "items": [
                {
                    "project_id": w.project_id,
                    "project_name": w.project_name,
                    "kind": w.kind,
                    "title": w.title,
                    "detail": w.detail,
                    "href": w.href,
                    "since": w.since.replace(microsecond=0).isoformat(),
                }
                for w in entries
            ],
        }

    @app.get("/today")
    def today(session: SessionDep, me: Me, on: AsOf) -> dict:
        projects = visible(session, me)
        if me.is_certifier_only:
            return certifier_today(session, me, projects, on)

        snaps = [services.snapshot(session, p, on) for p in projects if me.is_team(p)]
        items = sort_obligations([o for s in snaps for o in s.obligations])
        due_this_week = sum(
            1
            for o in items
            if o.status == ObligationStatus.OVERDUE
            or (o.status == ObligationStatus.DUE_SOON and o.due_on and (o.due_on - on).days <= 7)
        )
        org_names = sorted({s.project.organization.name for s in snaps})
        waiting = review.waiting(session, app.state.storage, settings, reviewable(session, me))
        return {
            "as_of": on.isoformat(),
            "kind": "team",
            "to_review": len(waiting),
            "organization": ", ".join(org_names),
            "summary": {
                "drawable_now": views.m(sum((s.escrow.drawable_now for s in snaps), ZERO)),
                "at_stake": views.m(sum((o.amount or ZERO for o in items if o.exposure), ZERO)),
                "due_this_week": due_this_week,
                "projects": len(snaps),
            },
            "items": [views.obligation(o) for o in items if o.status != ObligationStatus.DONE],
        }

    def certifier_today(
        session: Session, me: auth.Principal, projects: list[Project], on: date
    ) -> dict:
        items = []
        for project in projects:
            request = services.open_request(session, project)
            if request is None or request.submitted_on is not None:
                continue
            state = services.request_state(session, request, on)
            for role in ROLE_ORDER:
                certificate = state.certificates.get(role)
                if not me.certifies(project, role) or certificate is None or certificate.signed:
                    continue
                items.append(
                    {
                        "key": f"sign:{request.id}:{role.value}",
                        "project_id": project.id,
                        "project_name": project.name,
                        "title": f"Review and sign the {auth.CERTIFIER_LABEL[role].lower()}'s "
                        "certificate",
                        "detail": "A withdrawal from the RERA account is waiting for you. Lekhara "
                        "has prepared the figures from the developer's books.",
                        "owed_to": project.organization.name,
                        "status": ObligationStatus.DUE_SOON.value,
                        "area": "escrow",
                        "due_on": on.isoformat(),
                        "amount": views.m(request.amount),
                        "amount_label": "Withdrawal",
                        "exposure": False,
                        "rule_key": "escrow.withdrawal_cost_basis",
                        "action": "Review and sign",
                        "link": f"/withdrawals/{request.id}",
                    }
                )
        return {
            "as_of": on.isoformat(),
            "kind": "certifier",
            "organization": me.firm or me.name,
            "summary": {"waiting": len(items), "projects": len(projects)},
            "items": items,
        }

    # Projects

    @app.get("/projects")
    def list_projects(session: SessionDep, me: Me, on: AsOf) -> list[dict]:
        own = [
            {**views.project_card(services.snapshot(session, p, on)), "sample": False}
            for p in visible(session, me)
        ]
        samples = [
            {**views.project_card(services.snapshot(session, p, on)), "sample": True}
            for p in services.sample_projects(session, set(me.org_roles))
            if not me.is_certifier_only
        ]
        return own + samples

    @app.get("/projects/{project_id}")
    def project(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = viewable_project(session, me, project_id)
        detail = views.project_detail(services.snapshot(session, p, on))
        if not me.is_team(p):
            # Certifiers see what they certify: the escrow side, not the developer's tax position.
            detail["obligations"] = [o for o in detail["obligations"] if o["area"] == "escrow"]
            detail["counts"] = {
                status.value: sum(1 for o in detail["obligations"] if o["status"] == status.value)
                for status in ObligationStatus
            }
        detail["access"] = {
            "sample": me.views_as_sample(p),
            "team": me.is_team(p),
            "certifies": [r.value for r in ROLE_ORDER if me.certifies(p, r)],
        }
        return detail

    @app.get("/projects/{project_id}/money")
    def project_money(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        s = services.snapshot(session, viewable_project(session, me, project_id), on)
        return {"summary": views.money_summary(s), "lines": views.money_lines(s)}

    @app.get("/projects/{project_id}/escrow")
    def project_escrow(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = viewable_project(session, me, project_id)
        s = services.snapshot(session, p, on)
        states = [
            services.request_state(session, r, on) for r in services.project_requests(session, p)
        ]
        return views.escrow(s, states, can_start=me.can_prepare(p))

    @app.get("/projects/{project_id}/tax")
    def project_tax(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return views.tax(services.snapshot(session, p, on))

    @app.get("/projects/{project_id}/units")
    def project_units(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        s = services.snapshot(session, p, on)
        return views.units(s, services.project_units(session, p), services.landowners(session, p))

    # Collections

    @app.get("/projects/{project_id}/collections")
    def project_collections(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return views.collections(
            services.collections_for(session, p, on), can_raise=me.can_prepare(p)
        )

    @app.post("/projects/{project_id}/milestones/{milestone_id}/raise")
    def raise_demands(
        project_id: str, milestone_id: str, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        raised = services.raise_demands(session, p, milestone_id, on, user_id=me.user_id)
        view = views.collections(services.collections_for(session, p, on), can_raise=True)
        return {"raised": raised, **view}

    @app.get("/demands/{demand_id}")
    def demand(demand_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row = services.get_demand(session, demand_id)
        p = services.get_project(session, row.project_id)
        auth.require_team(me, p)
        return views.demand_letter(
            demand=row,
            project=p,
            unit=session.get(Unit, row.unit_id),
            milestone=session.get(PaymentMilestone, row.milestone_id),
            gst_rate=services.sale_gst_rate(p, on, KARNATAKA),
            tds_threshold=KARNATAKA.value("it.s194ia.threshold", on),
        )

    # Registration and handover

    @app.get("/projects/{project_id}/handover")
    def project_handover(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return views.handover(services.handover_for(session, p, on), p, can_edit=me.can_prepare(p))

    @app.get("/units/{unit_id}/handover")
    def unit_handover(unit_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        unit = services.get_unit(session, unit_id)
        p = services.get_project(session, unit.project_id)
        auth.require_team(me, p)
        if not unit.booked:
            raise ServiceError("This unit is not booked.", 404)
        h = services.handover_for(session, p, on)
        return views.unit_handover(h, p, unit, can_edit=me.can_prepare(p))

    @app.put("/units/{unit_id}/handover")
    def update_unit_handover(
        unit_id: str, body: HandoverUpdate, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        unit = services.get_unit(session, unit_id)
        p = services.get_project(session, unit.project_id)
        auth.require_prepare(me, p)
        services.update_handover(
            session, unit, body.model_dump(exclude_unset=True), user_id=me.user_id
        )
        h = services.handover_for(session, p, on)
        return views.unit_handover(h, p, unit, can_edit=True)

    # Disputes and orders

    @app.get("/projects/{project_id}/disputes")
    def project_disputes(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        return views.disputes(
            services.disputes_for(session, p, on),
            p,
            services.booked_units(session, p, on),
            can_edit=me.can_prepare(p),
        )

    @app.post("/projects/{project_id}/disputes", status_code=201)
    def create_case(project_id: str, body: NewCase, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        row = services.create_case(
            session, p, body.model_dump(exclude_unset=True), as_of=on, user_id=me.user_id
        )
        return {"id": row.id}

    def case_for(session: Session, me: auth.Principal, case_id: str, *, edit: bool = False):
        row = services.get_case(session, case_id)
        p = services.get_project(session, row.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return row, p

    def case_view(session: Session, me: auth.Principal, row, p: Project, on: date) -> dict:
        session.refresh(row)
        position = services.case_position_for(session, row, p, on)
        return views.case_detail(position, row, p, can_edit=me.can_prepare(p))

    @app.get("/cases/{case_id}")
    def get_case(case_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = case_for(session, me, case_id)
        return case_view(session, me, row, p, on)

    @app.put("/cases/{case_id}")
    def update_case(case_id: str, body: CaseUpdate, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = case_for(session, me, case_id, edit=True)
        services.update_case(
            session, row, body.model_dump(exclude_unset=True), as_of=on, user_id=me.user_id
        )
        return case_view(session, me, row, p, on)

    @app.post("/cases/{case_id}/hearings")
    def add_hearing(case_id: str, body: NewHearing, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = case_for(session, me, case_id, edit=True)
        services.add_hearing(session, row, body.model_dump(), as_of=on, user_id=me.user_id)
        return case_view(session, me, row, p, on)

    @app.post("/cases/{case_id}/orders")
    def add_order(case_id: str, body: NewOrder, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = case_for(session, me, case_id, edit=True)
        services.add_order(session, row, body.model_dump(), as_of=on, user_id=me.user_id)
        return case_view(session, me, row, p, on)

    @app.post("/cases/{case_id}/payments")
    def add_payment(case_id: str, body: NewPayment, session: SessionDep, me: Me, on: AsOf) -> dict:
        row, p = case_for(session, me, case_id, edit=True)
        services.add_payment(session, row, p, body.model_dump(), as_of=on, user_id=me.user_id)
        return case_view(session, me, row, p, on)

    # Document vault

    def notice_days(on: date) -> int:
        return KARNATAKA.value("documents.expiry_notice_days", on)

    def disposition(filename: str, inline: bool) -> str:
        plain = re.sub(r"[^A-Za-z0-9._ -]", "_", filename) or "document"
        kind = "inline" if inline else "attachment"
        return f"{kind}; filename=\"{plain}\"; filename*=UTF-8''{quote(filename)}"

    def file_response(doc, data: bytes, inline: bool) -> Response:
        inline = inline and (
            doc.content_type == "application/pdf" or doc.content_type.startswith("image/")
        )
        return Response(
            content=data,
            media_type=doc.content_type,
            headers={
                "Content-Disposition": disposition(doc.filename, inline),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    def form_date(value: str | None, label: str) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ServiceError(f"{label} is not a date.") from None

    @app.get("/projects/{project_id}/documents")
    def project_documents(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        rooms = services.project_rooms(session, p)
        counts = [(r, len(services.room_documents(session, r))) for r in rooms]
        return views.documents(
            services.documents_for(session, p, on),
            counts,
            as_of=on,
            can_edit=me.can_prepare(p),
            can_share=me.can_release(p),
        )

    @app.get("/projects/{project_id}/documents/search")
    def search_documents(project_id: str, q: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        hits = services.search_documents(session, p, q)
        return views.search_results(hits, q, as_of=on, notice_days=notice_days(on))

    @app.post("/projects/{project_id}/documents", status_code=201)
    def upload_document(
        project_id: str,
        session: SessionDep,
        me: Me,
        on: AsOf,
        file: UploadFile,
        category: Annotated[str | None, Form()] = None,
        title: Annotated[str | None, Form()] = None,
        document_date: Annotated[str | None, Form()] = None,
        expires_on: Annotated[str | None, Form()] = None,
        reference: Annotated[str | None, Form()] = None,
        notes: Annotated[str | None, Form()] = None,
        requirement: Annotated[str | None, Form()] = None,
        link_type: Annotated[str | None, Form()] = None,
        link_id: Annotated[str | None, Form()] = None,
        replaces: Annotated[str | None, Form()] = None,
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        limit = settings.max_upload_mb * 1_000_000
        data = file.file.read(limit + 1)
        doc = services.store_document(
            session,
            app.state.storage,
            p,
            data=data,
            filename=file.filename or "document",
            fields={
                "category": category,
                "title": title,
                "document_date": form_date(document_date, "The document date"),
                "expires_on": form_date(expires_on, "The expiry date"),
                "reference": reference,
                "notes": notes,
                "requirement": requirement,
                "link_type": link_type,
                "link_id": link_id,
                "replaces": replaces,
            },
            max_bytes=limit,
            user_id=me.user_id,
        )
        return {"id": doc.id}

    @app.get("/documents")
    def documents_for_record(
        link_type: str, link_id: str, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.project_for_record(session, link_type, link_id)
        auth.require_team(me, p)
        docs = services.linked_documents(session, p, link_type, link_id)
        return {
            "project_id": p.id,
            "can_edit": me.can_prepare(p),
            "documents": [views.doc_row(d, as_of=on, notice_days=notice_days(on)) for d in docs],
            "categories": views._category_choices(),
        }

    def document_view(session: Session, me: auth.Principal, doc, on: date) -> dict:
        p = services.get_project(session, doc.project_id)
        rooms = [
            r
            for r in services.project_rooms(session, p)
            if any(e.family_id == doc.family_id for e in r.entries)
        ]
        return views.document_detail(
            doc,
            services.document_versions(session, doc),
            p,
            record=services.record_label(session, doc.link_type, doc.link_id),
            rooms=rooms,
            as_of=on,
            notice_days=notice_days(on),
            can_edit=me.can_prepare(p),
        )

    def document_for(session: Session, me: auth.Principal, document_id: str, *, edit=False):
        doc = services.get_document(session, document_id)
        p = services.get_project(session, doc.project_id)
        if edit:
            auth.require_prepare(me, p)
        else:
            auth.require_team(me, p)
        return doc

    @app.get("/documents/{document_id}")
    def get_document(document_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        return document_view(session, me, document_for(session, me, document_id), on)

    @app.put("/documents/{document_id}")
    def update_document(
        document_id: str, body: DocumentUpdate, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        doc = document_for(session, me, document_id, edit=True)
        services.update_document(session, doc, body.model_dump(exclude_unset=True))
        return document_view(session, me, doc, on)

    @app.post("/documents/{document_id}/archive")
    def archive_document(document_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        doc = document_for(session, me, document_id, edit=True)
        services.archive_document(session, doc, on)
        return {"project_id": doc.project_id}

    @app.get("/documents/{document_id}/file")
    def document_file(
        document_id: str, session: SessionDep, me: Me, request: Request, inline: bool = False
    ) -> Response:
        doc = document_for(session, me, document_id)
        data = services.read_file(app.state.storage, doc)
        log(session, request, "document_opened", me=me, organization_id=doc.organization_id,
            detail=doc.title)  # fmt: skip
        return file_response(doc, data, inline)

    @app.post("/projects/{project_id}/checklist/{requirement}/waive")
    def waive_requirement(
        project_id: str, requirement: str, body: Waiver, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        services.waive_requirement(
            session, p, requirement, body.reason, as_of=on, user_id=me.user_id
        )
        return {"ok": True}

    @app.post("/projects/{project_id}/checklist/{requirement}/restore")
    def restore_requirement(project_id: str, requirement: str, session: SessionDep, me: Me) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        services.restore_requirement(session, p, requirement)
        return {"ok": True}

    # Data rooms

    def room_view(session: Session, me: auth.Principal, room, on: date) -> dict:
        p = services.get_project(session, room.project_id)
        docs = services.room_documents(session, room)
        inside = {d.id for d in docs}
        available = [d for d in services.current_documents(session, p) if d.id not in inside]
        return views.room_detail(
            room,
            docs,
            available,
            p,
            as_of=on,
            notice_days=notice_days(on),
            can_share=me.can_release(p),
        )

    def room_for(session: Session, me: auth.Principal, room_id: str, *, share=False):
        room = services.get_room(session, room_id)
        p = services.get_project(session, room.project_id)
        if share:
            auth.require_share(me, p)
        else:
            auth.require_team(me, p)
        return room

    @app.post("/projects/{project_id}/rooms", status_code=201)
    def create_room(project_id: str, body: NewRoom, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        auth.require_share(me, p)
        room, token = services.create_room(
            session, p, body.model_dump(), as_of=on, user_id=me.user_id
        )
        return {"id": room.id, "token": token}

    @app.get("/rooms/{room_id}")
    def get_room(room_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        return room_view(session, me, room_for(session, me, room_id), on)

    @app.put("/rooms/{room_id}")
    def update_room(room_id: str, body: RoomUpdate, session: SessionDep, me: Me, on: AsOf) -> dict:
        room = room_for(session, me, room_id, share=True)
        services.update_room(session, room, body.model_dump(exclude_unset=True), as_of=on)
        return room_view(session, me, room, on)

    @app.post("/rooms/{room_id}/link")
    def new_room_link(room_id: str, session: SessionDep, me: Me) -> dict:
        room = room_for(session, me, room_id, share=True)
        return {"token": services.new_room_link(session, room)}

    @app.post("/rooms/{room_id}/revoke")
    def revoke_room(room_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        room = room_for(session, me, room_id, share=True)
        services.revoke_room(session, room, on)
        return room_view(session, me, room, on)

    # Shared links: no sign-in; the token in the link is the permission.

    @app.get("/shared/{token}")
    def shared_room(token: str, session: SessionDep, on: AsOf) -> dict:
        room = services.open_room(session, token, on)
        p = services.get_project(session, room.project_id)
        view = views.shared_room(room, services.room_documents(session, room), p)
        services.log_visit(session, room, "open")
        return view

    @app.get("/shared/{token}/documents/{document_id}/file")
    def shared_file(
        token: str, document_id: str, session: SessionDep, on: AsOf, inline: bool = False
    ) -> Response:
        room = services.open_room(session, token, on)
        doc = next((d for d in services.room_documents(session, room) if d.id == document_id), None)
        if doc is None:
            raise ServiceError("Document not found.", 404)
        data = services.read_file(app.state.storage, doc)
        services.log_visit(session, room, "download", doc.id)
        return file_response(doc, data, inline)

    # Withdrawals

    def withdrawal_view(
        session: Session, me: auth.Principal, request_id: str, on: date
    ) -> tuple[dict, services.RequestState, Project]:
        r = services.get_request(session, request_id)
        p = viewable_project(session, me, r.project_id)
        state = services.request_state(session, r, on)
        return views.request(state, _withdrawal_permissions(me, p, state)), state, p

    @app.post("/projects/{project_id}/withdrawals", status_code=201)
    def new_withdrawal(
        project_id: str, body: NewWithdrawal, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        p = services.get_project(session, project_id)
        auth.require_prepare(me, p)
        r = services.create_withdrawal(session, p, body.amount, on, user_id=me.user_id)
        return withdrawal_view(session, me, r.id, on)[0]

    @app.get("/withdrawals/{request_id}")
    def withdrawal(request_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        return withdrawal_view(session, me, request_id, on)[0]

    @app.get("/withdrawals/{request_id}/pack.pdf")
    def withdrawal_pack(request_id: str, session: SessionDep, me: Me, on: AsOf) -> Response:
        _, state, p = withdrawal_view(session, me, request_id, on)
        data = packs.to_pdf(packs.withdrawal_pack(state, on))
        name = f"{p.name} withdrawal {state.request.created_on.isoformat()}.pdf"
        return file_download(data, name.replace(" ", "-"))

    @app.get("/projects/{project_id}/packs/{kind}/{name}")
    def filing_pack(project_id: str, kind: str, name: str, session: SessionDep, me: Me) -> Response:
        p = services.get_project(session, project_id)
        auth.require_team(me, p)
        period, _, fmt = name.partition(".")
        if kind not in ("qpr", "audit") or fmt not in ("pdf", "xlsx"):
            raise ServiceError("Not found.", 404)
        try:
            end = date.fromisoformat(period)
        except ValueError:
            raise ServiceError("Not found.", 404) from None
        pack = (packs.qpr_pack if kind == "qpr" else packs.audit_pack)(session, p, end)
        data = packs.to_pdf(pack) if fmt == "pdf" else packs.to_xlsx(pack)
        label = "quarterly report" if kind == "qpr" else "annual audit"
        return file_download(data, f"{p.name} {label} {period}.{fmt}".replace(" ", "-"))

    @app.put("/withdrawals/{request_id}/certificates/{role}")
    def update_certificate(
        request_id: str,
        role: CertifierRole,
        body: CertificateFigures,
        session: SessionDep,
        me: Me,
        on: AsOf,
    ) -> dict:
        r = services.get_request(session, request_id)
        auth.require_certifier(me, services.get_project(session, r.project_id), role)
        services.update_certificate(session, r, role, body.model_dump(exclude_unset=True))
        return withdrawal_view(session, me, request_id, on)[0]

    @app.post("/withdrawals/{request_id}/certificates/{role}/sign")
    def sign_certificate(
        request_id: str,
        role: CertifierRole,
        body: SignCertificate,
        session: SessionDep,
        me: Me,
        on: AsOf,
    ) -> dict:
        r = services.get_request(session, request_id)
        auth.require_certifier(me, services.get_project(session, r.project_id), role)
        services.sign_certificate(
            session,
            r,
            role,
            signer_name=me.name,
            signer_firm=me.firm,
            issued_on=body.issued_on or on,
            user_id=me.user_id,
        )
        return withdrawal_view(session, me, request_id, on)[0]

    @app.post("/withdrawals/{request_id}/submit")
    def submit(request_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        r = services.get_request(session, request_id)
        auth.require_prepare(me, services.get_project(session, r.project_id))
        services.submit_request(session, r, on, user_id=me.user_id)
        return withdrawal_view(session, me, request_id, on)[0]

    @app.post("/withdrawals/{request_id}/release")
    def release(
        request_id: str, body: ReleaseWithdrawal, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        r = services.get_request(session, request_id)
        auth.require_release(me, services.get_project(session, r.project_id))
        services.release_request(
            session,
            r,
            amount=body.amount,
            bank_reference=body.bank_reference,
            released_on=body.released_on or on,
            user_id=me.user_id,
        )
        return withdrawal_view(session, me, request_id, on)[0]

    @app.post("/withdrawals/{request_id}/reject")
    def reject(
        request_id: str, body: RejectWithdrawal, session: SessionDep, me: Me, on: AsOf
    ) -> dict:
        r = services.get_request(session, request_id)
        auth.require_release(me, services.get_project(session, r.project_id))
        services.reject_request(session, r, reason=body.reason, rejected_on=on)
        return withdrawal_view(session, me, request_id, on)[0]

    @app.get("/rules")
    def rules(on: AsOf) -> dict:
        return views.rules(KARNATAKA, on)

    return app


def __getattr__(name: str):
    # `uvicorn lekhara.app:app` builds the app lazily, so importing this module stays cheap.
    if name == "app":
        return create_app()
    raise AttributeError(name)
