"""Landowner payments, approvals and K-RERA filings, typed in and imported; and records edited
as a table."""

from fastapi.testclient import TestClient

PASSWORD = "a-long-password"


def firm(app) -> tuple[TestClient, str]:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={
            "accept_terms": True,
            "name": "Anil",
            "email": "anil@kaverihomes.in",
            "password": PASSWORD,
            "firm": "Kaveri Homes",
        },
    )
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    project = client.post(
        "/projects",
        json={
            "name": "Kaveri Heights",
            "krera_registration": "PRM/K/1",
            "registered_on": "2025-04-01",
            "land_structure": "jda_revenue_share",
        },
    ).json()["id"]
    return client, project


def upload(client, project, kind: str, text: str):
    r = client.post(
        f"/projects/{project}/imports/{kind}",
        files={"file": (f"{kind}.csv", text.encode(), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return client.get(f"/imports/{r.json()['id']}").json()


def titles(client, project) -> list[str]:
    return [o["title"] for o in client.get(f"/projects/{project}").json()["obligations"]]


def keys(client, project) -> list[str]:
    return [o["key"] for o in client.get(f"/projects/{project}").json()["obligations"]]


def test_landowner_payments(app) -> None:
    client, project = firm(app)
    owner = client.post(
        f"/projects/{project}/landowners",
        json={
            "name": "R. Venkatesh",
            "share_type": "revenue",
            "share_pct": "30",
            "pan": "ABCPV1234K",
        },
    ).json()["id"]

    r = client.post(
        f"/landowners/{owner}/payments",
        json={"paid_on": "2026-06-05", "amount": "30 lakh", "tds_deducted": "300000"},
    )
    assert r.status_code == 201, r.text
    lo = r.json()
    assert lo["totals"]["consideration"] == "3000000.00" and lo["totals"]["tds_short"] == "0"
    assert lo["history"][0]["subject"] == "Payment"

    # Short TDS is flagged per payment; a refundable deposit carries none.
    lo = client.post(
        f"/landowners/{owner}/payments",
        json={"paid_on": "2026-07-05", "amount": "1000000", "reference": "UTR-77"},
    ).json()
    short = next(p for p in lo["payments"] if p["reference"] == "UTR-77")
    assert short["tds_short"] == "100000.00" and short["source"] == "typed"
    lo = client.post(
        f"/landowners/{owner}/payments",
        json={"paid_on": "2026-07-06", "amount": "500000", "deposit": "yes"},
    ).json()
    assert lo["totals"]["deposits"] == "500000.00" and lo["totals"]["tds_short"] == "100000.00"

    bad = client.post(
        f"/landowners/{owner}/payments", json={"paid_on": "2027-01-01", "amount": "1"}
    )
    assert bad.status_code == 400 and "future" in bad.json()["detail"]

    lo = client.put(f"/landowner-payments/{short['id']}", json={"tds_deducted": "100000"}).json()
    assert lo["totals"]["tds_short"] == "0"
    lo = client.post(f"/landowner-payments/{short['id']}/delete").json()
    assert len(lo["payments"]) == 2
    actions = [(h["subject"], h["action"]) for h in lo["history"]]
    assert actions[:2] == [("Payment", "deleted"), ("Payment", "updated")]

    # The same rows imported twice add nothing the second time; an unknown landowner is refused.
    sheet = (
        "Landowner,Paid on,Amount,TDS deducted,Refundable deposit,Reference\n"
        "abcpv1234k,05/08/2026,10 lakh,100000,No,UTR-81\n"
        "Someone Else,05/08/2026,10 lakh,100000,No,UTR-82\n"
    )
    batch = upload(client, project, "landowner_payments", sheet)
    assert batch["counts"] == {"add": 1, "update": 0, "unchanged": 0, "error": 1}
    assert "There is no landowner Someone Else" in next(
        r["messages"][0] for r in batch["rows"] if r["action"] == "error"
    )
    client.post(f"/imports/{batch['id']}/apply")
    again = upload(client, project, "landowner_payments", sheet)
    assert again["counts"]["unchanged"] == 1 and again["counts"]["add"] == 0
    assert client.post(f"/imports/{batch['id']}/undo").status_code == 200
    assert len(client.get(f"/landowners/{owner}").json()["payments"]) == 2

    exported = client.get(f"/projects/{project}/exports/landowner_payments.csv").text
    assert "R. Venkatesh" in exported and "Refundable deposit" in exported


def test_approvals(app) -> None:
    client, project = firm(app)
    view = client.post(f"/projects/{project}/approvals/standard").json()
    assert len(view["approvals"]) == 12 and view["standard_missing"] == 0
    assert view["counts"]["to_apply"] == 12

    fire = next(a for a in view["approvals"] if a["name"] == "Fire NOC (provisional)")
    bad = client.put(
        f"/approvals/{fire['id']}", json={"applied_on": "2026-03-01", "granted_on": "2026-02-01"}
    )
    assert bad.status_code == 400 and "before it was applied" in bad.json()["detail"]
    view = client.put(
        f"/approvals/{fire['id']}",
        json={"applied_on": "2025-01-10", "granted_on": "2025-03-22", "valid_until": "2026-11-30"},
    ).json()
    fire = next(a for a in view["approvals"] if a["name"] == "Fire NOC (provisional)")
    assert fire["status"] == "lapsing" and fire["days_left"] == 44
    assert view["approvals"][0]["id"] == fire["id"]
    assert "Renew Fire NOC (provisional)" in titles(client, project)

    # Clearing the validity takes it off Today.
    view = client.put(f"/approvals/{fire['id']}", json={"valid_until": ""}).json()
    assert next(a for a in view["approvals"] if a["id"] == fire["id"])["status"] == "granted"
    assert "Renew Fire NOC (provisional)" not in titles(client, project)

    # A sheet updates approvals by name and adds new ones.
    sheet = (
        "Approval,Authority,Number,Applied on,Granted on,Valid until\n"
        "Consent to operate,KSPCB,CFO/1,01/02/2026,01/04/2026,01/10/2026\n"
        "Lift licence,Electrical Inspectorate,,01/09/2026,,\n"
    )
    batch = upload(client, project, "approvals", sheet)
    assert batch["counts"] == {"add": 1, "update": 1, "unchanged": 0, "error": 0}
    client.post(f"/imports/{batch['id']}/apply")
    assert "Consent to operate has lapsed" in titles(client, project)
    client.post(f"/imports/{batch['id']}/undo")
    view = client.get(f"/projects/{project}/approvals").json()
    cto = next(a for a in view["approvals"] if a["name"] == "Consent to operate")
    assert cto["status"] == "to_apply" and cto["granted_on"] is None
    assert not any(a["name"] == "Lift licence" for a in view["approvals"])
    assert [h["source"] for h in cto["history"]][:2] == ["undo", "import"]

    dup = client.post(f"/projects/{project}/approvals", json={"name": "consent to operate"})
    assert dup.status_code == 400
    view = client.post(f"/approvals/{cto['id']}/delete").json()
    assert len(view["approvals"]) == 11


def test_filings(app) -> None:
    client, project = firm(app)
    krera = client.get(f"/projects/{project}/krera").json()
    states = {q["period_end"]: q["state"] for q in krera["quarters"]}
    assert states["2026-06-30"] == "late" and states["2026-09-30"] == "late"
    assert states["2026-12-31"] == "open"
    assert krera["audits"][0]["period_end"] == "2026-03-31"
    assert krera["audits"][0]["due_on"] == "2026-09-30"

    wrong = client.post(
        f"/projects/{project}/filings",
        json={"kind": "qpr", "period_end": "2026-08-31", "filed_on": "2026-09-05"},
    )
    assert wrong.status_code == 400 and "quarter ending" in wrong.json()["detail"]
    early = client.post(
        f"/projects/{project}/filings",
        json={"kind": "qpr", "period_end": "2026-09-30", "filed_on": "2026-09-20"},
    )
    assert "before the period" in early.json()["detail"]

    assert "qpr:2026-09-30" in keys(client, project)
    krera = client.post(
        f"/projects/{project}/filings",
        json={
            "kind": "Quarterly progress report",
            "period_end": "30/09/2026",
            "filed_on": "10/10/2026",
            "reference": "ACK-1",
        },
    ).json()
    q = next(q for q in krera["quarters"] if q["period_end"] == "2026-09-30")
    assert q["state"] == "filed" and q["filing"]["reference"] == "ACK-1"
    assert "qpr:2026-09-30" not in keys(client, project)

    sheet = (
        "Filing,Period ending,Filed on,Acknowledgement\n"
        "Quarterly progress report,30/09/2026,11/10/2026,ACK-1B\n"
        "Annual audit report,31/03/2026,15/09/2026,\n"
        "Annual audit report,31/12/2025,15/09/2026,\n"
    )
    batch = upload(client, project, "filings", sheet)
    assert batch["counts"] == {"add": 1, "update": 1, "unchanged": 0, "error": 1}
    client.post(f"/imports/{batch['id']}/apply")
    krera = client.get(f"/projects/{project}/krera").json()
    assert krera["audits"][0]["state"] == "filed"
    q = next(q for q in krera["quarters"] if q["period_end"] == "2026-09-30")
    assert q["filing"]["filed_on"] == "2026-10-11"
    assert client.post(f"/filings/{q['filing']['id']}/delete").status_code == 200


def test_edit_as_a_table(app) -> None:
    client, project = firm(app)
    sheet = (
        "Unit,Tower,Carpet area (sq ft),List price,Guidance value\n"
        "A-101,Tower A,1100,90 lakh,85 lakh\n"
        "A-102,Tower A,1150,95 lakh,88 lakh\n"
    )
    client.post(f"/imports/{upload(client, project, 'units', sheet)['id']}/apply")

    table = client.get(f"/projects/{project}/table/units").json()
    assert table["total"] == 2 and table["fields"][0]["locked"] is True
    rows = table["rows"]
    price = [f["key"] for f in table["fields"]].index("list_price")
    assert rows[0][price] == "9000000"
    rows[0][price] = "92 lakh"
    r = client.post(f"/projects/{project}/table/units", json={"rows": rows})
    assert r.status_code == 201, r.text
    batch = client.get(f"/imports/{r.json()['id']}").json()
    assert batch["counts"] == {"add": 0, "update": 1, "unchanged": 1, "error": 0}
    client.post(f"/imports/{batch['id']}/apply")

    unit = next(
        u for u in client.get(f"/projects/{project}/units").json()["units"] if u["label"] == "A-101"
    )
    detail = client.get(f"/units/{unit['id']}").json()
    assert detail["list_price"] == "9200000.00"
    assert detail["history"][0]["source"] == "edited"

    assert client.get(f"/projects/{project}/table/receipts").status_code == 404
    short = client.post(f"/projects/{project}/table/units", json={"rows": [["A-101"]]})
    assert short.status_code == 400
