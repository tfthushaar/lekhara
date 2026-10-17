from datetime import date
from decimal import Decimal as D

from horus.engines.handover import (
    Stage,
    UnitHandoverIn,
    handover_position,
    registration_cost,
)
from horus.rules import KARNATAKA

TODAY = date(2026, 10, 17)
SG = "sarjapur-greens"
WF = "whitefield-residences"


def unit(label="A-0101", **kw) -> UnitHandoverIn:
    base = {
        "unit_id": label,
        "label": label,
        "buyer": "Buyer",
        "agreement_value": D("10000000"),
        "guidance_value": D("9000000"),
        "ekhata_status": "final",
        "khata_type": "A",
        "final_demand_raised": True,
        "balance_due": D("0"),
    }
    base.update(kw)
    return UnitHandoverIn(**base)


def position(units, oc_on=date(2026, 9, 27)):
    return handover_position(
        units, oc_received_on=oc_on, common_areas_conveyed_on=None, on=TODAY, rules=KARNATAKA
    )


def test_first_missing_step_is_the_blocker() -> None:
    p = position(
        [
            unit("a", ekhata_status="draft"),
            unit("b", final_demand_raised=False),
            unit("c", balance_due=D("100")),
            unit("d"),
            unit("e", deed_drafted_on=TODAY, appointment_on=TODAY),
            unit(
                "f",
                deed_drafted_on=TODAY,
                appointment_on=TODAY,
                registered_on=TODAY,
                document_no="X",
                possession_on=TODAY,
            ),
        ]
    )
    blockers = {r.unit.label: r.blocker for r in p.units}
    assert blockers == {
        "a": Stage.EKHATA,
        "b": Stage.FINAL_DEMAND,
        "c": Stage.PAYMENT,
        "d": Stage.DEED,
        "e": Stage.REGISTRATION,
        "f": Stage.DONE,
    }
    assert p.registered == 1
    assert p.handed_over == 1


def test_without_an_occupancy_certificate_everything_waits_for_it() -> None:
    p = position([unit("a"), unit("b")], oc_on=None)
    assert {r.blocker for r in p.units} == {Stage.OC}
    assert p.conveyance_due_on is None


def test_conveyance_is_due_three_months_after_the_oc() -> None:
    assert position([unit()]).conveyance_due_on == date(2026, 12, 27)
    assert position([unit()], oc_on=date(2026, 8, 31)).conveyance_due_on == date(2026, 11, 30)


def test_money_waiting_counts_unregistered_units_only() -> None:
    p = position(
        [
            unit("a", balance_due=D("500")),
            unit(
                "b",
                balance_due=D("300"),
                deed_drafted_on=TODAY,
                appointment_on=TODAY,
                registered_on=TODAY,
                document_no="X",
            ),
        ]
    )
    assert p.money_waiting == D("500")


def test_registration_cost_uses_the_higher_of_price_and_guidance_value() -> None:
    c = registration_cost(D("8000000"), D("9000000"), on=TODAY, rules=KARNATAKA)
    assert c.base == D("9000000")
    assert c.stamp_duty == D("450000.00")
    assert c.cess == D("45000.00")
    assert c.registration_fee == D("180000.00")
    assert c.total == D("675000.00")


# Through the API


def test_handover_board(owner) -> None:
    h = owner.get(f"/projects/{SG}/handover").json()
    assert h["oc"]["label"] == "Received"
    assert h["conveyance_due_on"] == "2026-12-27"
    assert h["summary"]["registered"] == 20
    assert h["summary"]["handed_over"] == 16
    blocked = {s["stage"]: s["blocked"] for s in h["stages"]}
    assert blocked["ekhata"] == 65
    today = {i["key"]: i for i in owner.get("/today").json()["items"] if i["project_id"] == SG}
    assert today["handover:registration"]["amount_label"] == "Waiting on registration"
    assert today["handover:conveyance"]["due_on"] == "2026-12-27"


def test_possession_instalment_becomes_ready_after_the_oc(owner) -> None:
    ready = owner.get(f"/projects/{SG}/collections").json()["ready"]
    assert [(r["name"], r["units"]) for r in ready] == [("On possession", 45)]
    assert owner.get(f"/projects/{WF}/collections").json()["ready"][0]["name"] != "On possession"


def test_recording_a_unit_through_to_registration(owner, accounts) -> None:
    h = owner.get(f"/projects/{SG}/handover").json()
    unit_row = next(u for u in h["units"] if u["blocker"] == "deed")
    unit_id = unit_row["unit_id"]
    assert unit_row["cost"]["total"]

    r = accounts.put(f"/units/{unit_id}/handover", json={"deed_drafted_on": "2026-10-17"})
    assert r.status_code == 200, r.text
    assert r.json()["blocker"] == "appointment"
    r = accounts.put(f"/units/{unit_id}/handover", json={"appointment_on": "2026-10-20"})
    assert r.json()["blocker"] == "registration"
    bad = accounts.put(f"/units/{unit_id}/handover", json={"registered_on": "2026-10-20"})
    assert bad.status_code == 400
    r = accounts.put(
        f"/units/{unit_id}/handover",
        json={"registered_on": "2026-10-20", "document_no": "BNG-2026-1"},
    )
    assert r.json()["blocker"] == "possession"
    sheet = {row["label"]: row["value"] for row in r.json()["fact_sheet"]}
    assert sheet["Seller"] == "Demo Builders"
    assert sheet["Undivided share of land"] == "To be completed by your lawyer"


def test_handover_permissions(ca, owner) -> None:
    assert ca.get(f"/projects/{SG}/handover").status_code == 403
    unit_id = owner.get(f"/projects/{SG}/handover").json()["units"][0]["unit_id"]
    assert ca.put(f"/units/{unit_id}/handover", json={"ekhata_status": "final"}).status_code == 403
    bad = owner.put(f"/units/{unit_id}/handover", json={"ekhata_status": "maybe"})
    assert bad.status_code == 400
