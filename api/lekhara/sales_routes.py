"""The routes for sales (lekhara.sales): leads, visits, holds, prices, bookings, channel
partners and their commission.

The firm's owner, finance and accounts people work the leads; a viewer can look. The sample
firm can be looked at by anyone, and changed by no one.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import FastAPI, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from lekhara import accounts, auth, sales, services
from lekhara.models import (
    Booking,
    Commission,
    Lead,
    Organization,
    Project,
    SiteVisit,
    Unit,
    UnitHold,
)
from lekhara.services import ServiceError

MANAGERS = (auth.OrgRole.OWNER, auth.OrgRole.FINANCE, auth.OrgRole.ACCOUNTS)


class LeadBody(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    source: str | None = None
    partner_id: str | None = None
    interest: str | None = None
    budget: str | None = None
    owner_user_id: str | None = None
    next_follow_up_on: str | None = None
    project_id: str | None = None
    stage: str | None = None
    lost_reason: str | None = None


class ActivityBody(BaseModel):
    kind: str | None = None
    detail: str | None = None
    next_follow_up_on: str | None = None


class VisitBody(BaseModel):
    on: str | None = None
    time: str | None = None
    project_id: str | None = None


class VisitDoneBody(BaseModel):
    status: str | None = None
    feedback: str | None = None


class HoldBody(BaseModel):
    unit_id: str


class PriceListBody(BaseModel):
    base_rate: str | None = None
    floor_rise: str | None = None
    floor_rise_from: str | None = None
    plc: str | None = None
    car_park: str | None = None
    amenities: str | None = None
    other_charges: str | None = None
    corpus_per_sqft: str | None = None
    maintenance_per_sqft_month: str | None = None
    maintenance_months: str | None = None


class BookBody(BaseModel):
    unit_id: str
    booked_on: str | None = None
    booking_amount: str | None = None
    reference: str | None = None
    buyer_pan: str | None = None
    aadhaar_last4: str | None = None
    buyer_address: str | None = None
    plc: list[str] | None = None
    discount_per_sqft: str | None = None
    partner_id: str | None = None


class PartnerBody(BaseModel):
    name: str | None = None
    firm: str | None = None
    phone: str | None = None
    email: str | None = None
    krera_number: str | None = None
    krera_valid_until: str | None = None
    commission_pct: str | None = None
    payable_after_pct: str | None = None
    gstin: str | None = None
    pan: str | None = None
    active: bool | None = None


class PayBody(BaseModel):
    paid_on: str | None = None
    reference: str | None = None


def _fields(body: BaseModel) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)


def _pdf(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def register(app: FastAPI, SessionDep, Me, AsOf) -> None:  # noqa: C901, N803
    def org_access(session: Session, me: auth.Principal, org_id: str, *, edit: bool):
        org = session.get(Organization, org_id)
        role = me.org_roles.get(org_id)
        if org is None or (role is None and not org.is_sample):
            return None
        if edit:
            if role is None:
                raise ServiceError("The sample firm is read-only.", 403)
            if role not in MANAGERS:
                raise ServiceError("Your role cannot change sales records.", 403)
            if services.access_state(org, me.as_of) == "read_only":
                raise ServiceError(services.read_only_message(org), 402)
        return org

    def can_edit(session: Session, me: auth.Principal, org_id: str) -> bool:
        try:
            return org_access(session, me, org_id, edit=True) is not None
        except ServiceError:
            return False

    def project_for(session: Session, me: auth.Principal, project_id: str, *, edit=False):
        project = services.get_project(session, project_id)
        auth.require_team(me, project)
        if org_access(session, me, project.organization_id, edit=edit) is None:
            raise ServiceError("Project not found.", 404)
        return project

    def lead_for(session: Session, me: auth.Principal, lead_id: str, *, edit=False) -> Lead:
        lead = session.get(Lead, lead_id)
        if lead is None or org_access(session, me, lead.organization_id, edit=edit) is None:
            raise ServiceError("Lead not found.", 404)
        if lead.project_id:
            project = services.get_project(session, lead.project_id)
            if not me.is_team(project):
                raise ServiceError("Lead not found.", 404)
        return lead

    def unit_in(session: Session, project: Project, unit_id: str) -> Unit:
        unit = session.get(Unit, unit_id)
        if unit is None or unit.project_id != project.id:
            raise ServiceError("Unit not found.", 404)
        return unit

    def unit_for_lead(session: Session, lead: Lead, unit_id: str) -> Unit:
        unit = session.get(Unit, unit_id)
        project = session.get(Project, unit.project_id) if unit else None
        if project is None or project.organization_id != lead.organization_id:
            raise ServiceError("Unit not found.", 404)
        return unit

    def lead_payload(session: Session, me: auth.Principal, lead: Lead, on: date) -> dict:
        return sales.lead_view(
            session, lead, as_of=on, can_edit=can_edit(session, me, lead.organization_id)
        )

    # Leads and the project's sales page

    @app.get("/projects/{project_id}/sales")
    def project_sales(
        project_id: str,
        session: SessionDep,
        me: Me,
        on: AsOf,
        stage: Annotated[str | None, Query()] = None,
    ) -> dict:
        p = project_for(session, me, project_id)
        if stage is not None and stage not in sales.STAGES:
            stage = None
        return sales.project_view(
            session, p, as_of=on, stage=stage, can_edit=can_edit(session, me, p.organization_id)
        )

    @app.post("/projects/{project_id}/leads", status_code=201)
    def create_lead(project_id: str, body: LeadBody, session: SessionDep, me: Me, on: AsOf):
        p = project_for(session, me, project_id, edit=True)
        org = session.get(Organization, p.organization_id)
        fields = {**_fields(body), "project_id": body.project_id or p.id}
        lead, new = sales.add_lead(session, org, fields, as_of=on, user_id=me.user_id)
        return {"id": lead.id, "new": new}

    @app.get("/leads/{lead_id}")
    def get_lead(lead_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        return lead_payload(session, me, lead_for(session, me, lead_id), on)

    @app.put("/leads/{lead_id}")
    def update_lead(lead_id: str, body: LeadBody, session: SessionDep, me: Me, on: AsOf):
        lead = lead_for(session, me, lead_id, edit=True)
        sales.update_lead(session, lead, _fields(body), as_of=on, user_id=me.user_id)
        return lead_payload(session, me, lead, on)

    @app.post("/leads/{lead_id}/activities", status_code=201)
    def add_activity(lead_id: str, body: ActivityBody, session: SessionDep, me: Me, on: AsOf):
        lead = lead_for(session, me, lead_id, edit=True)
        sales.log_activity(session, lead, _fields(body), as_of=on, user_id=me.user_id)
        return lead_payload(session, me, lead, on)

    @app.post("/leads/{lead_id}/visits", status_code=201)
    def plan_visit(lead_id: str, body: VisitBody, session: SessionDep, me: Me, on: AsOf):
        lead = lead_for(session, me, lead_id, edit=True)
        sales.plan_visit(session, lead, _fields(body), as_of=on, user_id=me.user_id)
        return lead_payload(session, me, lead, on)

    @app.post("/visits/{visit_id}")
    def record_visit(visit_id: str, body: VisitDoneBody, session: SessionDep, me: Me, on: AsOf):
        visit = session.get(SiteVisit, visit_id)
        if visit is None:
            raise ServiceError("Visit not found.", 404)
        lead = lead_for(session, me, visit.lead_id, edit=True)
        sales.record_visit(session, visit, _fields(body), as_of=on, user_id=me.user_id)
        return lead_payload(session, me, lead, on)

    @app.post("/leads/{lead_id}/holds", status_code=201)
    def hold(lead_id: str, body: HoldBody, session: SessionDep, me: Me, on: AsOf):
        lead = lead_for(session, me, lead_id, edit=True)
        unit = unit_for_lead(session, lead, body.unit_id)
        sales.hold_unit(session, lead, unit, as_of=on, user_id=me.user_id)
        return lead_payload(session, me, lead, on)

    @app.post("/holds/{hold_id}/release")
    def release(hold_id: str, session: SessionDep, me: Me, on: AsOf):
        row = session.get(UnitHold, hold_id)
        if row is None:
            raise ServiceError("Hold not found.", 404)
        lead = lead_for(session, me, row.lead_id, edit=True)
        sales.release_hold(session, row, user_id=me.user_id)
        return lead_payload(session, me, lead, on)

    # Prices, cost sheets and bookings

    @app.put("/projects/{project_id}/price-list")
    def put_price_list(project_id: str, body: PriceListBody, session: SessionDep, me: Me):
        p = project_for(session, me, project_id, edit=True)
        sales.set_price_list(session, p, _fields(body), user_id=me.user_id)
        return {"ok": True}

    @app.get("/projects/{project_id}/units/{unit_id}/cost-sheet")
    def unit_cost_sheet(
        project_id: str,
        unit_id: str,
        session: SessionDep,
        me: Me,
        on: AsOf,
        plc: Annotated[list[str] | None, Query()] = None,
        discount: Annotated[str | None, Query()] = None,
    ) -> dict:
        p = project_for(session, me, project_id)
        unit = unit_in(session, p, unit_id)
        sheet = sales.sheet_for(session, p, unit, plc=plc or (), discount=discount, as_of=on)
        return {**sales.sheet_json(sheet), "project": p.name, "tower": unit.tower}

    @app.get("/projects/{project_id}/units/{unit_id}/cost-sheet.pdf")
    def unit_cost_sheet_pdf(
        project_id: str,
        unit_id: str,
        session: SessionDep,
        me: Me,
        on: AsOf,
        plc: Annotated[list[str] | None, Query()] = None,
        discount: Annotated[str | None, Query()] = None,
    ) -> Response:
        p = project_for(session, me, project_id)
        unit = unit_in(session, p, unit_id)
        sheet = sales.sheet_for(session, p, unit, plc=plc or (), discount=discount, as_of=on)
        org = session.get(Organization, p.organization_id)
        data = sales.cost_sheet_pdf(sheet, project=p, unit=unit, org=org, as_of=on)
        return _pdf(data, f"cost-sheet-{unit.label}.pdf")

    @app.post("/leads/{lead_id}/book", status_code=201)
    def book(lead_id: str, body: BookBody, session: SessionDep, me: Me, on: AsOf) -> dict:
        lead = lead_for(session, me, lead_id, edit=True)
        unit = unit_for_lead(session, lead, body.unit_id)
        booking = sales.book(session, lead, unit, _fields(body), as_of=on, user_id=me.user_id)
        return {"id": booking.id, "unit_id": unit.id, "project_id": unit.project_id}

    @app.get("/bookings/{booking_id}/allotment.pdf")
    def allotment(booking_id: str, session: SessionDep, me: Me) -> Response:
        booking = session.get(Booking, booking_id)
        project = session.get(Project, booking.project_id) if booking else None
        if project is None:
            raise ServiceError("Booking not found.", 404)
        project_for(session, me, project.id)
        unit = session.get(Unit, booking.unit_id)
        return _pdf(sales.allotment_letter(session, booking), f"allotment-{unit.label}.pdf")

    # Channel partners

    @app.get("/partners")
    def list_partners(session: SessionDep, me: Me, on: AsOf) -> dict:
        org = accounts.current_org(session, me)
        if org is None or org_access(session, me, org.id, edit=False) is None:
            raise ServiceError("Firm not found.", 404)
        return sales.partners_view(session, org, as_of=on, can_edit=can_edit(session, me, org.id))

    @app.post("/partners", status_code=201)
    def create_partner(body: PartnerBody, session: SessionDep, me: Me) -> dict:
        org = accounts.current_org(session, me)
        if org is None or org_access(session, me, org.id, edit=True) is None:
            raise ServiceError("Firm not found.", 404)
        return {"id": sales.save_partner(session, org, _fields(body)).id}

    @app.put("/partners/{partner_id}")
    def update_partner(partner_id: str, body: PartnerBody, session: SessionDep, me: Me):
        org = accounts.current_org(session, me)
        if org is None or org_access(session, me, org.id, edit=True) is None:
            raise ServiceError("Firm not found.", 404)
        partner = sales.partner_for(session, org, partner_id)
        fields = _fields(body)
        if "active" in fields:
            partner.active = bool(fields.pop("active"))
        merged = {
            "name": partner.name, "firm": partner.firm, "phone": partner.phone,
            "email": partner.email, "krera_number": partner.krera_number,
            "krera_valid_until": partner.krera_valid_until,
            "commission_pct": partner.commission_pct,
            "payable_after_pct": partner.payable_after_pct, "gstin": partner.gstin,
            "pan": partner.pan, **fields,
        }  # fmt: skip
        sales.save_partner(session, org, merged, partner)
        return {"ok": True}

    def commission_for(session: Session, me: auth.Principal, commission_id: str) -> Commission:
        c = session.get(Commission, commission_id)
        if c is None or org_access(session, me, c.organization_id, edit=True) is None:
            raise ServiceError("Commission not found.", 404)
        return c

    @app.post("/commissions/{commission_id}/pay")
    def pay(commission_id: str, body: PayBody, session: SessionDep, me: Me, on: AsOf) -> dict:
        c = commission_for(session, me, commission_id)
        sales.pay_commission(session, c, _fields(body), as_of=on, user_id=me.user_id)
        return {"ok": True}
