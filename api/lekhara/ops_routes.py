"""Routes for running the firm: contractors and payments, the site, after handover, and cash
and loans; and what Today shows each role.

Each route checks two things: that the place is part of the person's role (lekhara.roles), and,
to change anything, that their role may.
"""

from datetime import date, timedelta
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara import (
    accounts,
    aftercare,
    auth,
    contractors,
    lending,
    roles,
    sales,
    scan,
    services,
    site,
)
from lekhara.auth import OrgRole
from lekhara.models import (
    Bill,
    Commitment,
    DailyReport,
    Lead,
    Loan,
    LoanCondition,
    MaterialItem,
    MaterialRequest,
    Organization,
    Project,
    SiteVisit,
    UnitIssue,
)
from lekhara.services import ServiceError


class Fields(BaseModel):
    model_config = {"extra": "allow"}


def _f(body: Fields) -> dict:
    return {k: v for k, v in body.model_dump().items() if v is not None}


def register(app: FastAPI, SessionDep, Me, AsOf, settings) -> None:  # noqa: C901, N803
    def place(session: Session, me: auth.Principal, project_id: str, area: str,
              edit: tuple[OrgRole, ...] | None = None) -> Project:  # fmt: skip
        project = services.get_project(session, project_id)
        auth.require_team(me, project)
        role = me.org_roles.get(project.organization_id)
        if role is not None and area not in roles.areas_for(role):
            raise ServiceError("This isn't part of your work in Lekhara.", 403)
        if edit is not None:
            if role is None:
                raise ServiceError("The sample projects are read-only.", 403)
            if role not in edit:
                raise ServiceError("Your role can't change this.", 403)
            auth.require_writable(me, project)
        return project

    def firm(session: Session, me: auth.Principal) -> tuple[Organization, OrgRole]:
        org = accounts.current_org(session, me)
        return org, me.org_roles[org.id]

    def can(me: auth.Principal, p: Project, who) -> bool:
        return roles.can(me, p, who) and not me.views_as_sample(p)

    # Contractors and payments

    @app.get("/projects/{project_id}/contractors")
    def get_contractors(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = place(session, me, project_id, "contractors")
        return contractors.contractors_view(session, p, as_of=on,
                                            can_edit=can(me, p, roles.MANAGERS))  # fmt: skip

    @app.post("/projects/{project_id}/contractors/orders", status_code=201)
    def new_order(project_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf):
        p = place(session, me, project_id, "contractors", roles.MANAGERS)
        o = contractors.create_order(session, p, _f(body), as_of=on, user_id=me.user_id)
        return {"id": o.id}

    def order_for(session, me, order_id: str, edit=True) -> tuple[Project, Commitment]:
        o = session.get(Commitment, order_id)
        if o is None:
            raise ServiceError("Order not found.", 404)
        p = place(session, me, o.project_id, "contractors", roles.MANAGERS if edit else None)
        return p, o

    @app.post("/contractors/orders/{order_id}/bills", status_code=201)
    def new_running_bill(order_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf):
        p, o = order_for(session, me, order_id)
        ra = contractors.add_running_bill(session, p, o, _f(body), as_of=on, user_id=me.user_id)
        return {"id": ra.id, "net_payable": f"{ra.net_payable:.2f}"}

    @app.post("/contractors/orders/{order_id}/preview")
    def preview_running_bill(order_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf):
        p, o = order_for(session, me, order_id, edit=False)
        f = _f(body)
        value = contractors._money(f.get("work_value"), "the value of work done", required=True)
        held = contractors.work_out(session, p, o, value, on)
        return {k: (f"{v:.2f}" if hasattr(v, "quantize") else v) for k, v in held.items()}

    @app.post("/contractors/orders/{order_id}/release-retention")
    def release(order_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        _, o = order_for(session, me, order_id)
        contractors.release_retention(session, o, as_of=on)
        return {"ok": True}

    @app.get("/payables")
    def get_payables(session: SessionDep, me: Me, on: AsOf) -> dict:
        org, role = firm(session, me)
        if role not in (*roles.MANAGERS, OrgRole.VIEWER):
            raise ServiceError("This isn't part of your work in Lekhara.", 403)
        return contractors.payables_view(
            session, org, as_of=on, can_approve=role in roles.APPROVERS,
            can_pay=role in roles.MANAGERS,
        )  # fmt: skip

    def bill_for(session, me, bill_id: str, who) -> tuple[Bill, OrgRole]:
        bill = session.get(Bill, bill_id)
        if bill is None:
            raise ServiceError("Bill not found.", 404)
        p = place(session, me, bill.project_id, "suppliers", who)
        return bill, me.org_roles[p.organization_id]

    @app.post("/payables/{bill_id}/approve")
    def approve(bill_id: str, session: SessionDep, me: Me) -> dict:
        bill, _ = bill_for(session, me, bill_id, roles.APPROVERS)
        contractors.approve(session, bill, user_id=me.user_id)
        return {"ok": True}

    @app.post("/payables/{bill_id}/hold")
    def hold(bill_id: str, body: Fields, session: SessionDep, me: Me) -> dict:
        bill, _ = bill_for(session, me, bill_id, roles.APPROVERS)
        contractors.hold(session, bill, _f(body).get("note"), user_id=me.user_id)
        return {"ok": True}

    @app.post("/payables/{bill_id}/pay")
    def pay(bill_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf) -> dict:
        bill, role = bill_for(session, me, bill_id, roles.MANAGERS)
        contractors.pay(session, bill, _f(body), as_of=on, user_id=me.user_id,
                        approver=role in roles.APPROVERS)  # fmt: skip
        return {"ok": True}

    # The site

    @app.get("/projects/{project_id}/site")
    def get_site(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = place(session, me, project_id, "site")
        return site.site_view(session, p, as_of=on, can_report=can(me, p, roles.SITE_WORK))

    @app.post("/projects/{project_id}/daily-reports", status_code=201)
    async def save_report(
        project_id: str,
        request: Request,
        session: SessionDep,
        me: Me,
        on: AsOf,
        photos: Annotated[list[UploadFile] | None, File()] = None,
        work_done: Annotated[str | None, Form()] = None,
        workers: Annotated[str | None, Form()] = None,
        issues: Annotated[str | None, Form()] = None,
        day: Annotated[str | None, Form()] = None,
    ) -> dict:
        p = place(session, me, project_id, "site", roles.SITE_WORK)
        form = await request.form()
        used = [
            {"item": form.get(f"used_item_{i}"), "quantity": form.get(f"used_qty_{i}"),
             "unit": form.get(f"used_unit_{i}")}
            for i in range(6)
        ]  # fmt: skip
        files = []
        for upload in photos or []:
            data = await upload.read()
            if data:
                scan.check(settings, data, upload.filename or "A photo")
                files.append((upload.filename or "photo", data))
        r = site.save_report(
            session, app.state.storage, p,
            {"on": day, "work_done": work_done, "workers": workers, "issues": issues,
             "used": used},
            files, as_of=on, user_id=me.user_id,
        )  # fmt: skip
        return {"id": r.id}

    @app.get("/daily-reports/{report_id}/photos/{photo_id}")
    def get_photo(report_id: str, photo_id: str, session: SessionDep, me: Me) -> Response:
        r = session.get(DailyReport, report_id)
        if r is None:
            raise ServiceError("Report not found.", 404)
        place(session, me, r.project_id, "site")
        data, kind = site.photo(session, app.state.storage, r, photo_id)
        return Response(
            content=data, media_type=kind, headers={"Cache-Control": "private, max-age=86400"}
        )

    @app.get("/projects/{project_id}/materials")
    def get_materials(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = place(session, me, project_id, "materials")
        return site.materials_view(session, p, as_of=on, can_ask=can(me, p, roles.SITE_WORK),
                                   can_order=can(me, p, roles.MANAGERS))  # fmt: skip

    @app.post("/projects/{project_id}/material-requests", status_code=201)
    def ask(project_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = place(session, me, project_id, "materials", roles.SITE_WORK)
        return {"id": site.request(session, p, _f(body), as_of=on, user_id=me.user_id).id}

    @app.post("/projects/{project_id}/materials/received", status_code=201)
    def arrived(project_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = place(session, me, project_id, "materials", roles.SITE_WORK)
        return {"id": site.received(session, p, _f(body), as_of=on, user_id=me.user_id).id}

    def request_for(session, me, request_id: str, who) -> tuple[Project, MaterialRequest]:
        r = session.get(MaterialRequest, request_id)
        if r is None:
            raise ServiceError("Request not found.", 404)
        return place(session, me, r.project_id, "materials", who), r

    @app.post("/material-requests/{request_id}/quotes", status_code=201)
    def quote(request_id: str, body: Fields, session: SessionDep, me: Me) -> dict:
        _, r = request_for(session, me, request_id, roles.MANAGERS)
        return {"id": site.add_quote(session, r, _f(body)).id}

    @app.post("/material-requests/{request_id}/order")
    def order(request_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf) -> dict:
        p, r = request_for(session, me, request_id, roles.MANAGERS)
        c = site.order(session, p, r, _f(body), as_of=on, user_id=me.user_id)
        return {"order": c.reference}

    @app.post("/material-requests/{request_id}/receive")
    def receive(request_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf) -> dict:
        _, r = request_for(session, me, request_id, roles.SITE_WORK)
        site.receive(session, r, _f(body), as_of=on, user_id=me.user_id)
        return {"ok": True}

    @app.post("/material-requests/{request_id}/cancel")
    def cancel(request_id: str, session: SessionDep, me: Me) -> dict:
        _, r = request_for(session, me, request_id, roles.SITE_WORK)
        site.cancel(session, r)
        return {"ok": True}

    @app.post("/material-items/{item_id}")
    def set_low(item_id: str, body: Fields, session: SessionDep, me: Me) -> dict:
        item = session.get(MaterialItem, item_id)
        if item is None:
            raise ServiceError("Material not found.", 404)
        place(session, me, item.project_id, "materials", roles.SITE_WORK)
        site.set_min_level(session, item, _f(body).get("min_level"))
        return {"ok": True}

    # After handover

    @app.get("/projects/{project_id}/issues")
    def get_issues(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = place(session, me, project_id, "issues")
        return aftercare.view(session, p, as_of=on, can_edit=can(me, p, roles.ISSUE_WORK))

    @app.post("/projects/{project_id}/issues", status_code=201)
    def new_issue(project_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf):
        p = place(session, me, project_id, "issues", roles.ISSUE_WORK)
        return {"id": aftercare.add(session, p, _f(body), as_of=on, user_id=me.user_id).id}

    def issue_for(session, me, issue_id: str) -> UnitIssue:
        i = session.get(UnitIssue, issue_id)
        if i is None:
            raise ServiceError("Not found.", 404)
        place(session, me, i.project_id, "issues", roles.ISSUE_WORK)
        return i

    @app.post("/issues/{issue_id}/done")
    def issue_done(issue_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf) -> dict:
        aftercare.close(session, issue_for(session, me, issue_id), _f(body), as_of=on)
        return {"ok": True}

    @app.post("/issues/{issue_id}/reopen")
    def issue_reopen(issue_id: str, session: SessionDep, me: Me) -> dict:
        aftercare.reopen(session, issue_for(session, me, issue_id))
        return {"ok": True}

    # Cash and loans

    @app.get("/projects/{project_id}/cash")
    def get_cash(project_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        p = place(session, me, project_id, "cash")
        snap = services.snapshot(session, p, on)
        return lending.cash_view(session, p, as_of=on, drawable=snap.escrow.drawable_now,
                                 can_edit=can(me, p, roles.APPROVERS))  # fmt: skip

    @app.post("/projects/{project_id}/loans", status_code=201)
    def new_loan(project_id: str, body: Fields, session: SessionDep, me: Me) -> dict:
        p = place(session, me, project_id, "cash", roles.APPROVERS)
        return {"id": lending.add_loan(session, p, _f(body)).id}

    def loan_for(session, me, loan_id: str) -> Loan:
        loan = session.get(Loan, loan_id)
        if loan is None:
            raise ServiceError("Loan not found.", 404)
        place(session, me, loan.project_id, "cash", roles.APPROVERS)
        return loan

    @app.post("/loans/{loan_id}/moves", status_code=201)
    def loan_move(loan_id: str, body: Fields, session: SessionDep, me: Me, on: AsOf) -> dict:
        return {"id": lending.add_move(session, loan_for(session, me, loan_id), _f(body),
                                       as_of=on).id}  # fmt: skip

    @app.post("/loans/{loan_id}/conditions", status_code=201)
    def loan_condition(loan_id: str, body: Fields, session: SessionDep, me: Me) -> dict:
        return {"id": lending.add_condition(session, loan_for(session, me, loan_id), _f(body)).id}

    @app.post("/loan-conditions/{condition_id}/met")
    def condition_met(condition_id: str, session: SessionDep, me: Me, on: AsOf) -> dict:
        c = session.get(LoanCondition, condition_id)
        if c is None:
            raise ServiceError("Not found.", 404)
        loan_for(session, me, c.loan_id)
        lending.meet_condition(session, c, as_of=on)
        return {"ok": True}


# What Today shows each role


def _projects(session: Session, org_id: str) -> list[Project]:
    return list(
        session.scalars(
            select(Project).where(Project.organization_id == org_id).order_by(Project.name)
        )
    )


def role_today(session: Session, me: auth.Principal, on: date) -> dict | None:
    """Today for Sales and the site engineer; None for everyone else."""
    if not me.org_roles:
        return None
    org = accounts.current_org(session, me)
    role = me.org_roles[org.id]
    projects = _projects(session, org.id)
    ids = [p.id for p in projects]
    names = {p.id: p.name for p in projects}
    if role == OrgRole.SALES:
        leads = list(
            session.scalars(
                select(Lead)
                .where(
                    Lead.organization_id == org.id,
                    Lead.stage.in_(sales.OPEN_STAGES),
                    Lead.next_follow_up_on <= on,
                )
                .order_by(Lead.next_follow_up_on)
            )
        )
        visits = list(
            session.scalars(
                select(SiteVisit)
                .where(
                    SiteVisit.project_id.in_(ids),
                    SiteVisit.status == "planned",
                    SiteVisit.on.between(on, on + timedelta(days=7)),
                )
                .order_by(SiteVisit.on)
            )
        )
        requests = session.scalar(
            select(func.count())
            .select_from(UnitIssue)
            .where(
                UnitIssue.project_id.in_(ids),
                UnitIssue.kind == "request",
                UnitIssue.status == "open",
            )  # fmt: skip
        )
        return {
            "kind": "sales",
            "as_of": on.isoformat(),
            "organization": org.name,
            "calls": [
                {**sales.lead_row(x, {}, on), "project": names.get(x.project_id, "")} for x in leads
            ],
            "visits": [
                {
                    "id": v.id,
                    "lead_id": v.lead_id,
                    "lead": (session.get(Lead, v.lead_id).name),
                    "on": v.on.isoformat(),
                    "time": v.time,
                    "project": names[v.project_id],
                }
                for v in visits
            ],  # fmt: skip
            "requests": requests or 0,
            "first_project": ids[0] if ids else None,
        }
    if role == OrgRole.SITE:
        out = []
        for p in projects:
            filed = session.scalars(
                select(DailyReport).where(DailyReport.project_id == p.id, DailyReport.on == on)
            ).first()
            waiting = session.scalar(
                select(func.count())
                .select_from(MaterialRequest)
                .where(
                    MaterialRequest.project_id == p.id,
                    MaterialRequest.status.in_(("requested", "ordered")),
                )  # fmt: skip
            )
            issues = list(
                session.scalars(
                    select(UnitIssue).where(
                        UnitIssue.project_id == p.id,
                        UnitIssue.status == "open",
                        UnitIssue.kind.in_(("snag", "defect")),
                    )
                )
            )
            low = sum(1 for s in site.stock(session, p) if s["low"])
            out.append({
                "id": p.id, "name": p.name, "report_filed": filed is not None,
                "requests_waiting": waiting or 0, "issues_open": len(issues),
                "issues_late": sum(1 for i in issues if i.due_on and i.due_on < on),
                "low_stock": low,
            })  # fmt: skip
        return {"kind": "site", "as_of": on.isoformat(), "organization": org.name, "projects": out}
    return None


def manager_extras(session: Session, me: auth.Principal, on: date) -> dict:
    """What the owner, finance and accounts are asked to act on, beyond the project lists."""
    if not me.org_roles:
        return {}
    org = accounts.current_org(session, me)
    role = me.org_roles[org.id]
    if role not in (*roles.MANAGERS, OrgRole.VIEWER):
        return {}
    ids = [p.id for p in _projects(session, org.id)]
    c = contractors.counts(session, org)

    def first(model, *where) -> tuple[int, str | None]:
        rows = session.execute(
            select(model.project_id, func.count()).where(model.project_id.in_(ids), *where)
            .group_by(model.project_id)
        ).all()  # fmt: skip
        return sum(n for _, n in rows), (rows[0][0] if rows else None)

    late_defects, defects_at = first(UnitIssue, UnitIssue.kind == "defect",
                                     UnitIssue.status == "open", UnitIssue.due_on < on)  # fmt: skip
    to_order, order_at = first(MaterialRequest, MaterialRequest.status == "requested")
    conditions, loan_at = first(LoanCondition, LoanCondition.met_on.is_(None),
                                LoanCondition.due_on <= on + timedelta(days=14))  # fmt: skip
    return {
        "tasks": {
            "to_approve": c["waiting"] if role in roles.APPROVERS else 0,
            "to_pay": c["approved"] if role in roles.MANAGERS else 0,
            "held": c["held"],
            "late_defects": late_defects,
            "late_defects_at": defects_at,
            "loan_conditions": conditions,
            "loan_at": loan_at,
            "to_order": to_order,
            "to_order_at": order_at,
        }
    }
