"""JSON views for the web app. Money is sent as decimal strings, dates as ISO strings."""

from datetime import date
from decimal import Decimal

from horus.engines.collections import CollectionsPosition
from horus.engines.disputes import (
    FORUM_LABEL,
    ORDER_LABEL,
    RELIEF_LABEL,
    RUNNING,
    STATUS_LABEL,
    CasePosition,
    DisputesPosition,
    Event,
)
from horus.engines.escrow import (
    ROLE_CERTIFIES,
    ROLE_LABEL,
    ROLE_ORDER,
    CertifierRole,
    LimitedBy,
    RequestStatus,
    can_submit,
)
from horus.engines.handover import (
    BLOCKER_TEXT,
    STAGE_LABEL,
    STAGES,
    HandoverPosition,
    UnitReadiness,
)
from horus.engines.obligations import Obligation, ObligationStatus
from horus.engines.tax import MsmeStatus
from horus.models import (
    DemandRow,
    DisputeCase,
    Landowner,
    PaymentMilestone,
    Project,
    Unit,
    WithdrawalRequest,
)
from horus.money import ZERO
from horus.rules import KARNATAKA, RuleNotFound, RulesPack
from horus.services import ProjectSnapshot, RequestState


def m(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def d(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


LAND_STRUCTURE = {
    "own": "Own land",
    "jda_area_share": "Joint development, area share",
    "jda_revenue_share": "Joint development, revenue share",
}

GST_REGIME = {
    "affordable_1pc": "Affordable housing, 1% without input credit",
    "residential_5pc": "Residential, 5% without input credit",
    "commercial_12pc": "Commercial, 12% with input credit",
    "rrep_mixed": "Residential with commercial space",
}


def obligation(o: Obligation) -> dict:
    return {
        "key": o.key,
        "project_id": o.project_id,
        "project_name": o.project_name,
        "title": o.title,
        "detail": o.detail,
        "owed_to": o.owed_to,
        "status": o.status.value,
        "area": o.area.value,
        "due_on": d(o.due_on),
        "amount": m(o.amount),
        "rule_key": o.rule_key,
        "action": o.action,
        "amount_label": o.amount_label,
        "exposure": o.exposure,
        "link": f"/cases/{o.ref}" if o.ref else None,
    }


def _counts(items: list[Obligation]) -> dict:
    counts = {status.value: 0 for status in ObligationStatus}
    for o in items:
        counts[o.status.value] += 1
    return counts


def project_card(s: ProjectSnapshot) -> dict:
    p = s.project
    return {
        "id": p.id,
        "name": p.name,
        "locality": p.locality,
        "land_structure": LAND_STRUCTURE.get(p.land_structure, p.land_structure),
        "progress_pct": m(s.money.certified_progress_pct),
        "budget": m(s.money.budget),
        "anticipated_final_cost": m(s.money.anticipated_final_cost),
        "incurred": m(s.money.incurred),
        "drawable_now": m(s.escrow.drawable_now),
        "possession_due_on": d(p.possession_due_on),
        "counts": _counts(s.obligations),
        "next": obligation(s.obligations[0]) if s.obligations else None,
    }


def _head(h) -> dict:
    return {"estimated_cost": m(h.estimated_cost), "incurred": m(h.incurred), "paid": m(h.paid)}


def money_summary(s: ProjectSnapshot) -> dict:
    x = s.money
    return {
        "as_of": d(x.as_of),
        "budget": m(x.budget),
        "committed": m(x.committed),
        "incurred": m(x.incurred),
        "paid": m(x.paid),
        "retained": m(x.retained),
        "advance_outstanding": m(x.advance_outstanding),
        "contingency_budget": m(x.contingency_budget),
        "contingency_used": m(x.contingency_used),
        "contingency_remaining": m(x.contingency_remaining),
        "overrun_beyond_contingency": m(x.overrun_beyond_contingency),
        "anticipated_final_cost": m(x.anticipated_final_cost),
        "cost_to_complete": m(x.cost_to_complete),
        "land": _head(x.land),
        "development": _head(x.development),
        "certified_progress_pct": m(x.certified_progress_pct),
        "development_incurred_pct": m(x.development_incurred_pct),
        "alerts": [
            {"code": a.code, "title": a.title, "detail": a.detail, "amount": m(a.amount)}
            for a in x.alerts
        ],
    }


def project_detail(s: ProjectSnapshot) -> dict:
    p = s.project
    return {
        "id": p.id,
        "name": p.name,
        "locality": p.locality,
        "city": p.city,
        "krera_registration": p.krera_registration,
        "registered_on": d(p.registered_on),
        "spv_name": p.spv_name,
        "gst_regime": GST_REGIME.get(p.gst_regime, p.gst_regime),
        "land_structure": LAND_STRUCTURE.get(p.land_structure, p.land_structure),
        "possession_due_on": d(p.possession_due_on),
        "escrow_bank": p.escrow_bank,
        "money": money_summary(s),
        "drawable_now": m(s.escrow.drawable_now),
        "open_request_id": s.open_request.id if s.open_request else None,
        "obligations": [obligation(o) for o in s.obligations],
        "counts": _counts(s.obligations),
    }


def money_lines(s: ProjectSnapshot) -> list[dict]:
    return [
        {
            "id": p.line.id,
            "code": p.line.code,
            "name": p.line.name,
            "category": p.line.category.value,
            "rera_head": p.line.rera_head.value,
            "budget": m(p.line.revised_budget),
            "committed": m(p.committed),
            "incurred": m(p.incurred),
            "paid": m(p.paid),
            "anticipated_final_cost": m(p.anticipated_final_cost),
            "cost_to_complete": m(p.cost_to_complete),
            "overrun": m(p.overrun),
        }
        for p in s.money.lines
    ]


def _request_summary(request: WithdrawalRequest, status: RequestStatus, waiting_on) -> dict:
    return {
        "id": request.id,
        "amount": m(request.amount),
        "created_on": d(request.created_on),
        "submitted_on": d(request.submitted_on),
        "released_on": d(request.released_on),
        "released_amount": m(request.released_amount),
        "status": status.value,
        "waiting_on": waiting_on,
    }


def escrow(s: ProjectSnapshot, requests: list[RequestState], *, can_start: bool = False) -> dict:
    e = s.escrow
    basis_label = (
        "Cost incurred and paid so far"
        if e.cost_basis == "incurred_and_paid"
        else "Cost incurred so far"
    )
    return {
        "as_of": d(e.as_of),
        "drawable_now": m(e.drawable_now),
        "limited_by": e.limited_by.value,
        "limited_by_text": (
            "The account balance is lower than what your costs allow."
            if e.limited_by == LimitedBy.BALANCE
            else "Your costs incurred set the limit."
        ),
        "steps": [
            {
                "label": "Estimated cost of the project",
                "value": m(e.estimated_cost),
                "kind": "money",
            },
            {"label": basis_label, "value": m(e.basis_amount), "kind": "money"},
            {"label": "Share of estimated cost", "value": m(e.proportion_pct), "kind": "percent"},
            {
                "label": "Withdrawal limit so far (estimated cost times that share)",
                "value": m(e.cumulative_limit),
                "kind": "money",
            },
            {"label": "Less: already withdrawn", "value": m(e.withdrawn_to_date), "kind": "money"},
            {"label": "Limit remaining", "value": m(e.limit_remaining), "kind": "money"},
            {"label": "Balance in the RERA account", "value": m(e.balance), "kind": "money"},
        ],
        "deposits": {
            "receipts_from_buyers": m(e.receipts_from_buyers),
            "deposit_share_pct": m((e.deposit_share * 100).quantize(Decimal("0.01"))),
            "required": m(e.required_deposits),
            "deposited": m(e.deposits),
            "shortfall": m(e.deposit_shortfall),
        },
        "last_withdrawal_on": d(e.last_withdrawal_on),
        "next_cycle_due_on": d(e.next_cycle_due_on),
        "open_request_id": s.open_request.id if s.open_request else None,
        "can_start": can_start and s.open_request is None and e.drawable_now > 0,
        "requests": [_request_summary(r.request, r.status, r.waiting_on) for r in requests],
    }


STEP_NAMES = ("Prepared", "Architect", "Engineer", "CA", "Bank", "Released")


def _steps(state: RequestState) -> list[dict]:
    r = state.request
    signed = [
        bool(state.certificates.get(role) and state.certificates[role].signed)
        for role in ROLE_ORDER
    ]
    done = [True, *signed, r.submitted_on is not None, r.released_on is not None]
    steps = []
    current_found = False
    for name, is_done in zip(STEP_NAMES, done, strict=True):
        if is_done:
            status = "done"
        elif not current_found and state.status != RequestStatus.REJECTED:
            status, current_found = "current", True
        else:
            status = "todo"
        steps.append({"name": name, "status": status})
    if state.status == RequestStatus.REJECTED:
        steps[-1] = {"name": "Rejected", "status": "current"}
    return steps


NO_PERMISSIONS = {"edit_roles": [], "sign_roles": [], "can_submit": False, "can_release": False}


def request(state: RequestState, permissions: dict | None = None) -> dict:
    r = state.request
    snap = state.snapshot
    certificates = []
    for role in ROLE_ORDER:
        c = state.certificates.get(role)
        if c is None:
            continue
        figures: list[dict] = []
        if role == CertifierRole.ARCHITECT:
            figures.append(
                {
                    "field": "completion_pct",
                    "label": "Physical completion",
                    "value": m(c.completion_pct),
                    "books": m(snap.money.certified_progress_pct),
                    "kind": "percent",
                }
            )
        elif role == CertifierRole.ENGINEER:
            figures.append(
                {
                    "field": "development_cost_incurred",
                    "label": "Development cost incurred",
                    "value": m(c.development_cost_incurred),
                    "books": m(snap.money.development.incurred),
                    "kind": "money",
                }
            )
        else:
            figures.append(
                {
                    "field": "total_cost_incurred",
                    "label": "Total cost incurred and paid",
                    "value": m(c.total_cost_incurred),
                    "books": m(snap.escrow.basis_amount),
                    "kind": "money",
                }
            )
            figures.append(
                {
                    "field": "withdrawable_amount",
                    "label": "Amount that can be withdrawn",
                    "value": m(c.withdrawable_amount),
                    "books": m(snap.escrow.drawable_now),
                    "kind": "money",
                }
            )
        certificates.append(
            {
                "role": role.value,
                "label": ROLE_LABEL[role],
                "certifies": ROLE_CERTIFIES[role],
                "signed": c.signed,
                "signer_name": c.signer_name,
                "signer_firm": c.signer_firm,
                "issued_on": d(c.issued_on),
                "figures": figures,
            }
        )
    tolerance = KARNATAKA.value("escrow.figure_tolerance", snap.as_of)
    for cert in certificates:
        for figure in cert["figures"]:
            value, books = figure["value"], figure["books"]
            figure["matches_books"] = (
                value is None
                or books is None
                or abs(Decimal(value) - Decimal(books)) <= abs(Decimal(books)) * tolerance
            )
    return {
        "id": r.id,
        "project_id": snap.project.id,
        "project_name": snap.project.name,
        "escrow_bank": snap.project.escrow_bank,
        "amount": m(r.amount),
        "created_on": d(r.created_on),
        "submitted_on": d(r.submitted_on),
        "released_on": d(r.released_on),
        "released_amount": m(r.released_amount),
        "bank_reference": r.bank_reference,
        "rejected_on": d(r.rejected_on),
        "rejection_reason": r.rejection_reason,
        "status": state.status.value,
        "waiting_on": state.waiting_on,
        "permissions": permissions or NO_PERMISSIONS,
        "can_submit": state.status == RequestStatus.READY and can_submit(state.checks),
        "drawable_now": m(snap.escrow.drawable_now),
        "steps": _steps(state),
        "certificates": certificates,
        "checks": [
            {"code": c.code, "status": c.status.value, "title": c.title, "detail": c.detail}
            for c in state.checks
        ],
    }


def tax(s: ProjectSnapshot) -> dict:
    p = s.procurement
    dr = s.development_rights
    return {
        "as_of": d(s.as_of),
        "regime": GST_REGIME.get(s.project.gst_regime, s.project.gst_regime),
        "procurement": {
            "applies": p.applies,
            "fy": p.fy,
            "total": m(p.total),
            "qualifying": m(p.qualifying),
            "registered_share_pct": m(p.registered_share_pct),
            "min_share_pct": m(p.min_share_pct),
            "shortfall": m(p.shortfall),
            "rcm_on_shortfall": m(p.rcm_on_shortfall),
            "unregistered_headroom": m(p.unregistered_headroom),
            "unregistered_cement": m(p.unregistered_cement),
            "cement_rcm": m(p.cement_rcm),
            "payment_due_on": d(p.payment_due_on),
        },
        "development_rights": {
            "applies": dr.applies,
            "dr_value": m(dr.dr_value),
            "unbooked_units": dr.unbooked_units,
            "unbooked_area": m(dr.unbooked_area),
            "total_residential_area": m(dr.total_residential_area),
            "unbooked_value": m(dr.unbooked_value),
            "gst_on_unbooked_share": m(dr.gst_on_unbooked_share),
            "cap": m(dr.cap),
            "liability": m(dr.liability),
            "capped": dr.capped,
            "saving_per_unit_sold": m(dr.saving_per_unit_sold),
        },
        "guidance": [
            {
                "unit": f.sale.unit_label,
                "agreement_value": m(f.sale.agreement_value),
                "guidance_value": m(f.sale.guidance_value),
                "gap": m(f.gap),
                "gap_pct": m(f.gap_pct),
                "estimated_tax": m(f.estimated_tax),
                "booked_on": d(f.sale.booked_on),
            }
            for f in s.guidance_flags
        ],
        "landowner_tds": [
            {
                "landowner": t.payment.landowner,
                "paid_on": d(t.payment.on),
                "amount": m(t.payment.amount),
                "expected": m(t.expected),
                "deducted": m(t.payment.tds_deducted),
                "short": m(t.short),
            }
            for t in s.landowner_tds
        ],
        "msme": [
            {
                "vendor": i.bill.vendor,
                "bill_no": i.bill.bill_no,
                "amount": m(i.bill.amount),
                "accepted_on": d(i.bill.accepted_on),
                "due_on": d(i.due_on),
                "status": i.status.value,
                "days_left": i.days_left,
            }
            for i in s.msme
            if i.status in (MsmeStatus.OVERDUE, MsmeStatus.DUE_SOON, MsmeStatus.OK)
        ],
        "cess": {
            "construction_incurred": m(s.cess.construction_incurred),
            "due_to_date": m(s.cess.cess_due_to_date),
            "paid": m(s.cess.cess_paid),
            "balance_due": m(s.cess.balance_due),
            "on_estimate": m(s.cess.cess_on_estimate),
        },
        "delay": {
            "possession_due_on": d(s.delay.possession_due_on),
            "days_late": s.delay.days_late,
            "days_to_possession": s.delay.days_to_possession,
            "annual_rate_pct": m((s.delay.annual_rate * 100).quantize(Decimal("0.01"))),
            "buyer_money": m(s.delay.buyer_money),
            "accrued": m(s.delay.accrued),
            "per_month": m(s.delay.per_month),
        },
    }


def units(s: ProjectSnapshot, rows: list[Unit], owners: list[Landowner]) -> dict:
    flagged = {f.sale.unit_label for f in s.guidance_flags}
    developer = [u for u in rows if u.owner_share == "developer"]
    landowner = [u for u in rows if u.owner_share == "landowner"]
    return {
        "summary": {
            "total": len(rows),
            "developer": len(developer),
            "landowner": len(landowner),
            "developer_booked": sum(1 for u in developer if u.booked),
            "developer_unbooked": sum(1 for u in developer if not u.booked),
        },
        "landowners": [
            {
                "name": o.name,
                "share_type": o.share_type,
                "share_pct": m(o.share_pct),
                "refundable_deposit": m(o.refundable_deposit),
                "paid_to_date": m(sum((p.amount for p in o.payments), Decimal("0"))),
                "tds_to_date": m(sum((p.tds_deducted for p in o.payments), Decimal("0"))),
            }
            for o in owners
        ],
        "units": [
            {
                "label": u.label,
                "tower": u.tower,
                "carpet_area_sqft": u.carpet_area_sqft,
                "owner_share": u.owner_share,
                "booked": u.booked,
                "list_price": m(u.list_price),
                "agreement_value": m(u.agreement_value),
                "guidance_value": m(u.guidance_value),
                "below_guidance": u.label in flagged,
            }
            for u in rows
        ],
    }


# Collections


def collections(c: CollectionsPosition, *, can_raise: bool) -> dict:
    overdue = sorted((a for a in c.accounts if a.overdue > 0), key=lambda a: -a.overdue)
    return {
        "as_of": d(c.as_of),
        "can_raise": can_raise,
        "summary": {
            "billed": m(c.billed),
            "received": m(c.received),
            "outstanding": m(c.outstanding),
            "overdue": m(c.overdue),
            "overdue_buyers": c.overdue_buyers,
            "interest": m(c.interest),
        },
        "ready": [
            {
                "milestone_id": r.milestone.id,
                "name": r.milestone.name,
                "units": len(r.unit_ids),
                "amount": m(r.amount),
                "gst": m(r.gst),
                "total": m(r.amount + r.gst),
                "reason": r.reason,
            }
            for r in c.ready
        ],
        "milestones": [
            {
                "id": s.milestone.id,
                "sequence": s.milestone.sequence,
                "name": s.milestone.name,
                "share_pct": m(s.milestone.share_pct),
                "trigger": s.milestone.trigger.value,
                "progress_pct": m(s.milestone.progress_pct),
                "reached": s.reached,
                "raised_units": s.raised_units,
                "billed": m(s.billed),
            }
            for s in c.milestones
        ],
        "overdue": [
            {
                "unit": a.unit.label,
                "buyer": a.unit.buyer,
                "overdue": m(a.overdue),
                "interest": m(a.interest),
                "days_overdue": max((s.days_overdue for s in a.demands if s.overdue), default=0),
                "demand_id": next((s.demand.id for s in a.demands if s.overdue), None),
            }
            for a in overdue
        ],
        "accounts": [
            {
                "unit": a.unit.label,
                "buyer": a.unit.buyer,
                "agreement_value": m(a.unit.agreement_value),
                "billed": m(a.billed),
                "received": m(a.received),
                "tds": m(a.tds),
                "outstanding": m(a.outstanding),
                "overdue": m(a.overdue),
                "interest": m(a.interest),
                "last_demand_id": a.demands[-1].demand.id if a.demands else None,
            }
            for a in c.accounts
        ],
        "deposit_checks": [
            {
                "month_end": d(x.month_end),
                "receipts": m(x.receipts),
                "required": m(x.required),
                "deposits": m(x.deposits),
                "shortfall": m(x.shortfall),
            }
            for x in c.deposit_checks
        ],
    }


def _indian(amount: Decimal) -> str:
    """Rupees in full with Indian digit grouping: 6,40,00,000.00."""
    whole, _, paise = f"{amount:.2f}".partition(".")
    sign = "-" if whole.startswith("-") else ""
    whole = whole.lstrip("-")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join([*groups, tail]) if groups else tail}.{paise}"


def demand_letter(
    *,
    demand: DemandRow,
    project: Project,
    unit: Unit,
    milestone: PaymentMilestone,
    gst_rate: Decimal,
    tds_threshold: Decimal,
) -> dict:
    total = demand.amount + demand.gst
    share = f"{milestone.share_pct.normalize():f}%"
    paragraphs = [
        f"In line with the payment plan in your agreement for sale, the instalment due "
        f"{milestone.name.lower()} is now payable.",
    ]
    if demand.certified_progress_pct is not None:
        paragraphs.append(
            "Our architect has certified that construction has reached "
            f"{demand.certified_progress_pct.normalize():f}% completion, which reaches this "
            "milestone."
        )
    if unit.agreement_value and unit.agreement_value > tds_threshold:
        paragraphs.append(
            "As the value of your home is above ₹50 lakh, please deduct TDS at 1% of the "
            "instalment, deposit it using Form 26QB, and send us the Form 16B certificate."
        )
    paragraphs.append(
        "Your payment will be deposited in the project's RERA account as the law requires."
    )
    return {
        "id": demand.id,
        "project_id": project.id,
        "from": project.organization.name,
        "project": f"{project.name}, {project.locality}, {project.city}",
        "krera_registration": project.krera_registration,
        "date": d(demand.raised_on),
        "to": unit.buyer_name,
        "unit": unit.label,
        "subject": f"Demand for payment: {milestone.name}",
        "paragraphs": paragraphs,
        "lines": [
            {
                "label": f"Instalment ({share} of the agreement value)",
                "value": _indian(demand.amount),
            },
            {"label": f"GST at {(gst_rate * 100).normalize():f}%", "value": _indian(demand.gst)},
            {"label": "Total due", "value": _indian(total)},
        ],
        "due_on": d(demand.due_on),
        "note": "Draft prepared by Horus. Your team sends it from your own address.",
    }


# Registration and handover

OC_LABEL = {
    "none": "Not applied for",
    "applied": "Applied for",
    "partial": "Partial OC received",
    "received": "Received",
}
EKHATA_LABEL = {"none": "Not applied", "applied": "Applied", "draft": "Draft", "final": "Final"}


def _cost(c) -> dict:
    return {
        "base": m(c.base),
        "stamp_duty": m(c.stamp_duty),
        "cess": m(c.cess),
        "registration_fee": m(c.registration_fee),
        "total": m(c.total),
    }


def _unit_readiness(r: UnitReadiness) -> dict:
    u = r.unit
    return {
        "unit_id": u.unit_id,
        "label": u.label,
        "buyer": u.buyer,
        "blocker": r.blocker.value,
        "blocker_text": BLOCKER_TEXT[r.blocker],
        "steps": [{"stage": s.value, "label": STAGE_LABEL[s], "done": s in r.done} for s in STAGES],
        "ekhata_status": u.ekhata_status,
        "ekhata_label": EKHATA_LABEL.get(u.ekhata_status, u.ekhata_status),
        "khata_type": u.khata_type,
        "agreement_value": m(u.agreement_value),
        "guidance_value": m(u.guidance_value),
        "balance_due": m(u.balance_due),
        "final_demand_raised": u.final_demand_raised,
        "deed_drafted_on": d(u.deed_drafted_on),
        "appointment_on": d(u.appointment_on),
        "registered_on": d(u.registered_on),
        "document_no": u.document_no,
        "possession_on": d(u.possession_on),
        "cost": _cost(r.cost),
    }


def handover(h: HandoverPosition, project: Project, *, can_edit: bool) -> dict:
    return {
        "can_edit": can_edit,
        "oc": {
            "status": project.oc_status,
            "label": OC_LABEL.get(project.oc_status, project.oc_status),
            "received_on": d(project.oc_received_on),
            "reference": project.oc_reference,
        },
        "conveyance_due_on": d(h.conveyance_due_on),
        "common_areas_conveyed_on": d(h.common_areas_conveyed_on),
        "association_formed_on": d(project.association_formed_on),
        "summary": {
            "units": len(h.units),
            "registered": h.registered,
            "handed_over": h.handed_over,
            "money_waiting": m(h.money_waiting),
        },
        "stages": [
            {"stage": s.value, "label": STAGE_LABEL[s], "blocked": h.by_blocker[s]} for s in STAGES
        ],
        "units": [_unit_readiness(r) for r in h.units],
    }


def unit_handover(h: HandoverPosition, project: Project, unit: Unit, *, can_edit: bool) -> dict:
    r = next(r for r in h.units if r.unit.unit_id == unit.id)
    detail = _unit_readiness(r)
    detail.update(
        {
            "project_id": project.id,
            "project_name": project.name,
            "can_edit": can_edit,
            "fact_sheet": [
                {"label": "Seller", "value": project.organization.name},
                {"label": "Buyer", "value": unit.buyer_name or ""},
                {
                    "label": "Project",
                    "value": f"{project.name}, {project.locality}, {project.city}",
                },
                {"label": "K-RERA registration", "value": project.krera_registration},
                {"label": "Unit", "value": f"{unit.label}, {unit.tower}"},
                {"label": "Carpet area", "value": f"{unit.carpet_area_sqft:,} sq ft"},
                {"label": "Agreement value", "value": _indian(unit.agreement_value or ZERO)},
                {"label": "Guidance value", "value": _indian(unit.guidance_value)},
                {"label": "Booked on", "value": d(unit.booked_on) or ""},
                {"label": "Occupancy certificate", "value": project.oc_reference or "Not received"},
                {
                    "label": "e-Khata",
                    "value": f"{detail['ekhata_label']}"
                    + (f", {r.unit.khata_type}-Khata" if r.unit.khata_type else ""),
                },
                {"label": "Balance due", "value": _indian(r.unit.balance_due)},
                {"label": "Undivided share of land", "value": "To be completed by your lawyer"},
                {"label": "Schedule of the property", "value": "To be completed by your lawyer"},
            ],
        }
    )
    return detail


# Disputes and orders


def _event(e: Event) -> dict:
    return {"on": d(e.on), "kind": e.kind, "case_id": e.case_id, "text": e.text}


def _choices(labels: dict) -> list[dict]:
    return [{"value": k.value, "label": v} for k, v in labels.items()]


def case_row(cp: CasePosition) -> dict:
    c = cp.case
    return {
        "id": c.case_id,
        "forum": c.forum.value,
        "forum_label": FORUM_LABEL[c.forum],
        "case_number": c.case_number,
        "complainant": c.complainant,
        "unit": c.unit_label,
        "relief": c.relief.value,
        "relief_label": RELIEF_LABEL[c.relief],
        "status": c.status.value,
        "status_label": STATUS_LABEL[c.status],
        "open": cp.open,
        "at_stake": m(cp.at_stake),
        "ordered": bool(cp.orders),
        "next": _event(cp.next_event) if cp.next_event else None,
    }


def disputes(dp: DisputesPosition, project: Project, units: list[Unit], *, can_edit: bool) -> dict:
    pt = dp.patterns
    return {
        "can_edit": can_edit,
        "summary": {
            "open": dp.open_cases,
            "at_stake": m(dp.at_stake),
            "owed_under_orders": m(dp.owed_under_orders),
            "overdue_orders": dp.overdue_orders,
            "next": _event(dp.events[0]) if dp.events else None,
        },
        "events": [_event(e) for e in dp.events],
        "cases": [case_row(cp) for cp in dp.cases],
        "patterns": {
            "total": len(dp.cases),
            "by_relief": [
                {"label": RELIEF_LABEL[r], "count": n} for r, n in pt.by_relief.items() if n
            ],
            "by_forum": [
                {"label": FORUM_LABEL[f], "count": n} for f, n in pt.by_forum.items() if n
            ],
            "filed_after_possession_due": pt.filed_after_possession_due,
            "with_filing_date": pt.with_filing_date,
            "possession_due_on": d(project.possession_due_on),
            "units_with_cases": pt.units_with_cases,
            "booked_units": pt.booked_units,
        },
        "choices": {"forums": _choices(FORUM_LABEL), "reliefs": _choices(RELIEF_LABEL)},
        "units": [u.label for u in units],
    }


def case_detail(cp: CasePosition, row: DisputeCase, project: Project, *, can_edit: bool) -> dict:
    c = cp.case
    e = cp.estimate
    summaries = {o.id: o.summary for o in row.orders}
    detail = case_row(cp)
    detail.update(
        {
            "project_id": project.id,
            "project_name": project.name,
            "can_edit": can_edit,
            "summary": row.summary,
            "lawyer": row.lawyer,
            "claim_amount": m(row.claim_amount),
            "filed_on": d(row.filed_on),
            "notice_received_on": d(row.notice_received_on),
            "reply_due_on": d(row.reply_due_on),
            "reply_filed_on": d(row.reply_filed_on),
            "next_hearing_on": d(row.next_hearing_on),
            "appealed_on": d(row.appealed_on),
            "closed_on": d(row.closed_on),
            "possession_due_on": d(c.possession_due_on),
            "possession_on": d(c.possession_on),
            "buyer_paid": m(sum((p.amount for p in c.buyer_payments), ZERO)),
            "rate_pct": str((cp.rate * 100).quantize(Decimal("0.01"))),
            "estimate": {
                "principal": m(e.principal),
                "interest": m(e.interest),
                "other": m(e.other),
                "total": m(e.total),
                "basis": e.basis,
            },
            "orders": [
                {
                    "id": o.order.order_id,
                    "kind": o.order.kind.value,
                    "label": ORDER_LABEL[o.order.kind],
                    "summary": summaries.get(o.order.order_id),
                    "ordered_on": d(o.order.ordered_on),
                    "received_on": d(o.order.received_on),
                    "comply_by": d(o.order.comply_by),
                    "worked_out": o.order.amount is None and o.order.kind in RUNNING,
                    "due": m(o.due),
                    "paid": m(o.paid),
                    "outstanding": m(o.outstanding),
                    "overdue": o.overdue,
                    "appeal_to": o.appeal.to if o.appeal else None,
                    "appeal_by": d(o.appeal_by),
                    "appeal_deposit": m(o.appeal_deposit),
                }
                for o in cp.orders
            ],
            "ordered_total": m(cp.ordered),
            "owed": m(cp.owed),
            "paid": m(cp.paid),
            "settlement": {
                "offered": m(row.settlement_offered),
                "agreed": m(row.settlement_agreed),
                "saving": m(cp.settlement_saving),
            },
            "hearings": [
                {"held_on": d(h.held_on), "purpose": h.purpose, "outcome": h.outcome}
                for h in reversed(row.hearings)
            ],
            "payments": [
                {"paid_on": d(p.paid_on), "amount": m(p.amount), "reference": p.reference}
                for p in row.payments
            ],
            "events": [_event(ev) for ev in cp.events],
            "choices": {
                "statuses": _choices(STATUS_LABEL),
                "order_kinds": _choices(ORDER_LABEL),
            },
        }
    )
    return detail


_MONEY_RULES = {
    "escrow.min_suggested_withdrawal",
    "krera.qpr_late_fee_per_quarter",
    "it.s194ia.threshold",
}
_DAY_RULES = {
    "escrow.cycle_days",
    "escrow.certificate_window_days",
    "krera.qpr_due_days",
    "it.msme.days_with_agreement",
    "it.msme.days_without_agreement",
    "it.msme.warning_days",
    "obligations.due_soon_days",
}
_POINT_RULES = {
    "escrow.progress_gap_points",
    "money.cost_ahead_points",
    "obligations.headroom_warning_points",
}
_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _inr(amount: Decimal) -> str:
    """Indian style: 25,000 / 10 lakh / 1.5 crore."""
    if amount >= 10_000_000:
        return f"₹{(amount / 10_000_000).normalize():f} crore"
    if amount >= 100_000:
        return f"₹{(amount / 100_000).normalize():f} lakh"
    return f"₹{int(amount):,}"


def rule_display(key: str, value) -> str:
    if key in _MONEY_RULES:
        return _inr(Decimal(value))
    if key in _DAY_RULES:
        return f"{value} days"
    if key in _POINT_RULES:
        return f"{value} points"
    if key == "krera.annual_audit_months":
        return f"{value} months after the financial year"
    if key == "gst.procurement.payment_due":
        month, day = value
        return f"{day} {_MONTHS[month - 1]} of the following year"
    if key == "escrow.withdrawal_cost_basis":
        return "Cost incurred and paid" if value == "incurred_and_paid" else "Cost incurred"
    if key == "escrow.ongoing_ratio_threshold":
        return f"Ratio above {value}"
    if isinstance(value, Decimal):
        return f"{(value * 100).normalize():f}%"
    return str(value)


def rules(pack: RulesPack, on: date) -> dict:
    items = []
    for key in pack.rule_keys():
        try:
            rule = pack.get(key, on)
        except RuleNotFound:
            continue
        value = rule.value
        if isinstance(value, tuple):
            value = "-".join(str(v) for v in value)
        items.append(
            {
                "key": rule.key,
                "title": rule.title,
                "value": str(value),
                "display": rule_display(rule.key, rule.value),
                "basis": rule.basis,
                "source_quality": rule.source_quality.value,
                "confirm_against": rule.confirm_against,
                "effective_from": d(rule.effective_from),
                "note": rule.note,
            }
        )
    return {"state": pack.state, "version": pack.version, "rules": items}
