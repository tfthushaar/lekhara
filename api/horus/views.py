"""JSON views for the web app. Money is sent as decimal strings, dates as ISO strings."""

from datetime import date
from decimal import Decimal

from horus.engines.escrow import (
    ROLE_CERTIFIES,
    ROLE_LABEL,
    ROLE_ORDER,
    CertifierRole,
    LimitedBy,
    RequestStatus,
    can_submit,
)
from horus.engines.obligations import Obligation, ObligationStatus
from horus.engines.tax import MsmeStatus
from horus.models import Landowner, Unit, WithdrawalRequest
from horus.rules import RuleNotFound, RulesPack
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


def escrow(s: ProjectSnapshot, requests: list[RequestState]) -> dict:
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


def request(state: RequestState) -> dict:
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
                "basis": rule.basis,
                "source_quality": rule.source_quality.value,
                "confirm_against": rule.confirm_against,
                "effective_from": d(rule.effective_from),
                "note": rule.note,
            }
        )
    return {"state": pack.state, "version": pack.version, "rules": items}
