"""Sales: the cost sheet and commission arithmetic, and a lead taken from enquiry to booking."""

from datetime import date, timedelta
from decimal import Decimal

from conftest import TODAY

from lekhara.engines.sales import (
    CommissionIn,
    PriceListIn,
    commission,
    commission_due,
    cost_sheet,
    floor_of,
)
from lekhara.rules import KARNATAKA

HB = "hebbal-heights"
D = Decimal


def sheet(**kw):
    args = dict(
        unit_label="A-0304",
        carpet_area_sqft=1000,
        guidance_value=D("8000000"),
        prices=PriceListIn(
            base_rate=D("10000"),
            floor_rise=D("50"),
            floor_rise_from=2,
            plc={"Corner": D("150")},
            car_park=D("300000"),
            amenities=D("200000"),
            other_charges=D("150000"),
            corpus_per_sqft=D("50"),
            maintenance_per_sqft_month=D("4"),
            maintenance_months=12,
        ),
        gst_regime="residential_5pc",
        on=TODAY,
        rules=KARNATAKA,
    )
    args.update(kw)
    return cost_sheet(**args)


def test_floor_from_unit_number():
    assert floor_of("A-0304") == 3
    assert floor_of("B-1201") == 12
    assert floor_of("Villa 7") == 0


def test_cost_sheet_adds_up():
    s = sheet(plc=["Corner"])
    labels = [x.label for x in s.agreement_lines]
    assert labels == [
        "Basic price",
        "Floor rise",
        "Location: Corner",
        "Car park",
        "Amenities and clubhouse",
    ]
    # 1,00,00,000 + floors 2 and 3 at 50 (1,00,000) + corner 1,50,000 + 3,00,000 + 2,00,000
    assert s.agreement_value == D("10750000")
    assert s.gst_rate == D("0.05")
    assert s.gst == D("537500")
    handover = {x.label: x.amount for x in s.handover_lines}
    assert handover["Corpus fund"] == D("50000")
    assert handover["Maintenance in advance"] == D("48000")
    # Agreement for sale without possession: 0.1%, at most 20,000.
    assert s.agreement_stamp_duty == D("10750")
    # The buyer deducts 1% TDS at 50 lakh or more.
    assert s.tds_rate == D("0.01")
    assert s.tds == D("107500")
    assert not s.below_guidance
    assert s.total == (
        s.agreement_value
        + s.gst
        + sum(handover.values())
        + s.registration.total
        + s.agreement_stamp_duty
    )


def test_discount_below_guidance_is_flagged():
    s = sheet(guidance_value=D("12000000"), discount_per_sqft=D("1500"))
    assert s.below_guidance
    assert s.guidance_gap == D("12000000") - s.agreement_value
    assert s.guidance_tax > 0


def test_affordable_housing_gst_and_small_price_tds():
    s = sheet(
        gst_regime="affordable_1pc", carpet_area_sqft=400, prices=PriceListIn(base_rate=D("8000"))
    )
    assert s.gst_rate == D("0.01")
    assert s.agreement_value == D("3200000")
    assert s.tds == 0


def test_commission_gst_and_tds():
    c = commission(CommissionIn(D("10000000"), D("2"), True, D("0")), on=TODAY, rules=KARNATAKA)
    assert c.amount == D("200000")
    assert c.gst == D("36000")
    assert c.tds == D("4000")  # 2% since October 2024
    assert c.payable == D("232000")
    small = commission(CommissionIn(D("900000"), D("2"), False, D("0")), on=TODAY, rules=KARNATAKA)
    assert small.amount == D("18000") and small.gst == 0 and small.tds == 0
    before = commission(
        CommissionIn(D("10000000"), D("2"), False, D("0")), on=date(2024, 6, 1), rules=KARNATAKA
    )
    assert before.tds == D("10000")  # 5% before October 2024
    assert commission_due(D("1000000"), D("10000000"), D("10"))
    assert not commission_due(D("999999"), D("10000000"), D("10"))


def free_unit(owner) -> dict:
    page = owner.get(f"/projects/{HB}/sales").json()
    return next(u for u in page["inventory"]["units"] if not u["held_for"])


def test_lead_to_booking(owner):
    created = owner.post(
        f"/projects/{HB}/leads",
        json={
            "name": "Sahana Rao",
            "phone": "+91 98450 77665",
            "source": "99acres",
            "interest": "3 BHK",
        },
    )
    assert created.status_code == 201, created.text
    lead_id = created.json()["id"]
    assert created.json()["new"]

    # The same person from another portal is the same lead.
    again = owner.post(
        f"/projects/{HB}/leads",
        json={"name": "Sahana R", "phone": "9845077665", "source": "magicbricks"},
    )
    assert again.json() == {"id": lead_id, "new": False}

    page = owner.post(
        f"/leads/{lead_id}/activities", json={"kind": "call", "detail": "Wants a corner unit."}
    ).json()
    assert page["stage"] == "contacted"
    # A call with no next date comes back in three days, by itself.
    assert page["next_follow_up_on"] == (TODAY + timedelta(days=3)).isoformat()
    assert any("MagicBricks" in a["detail"] for a in page["activities"])

    page = owner.post(
        f"/leads/{lead_id}/visits",
        json={"on": (TODAY + timedelta(days=2)).isoformat(), "time": "11:00"},
    ).json()
    assert page["stage"] == "visit_planned"
    visit_id = page["visits"][0]["id"]
    page = owner.post(f"/visits/{visit_id}", json={"status": "done", "feedback": "Liked it."})
    assert page.json()["stage"] == "visited"

    unit = free_unit(owner)
    page = owner.post(f"/leads/{lead_id}/holds", json={"unit_id": unit["id"]}).json()
    assert page["stage"] == "negotiating"
    assert next(u for u in page["units"] if u["id"] == unit["id"])["held_by_this_lead"]

    # Nobody else can take a held unit.
    other = owner.post(
        f"/projects/{HB}/leads", json={"name": "Someone Else", "phone": "9000000001"}
    ).json()["id"]
    refused = owner.post(f"/leads/{other}/holds", json={"unit_id": unit["id"]})
    assert refused.status_code == 400
    assert "Sahana Rao" in refused.json()["detail"]
    refused = owner.post(
        f"/leads/{other}/book", json={"unit_id": unit["id"], "booking_amount": "200000"}
    )
    assert refused.status_code == 400

    cost = owner.get(
        f"/projects/{HB}/units/{unit['id']}/cost-sheet", params={"plc": "Corner"}
    ).json()
    assert any(x["label"] == "Location: Corner" for x in cost["agreement_lines"])
    pdf = owner.get(f"/projects/{HB}/units/{unit['id']}/cost-sheet.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    bad = owner.post(
        f"/leads/{lead_id}/book",
        json={"unit_id": unit["id"], "booking_amount": "200000", "aadhaar_last4": "1234 5678 9012"},
    )
    assert bad.status_code == 400 and "last four" in bad.json()["detail"]
    booked = owner.post(
        f"/leads/{lead_id}/book",
        json={
            "unit_id": unit["id"],
            "booking_amount": "200000",
            "buyer_pan": "abcps1234k",
            "aadhaar_last4": "9012",
            "plc": ["Corner"],
        },
    )
    assert booked.status_code == 201, booked.text
    page = owner.get(f"/leads/{lead_id}").json()
    assert page["stage"] == "booked"
    assert page["booking"]["agreement_value"] == cost["agreement_value"]

    detail = owner.get(f"/units/{unit['id']}").json()
    assert detail["buyer_name"] == "Sahana Rao"
    letter = owner.get(f"/bookings/{booked.json()['id']}/allotment.pdf")
    assert letter.status_code == 200 and letter.content.startswith(b"%PDF")

    # The unit has left the unsold list.
    page = owner.get(f"/projects/{HB}/sales").json()
    assert unit["id"] not in {u["id"] for u in page["inventory"]["units"]}
    assert any(b["unit_id"] == unit["id"] for b in page["bookings"])


def test_partner_commission(owner, cfo):
    partner = owner.post(
        "/partners",
        json={
            "name": "Test Partner",
            "krera_number": "PRM/KA/RERA/TEST",
            "commission_pct": "2",
            "krera_valid_until": (TODAY + timedelta(days=300)).isoformat(),
            "gstin": "",
            "payable_after_pct": "10",
        },
    ).json()["id"]
    lead = owner.post(
        f"/projects/{HB}/leads",
        json={"name": "Partner Buyer", "phone": "9000000002", "partner_id": partner},
    ).json()["id"]
    unit = free_unit(owner)
    owner.post(f"/leads/{lead}/book", json={"unit_id": unit["id"], "booking_amount": "100000"})
    row = next(p for p in owner.get("/partners").json()["partners"] if p["id"] == partner)
    assert row["bookings"] == 1
    c = next(x for x in owner.get("/partners").json()["waiting"] if x["partner"] == "Test Partner")
    assert c["state"] == "pending"  # a lakh is well short of 10% of the price
    assert D(c["gst"]) == 0 and D(c["tds"]) == D(c["amount"]) * D("0.02")
    refused = cfo.post(f"/commissions/{c['id']}/pay", json={})
    assert refused.status_code == 400 and "Not due" in refused.json()["detail"]
    assert owner.get("/partners").json()["waiting"]


def test_lapsed_partner_cannot_be_credited(owner):
    partner = owner.post(
        "/partners",
        json={
            "name": "Lapsed Agent",
            "commission_pct": "2",
            "krera_valid_until": (TODAY - timedelta(days=1)).isoformat(),
        },
    ).json()["id"]
    lead = owner.post(
        f"/projects/{HB}/leads",
        json={"name": "Lapsed Buyer", "phone": "9000000003", "partner_id": partner},
    ).json()["id"]
    refused = owner.post(
        f"/leads/{lead}/book", json={"unit_id": free_unit(owner)["id"], "booking_amount": "100000"}
    )
    assert refused.status_code == 400
    assert "K-RERA" in refused.json()["detail"]


def test_lost_needs_a_reason(owner):
    lead = owner.post(
        f"/projects/{HB}/leads", json={"name": "Gone Away", "phone": "9000000004"}
    ).json()["id"]
    assert owner.put(f"/leads/{lead}", json={"stage": "lost"}).status_code == 400
    page = owner.put(f"/leads/{lead}", json={"stage": "lost", "lost_reason": "Bought elsewhere"})
    assert page.json()["stage"] == "lost"
    # Coming back reopens the lead.
    again = owner.post(
        f"/projects/{HB}/leads",
        json={"name": "Gone Away", "phone": "9000000004", "source": "walk_in"},
    )
    assert again.json()["new"] is False
    assert owner.get(f"/leads/{lead}").json()["stage"] == "new"


def test_demo_sales_are_seeded(owner):
    page = owner.get(f"/projects/{HB}/sales").json()
    assert page["price_list"]["base_rate"] == "10400.00"
    assert page["conversion"]["leads"] > 10
    assert page["bookings"]
    assert page["follow_ups_late"] > 0
    assert page["call_today"]
    assert all(x["next_follow_up_on"] <= TODAY.isoformat() for x in page["call_today"])
    assert sum(1 for u in page["inventory"]["units"] if u["held_for"]) == 2
    partners = owner.get("/partners").json()["partners"]
    assert any(p["krera_lapsed"] for p in partners)
    money = owner.get("/partners").json()
    assert money["to_pay"]
    due = money["to_pay"][0]
    assert (
        owner.post(f"/commissions/{due['id']}/pay", json={"reference": "NEFT 1"}).status_code == 200
    )
    after = owner.get("/partners").json()
    assert due["id"] not in {c["id"] for c in after["to_pay"]}
    assert any(p["paid"] != "0.00" for p in after["partners"])


def test_certifiers_cannot_see_sales(architect, owner):
    assert architect.get(f"/projects/{HB}/sales").status_code in (403, 404)
    lead = owner.get(f"/projects/{HB}/sales").json()["leads"][0]["id"]
    assert architect.get(f"/leads/{lead}").status_code == 404


PORTAL = """Name,Mobile,Email,Lead Source,Requirement,Budget,Received On
Kiran Hegde,+91 98450 11111,kiran@example.com,99acres,3 BHK,1.2 crore,02/10/2026
Asha Nair,9845022222,,Facebook Ads,2 BHK,95 lakh,03/10/2026
Asha N,98450 22222,,Instagram,2 BHK,,04/10/2026
No Contact,,,Walk-in,,,05/10/2026
Bad Budget,9845033333,,Google,,lots,05/10/2026
"""


def test_import_leads_from_a_portal_export(owner):
    files = {"file": ("99acres-leads.csv", PORTAL.encode(), "text/csv")}
    started = owner.post(f"/projects/{HB}/imports/leads", files=files)
    assert started.status_code == 201, started.text
    batch = owner.get(f"/imports/{started.json()['id']}").json()
    assert batch["counts"] == {"add": 2, "update": 0, "unchanged": 1, "error": 2}
    applied = owner.post(f"/imports/{batch['id']}/apply").json()
    assert applied["result"]["added"] == 2
    leads = {x["name"]: x for x in owner.get(f"/projects/{HB}/sales?stage=new").json()["leads"]}
    assert leads["Kiran Hegde"]["source"] == "99acres"
    assert leads["Kiran Hegde"]["budget"] == "12000000.00"
    assert leads["Kiran Hegde"]["created_on"] == "2026-10-02"
    assert leads["Asha Nair"]["source"] == "facebook"

    # The same export again adds nobody.
    again = owner.post(f"/projects/{HB}/imports/leads", files=files).json()["id"]
    assert owner.get(f"/imports/{again}").json()["counts"]["add"] == 0

    # Undone, unless someone has started working the lead.
    lead = leads["Kiran Hegde"]["id"]
    owner.post(f"/leads/{lead}/activities", json={"kind": "call", "detail": "Called."})
    refused = owner.post(f"/imports/{batch['id']}/undo")
    assert refused.status_code == 400 and "Kiran Hegde" in refused.json()["detail"]


def test_a_missed_visit_brings_the_lead_back_to_call(owner):
    lead = owner.post(
        f"/projects/{HB}/leads", json={"name": "No Show", "phone": "9000000005"}
    ).json()["id"]
    on = (TODAY + timedelta(days=1)).isoformat()
    visit = owner.post(f"/leads/{lead}/visits", json={"on": on}).json()["planned_visit"]["id"]
    page = owner.post(f"/visits/{visit}", json={"status": "no_show"}).json()
    assert page["stage"] == "contacted"
    assert page["next_follow_up_on"] == (TODAY + timedelta(days=1)).isoformat()
    assert page["planned_visit"] is None


def test_units_show_their_price_on_the_lead(owner):
    lead = owner.post(
        f"/projects/{HB}/leads", json={"name": "Priced", "phone": "9000000006"}
    ).json()["id"]
    page = owner.get(f"/leads/{lead}").json()
    assert page["has_prices"]
    assert all(D(u["price"]) > 0 for u in page["units"])


def test_lost_lead_can_come_back(owner):
    lead = owner.post(
        f"/projects/{HB}/leads", json={"name": "Back Again", "phone": "9000000007"}
    ).json()["id"]
    page = owner.put(f"/leads/{lead}", json={"stage": "lost", "lost_reason": "Budget"}).json()
    assert page["next_follow_up_on"] is None
    page = owner.put(f"/leads/{lead}", json={"stage": "contacted"}).json()
    assert page["stage"] == "contacted"
    assert page["next_follow_up_on"] == TODAY.isoformat()


def test_one_box_for_any_file(owner):
    add = lambda name, data, kind="text/csv": owner.post(  # noqa: E731
        f"/projects/{HB}/files", files={"file": (name, data, kind)}
    )
    leads = add("leads.csv", b"Name,Mobile,Lead Source\nAsha,9845044444,99acres\n")
    assert leads.status_code == 201, leads.text
    assert leads.json()["to"].startswith("/imports/")
    assert owner.get(leads.json()["to"]).json()["kind"] == "leads"
    other = add("notes.txt", b"Meeting notes, nothing to import here at all.", "text/plain")
    assert other.json()["to"].startswith("/documents/")
    assert owner.get(other.json()["to"]).status_code == 200
