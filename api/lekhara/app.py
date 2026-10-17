import re
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Header, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lekhara import accounts, auth, imports, registers, services, views
from lekhara.config import Settings, get_settings
from lekhara.db import make_engine, make_sessionmaker
from lekhara.engines.escrow import ROLE_ORDER, CertifierRole, RequestStatus
from lekhara.engines.obligations import ObligationStatus, sort_obligations
from lekhara.migrate import upgrade
from lekhara.models import (
    CostLineRow,
    Landowner,
    Organization,
    PaymentMilestone,
    Project,
    Unit,
    User,
)
from lekhara.money import ZERO
from lekhara.rules import KARNATAKA
from lekhara.services import ServiceError
from lekhara.storage import LocalStorage
from lekhara.tally import service as tally

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


class MappingBody(BaseModel):
    mapping: dict[str, str | None] = {}


class Signup(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None
    firm: str | None = None


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

    app = FastAPI(title="Lekhara API", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.storage = LocalStorage(settings.storage_dir)

    def get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    def as_of() -> date:
        return settings.as_of()

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
    def login(body: Login, session: SessionDep) -> dict:
        token, user = auth.login(session, body.email, body.password, throttle)
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
    def signup(body: Signup, session: SessionDep, on: AsOf) -> dict:
        token, user = accounts.signup(
            session,
            settings,
            name=body.name,
            email=body.email,
            password=body.password,
            firm=body.firm,
            as_of=on,
        )
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
    def reset(body: Reset, session: SessionDep) -> dict:
        accounts.reset_password(session, body.token, body.password)
        return {"ok": True}

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

    @app.post("/organization/invitations", status_code=201)
    def invite(body: NewInvitation, session: SessionDep, me: Me) -> dict:
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
        return {"id": row.id, "link": link}

    @app.post("/organization/invitations/{invitation_id}/cancel")
    def cancel_invitation(invitation_id: str, session: SessionDep, me: Me) -> dict:
        accounts.cancel_invitation(session, accounts.current_org(session, me), me, invitation_id)
        return {"ok": True}

    @app.put("/organization/members/{user_id}")
    def change_role(user_id: str, body: RoleChange, session: SessionDep, me: Me) -> dict:
        accounts.change_role(session, accounts.current_org(session, me), me, user_id, body.role)
        return {"ok": True}

    @app.post("/organization/members/{user_id}/remove")
    def remove_member(user_id: str, session: SessionDep, me: Me) -> dict:
        accounts.remove_member(session, accounts.current_org(session, me), me, user_id)
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
    def accept_invitation(token: str, body: Acceptance, session: SessionDep) -> dict:
        session_token = accounts.accept_invitation(
            session, settings, token, name=body.name, password=body.password, firm=body.firm
        )
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
        data = imports.export_units(session, p, fmt)
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
        rows = imports.evaluate(session, batch) if batch.status == "preview" else None
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
        imports.apply(session, batch, user_id=me.user_id)
        return batch_view(session, me, batch, p)

    @app.post("/imports/{batch_id}/undo")
    def undo_import(batch_id: str, session: SessionDep, me: Me) -> dict:
        batch, p = batch_for(session, me, batch_id, edit=True)
        imports.undo(session, batch, user_id=me.user_id)
        return batch_view(session, me, batch, p)

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

    # Today

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
        return {
            "as_of": on.isoformat(),
            "kind": "team",
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
        document_id: str, session: SessionDep, me: Me, inline: bool = False
    ) -> Response:
        doc = document_for(session, me, document_id)
        return file_response(doc, services.read_file(app.state.storage, doc), inline)

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
