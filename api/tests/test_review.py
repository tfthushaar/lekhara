from email.message import EmailMessage

import bank_samples as samples
from fastapi.testclient import TestClient
from tally_samples import full_xml_utf16

from lekhara import inbound
from lekhara.db import make_sessionmaker
from lekhara.models import Project

PASSWORD = "a-long-password"


def firm(app) -> tuple[TestClient, str, dict]:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={
            "name": "Anil",
            "email": "anil@kaverihomes.in",
            "password": PASSWORD,
            "firm": "Kaveri Homes LLP",
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
    units = {}
    for label, buyer in (
        ("A-101", "Priya Sharma"),
        ("A-102", "Rahul Kumar"),
        ("B-201", "Anand Rao"),
        ("B-202", "Meera Iyer"),
    ):
        units[label] = client.post(
            f"/projects/{project}/units",
            json={
                "label": label,
                "carpet_area_sqft": "1100",
                "buyer_name": buyer,
                "booked_on": "01/03/2026",
                "agreement_value": "90 lakh",
            },
        ).json()["id"]
    return client, project, units


def titles(client) -> list[str]:
    return [i["title"] for i in client.get("/review").json()["items"]]


def test_the_queue_follows_what_waits(app) -> None:
    client, project, units = firm(app)
    assert client.get("/review").json() == {"count": 0, "items": []}

    sid = client.post(
        f"/projects/{project}/bank-statements",
        files={"file": ("s.xls", samples.hdfc_xls(), "application/octet-stream")},
    ).json()["id"]
    assert titles(client) == ["Which account is this statement for?"]
    view = client.put(f"/bank-statements/{sid}/options", json={"role": "collections"}).json()
    assert titles(client) == ["1 payment to place"]
    assert client.get("/today").json()["to_review"] == 1

    # Brought in with the payment still waiting; it stays in the queue until placed.
    client.post(f"/bank-statements/{sid}/apply")
    assert titles(client) == ["1 payment to place"]
    suresh = next(line for line in view["lines"] if line["payer"] == "SURESH TRADERS")
    placed = client.put(
        f"/bank-statements/{sid}/options", json={"lines": {suresh["key"]: units["B-201"]}}
    ).json()
    assert placed["can_apply_rest"] and placed["can_place"]
    assert titles(client) == []
    again = client.post(f"/bank-statements/{sid}/apply").json()
    assert not again["can_apply_rest"]
    payments = client.get(f"/units/{units['B-201']}").json()["receipts"]
    assert sorted(p["amount"] for p in payments) == ["100000.00", "75000.00"]
    assert client.post(f"/bank-statements/{sid}/apply").status_code == 400
    assert client.put(f"/bank-statements/{sid}/options", json={"role": "rera"}).status_code == 400

    sheet = "Unit,Carpet area (sq ft)\nC-301,1200\n"
    client.post(
        f"/projects/{project}/imports/units",
        files={"file": ("units.csv", sheet.encode(), "text/csv")},
    )
    client.post(
        f"/projects/{project}/tally",
        files={"file": ("export.xml", full_xml_utf16(), "application/xml")},
    )
    found = client.get("/review").json()["items"]
    assert {i["kind"] for i in found} == {"sheet", "tally"}
    assert all(i["project_name"] == "Kaveri Heights" for i in found)
    assert any(i["href"].startswith("/imports/") for i in found)


def test_mail_waiting_to_be_allowed(app, engine) -> None:
    client, project, _ = firm(app)
    address = client.get(f"/projects/{project}/inbound").json()["address"]
    msg = EmailMessage()
    msg["From"] = "someone@elsewhere.in"
    msg["To"] = address
    msg["Subject"] = "Quotation"
    msg.set_content("Attached")
    msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="q.pdf")
    with make_sessionmaker(engine)() as session:
        inbound.receive(session, app.state.storage, app.state.settings, msg.as_bytes())
        assert session.get(Project, project).mail_token
    [item] = client.get("/review").json()["items"]
    assert item["kind"] == "mail" and "someone@elsewhere.in" in item["detail"]


def test_certifiers_and_the_sample_have_no_queue(app, architect, owner) -> None:
    assert architect.get("/review").json()["count"] == 0
    assert owner.get("/review").json()["count"] == 0
