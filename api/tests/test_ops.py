"""Running the firm: contractors' bills, approving payments, the site, after handover, loans, and
what each role can see and do."""

from datetime import timedelta
from decimal import Decimal

import pytest
from conftest import TODAY, signed_in

HB, SG = "hebbal-heights", "sarjapur-greens"
D = Decimal
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def sales(app):
    return signed_in(app, "sales@demo.lekhara")


@pytest.fixture
def site(app):
    return signed_in(app, "site@demo.lekhara")


def _order(owner, **extra):
    body = {
        "contractor": "Test Builders LLP",
        "amount": "1000000",
        "retention_pct": "5",
        "advance": "100000",
        "deduct_cess": "yes",
        "cost_line": "CIVIL",
        **extra,
    }
    r = owner.post(f"/projects/{HB}/contractors/orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_running_bill_holds_back_what_it_should(owner):
    order = _order(owner)
    sup = next(
        s
        for s in owner.get(f"/projects/{HB}/purchases").json()["suppliers"]
        if s["name"] == "Test Builders LLP"
    )
    assert owner.put(f"/suppliers/{sup['id']}", json={"pan": "AAKFT1234Q"}).status_code == 200
    r = owner.post(
        f"/contractors/orders/{order}/bills", json={"work_value": "200000", "gst": "36000"}
    )
    assert r.status_code == 201, r.text
    view = owner.get(f"/projects/{HB}/contractors").json()
    o = next(x for x in view["orders"] if x["id"] == order)
    b = o["bills"][0]
    assert D(b["retention"]) == D("10000")  # 5%
    assert D(b["advance_recovery"]) == D("20000")  # the advance in proportion: 1 lakh x 20%
    assert D(b["tds"]) == D("4000")  # 2% for a firm, over the single-bill threshold
    assert D(b["cess"]) == D("2000")  # 1% labour cess
    assert D(b["net_payable"]) == D("236000") - D("10000") - D("20000") - D("4000") - D("2000")
    assert D(o["advance_left"]) == D("80000")
    assert o["has_pan"]


def test_contractor_tds_by_pan(owner):
    order = _order(owner, contractor="Suresh Kumar")
    # No PAN: TDS at the higher rate.
    preview = owner.post(
        f"/contractors/orders/{order}/preview", json={"work_value": "100000"}
    ).json()
    assert D(preview["tds"]) == D("20000")
    assert preview["note"]
    # An individual's PAN: 1%.
    sup = next(
        s
        for s in owner.get(f"/projects/{HB}/purchases").json()["suppliers"]
        if s["name"] == "Suresh Kumar"
    )
    assert owner.put(f"/suppliers/{sup['id']}", json={"pan": "ABCPK1234F"}).status_code == 200
    preview = owner.post(
        f"/contractors/orders/{order}/preview", json={"work_value": "100000"}
    ).json()
    assert D(preview["tds"]) == D("1000")
    # Below both thresholds, no TDS.
    small = _order(owner, contractor="Small Works", advance="0")
    preview = owner.post(
        f"/contractors/orders/{small}/preview", json={"work_value": "20000"}
    ).json()
    assert D(preview["tds"]) == 0


def test_payments_need_a_second_person(owner, accounts, cfo):
    order = _order(owner, contractor="Approval Test Co", advance="0")
    owner.post(f"/contractors/orders/{order}/bills", json={"work_value": "50000"})
    bill = next(
        x
        for x in accounts.get("/payables").json()["waiting"]
        if x["supplier"] == "Approval Test Co"
    )
    assert accounts.post(f"/payables/{bill['id']}/approve").status_code == 403
    refused = accounts.post(f"/payables/{bill['id']}/pay", json={})
    assert refused.status_code == 400 and "approve" in refused.json()["detail"]
    assert cfo.post(f"/payables/{bill['id']}/hold", json={}).status_code == 400
    assert cfo.post(f"/payables/{bill['id']}/approve").status_code == 200
    assert (
        accounts.post(f"/payables/{bill['id']}/pay", json={"reference": "UTR1"}).status_code == 200
    )
    after = accounts.get("/payables").json()
    assert bill["id"] not in {x["id"] for x in after["waiting"] + after["approved"]}
    assert not accounts.get("/payables").json()["can_approve"]


def test_each_role_sees_its_own_part(sales, site, owner):
    me = sales.get("/auth/me").json()
    assert me["role"] == "sales" and set(me["areas"]) == {"sales", "units", "handover", "issues"}
    assert set(site.get("/auth/me").json()["areas"]) == {"site", "materials", "issues"}
    assert "escrow" in owner.get("/auth/me").json()["areas"]
    for path in (
        f"/projects/{HB}/escrow",
        f"/projects/{HB}/tax",
        "/payables",
        f"/projects/{HB}/cash",
        f"/projects/{HB}/site",
    ):
        assert sales.get(path).status_code == 403, path
    for path in (
        f"/projects/{HB}/sales",
        f"/projects/{HB}/escrow",
        "/partners",
        f"/projects/{HB}/contractors",
    ):
        assert site.get(path).status_code == 403, path
    assert sales.get(f"/projects/{HB}/sales").status_code == 200
    assert site.get(f"/projects/{HB}/site").status_code == 200
    detail = sales.get(f"/projects/{HB}").json()
    assert "money" not in detail and detail["name"]
    card = next(p for p in sales.get("/projects").json() if p["id"] == HB)
    assert "drawable_now" not in card
    # Sales works leads but doesn't set prices.
    lead = sales.post(f"/projects/{HB}/leads", json={"name": "From Sales", "phone": "9100000001"})
    assert lead.status_code == 201
    assert sales.put(f"/projects/{HB}/price-list", json={"base_rate": "1"}).status_code == 403


def test_today_follows_the_role(sales, site, owner):
    t = sales.get("/today").json()
    assert t["kind"] == "sales" and t["calls"]
    t = site.get("/today").json()
    assert t["kind"] == "site" and any(p["id"] == HB for p in t["projects"])
    t = owner.get("/today").json()
    assert t["kind"] == "team" and t["tasks"]["to_approve"] >= 1
    assert t["tasks"]["to_order"] >= 1


def test_daily_report_with_material_and_photos(site):
    before = {
        s["name"]: D(s["in_stock"]) for s in site.get(f"/projects/{HB}/materials").json()["stock"]
    }
    r = site.post(
        f"/projects/{HB}/daily-reports",
        data={
            "work_done": "Slab cast.",
            "workers": "40",
            "used_item_0": "Cement",
            "used_qty_0": "50",
        },
        files=[("photos", ("slab.png", PNG, "image/png"))],
    )
    assert r.status_code == 201, r.text
    view = site.get(f"/projects/{HB}/site").json()
    assert view["today_report"]["work_done"] == "Slab cast."
    photo = view["today_report"]["photos"][0]
    got = site.get(f"/daily-reports/{view['today_report']['id']}/photos/{photo}")
    assert got.status_code == 200 and got.content == PNG
    after = {
        s["name"]: D(s["in_stock"]) for s in site.get(f"/projects/{HB}/materials").json()["stock"]
    }
    assert after["Cement"] == before["Cement"] - 50
    # Saving the day again replaces what it said.
    site.post(
        f"/projects/{HB}/daily-reports",
        data={"work_done": "Slab cast and cured.", "used_item_0": "Cement", "used_qty_0": "60"},
    )
    again = {
        s["name"]: D(s["in_stock"]) for s in site.get(f"/projects/{HB}/materials").json()["stock"]
    }
    assert again["Cement"] == before["Cement"] - 60
    bad = site.post(
        f"/projects/{HB}/daily-reports",
        data={"work_done": "x"},
        files=[("photos", ("notes.txt", b"not a photo", "text/plain"))],
    )
    assert bad.status_code == 400


def test_material_request_to_order_to_stock(site, owner):
    r = site.post(
        f"/projects/{HB}/material-requests",
        json={"item": "Waterproofing", "unit": "litres", "quantity": "200"},
    )
    assert r.status_code == 201
    req = r.json()["id"]
    assert (
        site.post(
            f"/material-requests/{req}/quotes", json={"supplier": "X", "rate": "10"}
        ).status_code
        == 403
    )
    owner.post(
        f"/material-requests/{req}/quotes", json={"supplier": "Dr Fixit dealer", "rate": "180"}
    )
    owner.post(
        f"/material-requests/{req}/quotes", json={"supplier": "Asian Paints depot", "rate": "175"}
    )
    view = owner.get(f"/projects/{HB}/materials").json()
    row = next(x for x in view["open"] if x["id"] == req)
    cheapest = next(q for q in row["quotes"] if q["cheapest"])
    assert cheapest["supplier"] == "Asian Paints depot" and D(cheapest["total"]) == D("35000")
    ordered = owner.post(f"/material-requests/{req}/order", json={"quote_id": cheapest["id"]})
    assert ordered.status_code == 200 and ordered.json()["order"].startswith("PO-")
    assert site.post(f"/material-requests/{req}/receive", json={}).status_code == 200
    stock = {
        s["name"]: D(s["in_stock"]) for s in site.get(f"/projects/{HB}/materials").json()["stock"]
    }
    assert stock["Waterproofing"] == 200


def test_defects_have_thirty_days(site, sales):
    units = site.get(f"/projects/{SG}/issues").json()["units"]
    r = site.post(
        f"/projects/{SG}/issues",
        json={
            "unit_id": units[0]["id"],
            "kind": "defect",
            "title": "Leak",
            "reported_on": (TODAY - timedelta(days=31)).isoformat(),
        },
    )
    assert r.status_code == 201
    view = sales.get(f"/projects/{SG}/issues").json()
    row = next(x for x in view["open"] if x["id"] == r.json()["id"])
    assert row["due_on"] == (TODAY - timedelta(days=1)).isoformat() and row["late"]
    assert view["open"][0]["late"]
    assert sales.post(f"/issues/{row['id']}/done", json={"reply": "Fixed."}).status_code == 200
    assert row["id"] in {x["id"] for x in sales.get(f"/projects/{SG}/issues").json()["done"]}


def test_loans_and_the_forecast(owner, accounts):
    loan = owner.post(
        f"/projects/{SG}/loans", json={"lender": "SBI", "sanctioned": "1 crore", "rate_pct": "11"}
    ).json()["id"]
    assert (
        owner.post(
            f"/loans/{loan}/moves", json={"kind": "drawdown", "amount": "60 lakh"}
        ).status_code
        == 201
    )
    over = owner.post(f"/loans/{loan}/moves", json={"kind": "drawdown", "amount": "50 lakh"})
    assert over.status_code == 400
    owner.post(
        f"/loans/{loan}/moves",
        json={
            "kind": "repayment",
            "amount": "10 lakh",
            "on": (TODAY + timedelta(days=20)).isoformat(),
        },
    )
    view = owner.get(f"/projects/{SG}/cash").json()
    row = next(x for x in view["loans"] if x["id"] == loan)
    assert D(row["outstanding"]) == D("6000000") and D(row["can_draw"]) == D("4000000")
    assert row["next"]["kind"] == "Repaid"
    assert len(view["forecast"]) == 3
    assert any(D(m["out"]) > 0 for m in view["forecast"])
    assert view["can_edit"]
    assert (
        accounts.post(f"/projects/{SG}/loans", json={"lender": "X", "sanctioned": "1"}).status_code
        == 403
    )
