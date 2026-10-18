from datetime import date, timedelta

from fastapi.testclient import TestClient

from lekhara import legal
from lekhara.db import make_sessionmaker
from lekhara.models import (
    Acceptance,
    AccessEvent,
    Document,
    Organization,
    Project,
    Unit,
    User,
)

PASSWORD = "a-long-password"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def sign_up(app, email="anil@kaverihomes.in", firm="Kaveri Homes", **extra) -> TestClient:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={"name": "Anil", "email": email, "password": PASSWORD, "firm": firm, **extra},
    )
    assert r.status_code == 201, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return client


def test_signing_up_means_accepting_the_terms(app, engine) -> None:
    refused = TestClient(app).post(
        "/auth/signup",
        json={"name": "A", "email": "a@x.in", "password": PASSWORD, "firm": "X"},
    )
    assert refused.status_code == 400 and "terms of service" in refused.json()["detail"]
    client = sign_up(app, accept_terms=True)
    assert client.get("/auth/me").json()["terms_accepted"]
    with make_sessionmaker(engine)() as session:
        user = session.query(User).filter_by(email="anil@kaverihomes.in").one()
        documents = {a.document for a in session.query(Acceptance).filter_by(user_id=user.id)}
        assert documents == {"terms", "privacy", "data_processing"}

    alone = client.post("/auth/delete-account", json={"password": PASSWORD})
    assert "only owner" in alone.json()["detail"]  # nobody would be left to manage the firm

    info = TestClient(app).get("/legal").json()
    assert info["version"] == legal.VERSION and info["grievance_email"]
    assert info["close_after_days"] == 30 and info["sub_processors"]


def test_a_new_version_is_accepted_again(app, monkeypatch) -> None:
    client = sign_up(app, accept_terms=True)
    monkeypatch.setattr(legal, "VERSION", "2099-01-01")
    assert client.get("/auth/me").json()["terms_accepted"] is False
    client.post("/auth/accept-terms")
    assert client.get("/auth/me").json()["terms_accepted"] is True


def test_the_access_log(app, accounts) -> None:
    client = sign_up(app, accept_terms=True)
    plain = TestClient(app)
    plain.post("/auth/login", json={"email": "anil@kaverihomes.in", "password": "wrong-one"})
    plain.post("/auth/login", json={"email": "anil@kaverihomes.in", "password": PASSWORD})
    client.get("/organization/export")
    events = client.get("/organization/access-log").json()
    actions = [e["action"] for e in events["events"]]
    assert {"signed_up", "sign_in", "workspace_exported"} <= set(actions)
    assert events["keep_days"] >= 180
    assert accounts.get("/organization/access-log").status_code == 403


def test_deleting_your_own_account(app, engine) -> None:
    owner = sign_up(app, accept_terms=True)
    link = owner.post(
        "/organization/invitations", json={"email": "ravi@kaverihomes.in", "role": "accounts"}
    ).json()["link"]
    token = link.rsplit("/", 1)[-1]
    joined = TestClient(app).post(
        f"/invitations/{token}/accept", json={"name": "Ravi", "password": PASSWORD}
    )
    assert joined.status_code == 400  # a new account accepts the terms first
    joined = TestClient(app).post(
        f"/invitations/{token}/accept",
        json={"name": "Ravi", "password": PASSWORD, "accept_terms": True},
    )
    assert joined.status_code == 200, joined.text
    ravi = TestClient(app)
    ravi.headers["Authorization"] = f"Bearer {joined.json()['token']}"

    refused = owner.post("/auth/delete-account", json={"password": PASSWORD})
    assert "only owner" in refused.json()["detail"]
    assert ravi.post("/auth/delete-account", json={"password": "wrong"}).status_code == 400
    assert ravi.post("/auth/delete-account", json={"password": PASSWORD}).json() == {"ok": True}
    again = TestClient(app).post(
        "/auth/login", json={"email": "ravi@kaverihomes.in", "password": PASSWORD}
    )
    assert again.status_code == 401
    with make_sessionmaker(engine)() as session:
        gone = session.query(User).filter(User.email.like("deleted-%")).one()
        assert gone.name == "A former user"
        assert session.query(AccessEvent).filter_by(action="account_deleted").count() == 1


def test_closing_a_firm_deletes_its_data_after_the_wait(app, engine, owner) -> None:
    from lekhara import jobs

    client = sign_up(app, accept_terms=True)
    project = client.post(
        "/projects",
        json={
            "name": "Kaveri Heights",
            "krera_registration": "PRM/K/1",
            "registered_on": "2025-04-01",
        },
    ).json()["id"]
    client.post(f"/projects/{project}/units", json={"label": "A-101", "carpet_area_sqft": "1100"})
    client.post(
        f"/projects/{project}/documents",
        data={"title": "Title deed", "category": "title"},
        files={"file": ("deed.pdf", PDF, "application/pdf")},
    )
    wrong = client.post("/organization/close", json={"confirm": "Someone Else"})
    assert wrong.status_code == 400
    closing = client.post("/organization/close", json={"confirm": "kaveri  homes"}).json()
    today = app.state.settings.as_of()
    assert closing["delete_after"] == (today + timedelta(days=30)).isoformat()
    assert client.post("/organization/keep").json()["delete_after"] is None
    client.post("/organization/close", json={"confirm": "Kaveri Homes"})
    assert owner.post("/organization/close", json={"confirm": "Demo Builders"}).status_code == 400

    files_before = [p for p in app.state.storage.root.rglob("*") if p.is_file()]
    assert files_before
    app.state.settings.today = today + timedelta(days=31)
    try:
        with make_sessionmaker(engine)() as session:
            session.query(Organization).filter_by(name="Kaveri Homes").one()
            ctx = jobs.Context(session, app.state.storage, app.state.settings)
            jobs.HANDLERS["legal.daily"](ctx, {})
    finally:
        app.state.settings.today = date(2026, 10, 17)
    with make_sessionmaker(engine)() as session:
        assert session.query(Organization).filter_by(name="Kaveri Homes").count() == 0
        assert session.get(Project, project) is None
        assert session.query(Unit).filter_by(project_id=project).count() == 0
        assert session.query(Document).filter_by(project_id=project).count() == 0
        assert session.query(User).filter_by(email="anil@kaverihomes.in").count() == 0
        assert session.query(AccessEvent).filter_by(action="firm_deleted").count() == 1
        assert session.query(Organization).filter_by(name="Demo Builders").count() == 1
    assert not [p for p in app.state.storage.root.rglob("*") if p.is_file()]
    assert owner.get("/projects").status_code == 200
