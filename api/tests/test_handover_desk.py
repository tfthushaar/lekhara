"""The possession letter, handing over to the residents' association, and cancelling a booking."""

from decimal import Decimal as D

from tests.test_records import firm, upload

SG = "sarjapur-greens"
WF = "whitefield-residences"


def booked_unit(client, project_id: str) -> dict:
    return next(
        u for u in client.get(f"/projects/{project_id}/units").json()["units"] if u["booked"]
    )


def test_possession_letter(owner) -> None:
    unit = booked_unit(owner, SG)
    letter = owner.get(f"/units/{unit['id']}/possession-letter").json()
    assert letter["subject"] == f"Offer of possession: unit {unit['label']}"
    assert "section 19(10)" in letter["paragraphs"][1]
    assert letter["take_by"] == "2026-11-27"  # two months after the certificate of 27 September
    assert [line["label"] for line in letter["lines"]][-3:] == [
        "Stamp duty (estimate)",
        "Cess on stamp duty (estimate)",
        "Registration fee (estimate)",
    ]
    assert any("section 14(3)" in p for p in letter["after"])

    refused = owner.get(f"/units/{booked_unit(owner, WF)['id']}/possession-letter")
    assert refused.status_code == 400 and "occupancy certificate" in refused.json()["detail"]


def test_association_handover(owner) -> None:
    items = owner.get(f"/projects/{SG}/handover").json()["association"]
    assert len(items) == 14 and items[0]["key"] == "association_formed"

    r = owner.put(
        f"/projects/{SG}/association/corpus", json={"done_on": "2026-10-10", "note": "Cheque"}
    )
    assert r.status_code == 200, r.text
    corpus = next(i for i in r.json()["association"] if i["key"] == "corpus")
    assert corpus == {**corpus, "done_on": "2026-10-10", "note": "Cheque"}

    future = owner.put(f"/projects/{SG}/association/keys", json={"done_on": "2026-12-01"})
    assert future.status_code == 400
    early = owner.put(f"/projects/{SG}/association/keys", json={"done_on": "2026-01-01"})
    assert "after the occupancy certificate" in early.json()["detail"]
    assert owner.put(f"/projects/{SG}/association/nothing", json={}).status_code == 404

    r = owner.put(f"/projects/{SG}/association/association_formed", json={"done_on": "2026-10-12"})
    assert r.json()["association_formed_on"] == "2026-10-12"
    r = owner.put(f"/projects/{SG}/association/association_formed", json={"done_on": ""})
    assert r.json()["association_formed_on"] is None


def test_cancelling_a_booking(app) -> None:
    client, project = firm(app)
    sheet = (
        "Unit,Tower,Carpet area (sq ft),List price,Guidance value,Buyer,Booked on,Agreement value\n"
        "A-101,Tower A,1100,90 lakh,85 lakh,Priya Sharma,01/03/2026,90 lakh\n"
    )
    client.post(f"/imports/{upload(client, project, 'units', sheet)['id']}/apply")
    unit = client.get(f"/projects/{project}/units").json()["units"][0]["id"]
    paid = client.post(
        f"/units/{unit}/receipts", json={"received_on": "2026-04-01", "amount": "9 lakh"}
    )
    assert paid.status_code == 201, paid.text

    refused = client.post(f"/units/{unit}/unsold")
    assert refused.status_code == 400 and "cancel the booking" in refused.json()["detail"]
    early = client.post(f"/units/{unit}/cancel-booking", json={"cancelled_on": "2026-02-01"})
    assert early.status_code == 400

    r = client.post(
        f"/units/{unit}/cancel-booking",
        json={
            "cancelled_on": "2026-09-01",
            "refunded": "8.5 lakh",
            "refunded_on": "2026-09-10",
            "reason": "Buyer withdrew",
        },
    )
    assert r.status_code == 200, r.text
    u = r.json()
    assert not u["booked"] and u["buyer_name"] is None and u["receipts"] == []
    earlier = u["earlier_bookings"][0]
    assert earlier["buyer_name"] == "Priya Sharma" and D(earlier["paid"]) == D("900000")
    assert D(earlier["refunded"]) == D("850000") and earlier["reason"] == "Buyer withdrew"
    assert u["history"][0]["source"] == "cancellation"

    # Sold again: the new buyer starts with nothing paid, and can be unmarked while no money moved.
    client.put(
        f"/units/{unit}",
        json={"buyer_name": "Rahul Kumar", "booked_on": "2026-10-01", "agreement_value": "95 lakh"},
    )
    assert client.get(f"/units/{unit}").json()["receipts"] == []
    assert client.post(f"/units/{unit}/unsold").status_code == 200


def test_a_refund_paid_under_an_order_cancels_the_booking(accounts) -> None:
    units = accounts.get(f"/projects/{SG}/disputes").json()["units"]
    r = accounts.post(
        f"/projects/{SG}/disputes",
        json={
            "forum": "krera",
            "case_number": "CMP/TEST/9/2026",
            "relief": "refund",
            "unit": units[40],
        },
    )
    case_id = r.json()["id"]
    c = accounts.get(f"/cases/{case_id}").json()
    assert c["booking"]["unit"] == units[40] and c["booking"]["can_cancel"] is False
    assert accounts.post(f"/cases/{case_id}/cancel-booking", json={}).status_code == 400

    order = accounts.post(
        f"/cases/{case_id}/orders", json={"ordered_on": "2026-10-17", "kind": "refund"}
    ).json()["orders"][0]
    accounts.post(
        f"/cases/{case_id}/payments",
        json={"paid_on": "2026-10-17", "amount": order["outstanding"], "reference": "RTGS 9"},
    )
    c = accounts.get(f"/cases/{case_id}").json()
    assert c["booking"]["refund_paid"] and c["booking"]["can_cancel"]

    c = accounts.post(f"/cases/{case_id}/cancel-booking", json={}).json()
    assert c["booking"]["cancelled_on"] == "2026-10-17" and not c["booking"]["can_cancel"]
    unit = c["booking"]["unit_id"]
    u = accounts.get(f"/units/{unit}").json()
    assert not u["booked"]
    assert u["earlier_bookings"][0]["reason"] == "Refund under case CMP/TEST/9/2026"
    # The case still counts what that buyer paid.
    assert D(accounts.get(f"/cases/{case_id}").json()["estimate"]["principal"]) > 0
