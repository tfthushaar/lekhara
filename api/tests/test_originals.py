"""The register of originals: numbered for the firm, moved with a history, found by scanning."""

from datetime import timedelta

from conftest import TODAY, signed_in
from fastapi.testclient import TestClient

SG = "sarjapur-greens"


def add(client: TestClient, project: str = SG, **fields):
    # Entered as held in the office since some time ago, as a register of old papers would be.
    since = (TODAY - timedelta(days=90)).isoformat()
    body = {"title": "Title deed, survey 42", "kind": "title", "since": since, **fields}
    return client.post(f"/projects/{project}/originals", json=body)


def test_originals_are_numbered_moved_and_found(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    first = add(owner).json()
    assert first["number"] == "O-0001" and first["held_at"] == "office"
    projects = owner.get("/projects").json()
    other = next(p["id"] for p in projects if p["id"] != SG)
    second = add(owner, other, title="Occupancy certificate, tower A", kind="approval").json()
    assert second["number"] == "O-0002"  # one series for the firm

    no_holder = owner.post(f"/originals/{first['id']}/move", json={"held_at": "bank"})
    assert no_holder.status_code == 400 and "who has it" in no_holder.json()["detail"]
    moved = owner.post(
        f"/originals/{first['id']}/move",
        json={"held_at": "bank", "held_by": "HDFC Bank, MG Road", "against": "Project loan 4471",
              "since": (TODAY - timedelta(days=3)).isoformat()},
    )  # fmt: skip
    assert moved.status_code == 200 and moved.json()["held_at_label"] == "With a bank, as security"
    earlier = owner.post(
        f"/originals/{first['id']}/move",
        json={"held_at": "office", "since": (TODAY - timedelta(days=30)).isoformat()},
    )
    assert earlier.status_code == 400

    detail = owner.get(f"/originals/{first['id']}").json()
    assert [m["held_at_label"] for m in detail["moves"]] == [
        "With a bank, as security",
        "In the office",
    ]
    assert detail["moves"][0]["against"] == "Project loan 4471"

    # A barcode reader types the number; any of these forms finds it.
    for typed in ("O-0001", "o-1", "1", " O-0001\n"):
        assert owner.get("/originals/find", params={"number": typed}).json()["id"] == first["id"]
    assert owner.get("/originals/find", params={"number": "O-0099"}).status_code == 404


def test_an_original_away_too_long_is_flagged(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    deed = add(owner).json()
    owner.post(
        f"/originals/{deed['id']}/move",
        json={"held_at": "lawyer", "held_by": "Rao & Co",
              "since": (TODAY - timedelta(days=45)).isoformat()},
    )  # fmt: skip
    listed = owner.get(f"/projects/{SG}/originals").json()["originals"]
    assert listed[0]["away_too_long"] is True


def test_other_firms_and_certifiers_cannot_see_originals(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    add(owner)
    client = TestClient(app)
    token = client.post(
        "/auth/signup",
        json={"accept_terms": True, "name": "Anil", "email": "anil@kaveri.in",
              "password": "a-long-password", "firm": "Kaveri Homes"},
    ).json()["token"]  # fmt: skip
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.get("/originals/find", params={"number": "O-0001"}).status_code == 404

    architect = signed_in(app, "architect@demo.lekhara")
    assert architect.get(f"/projects/{SG}/originals").status_code in (403, 404)
