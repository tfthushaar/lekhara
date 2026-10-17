from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from horus import services, views
from horus.config import Settings, get_settings
from horus.db import Base, make_engine, make_sessionmaker
from horus.engines.escrow import CertifierRole
from horus.engines.obligations import ObligationStatus, sort_obligations
from horus.money import ZERO
from horus.rules import KARNATAKA


class NewWithdrawal(BaseModel):
    amount: Decimal | None = None


class CertificateFigures(BaseModel):
    completion_pct: Decimal | None = None
    development_cost_incurred: Decimal | None = None
    total_cost_incurred: Decimal | None = None
    withdrawable_amount: Decimal | None = None


class SignCertificate(BaseModel):
    signer_name: str
    signer_firm: str
    issued_on: date | None = None


class ReleaseWithdrawal(BaseModel):
    amount: Decimal | None = None
    bank_reference: str | None = None
    released_on: date | None = None


class RejectWithdrawal(BaseModel):
    reason: str = ""


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = make_sessionmaker(engine)

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

    @app.exception_handler(services.ServiceError)
    def service_error(_request: Request, exc: services.ServiceError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/today")
    def today(session: SessionDep, on: AsOf) -> dict:
        org = services.organization(session)
        snaps = [services.snapshot(session, p, on) for p in services.projects(session)]
        items = sort_obligations([o for s in snaps for o in s.obligations])
        due_this_week = sum(
            1
            for o in items
            if o.status == ObligationStatus.OVERDUE
            or (o.status == ObligationStatus.DUE_SOON and o.due_on and (o.due_on - on).days <= 7)
        )
        return {
            "as_of": on.isoformat(),
            "organization": org.name,
            "summary": {
                "drawable_now": views.m(sum((s.escrow.drawable_now for s in snaps), ZERO)),
                "at_stake": views.m(sum((o.amount or ZERO for o in items if o.exposure), ZERO)),
                "due_this_week": due_this_week,
                "projects": len(snaps),
            },
            "items": [views.obligation(o) for o in items if o.status != ObligationStatus.DONE],
        }

    @app.get("/projects")
    def list_projects(session: SessionDep, on: AsOf) -> list[dict]:
        return [
            views.project_card(services.snapshot(session, p, on))
            for p in services.projects(session)
        ]

    @app.get("/projects/{project_id}")
    def project(project_id: str, session: SessionDep, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        return views.project_detail(services.snapshot(session, p, on))

    @app.get("/projects/{project_id}/money")
    def project_money(project_id: str, session: SessionDep, on: AsOf) -> dict:
        s = services.snapshot(session, services.get_project(session, project_id), on)
        return {"summary": views.money_summary(s), "lines": views.money_lines(s)}

    @app.get("/projects/{project_id}/escrow")
    def project_escrow(project_id: str, session: SessionDep, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        s = services.snapshot(session, p, on)
        states = [
            services.request_state(session, r, on) for r in services.project_requests(session, p)
        ]
        return views.escrow(s, states)

    @app.post("/projects/{project_id}/withdrawals", status_code=201)
    def new_withdrawal(project_id: str, body: NewWithdrawal, session: SessionDep, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        r = services.create_withdrawal(session, p, body.amount, on)
        return views.request(services.request_state(session, r, on))

    @app.get("/withdrawals/{request_id}")
    def withdrawal(request_id: str, session: SessionDep, on: AsOf) -> dict:
        r = services.get_request(session, request_id)
        return views.request(services.request_state(session, r, on))

    @app.put("/withdrawals/{request_id}/certificates/{role}")
    def update_certificate(
        request_id: str,
        role: CertifierRole,
        body: CertificateFigures,
        session: SessionDep,
        on: AsOf,
    ) -> dict:
        r = services.get_request(session, request_id)
        services.update_certificate(session, r, role, body.model_dump(exclude_unset=True))
        return views.request(services.request_state(session, r, on))

    @app.post("/withdrawals/{request_id}/certificates/{role}/sign")
    def sign_certificate(
        request_id: str, role: CertifierRole, body: SignCertificate, session: SessionDep, on: AsOf
    ) -> dict:
        r = services.get_request(session, request_id)
        services.sign_certificate(
            session,
            r,
            role,
            signer_name=body.signer_name,
            signer_firm=body.signer_firm,
            issued_on=body.issued_on or on,
        )
        return views.request(services.request_state(session, r, on))

    @app.post("/withdrawals/{request_id}/submit")
    def submit(request_id: str, session: SessionDep, on: AsOf) -> dict:
        r = services.get_request(session, request_id)
        services.submit_request(session, r, on)
        return views.request(services.request_state(session, r, on))

    @app.post("/withdrawals/{request_id}/release")
    def release(request_id: str, body: ReleaseWithdrawal, session: SessionDep, on: AsOf) -> dict:
        r = services.get_request(session, request_id)
        services.release_request(
            session,
            r,
            amount=body.amount,
            bank_reference=body.bank_reference,
            released_on=body.released_on or on,
        )
        return views.request(services.request_state(session, r, on))

    @app.post("/withdrawals/{request_id}/reject")
    def reject(request_id: str, body: RejectWithdrawal, session: SessionDep, on: AsOf) -> dict:
        r = services.get_request(session, request_id)
        services.reject_request(session, r, reason=body.reason, rejected_on=on)
        return views.request(services.request_state(session, r, on))

    @app.get("/projects/{project_id}/tax")
    def project_tax(project_id: str, session: SessionDep, on: AsOf) -> dict:
        return views.tax(services.snapshot(session, services.get_project(session, project_id), on))

    @app.get("/projects/{project_id}/units")
    def project_units(project_id: str, session: SessionDep, on: AsOf) -> dict:
        p = services.get_project(session, project_id)
        s = services.snapshot(session, p, on)
        return views.units(s, services.project_units(session, p), services.landowners(session, p))

    @app.get("/rules")
    def rules(on: AsOf) -> dict:
        return views.rules(KARNATAKA, on)

    return app


def __getattr__(name: str):
    # `uvicorn horus.app:app` builds the app lazily, so importing this module stays cheap.
    if name == "app":
        return create_app()
    raise AttributeError(name)
