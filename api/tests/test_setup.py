from fastapi.testclient import TestClient

PASSWORD = "a-long-password"
SG = "sarjapur-greens"


def firm(app, email="anil@kaverihomes.in") -> tuple[TestClient, str]:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={"name": "Anil", "email": email, "password": PASSWORD, "firm": "Kaveri"},
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
    return client, project


def statuses(view) -> dict:
    return {i["key"]: i["status"] for i in view["items"]}


def test_a_new_project_shows_what_to_bring_in(app) -> None:
    client, project = firm(app)
    view = client.get(f"/projects/{project}/setup").json()
    s = statuses(view)
    assert s["details"] == "partial" and s["units"] == "missing" and s["plan"] == "missing"
    assert s["certifiers"] == "missing"
    assert "landowners" not in s  # not a joint development
    assert view["summary"]["done"] == 0 and view["summary"]["next"] == "details"
    units = next(i for i in view["items"] if i["key"] == "units")
    assert units["href"] == f"/projects/{project}/import"

    client.post(f"/projects/{project}/payment-plan/template", json={"template": "twenty_eighty"})
    client.post(f"/projects/{project}/cost-lines/standard")
    s = statuses(client.get(f"/projects/{project}/setup").json())
    assert s["plan"] == "done" and s["cost_lines"] == "partial"  # no budgets yet


def test_changing_the_project_details(app) -> None:
    client, project = firm(app)
    r = client.put(
        f"/projects/{project}",
        json={
            "possession_due_on": "30/06/2028",
            "escrow_bank": "Canara Bank, MG Road",
            "land_structure": "jda_area_share",
        },
    )
    assert r.status_code == 200, r.text
    s = statuses(r.json())
    assert s["details"] == "done" and s["landowners"] == "missing"
    assert r.json()["details"]["possession_due_on"] == "2028-06-30"

    assert (
        client.put(f"/projects/{project}", json={"possession_due_on": "01/01/2024"}).status_code
        == 400
    )
    assert client.put(f"/projects/{project}", json={"oc_status": "received"}).status_code == 400
    oc = client.put(
        f"/projects/{project}",
        json={"oc_status": "received", "oc_received_on": "01/10/2026", "oc_reference": "GBA/OC/1"},
    )
    assert oc.json()["details"]["oc_status"] == "received"
    handover = client.get(f"/projects/{project}/handover").json()
    assert handover["oc"]["label"] == "Received"
    assert client.put(f"/projects/{project}", json={"name": " "}).status_code == 400

    # The form sends every field: blanks clear the optional ones and keep the registration date.
    cleared = client.put(
        f"/projects/{project}",
        json={"escrow_bank": "", "possession_due_on": "", "registered_on": "", "locality": ""},
    ).json()["details"]
    assert cleared["escrow_bank"] is None and cleared["possession_due_on"] is None
    assert cleared["registered_on"] == "2025-04-01" and cleared["locality"] == ""

    other = client.post(
        "/projects",
        json={"name": "Second", "krera_registration": "PRM/K/2", "registered_on": "2025-04-01"},
    ).json()["id"]
    assert (
        client.put(f"/projects/{other}", json={"krera_registration": "prm/k/1"}).status_code == 400
    )


def test_recording_certified_progress(app, architect) -> None:
    client, project = firm(app)
    url = f"/projects/{project}/progress"
    r = client.post(
        url, json={"as_of": "01/09/2026", "completion_pct": "35", "certified_by": "Rao Architects"}
    )
    assert r.status_code == 201, r.text
    assert statuses(r.json())["progress"] == "done"
    assert "35%" in next(i for i in r.json()["items"] if i["key"] == "progress")["detail"]
    lower = client.post(url, json={"as_of": "01/10/2026", "completion_pct": "30"})
    assert "cannot go down" in lower.json()["detail"]
    assert client.post(url, json={"as_of": "01/01/2027", "completion_pct": "40"}).status_code == 400
    assert (
        client.post(url, json={"as_of": "01/10/2026", "completion_pct": "140"}).status_code == 400
    )

    # The project's architect can record it too; someone else's project stays out of reach.
    assert architect.post(
        f"/projects/{SG}/progress", json={"as_of": "10/10/2026", "completion_pct": "92"}
    ).json() == {"ok": True}
    assert (
        architect.post(url, json={"as_of": "10/10/2026", "completion_pct": "40"}).status_code == 404
    )


def test_the_sample_project_is_mostly_set_up(owner) -> None:
    view = owner.get(f"/projects/{SG}/setup").json()
    s = statuses(view)
    assert s["units"] == "done" and s["plan"] == "done" and s["certifiers"] == "done"
    assert view["summary"]["done"] >= 8
