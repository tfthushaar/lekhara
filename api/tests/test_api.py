from decimal import Decimal as D

import pytest
from sqlalchemy import select

from lekhara.db import make_sessionmaker
from lekhara.models import AppendOnlyViolation, LedgerEntry

WF = "whitefield-residences"
HB = "hebbal-heights"
SG = "sarjapur-greens"


def keys_for(items, project_id):
    return {i["key"]: i for i in items if i["project_id"] == project_id}


def test_today_lists_what_needs_attention(owner) -> None:
    body = owner.get("/today").json()
    assert body["organization"] == "Demo Builders"
    assert body["summary"]["projects"] == 3
    drawable = sum(D(p["drawable_now"]) for p in owner.get("/projects").json())
    assert D(body["summary"]["drawable_now"]) == drawable
    assert D(body["summary"]["at_stake"]) > 0

    items = body["items"]
    assert items[0]["status"] == "overdue"
    wf, hb, sg = (keys_for(items, p) for p in (WF, HB, SG))

    assert wf["escrow:withdraw"]["status"] == "opportunity"
    assert wf["escrow:withdraw"]["amount_label"] == "Can be drawn now"
    assert wf["gst:dr"]["status"] == "at_risk"
    assert wf["gst80:2026-27"]["amount_label"] == "Still allowed unregistered"
    assert len([k for k in wf if k.startswith("s43ca:")]) == 2

    assert hb["escrow:deposit"]["status"] == "overdue"
    assert hb["qpr:2026-09-30"]["status"] == "overdue"
    assert hb["gst80:2026-27"]["status"] == "at_risk"
    assert any(k.startswith("msme:Kaveri Steel Traders") for k in hb)

    assert sg["escrow:open"]["title"] == "Withdrawal is waiting for the CA"
    assert sg["rera:delay"]["status"] == "overdue"
    assert sg["audit:2025"]["status"] == "overdue"
    assert any(k.startswith("s194ic:") for k in sg)


def test_only_exposures_count_as_at_stake(owner) -> None:
    body = owner.get("/today").json()
    exposures = sum(D(i["amount"]) for i in body["items"] if i["exposure"] and i["amount"])
    assert D(body["summary"]["at_stake"]) == exposures
    bills = [i for i in body["items"] if i["amount_label"] == "Bill"]
    assert bills and not any(i["exposure"] for i in bills)


def test_project_detail_and_alerts(owner) -> None:
    hb = owner.get(f"/projects/{HB}").json()
    assert hb["land_structure"] == "Own land"
    assert "cost_ahead_of_progress" in [a["code"] for a in hb["money"]["alerts"]]

    sg = owner.get(f"/projects/{SG}").json()
    assert "overrun_beyond_contingency" in [a["code"] for a in sg["money"]["alerts"]]
    assert sg["open_request_id"]


def test_money_lines(owner) -> None:
    body = owner.get(f"/projects/{WF}/money").json()
    assert [line["code"] for line in body["lines"]][:3] == ["LAND", "APPR", "CIVIL"]
    mep = next(line for line in body["lines"] if line["code"] == "MEP")
    assert D(mep["overrun"]) == D("12000000")


def test_escrow_explains_the_drawable_amount(owner) -> None:
    body = owner.get(f"/projects/{WF}/escrow").json()
    assert D(body["drawable_now"]) == D("64000000")
    assert body["limited_by"] == "balance"
    assert len(body["steps"]) == 7
    assert [r["status"] for r in body["requests"]] == ["released"]
    assert D(body["deposits"]["shortfall"]) == 0


def test_withdrawal_from_request_to_release(accounts, architect, engineer, ca, cfo) -> None:
    created = accounts.post(f"/projects/{WF}/withdrawals", json={})
    assert created.status_code == 201
    r = created.json()
    assert D(r["amount"]) == D("64000000")
    assert r["status"] == "awaiting_signatures"
    assert r["waiting_on"] == "the architect"
    assert [s["status"] for s in r["steps"]] == ["done", "current", "todo", "todo", "todo", "todo"]
    assert accounts.post(f"/projects/{WF}/withdrawals", json={}).status_code == 409
    assert accounts.post(f"/withdrawals/{r['id']}/submit").status_code == 400

    for certifier, role, firm in (
        (architect, "architect", "Studio Kaveri Architects"),
        (engineer, "engineer", "Sound Structures Consultants"),
        (ca, "ca", "Menon and Associates"),
    ):
        view = certifier.get(f"/withdrawals/{r['id']}").json()
        assert view["permissions"]["sign_roles"] == [role]
        response = certifier.post(f"/withdrawals/{r['id']}/certificates/{role}/sign", json={})
        assert response.status_code == 200, response.text
        signed = next(c for c in response.json()["certificates"] if c["role"] == role)
        assert signed["signer_firm"] == firm

    r = accounts.get(f"/withdrawals/{r['id']}").json()
    assert r["status"] == "ready"
    assert r["permissions"]["can_submit"]
    assert r["waiting_on"] == "submission to the bank"

    r = accounts.post(f"/withdrawals/{r['id']}/submit").json()
    assert r["status"] == "submitted"
    assert r["waiting_on"] == "the bank"
    assert not r["permissions"]["can_release"]  # accounts cannot record a release
    assert accounts.post(f"/withdrawals/{r['id']}/release", json={}).status_code == 403

    r = cfo.post(f"/withdrawals/{r['id']}/release", json={"bank_reference": "CNB-4471"}).json()
    assert r["status"] == "released"
    assert D(cfo.get(f"/projects/{WF}/escrow").json()["drawable_now"]) == 0


def test_certificate_that_disagrees_blocks_submission(owner, ca, accounts) -> None:
    request_id = owner.get(f"/projects/{SG}").json()["open_request_id"]
    r = ca.get(f"/withdrawals/{request_id}").json()
    assert r["waiting_on"] == "the CA"
    ca_cost = next(
        f for f in r["certificates"][2]["figures"] if f["field"] == "total_cost_incurred"
    )
    inflated = str(D(ca_cost["books"]) * D("1.05"))
    response = ca.put(
        f"/withdrawals/{request_id}/certificates/ca", json={"total_cost_incurred": inflated}
    )
    assert response.status_code == 200
    r = ca.post(f"/withdrawals/{request_id}/certificates/ca/sign", json={}).json()
    checks = {c["code"]: c["status"] for c in r["checks"]}
    assert checks["ca_matches_books"] == "fail"
    ca_figures = {f["field"]: f for f in r["certificates"][2]["figures"]}
    assert not ca_figures["total_cost_incurred"]["matches_books"]
    assert ca_figures["withdrawable_amount"]["matches_books"]
    assert not r["can_submit"]
    assert r["waiting_on"] == "corrected figures"
    assert accounts.post(f"/withdrawals/{request_id}/submit").status_code == 400


def test_signed_certificate_cannot_be_edited(owner, architect) -> None:
    request_id = owner.get(f"/projects/{SG}").json()["open_request_id"]
    response = architect.put(
        f"/withdrawals/{request_id}/certificates/architect", json={"completion_pct": "95"}
    )
    assert response.status_code == 409


def test_tax_view(owner) -> None:
    hb = owner.get(f"/projects/{HB}/tax").json()
    assert D(hb["procurement"]["shortfall"]) > 0
    assert [m["status"] for m in hb["msme"]].count("overdue") == 1

    wf = owner.get(f"/projects/{WF}/tax").json()
    assert wf["development_rights"]["applies"]
    assert wf["development_rights"]["capped"]
    assert D(wf["development_rights"]["saving_per_unit_sold"]) > 0
    assert len(wf["guidance"]) == 2

    sg = owner.get(f"/projects/{SG}/tax").json()
    assert len(sg["landowner_tds"]) == 1
    assert sg["delay"]["days_late"] == 64


def test_units_view(owner) -> None:
    body = owner.get(f"/projects/{WF}/units").json()
    assert body["summary"] == {
        "total": 240,
        "developer": 132,
        "landowner": 108,
        "developer_booked": 104,
        "developer_unbooked": 28,
    }
    assert body["landowners"][0]["share_type"] == "area"


def test_rules_are_published_with_their_basis(client) -> None:
    rules = {r["key"]: r for r in client.get("/rules").json()["rules"]}
    assert rules["escrow.deposit_share"]["source_quality"] == "official"
    assert rules["krera.qpr_late_fee_per_quarter"]["source_quality"] == "unverified"
    assert rules["gst.procurement.payment_due"]["value"] == "6-30"
    assert rules["gst.procurement.payment_due"]["display"] == "30 June of the following year"
    assert rules["escrow.deposit_share"]["display"] == "70%"
    assert rules["rera.sbi_mclr"]["display"] == "8.95%"
    assert rules["krera.qpr_late_fee_per_quarter"]["display"] == "₹25,000"
    assert rules["escrow.min_suggested_withdrawal"]["display"] == "₹10 lakh"
    assert rules["escrow.cycle_days"]["display"] == "90 days"


def test_unknown_project_is_404(owner) -> None:
    response = owner.get("/projects/nowhere")
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_ledger_is_append_only(engine) -> None:
    with make_sessionmaker(engine)() as session:
        entry = session.scalars(select(LedgerEntry)).first()
        entry.amount = D("1")
        with pytest.raises(AppendOnlyViolation):
            session.flush()


def test_collections_show_demands_ready_from_certified_progress(owner) -> None:
    body = owner.get(f"/projects/{WF}/collections").json()
    assert body["can_raise"]
    assert [r["name"] for r in body["ready"]] == ["On completion of the 8th floor slab"]
    assert body["ready"][0]["units"] == 104
    assert "certified 56%" in body["ready"][0]["reason"]
    assert body["summary"]["overdue_buyers"] > 0
    assert all(D(c["shortfall"]) == 0 for c in body["deposit_checks"])
    today = {i["key"]: i for i in owner.get("/today").json()["items"] if i["project_id"] == WF}
    ready_keys = [k for k in today if k.startswith("demand:")]
    assert len(ready_keys) == 1
    assert today["collections:overdue"]["amount_label"] == "Overdue from buyers"


def test_raising_demands(accounts, owner) -> None:
    before = owner.get(f"/projects/{WF}/collections").json()
    milestone_id = before["ready"][0]["milestone_id"]
    response = accounts.post(f"/projects/{WF}/milestones/{milestone_id}/raise")
    assert response.status_code == 200, response.text
    after = response.json()
    assert after["raised"] == 104
    assert after["ready"] == []
    assert D(after["summary"]["billed"]) == D(before["summary"]["billed"]) + D(
        before["ready"][0]["total"]
    )
    assert accounts.post(f"/projects/{WF}/milestones/{milestone_id}/raise").status_code == 409
    keys = [i["key"] for i in owner.get("/today").json()["items"] if i["project_id"] == WF]
    assert not [k for k in keys if k.startswith("demand:")]


def test_demand_letter(owner) -> None:
    body = owner.get(f"/projects/{WF}/collections").json()
    demand_id = body["overdue"][0]["demand_id"]
    letter = owner.get(f"/demands/{demand_id}").json()
    assert letter["from"] == "Demo Builders"
    assert letter["subject"].startswith("Demand for payment: ")
    assert [line["label"].split(" ")[0] for line in letter["lines"]] == [
        "Instalment",
        "GST",
        "Total",
    ]
    assert letter["lines"][2]["value"].startswith("₹")
    assert any("Form 26QB" in p for p in letter["paragraphs"])
    assert letter["note"].startswith("Draft prepared by Lekhara")


def test_certifiers_cannot_see_collections(ca) -> None:
    assert ca.get(f"/projects/{WF}/collections").status_code == 403
