from fastapi.testclient import TestClient

PASSWORD = "a-long-password"
SG = "sarjapur-greens"


def firm(app) -> tuple[TestClient, str]:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={
            "accept_terms": True,
            "name": "Anil",
            "email": "anil@kaverihomes.in",
            "password": PASSWORD,
            "firm": "Kaveri",
        },
    )
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    project = client.post(
        "/projects",
        json={
            "name": "Kaveri Heights",
            "krera_registration": "PRM/K/1",
            "registered_on": "2025-04-01",
        },
    ).json()["id"]
    sheet = (
        "Unit,Carpet area (sq ft),Buyer,Booked on,Agreement value\n"
        "A-101,1100,Priya Sharma,01/04/2025,92 lakh\nA-102,1150,,,\n"
    )
    batch = client.post(
        f"/projects/{project}/imports/units", files={"file": ("u.csv", sheet.encode(), "text/csv")}
    ).json()["id"]
    client.post(f"/imports/{batch}/apply")
    return client, project


def unit_id(client, project, label) -> str:
    units = client.get(f"/projects/{project}/units").json()["units"]
    return next(u["id"] for u in units if u["label"] == label)


# Payment plans


def test_starting_a_plan_from_a_template(app) -> None:
    client, project = firm(app)
    plan = client.get(f"/projects/{project}/payment-plan").json()
    assert plan["stages"] == [] and len(plan["templates"]) == 3
    r = client.post(
        f"/projects/{project}/payment-plan/template", json={"template": "construction_linked"}
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["stages"]) == 10 and r.json()["total_pct"] == "100.00"
    collections = client.get(f"/projects/{project}/collections").json()
    assert len(collections["milestones"]) == 10


def test_a_plan_must_add_up(app) -> None:
    client, project = firm(app)
    url = f"/projects/{project}/payment-plan"
    short = [{"name": "Booking", "trigger": "booking", "share_pct": "10"}]
    assert "add up to 10%" in client.put(url, json={"stages": short}).json()["detail"]
    no_stage = [
        {"name": "Booking", "trigger": "booking", "share_pct": "50"},
        {"name": "Slab", "trigger": "progress", "share_pct": "50"},
    ]
    assert client.put(url, json={"stages": no_stage}).status_code == 400
    good = [
        {"name": "Booking", "trigger": "booking", "share_pct": "20"},
        {"name": "Roof slab", "trigger": "progress", "progress_pct": "60", "share_pct": "50"},
        {"name": "Possession", "trigger": "possession", "share_pct": "30"},
    ]
    saved = client.put(url, json={"stages": good}).json()
    assert [s["trigger"] for s in saved["stages"]] == ["booking", "progress", "possession"]
    renamed = [{**s, "id": saved["stages"][i]["id"]} for i, s in enumerate(good)]
    renamed[0]["name"] = "On booking"
    assert client.put(url, json={"stages": renamed}).json()["stages"][0]["name"] == "On booking"


def test_stages_with_demands_raised_are_protected(owner) -> None:
    url = f"/projects/{SG}/payment-plan"
    plan = owner.get(url).json()
    raised = next(s for s in plan["stages"] if s["demands"])
    stages = [
        {k: s[k] for k in ("id", "name", "trigger", "progress_pct", "share_pct")}
        for s in plan["stages"]
    ]
    without = [s for s in stages if s["id"] != raised["id"]]
    assert "cannot be removed" in owner.put(url, json={"stages": without}).json()["detail"]
    changed = [dict(s) for s in stages]
    target = next(s for s in changed if s["id"] == raised["id"])
    target["share_pct"] = str(float(target["share_pct"]) + 1)
    next(s for s in changed if s["id"] != raised["id"])["share_pct"] = "9"
    assert owner.put(url, json={"stages": changed}).status_code == 400
    renamed = [dict(s) for s in stages]
    next(s for s in renamed if s["id"] == raised["id"])["name"] = "Renamed stage"
    assert owner.put(url, json={"stages": renamed}).status_code == 200
    template = owner.post(f"{url}/template", json={"template": "twenty_eighty"})
    assert template.status_code == 400


# Buyer payments


def test_typing_a_buyer_payment(app) -> None:
    client, project = firm(app)
    sold = unit_id(client, project, "A-101")
    r = client.post(
        f"/units/{sold}/receipts",
        json={
            "received_on": "05/06/2025",
            "amount": "4.95 lakh",
            "tds_deducted": "5000",
            "reference": "UTR1",
        },
    )
    assert r.status_code == 201, r.text
    unit = client.get(f"/units/{sold}").json()
    assert [(x["amount"], x["tds"], x["source"]) for x in unit["receipts"]] == [
        ("495000.00", "5000.00", "Typed in")
    ]
    unsold = client.post(
        f"/units/{unit_id(client, project, 'A-102')}/receipts",
        json={"received_on": "05/06/2025", "amount": "1000"},
    )
    assert unsold.status_code == 400
    assert (
        client.post(f"/units/{sold}/receipts", json={"received_on": "x", "amount": "1"}).status_code
        == 400
    )
    assert client.post(f"/receipts/{unit['receipts'][0]['id']}/delete").json() == {"unit_id": sold}


RECEIPTS_CSV = """Collections register
Flat No,Date,Amount Received,TDS,UTR
A-101,05/06/2025,4.95 lakh,5000,UTR1
A-101,05/07/2025,2 lakh,,UTR2
A-102,05/07/2025,1 lakh,,UTR3
Z-999,05/07/2025,1 lakh,,UTR4
"""


def test_importing_buyer_payments(app) -> None:
    client, project = firm(app)
    files = {"file": ("receipts.csv", RECEIPTS_CSV.encode(), "text/csv")}
    batch = client.post(f"/projects/{project}/imports/receipts", files=files).json()["id"]
    preview = client.get(f"/imports/{batch}").json()
    assert preview["title"] == "Buyer payments"
    assert preview["counts"] == {"add": 2, "update": 0, "unchanged": 0, "error": 2}
    reasons = {r["row"]: r["messages"][0] for r in preview["rows"] if r["action"] == "error"}
    assert "not sold yet" in reasons[5] and "no unit Z-999" in reasons[6]
    client.post(f"/imports/{batch}/apply")
    received = client.get(f"/projects/{project}/collections").json()["summary"]["received"]
    assert received == "695000.00"

    again = client.post(f"/projects/{project}/imports/receipts", files=files).json()["id"]
    assert client.get(f"/imports/{again}").json()["counts"]["unchanged"] == 2

    exported = client.get(f"/projects/{project}/exports/receipts.csv").content.decode("utf-8-sig")
    assert exported.splitlines()[0] == "Unit,Received on,Amount received,TDS deducted,Reference"
    round_trip = client.post(
        f"/projects/{project}/imports/receipts",
        files={"file": ("back.csv", exported.encode(), "text/csv")},
    ).json()["id"]
    assert client.get(f"/imports/{round_trip}").json()["counts"]["unchanged"] == 2

    assert client.post(f"/imports/{batch}/undo").json()["status"] == "undone"
    assert float(client.get(f"/projects/{project}/collections").json()["summary"]["received"]) == 0
