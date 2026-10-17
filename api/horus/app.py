from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from horus import auth, services, views
from horus.config import Settings, get_settings
from horus.db import make_engine, make_sessionmaker
from horus.engines.escrow import ROLE_ORDER, CertifierRole, RequestStatus
from horus.engines.obligations import ObligationStatus, sort_obligations
from horus.migrate import upgrade
from horus.models import Organization, PaymentMilestone, Project, Unit
from horus.money import ZERO
from horus.rules import KARNATAKA
from horus.services import ServiceError

DEMO_PASSWORD = "horus-demo"


class Login(BaseModel):
    email: str
    password: str


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

    app = FastAPI(title="Horus API", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory

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
        principal = auth.principal_for(session, token)
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
    def me(session: SessionDep, me: Me) -> dict:
        organizations = [
            org.name
            for org in session.scalars(
                select(Organization).where(Organization.id.in_(set(me.org_roles)))
            )
        ]
        return {
            "user": {"id": me.user_id, "name": me.name, "email": me.email, "firm": me.firm},
            "role_label": me.describe(),
            "kind": "certifier" if me.is_certifier_only else "team",
            "organizations": organizations,
        }

    @app.get("/auth/demo")
    def demo_accounts(session: SessionDep) -> dict:
        if not settings.demo:
            raise ServiceError("Not found.", 404)
        from horus.seed import DEMO_ACCOUNTS

        return {
            "password": DEMO_PASSWORD,
            "accounts": [
                {"email": a.email, "name": a.name, "label": a.label} for a in DEMO_ACCOUNTS
            ],
        }

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
                        "detail": "A withdrawal from the RERA account is waiting for you. Horus "
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
        return [views.project_card(services.snapshot(session, p, on)) for p in visible(session, me)]

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
    # `uvicorn horus.app:app` builds the app lazily, so importing this module stays cheap.
    if name == "app":
        return create_app()
    raise AttributeError(name)
