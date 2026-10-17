"""JSON views for the web app. Money is sent as decimal strings, dates as ISO strings."""

import json
from datetime import date
from decimal import Decimal

from lekhara import services
from lekhara.engines.collections import CollectionsPosition
from lekhara.engines.disputes import (
    FORUM_LABEL,
    ORDER_LABEL,
    RELIEF_LABEL,
    RUNNING,
    STATUS_LABEL,
    CasePosition,
    DisputesPosition,
    Event,
)
from lekhara.engines.documents import CATEGORY_LABEL, REQUIREMENTS, expiry_status
from lekhara.engines.escrow import (
    ROLE_CERTIFIES,
    ROLE_LABEL,
    ROLE_ORDER,
    CertifierRole,
    LimitedBy,
    RequestStatus,
    can_submit,
)
from lekhara.engines.handover import (
    BLOCKER_TEXT,
    STAGE_LABEL,
    STAGES,
    HandoverPosition,
    UnitReadiness,
)
from lekhara.engines.obligations import Area, Obligation, ObligationStatus
from lekhara.engines.tax import MsmeStatus
from lekhara.models import (
    DataRoom,
    DemandRow,
    DisputeCase,
    Document,
    Landowner,
    PaymentMilestone,
    Project,
    Unit,
    Vendor,
    WithdrawalRequest,
)
from lekhara.money import ZERO
from lekhara.records import RECORD_TYPES
from lekhara.rules import KARNATAKA, RuleNotFound, RulesPack
from lekhara.services import ProjectSnapshot, RequestState


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


_REF_LINK = {Area.DISPUTES: "/cases/", Area.DOCUMENTS: "/documents/"}


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
        "link": f"{_REF_LINK[o.area]}{o.ref}" if o.ref and o.area in _REF_LINK else None,
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
                "id": o.id,
                "pan": o.pan,
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
                "id": u.id,
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
        "note": "Draft prepared by Lekhara. Your team sends it from your own address.",
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


# Document vault


def _bytes(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    return f"{max(n // 1000, 1)} KB"


def doc_row(doc: Document, *, as_of: date, notice_days: int) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "category_label": CATEGORY_LABEL.get(doc.category, doc.category),
        "filename": doc.filename,
        "content_type": doc.content_type,
        "size": _bytes(doc.size),
        "document_date": d(doc.document_date),
        "expires_on": d(doc.expires_on),
        "expiry": expiry_status(doc.expires_on, as_of=as_of, notice_days=notice_days),
        "reference": doc.reference,
        "version": doc.version,
        "pages": doc.pages,
        "text_status": doc.text_status,
        "requirement": doc.requirement,
        "link_type": doc.link_type,
        "link_id": doc.link_id,
        "uploaded_on": d(doc.uploaded_at.date()),
    }


def _category_choices() -> list[dict]:
    return [{"value": k, "label": v} for k, v in CATEGORY_LABEL.items()]


def room_row(room: DataRoom, count: int, as_of: date) -> dict:
    return {
        "id": room.id,
        "name": room.name,
        "audience": room.audience,
        "created_on": d(room.created_on),
        "expires_on": d(room.expires_on),
        "state": services.room_state(room, as_of),
        "documents": count,
        "opens": sum(1 for v in room.visits if v.action == "open"),
        "downloads": sum(1 for v in room.visits if v.action == "download"),
        "last_visit": v_at(room.visits[0]) if room.visits else None,
    }


def v_at(visit) -> str:
    return visit.at.replace(microsecond=0).isoformat()


def documents(
    pos,
    rooms: list[tuple[DataRoom, int]],
    *,
    as_of: date,
    can_edit: bool,
    can_share: bool,
) -> dict:
    missing = sum(1 for i in pos.checklist if i.status == "missing") + sum(
        len(r.missing) for r in pos.records
    )
    return {
        "can_edit": can_edit,
        "can_share": can_share,
        "notice_days": pos.notice_days,
        "summary": {
            "documents": len(pos.documents),
            "missing": missing,
            "expiring": len(pos.expiring),
            "rooms_open": sum(1 for r, _ in rooms if services.room_state(r, as_of) == "open"),
        },
        "checklist": [
            {
                "key": i.requirement.key,
                "title": i.requirement.title,
                "category": i.requirement.category,
                "why": i.requirement.why,
                "tracks_expiry": i.requirement.tracks_expiry,
                "status": i.status,
                "document_id": i.document_id,
                "expires_on": d(i.expires_on),
                "waiver_reason": i.waiver_reason,
            }
            for i in pos.checklist
        ],
        "records": [
            {
                "key": r.key,
                "title": r.title,
                "category": r.category,
                "link_type": r.link_type,
                "needed": r.needed,
                "held": r.held,
                "missing": [{"id": rid, "label": label} for rid, label in r.missing],
            }
            for r in pos.records
        ],
        "documents": [
            doc_row(doc, as_of=as_of, notice_days=pos.notice_days) for doc in pos.documents
        ],
        "categories": _category_choices(),
        "rooms": [room_row(r, n, as_of) for r, n in rooms],
    }


def document_detail(
    doc: Document,
    versions: list[Document],
    project: Project,
    *,
    record: str | None,
    rooms: list[DataRoom],
    as_of: date,
    notice_days: int,
    can_edit: bool,
) -> dict:
    detail = doc_row(doc, as_of=as_of, notice_days=notice_days)
    detail.update(
        {
            "project_id": project.id,
            "project_name": project.name,
            "can_edit": can_edit,
            "notes": doc.notes,
            "archived_on": d(doc.archived_on),
            "record": record,
            "requirement_title": REQUIREMENTS[doc.requirement].title
            if doc.requirement in REQUIREMENTS
            else None,
            "current": doc.id == versions[0].id,
            "versions": [
                {
                    "id": v.id,
                    "version": v.version,
                    "filename": v.filename,
                    "size": _bytes(v.size),
                    "uploaded_on": d(v.uploaded_at.date()),
                    "expires_on": d(v.expires_on),
                }
                for v in versions
            ],
            "rooms": [
                {"id": r.id, "name": r.name, "state": services.room_state(r, as_of)} for r in rooms
            ],
            "categories": _category_choices(),
            "requirements": [{"value": k, "label": r.title} for k, r in REQUIREMENTS.items()],
        }
    )
    return detail


def search_results(hits, query: str, *, as_of: date, notice_days: int) -> dict:
    return {
        "query": query,
        "results": [
            {
                "document": doc_row(h.document, as_of=as_of, notice_days=notice_days),
                "page": h.page_no,
                "snippets": [
                    {"before": s.before, "match": s.match, "after": s.after} for s in h.snippets
                ],
            }
            for h in hits
        ],
    }


def room_detail(
    room: DataRoom,
    docs: list[Document],
    available: list[Document],
    project: Project,
    *,
    as_of: date,
    notice_days: int,
    can_share: bool,
) -> dict:
    titles = {doc.id: doc.title for doc in [*docs, *available]}
    row = room_row(room, len(docs), as_of)
    row.update(
        {
            "project_id": project.id,
            "project_name": project.name,
            "can_share": can_share,
            "documents_in_room": [
                doc_row(doc, as_of=as_of, notice_days=notice_days) for doc in docs
            ],
            "available": [
                {"id": doc.id, "title": doc.title, "category_label": CATEGORY_LABEL[doc.category]}
                for doc in available
            ],
            "visits": [
                {
                    "at": v_at(v),
                    "action": v.action,
                    "document": titles.get(v.document_id) if v.document_id else None,
                }
                for v in room.visits[:50]
            ],
        }
    )
    return row


def shared_room(room: DataRoom, docs: list[Document], project: Project) -> dict:
    return {
        "name": room.name,
        "audience": room.audience,
        "organization": project.organization.name,
        "project": project.name,
        "krera_registration": project.krera_registration,
        "expires_on": d(room.expires_on),
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "category_label": CATEGORY_LABEL.get(doc.category, doc.category),
                "document_date": d(doc.document_date),
                "reference": doc.reference,
                "size": _bytes(doc.size),
                "content_type": doc.content_type,
            }
            for doc in docs
        ],
    }


# Registers and the Import centre


def unit_detail(
    unit: Unit,
    project: Project,
    changes: list,
    names: dict[str, str],
    *,
    can_edit: bool,
    dependents: list[str],
    receipts: list = (),
) -> dict:
    record = RECORD_TYPES["units"]
    labels = {f.key: f.label for f in record.fields}
    return {
        "id": unit.id,
        "project_id": project.id,
        "project_name": project.name,
        "label": unit.label,
        "tower": unit.tower,
        "carpet_area_sqft": unit.carpet_area_sqft,
        "owner_share": unit.owner_share,
        "owner_share_label": "Landowner" if unit.owner_share == "landowner" else "Developer",
        "list_price": m(unit.list_price),
        "guidance_value": m(unit.guidance_value),
        "buyer_name": unit.buyer_name,
        "buyer_phone": unit.buyer_phone,
        "buyer_email": unit.buyer_email,
        "booked": unit.booked,
        "booked_on": d(unit.booked_on),
        "agreement_value": m(unit.agreement_value),
        "can_edit": can_edit,
        "can_delete": can_edit and not dependents,
        "dependents": dependents,
        "receipts": receipt_rows(list(receipts)),
        "history": [
            {
                "at": c.at.replace(microsecond=0).isoformat(),
                "action": c.action,
                "source": c.source,
                "by": names.get(c.user_id, "Lekhara"),
                "changes": [
                    {"field": labels.get(k, k), "before": b, "after": a}
                    for k, (b, a) in json.loads(c.changes).items()
                ],
            }
            for c in changes
        ],
    }


def import_batch(
    batch,
    rows: list[dict] | None,
    project: Project,
    *,
    can_edit: bool,
    can_undo: bool,
) -> dict:
    record = RECORD_TYPES[batch.kind]
    headers = json.loads(batch.headers)
    body = json.loads(batch.rows)
    mapping = {int(k): v for k, v in json.loads(batch.mapping).items()}
    labels = {f.key: f.label for f in record.fields}

    def sample(i: int) -> str:
        return next((str(r[i]) for r in body[:20] if i < len(r) and r[i] != ""), "")

    counts = {"add": 0, "update": 0, "unchanged": 0, "error": 0}
    for r in rows or []:
        counts[r["action"]] += 1
    order = {"error": 0, "add": 1, "update": 2, "unchanged": 3}
    shown = sorted(
        (r for r in rows or [] if r["action"] != "unchanged"), key=lambda r: order[r["action"]]
    )
    return {
        "id": batch.id,
        "kind": batch.kind,
        "title": record.title,
        "filename": batch.filename,
        "status": batch.status,
        "project_id": project.id,
        "project_name": project.name,
        "created_at": batch.created_at.replace(microsecond=0).isoformat(),
        "applied_at": batch.applied_at.replace(microsecond=0).isoformat()
        if batch.applied_at
        else None,
        "can_edit": can_edit and batch.status == "preview",
        "can_undo": can_undo,
        "header_row": batch.header_row,
        "total_rows": len(body),
        "columns": [
            {"index": i, "header": h, "field": mapping.get(i), "sample": sample(i)}
            for i, h in enumerate(headers)
        ],
        "fields": [
            {"value": f.key, "label": f.label, "required": f.required} for f in record.fields
        ],
        "missing_required": [
            f.label for f in record.fields if f.required and f.key not in mapping.values()
        ],
        "counts": counts,
        "rows": [
            {
                "row": r["row"],
                "key": r["key"],
                "action": r["action"],
                "messages": r["messages"],
                "changes": [
                    {"field": labels.get(k, k), "before": b, "after": a}
                    for k, (b, a) in r["changes"].items()
                ],
            }
            for r in shown[:300]
        ],
        "result": json.loads(batch.result) if batch.result else None,
    }


def batch_row(batch) -> dict:
    result = json.loads(batch.result) if batch.result else None
    return {
        "id": batch.id,
        "title": RECORD_TYPES[batch.kind].title,
        "filename": batch.filename,
        "status": batch.status,
        "created_at": batch.created_at.replace(microsecond=0).isoformat(),
        "added": result["added"] if result else None,
        "updated": result["updated"] if result else None,
    }


# Tally imports


def tally_review(
    row,
    book,
    plan,
    project: Project,
    units: list,
    *,
    can_edit: bool,
    can_undo: bool,
    lines: list = (),
    owners: list = (),
) -> dict:
    from lekhara.tally.service import SOURCE_LABEL

    kinds: dict[str, int] = {}
    for ledger in book.ledgers.values():
        kinds[ledger.kind] = kinds.get(ledger.kind, 0) + 1
    new_bills = [b for b in plan.bills if not b.exists]
    new_receipts = [r for r in plan.receipts if not r.exists and r.unit_id]
    return {
        "id": row.id,
        "filename": row.filename,
        "status": row.status,
        "project_id": project.id,
        "project_name": project.name,
        "created_at": row.created_at.replace(microsecond=0).isoformat(),
        "applied_at": row.applied_at.replace(microsecond=0).isoformat() if row.applied_at else None,
        "can_edit": can_edit and row.status == "review",
        "can_undo": can_undo,
        "source": book.source,
        "source_label": SOURCE_LABEL.get(book.source, book.source),
        "company": book.company or None,
        "period": {"from": d(plan.period[0]), "to": d(plan.period[1])},
        "found": {
            "masters": book.has_masters,
            "totals_only": book.summary_only,
            "groups": len(book.groups),
            "ledgers": len(book.ledgers),
            "ledger_kinds": kinds,
            "cost_centres": len(book.cost_centres) or len(plan.cost_centres),
            "stock_items": book.stock_items,
            "vouchers": len(book.vouchers),
            "voucher_kinds": plan.counts,
        },
        "counts": {
            "vendors_new": sum(1 for v in plan.vendors if not v.existing_id),
            "vendors_updated": sum(1 for v in plan.vendors if v.existing_id and v.changes),
            "bills_new": len(new_bills),
            "bills_known": sum(1 for b in plan.bills if b.exists),
            "bills_paid": sum(1 for b in new_bills if b.paid_on),
            "receipts_new": len(new_receipts),
            "receipts_known": sum(1 for r in plan.receipts if r.exists),
            "receipts_waiting": sum(1 for r in plan.receipts if not r.exists and not r.unit_id),
        },
        "alerts": [
            {
                "level": a.level,
                "code": a.code,
                "title": a.title,
                "detail": a.detail,
                "fix": a.fix,
                "items": a.items,
            }
            for a in sorted(
                plan.alerts, key=lambda a: ("blocking", "missing", "info").index(a.level)
            )
        ],
        "buyers": [
            {
                "ledger": b.ledger,
                "total": m(b.total),
                "count": b.count,
                "suggestions": b.suggestions,
                "ignored": b.ignored,
            }
            for b in plan.buyers
        ],
        "units": [{"id": u.id, "label": u.label, "buyer": u.buyer_name} for u in units],
        "cost_centres": plan.cost_centres,
        "cost_centre": json.loads(row.options or "{}").get("cost_centre"),
        "vendors": [
            {
                "name": v.name,
                "gstin": v.gstin,
                "registered": v.registered,
                "msme": v.msme_category,
                "existing": v.existing_id is not None,
                "changes": sorted(v.changes),
                "bills": v.bills,
            }
            for v in plan.vendors[:100]
        ],
        "bills": [
            {
                "vendor": b.vendor_name,
                "bill_no": b.bill_no,
                "bill_date": d(b.bill_date),
                "taxable_value": m(b.taxable_value),
                "gst": m(b.gst),
                "paid_on": d(b.paid_on),
                "is_cement": b.is_cement,
            }
            for b in new_bills[:100]
        ],
        "receipts": [
            {
                "ledger": r.ledger,
                "unit": r.unit_label,
                "amount": m(r.amount),
                "tds": m(r.tds),
                "received_on": d(r.received_on),
            }
            for r in new_receipts[:100]
        ],
        "result": json.loads(row.result) if row.result else None,
        "money": {
            **tally_money(plan, list(lines), list(owners)),
            "party_ledgers": sorted(
                (x.name for x in book.ledgers.values() if x.kind == "creditor"), key=str.casefold
            ),
        },
    }


def tally_row(row) -> dict:
    result = json.loads(row.result) if row.result else None
    return {
        "id": row.id,
        "filename": row.filename,
        "status": row.status,
        "company": row.company,
        "created_at": row.created_at.replace(microsecond=0).isoformat(),
        "bills": len(result["bills_added"]) if result else None,
        "receipts": len(result["receipts_added"]) if result else None,
    }


# Cost lines and the Tally ledger map


def cost_lines(lines: list, s, *, can_edit: bool) -> dict:
    from lekhara.registers import CATEGORY_LABEL

    spend = {row["id"]: row for row in money_lines(s)} if s else {}
    return {
        "can_edit": can_edit,
        "categories": [{"value": k, "label": v} for k, v in CATEGORY_LABEL.items()],
        "lines": [
            {
                "id": line.id,
                "code": line.code,
                "name": line.name,
                "category": line.category,
                "category_label": CATEGORY_LABEL.get(line.category, line.category),
                "rera_head": line.rera_head,
                "original_budget": m(line.original_budget),
                "revised_budget": m(line.revised_budget),
                "incurred": spend.get(line.id, {}).get("incurred"),
                "paid": spend.get(line.id, {}).get("paid"),
            }
            for line in lines
        ],
    }


def tally_money(plan, lines: list, owners: list) -> dict:
    cash = plan.money
    new_cost = [e for e in cash.cost_entries if not e.exists]
    return {
        "counts": {
            "incurred": m(sum((e.amount for e in new_cost if e.kind == "incurred"), ZERO)),
            "paid": m(sum((e.amount for e in new_cost if e.kind == "paid"), ZERO)),
            "cost_entries": len(new_cost),
            "escrow": sum(1 for e in cash.escrow if not e.exists),
            "deposits": m(
                sum((e.amount for e in cash.escrow if not e.exists and e.kind == "deposit"), ZERO)
            ),
            "withdrawals": m(
                sum(
                    (e.amount for e in cash.escrow if not e.exists and e.kind == "withdrawal"), ZERO
                )
            ),
            "landowner_payments": sum(1 for p in cash.landowner_payments if not p.exists),
            "unmapped_spend": m(cash.unmapped_spend),
        },
        "cost_ledgers": [
            {"ledger": c.ledger, "target": c.target, "source": c.source, "total": m(c.total)}
            for c in cash.cost_ledgers
        ],
        "bank_ledgers": [
            {"ledger": b.ledger, "rera": bool(b.target), "source": b.source, "total": m(b.total)}
            for b in cash.bank_ledgers
        ],
        "landowner_ledgers": [
            {"ledger": o.ledger, "target": o.target, "source": o.source, "total": m(o.total)}
            for o in cash.landowner_ledgers
        ],
        "cost_lines": [{"id": c.id, "code": c.code, "name": c.name} for c in lines],
        "landowners": [{"id": o.id, "name": o.name} for o in owners],
    }


# Payment plans and buyer payments

TRIGGER_LABEL = {
    "booking": "On booking",
    "agreement": "On the agreement for sale",
    "progress": "At certified progress",
    "possession": "On possession",
}


def payment_plan(stages: list, raised: dict[str, int], *, can_edit: bool) -> dict:
    from lekhara.registers import PLAN_TEMPLATES

    return {
        "can_edit": can_edit,
        "stages": [
            {
                "id": s.id,
                "name": s.name,
                "trigger": s.trigger,
                "trigger_label": TRIGGER_LABEL.get(s.trigger, s.trigger),
                "progress_pct": m(s.progress_pct),
                "share_pct": m(s.share_pct),
                "demands": raised.get(s.id, 0),
            }
            for s in stages
        ],
        "total_pct": m(sum((s.share_pct for s in stages), ZERO)),
        "any_raised": any(raised.values()),
        "templates": [
            {
                "key": key,
                "label": label,
                "stages": [
                    {
                        "name": n,
                        "trigger_label": TRIGGER_LABEL[t],
                        "progress_pct": p,
                        "share_pct": sh,
                    }
                    for n, t, p, sh in stages_
                ],
            }
            for key, (label, stages_) in PLAN_TEMPLATES.items()
        ],
        "triggers": [{"value": k, "label": v} for k, v in TRIGGER_LABEL.items()],
    }


def receipt_rows(receipts: list) -> list[dict]:
    def source(r) -> str:
        ref = r.source_ref or ""
        return (
            "Tally"
            if ref.startswith("tally:")
            else "Imported"
            if ref.startswith("import:")
            else "Typed in"
        )

    return [
        {
            "id": r.id,
            "received_on": d(r.received_on),
            "amount": m(r.amount),
            "tds": m(r.tds_deducted),
            "reference": r.reference,
            "source": source(r),
            "can_delete": not (r.source_ref or "").startswith("tally:"),
        }
        for r in receipts
    ]


# Set-up


def readiness(items: list, project: Project, *, can_edit: bool) -> dict:
    from lekhara.readiness import summary

    return {
        "project_id": project.id,
        "can_edit": can_edit,
        "summary": summary(items),
        "items": [
            {
                "key": i.key,
                "title": i.title,
                "status": i.status,
                "detail": i.detail,
                "unlocks": i.unlocks,
                "action": i.action,
                "href": i.href,
            }
            for i in items
        ],
        "details": {
            "name": project.name,
            "krera_registration": project.krera_registration,
            "registered_on": d(project.registered_on),
            "possession_due_on": d(project.possession_due_on),
            "locality": project.locality,
            "city": project.city,
            "spv_name": project.spv_name,
            "land_structure": project.land_structure,
            "gst_regime": project.gst_regime,
            "escrow_bank": project.escrow_bank,
            "statutory_auditor_firm": project.statutory_auditor_firm,
            "development_rights_value": m(project.development_rights_value),
            "cess_paid": m(project.cess_paid),
            "oc_status": project.oc_status,
            "oc_received_on": d(project.oc_received_on),
            "oc_reference": project.oc_reference,
            "association_formed_on": d(project.association_formed_on),
            "common_areas_conveyed_on": d(project.common_areas_conveyed_on),
        },
    }


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


# Bank statements

BANK_OUTCOME = {
    "buyer_payment": "Buyer payment",
    "deposit": "Deposit",
    "withdrawal": "Withdrawal",
    "interest": "Interest",
    "charges": "Bank charges",
    "not_buyer": "Not a buyer",
    "returned": "Came back",
    "needs_unit": "Choose the unit",
    "exists": "Already in",
    "left_out": "Left out",
    "waiting": "Waiting",
}


def _masked(number: str | None) -> str | None:
    if not number:
        return None
    digits = "".join(c for c in number if c.isdigit())
    return f"ending {digits[-4:]}" if len(digits) >= 4 else number


def bank_statement_row(row) -> dict:
    return {
        "id": row.id,
        "filename": row.filename,
        "bank": row.bank,
        "account": _masked(row.account_number),
        "period_from": d(row.period_from),
        "period_to": d(row.period_to),
        "lines": row.lines,
        "status": row.status,
        "created_at": row.created_at.replace(microsecond=0).isoformat(),
    }


def bank_review(
    row, statement, plan, project: Project, units: list, *, can_edit: bool, can_undo: bool
) -> dict:
    from lekhara.bank.service import options

    opts = options(row)
    labels = {u.id: u.label for u in units}
    return {
        **bank_statement_row(row),
        "project_id": project.id,
        "project_name": project.name,
        "applied_at": row.applied_at.replace(microsecond=0).isoformat() if row.applied_at else None,
        "role": opts.get("role"),
        "buyers_pay_here": bool(opts.get("buyers_pay_here")),
        "can_edit": can_edit and row.status == "review",
        "can_apply": can_edit and row.status == "review" and bool(opts.get("role")),
        "can_undo": can_edit and can_undo,
        "opening": m(statement.opening),
        "closing": m(statement.closing),
        "reversed_order": statement.reversed_order,
        "columns": statement.columns,
        "counts": plan.counts,
        "totals": {k: m(v) for k, v in plan.totals.items()},
        "alerts": [
            {
                "level": a.level,
                "code": a.code,
                "title": a.title,
                "detail": a.detail,
                "fix": a.fix,
                "items": a.items,
            }
            for a in plan.alerts
        ],
        "lines": [
            {
                "key": p.key,
                "on": d(p.on),
                "narration": p.narration,
                "reference": p.reference,
                "channel": p.channel,
                "payer": p.payer,
                "debit": m(p.debit) if p.debit else None,
                "credit": m(p.credit) if p.credit else None,
                "balance": m(p.balance),
                "outcome": p.outcome,
                "outcome_label": BANK_OUTCOME.get(p.outcome, p.outcome),
                "note": p.note,
                "unit_id": p.unit_id,
                "unit_label": labels.get(p.unit_id),
                "how": p.how,
                "candidates": [{"id": c, "label": labels.get(c, c)} for c in p.candidates],
                "loan": p.loan,
                "buyer_line": p.buyer_line,
                "choice": opts.get("lines", {}).get(p.key),
            }
            for p in plan.lines
        ],
        "units": [{"id": u.id, "label": u.label, "buyer": u.buyer} for u in units],
    }


# Suppliers, bills and commitments

MSME_LABEL = {"none": "Not MSME", "micro": "Micro", "small": "Small", "medium": "Medium"}


def vendor_row(v, *, bills: int = 0, unpaid: int = 0) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "gstin": v.gstin,
        "registered": v.registered,
        "pan": v.pan,
        "state": v.state,
        "msme_category": v.msme_category,
        "msme_label": MSME_LABEL.get(v.msme_category, v.msme_category),
        "udyam_number": v.udyam_number,
        "written_agreement": v.written_agreement,
        "bills": bills,
        "unpaid": unpaid,
    }


def bill_row(b, lines: dict) -> dict:
    line = lines.get(b.cost_line_id)
    return {
        "id": b.id,
        "supplier": {
            "id": b.vendor.id,
            "name": b.vendor.name,
            "registered": b.vendor.registered,
            "msme": b.vendor.msme_category in ("micro", "small"),
        },
        "bill_no": b.bill_no,
        "bill_date": d(b.bill_date),
        "accepted_on": d(b.accepted_on),
        "taxable_value": m(b.taxable_value),
        "gst_amount": m(b.gst_amount),
        "paid_on": d(b.paid_on),
        "cost_line": {"id": line.id, "code": line.code, "name": line.name} if line else None,
        "is_cement": b.is_cement,
        "rcm_paid": b.rcm_paid,
        "excluded": b.excluded,
        "source": "Tally" if (b.source_ref or "").startswith("tally:") else "Lekhara",
    }


def _lines(session, project) -> dict:
    from lekhara.registers import cost_lines

    return {line.id: line for line in cost_lines(session, project)}


def purchases_view(session, project: Project, *, can_edit: bool) -> dict:
    from lekhara import purchases

    lines = _lines(session, project)
    bills = purchases.bills_of(session, project)
    counts: dict[str, list[int]] = {}
    for b in bills:
        c = counts.setdefault(b.vendor_id, [0, 0])
        c[0] += 1
        c[1] += 0 if b.paid_on else 1
    vendors = purchases.vendors_of(session, project.organization_id)
    return {
        "project_id": project.id,
        "can_edit": can_edit,
        "bills": [bill_row(b, lines) for b in bills],
        "suppliers": [
            vendor_row(v, bills=counts.get(v.id, [0, 0])[0], unpaid=counts.get(v.id, [0, 0])[1])
            for v in vendors
        ],
        "cost_lines": [{"id": x.id, "code": x.code, "name": x.name} for x in lines.values()],
        "totals": {
            "taxable": m(sum((b.taxable_value for b in bills), Decimal("0"))),
            "gst": m(sum((b.gst_amount or Decimal("0") for b in bills), Decimal("0"))),
            "unpaid": sum(1 for b in bills if not b.paid_on),
        },
    }


def history_rows(changes: list, names: dict[str, str], labels: dict[str, str]) -> list[dict]:
    return [
        {
            "at": c.at.replace(microsecond=0).isoformat(),
            "action": c.action,
            "source": c.source,
            "by": names.get(c.user_id, "Lekhara"),
            "changes": [
                {"field": labels.get(k, k), "before": b, "after": a}
                for k, (b, a) in json.loads(c.changes).items()
            ],
        }
        for c in changes
    ]


def bill_detail(session, bill, project: Project, changes, names, *, can_edit: bool) -> dict:
    from lekhara.records import BILLS

    lines = _lines(session, project)
    labels = {f.key: f.label for f in BILLS.fields}
    return {
        **bill_row(bill, lines),
        "project_id": project.id,
        "project_name": project.name,
        "can_edit": can_edit,
        "can_delete": can_edit and not (bill.source_ref or "").startswith("tally:"),
        "cost_lines": [{"id": x.id, "code": x.code, "name": x.name} for x in lines.values()],
        "gst_is_cost": project.gst_regime != "commercial_12pc",
        "history": history_rows(changes, names, labels),
    }


def vendor_detail(session, vendor, changes, names, *, can_edit: bool, projects: dict) -> dict:
    from lekhara import purchases
    from lekhara.records import SUPPLIERS

    bills = purchases.vendor_bills(session, vendor)
    labels = {f.key: f.label for f in SUPPLIERS.fields}
    lines: dict = {}
    return {
        **vendor_row(vendor, bills=len(bills), unpaid=sum(1 for b in bills if not b.paid_on)),
        "can_edit": can_edit,
        "can_delete": can_edit and not bills,
        "bill_list": [
            {**bill_row(b, lines), "project": projects.get(b.project_id)}
            for b in reversed(bills)
            if b.project_id in projects
        ],
        "history": history_rows(changes, names, labels),
    }


def commitments_view(session, project: Project, *, can_edit: bool) -> dict:
    from lekhara import purchases

    lines = _lines(session, project)
    rows = purchases.commitments_of(session, project)
    return {
        "project_id": project.id,
        "can_edit": can_edit,
        "cost_lines": [{"id": x.id, "code": x.code, "name": x.name} for x in lines.values()],
        "commitments": [
            {
                "id": c.id,
                "reference": c.reference,
                "description": c.description,
                "amount": m(c.amount),
                "committed_on": d(c.committed_on),
                "cost_line": {
                    "id": c.cost_line_id,
                    "code": lines[c.cost_line_id].code if c.cost_line_id in lines else None,
                    "name": lines[c.cost_line_id].name if c.cost_line_id in lines else None,
                },
                "supplier": session.get(Vendor, c.vendor_id).name if c.vendor_id else None,
            }
            for c in rows
        ],
        "total": m(sum((c.amount for c in rows), Decimal("0"))),
    }


# The forwarding address

INBOUND_LINK = {
    "tally_import": "/tally/{}",
    "bank_statement": "/bank/{}",
    "import_batch": "/imports/{}",
    "document": "/documents/{}",
}


def inbound_view(
    session, project: Project, address: str, *, can_edit: bool, domain_ready: bool
) -> dict:
    from lekhara import inbound

    return {
        "project_id": project.id,
        "address": address,
        "ready": domain_ready,
        "can_edit": can_edit,
        "messages": [
            {
                "id": msg.id,
                "from_address": msg.from_address,
                "from_name": msg.from_name,
                "subject": msg.subject,
                "received_at": msg.received_at.replace(microsecond=0).isoformat(),
                "trusted": msg.trusted,
                "status": msg.status,
                "note": msg.note,
                "items": [
                    {
                        "id": i.id,
                        "filename": i.filename,
                        "size": i.size,
                        "kind": i.kind,
                        "status": i.status,
                        "note": i.note,
                        "link": INBOUND_LINK[i.result_type].format(i.result_id)
                        if i.result_type in INBOUND_LINK and i.result_id
                        else None,
                        "can_retry": can_edit
                        and msg.trusted
                        and i.status in ("failed", "review")
                        and not i.result_id,
                    }
                    for i in inbound.items_of(session, msg)
                ],
            }
            for msg in inbound.messages_of(session, project)
        ],
    }
