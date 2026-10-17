import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from lekhara.db import make_sessionmaker
from lekhara.models import Organization, OutboundEmail

SG = "sarjapur-greens"
PASSWORD = "a-long-password"


def join(app, *, email: str, firm: str = "Kaveri Homes", name: str = "Anil") -> TestClient:
    client = TestClient(app)
    r = client.post(
        "/auth/signup", json={"name": name, "email": email, "password": PASSWORD, "firm": firm}
    )
    assert r.status_code == 201, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return client


def link_in_last_email(engine, to: str, kind: str) -> str:
    with make_sessionmaker(engine)() as session:
        row = session.scalars(
            select(OutboundEmail)
            .where(OutboundEmail.to_address == to, OutboundEmail.kind == kind)
            .order_by(OutboundEmail.created_at.desc())
        ).first()
        assert row is not None, f"no {kind} email to {to}"
        return re.search(r"/(?:verify|reset|invite)/(\S+)", row.body).group(1)


def add_project(client, name="Kaveri Heights", krera="PRM/KA/RERA/1251/309/PR/010125/007001"):
    r = client.post(
        "/projects",
        json={
            "name": name,
            "krera_registration": krera,
            "registered_on": "2025-01-01",
            "possession_due_on": "2028-06-30",
            "locality": "Yelahanka",
            "land_structure": "own",
            "gst_regime": "residential_5pc",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_signing_up_starts_a_free_month(app) -> None:
    client = join(app, email="anil@kaverihomes.in")
    me = client.get("/auth/me").json()
    assert me["organization"]["name"] == "Kaveri Homes"
    assert me["organization"]["access"] == "trial"
    assert me["organization"]["days_left"] == 30
    assert me["role_label"] == "Owner"
    assert me["email_verified"] is False

    projects = client.get("/projects").json()
    assert projects and all(p["sample"] for p in projects)
    assert client.get("/today").json()["items"] == []


def test_signup_checks_its_input(app) -> None:
    client = TestClient(app)
    base = {"name": "A", "email": "a@b.in", "password": PASSWORD, "firm": "F"}
    assert client.post("/auth/signup", json={**base, "password": "short"}).status_code == 400
    assert client.post("/auth/signup", json={**base, "email": "not-an-email"}).status_code == 400
    assert client.post("/auth/signup", json={**base, "firm": " "}).status_code == 400
    taken = client.post("/auth/signup", json={**base, "email": "Promoter@demo.lekhara"})
    assert taken.status_code == 409


def test_confirming_the_email(app, engine) -> None:
    client = join(app, email="anil@kaverihomes.in")
    token = link_in_last_email(engine, "anil@kaverihomes.in", "verify_email")
    assert client.post("/auth/verify", json={"token": token}).status_code == 200
    assert client.get("/auth/me").json()["email_verified"] is True
    assert client.post("/auth/verify", json={"token": token}).status_code == 400


def test_resetting_a_password(app, engine) -> None:
    client = join(app, email="anil@kaverihomes.in")
    public = TestClient(app)
    assert public.post("/auth/forgot", json={"email": "nobody@nowhere.in"}).status_code == 200
    assert public.post("/auth/forgot", json={"email": "ANIL@kaverihomes.in"}).status_code == 200
    token = link_in_last_email(engine, "anil@kaverihomes.in", "reset_password")

    assert public.post("/auth/reset", json={"token": token, "password": "short"}).status_code == 400
    r = public.post("/auth/reset", json={"token": token, "password": "a-brand-new-password"})
    assert r.status_code == 200
    assert client.get("/auth/me").status_code == 401  # every old session ends
    login = public.post(
        "/auth/login", json={"email": "anil@kaverihomes.in", "password": "a-brand-new-password"}
    )
    assert login.status_code == 200
    again = public.post("/auth/reset", json={"token": token, "password": "another-password"})
    assert again.status_code == 400


def test_adding_a_project(app) -> None:
    client = join(app, email="anil@kaverihomes.in")
    project_id = add_project(client)
    mine = [p for p in client.get("/projects").json() if not p["sample"]]
    assert [p["name"] for p in mine] == ["Kaveri Heights"]
    detail = client.get(f"/projects/{project_id}").json()
    assert detail["access"]["team"] is True and detail["access"]["sample"] is False
    for tab in ("escrow", "collections", "handover", "disputes", "documents", "tax", "units"):
        assert client.get(f"/projects/{project_id}/{tab}").status_code == 200, tab

    duplicate = client.post(
        "/projects",
        json={
            "name": "Again",
            "krera_registration": "prm/ka/rera/1251/309/pr/010125/007001",
            "registered_on": "2025-01-01",
        },
    )
    assert duplicate.status_code == 400
    backwards = client.post(
        "/projects",
        json={
            "name": "Backwards",
            "krera_registration": "PRM/X",
            "registered_on": "2025-01-01",
            "possession_due_on": "2024-01-01",
        },
    )
    assert backwards.status_code == 400


def test_one_firm_never_sees_another(app) -> None:
    a = join(app, email="a@firm-a.in", firm="Firm A")
    b = join(app, email="b@firm-b.in", firm="Firm B")
    project = add_project(a, name="A Towers", krera="PRM/A/1")

    assert all(p["id"] != project for p in b.get("/projects").json())
    for path in ("", "/escrow", "/money", "/collections", "/handover", "/disputes", "/documents"):
        assert b.get(f"/projects/{project}{path}").status_code == 404, path
    assert b.get(f"/projects/{project}/tax").status_code == 404
    case = {"forum": "krera", "case_number": "X", "relief": "refund", "complainant": "Z"}
    assert b.post(f"/projects/{project}/disputes", json=case).status_code == 404
    upload = b.post(
        f"/projects/{project}/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert upload.status_code == 404
    assert b.get("/organization").json()["name"] == "Firm B"


def test_sample_projects_can_be_explored_but_not_changed(app) -> None:
    client = join(app, email="anil@kaverihomes.in")
    detail = client.get(f"/projects/{SG}").json()
    assert detail["access"]["sample"] is True
    assert client.get(f"/projects/{SG}/collections").status_code == 200
    case = {"forum": "krera", "case_number": "X", "relief": "refund", "complainant": "Z"}
    refused = client.post(f"/projects/{SG}/disputes", json=case)
    assert refused.status_code == 403
    assert "sample" in refused.json()["detail"]
    assert client.get("/today").json()["items"] == []


def test_inviting_the_team_and_a_certifier(app, engine) -> None:
    owner = join(app, email="anil@kaverihomes.in")
    project = add_project(owner)

    r = owner.post(
        "/organization/invitations", json={"email": "Ravi@KaveriHomes.in", "role": "accounts"}
    )
    assert r.status_code == 201, r.text
    token = r.json()["link"].rsplit("/", 1)[1]
    assert token == link_in_last_email(engine, "ravi@kaverihomes.in", "invitation")

    public = TestClient(app)
    info = public.get(f"/invitations/{token}").json()
    assert (info["firm"], info["role_label"], info["has_account"]) == (
        "Kaveri Homes",
        "Accounts",
        False,
    )
    accepted = public.post(
        f"/invitations/{token}/accept", json={"name": "Ravi", "password": PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text
    ravi = TestClient(app, headers={"Authorization": f"Bearer {accepted.json()['token']}"})
    assert ravi.get("/auth/me").json()["role_label"] == "Accounts"
    assert ravi.get(f"/projects/{project}").status_code == 200
    assert public.get(f"/invitations/{token}").status_code == 404  # used

    # Accounts cannot invite; a certifier is invited for chosen projects only.
    assert (
        ravi.post(
            "/organization/invitations", json={"email": "x@y.in", "role": "viewer"}
        ).status_code
        == 403
    )
    bad = owner.post("/organization/invitations", json={"email": "ca@firm.in", "role": "ca"})
    assert bad.status_code == 400
    r = owner.post(
        "/organization/invitations",
        json={"email": "ca@firm.in", "role": "ca", "project_ids": [project]},
    )
    token = r.json()["link"].rsplit("/", 1)[1]
    accepted = public.post(
        f"/invitations/{token}/accept",
        json={"name": "Shobha", "password": PASSWORD, "firm": "Shobha and Co"},
    )
    ca = TestClient(app, headers={"Authorization": f"Bearer {accepted.json()['token']}"})
    detail = ca.get(f"/projects/{project}").json()
    assert detail["access"]["certifies"] == ["ca"]
    assert ca.get(f"/projects/{project}/tax").status_code == 403
    firm = owner.get("/organization").json()
    assert [c["firm"] for c in firm["certifiers"]] == ["Shobha and Co"]


def test_an_existing_account_accepts_with_its_password(app) -> None:
    owner = join(app, email="anil@kaverihomes.in")
    r = owner.post(
        "/organization/invitations", json={"email": "promoter@demo.lekhara", "role": "viewer"}
    )
    token = r.json()["link"].rsplit("/", 1)[1]
    public = TestClient(app)
    assert public.get(f"/invitations/{token}").json()["has_account"] is True
    wrong = public.post(f"/invitations/{token}/accept", json={"password": "not-the-password"})
    assert wrong.status_code == 401
    ok = public.post(f"/invitations/{token}/accept", json={"password": "lekhara-demo"})
    assert ok.status_code == 200


def test_managing_the_team(app) -> None:
    owner = join(app, email="anil@kaverihomes.in")
    me = owner.get("/organization").json()["members"][0]
    assert me["you"] is True
    demote = owner.put(f"/organization/members/{me['user_id']}", json={"role": "viewer"})
    assert demote.status_code == 400  # the firm keeps an owner
    assert owner.post(f"/organization/members/{me['user_id']}/remove").status_code == 400

    r = owner.post("/organization/invitations", json={"email": "f@k.in", "role": "finance"})
    token = r.json()["link"].rsplit("/", 1)[1]
    accepted = TestClient(app).post(
        f"/invitations/{token}/accept", json={"name": "F", "password": PASSWORD}
    )
    finance = TestClient(app, headers={"Authorization": f"Bearer {accepted.json()['token']}"})
    assert (
        finance.post(
            "/organization/invitations", json={"email": "o@k.in", "role": "owner"}
        ).status_code
        == 403
    )
    assert (
        finance.post(
            "/organization/invitations", json={"email": "v@k.in", "role": "viewer"}
        ).status_code
        == 201
    )
    member = next(m for m in owner.get("/organization").json()["members"] if m["role"] == "finance")
    assert (
        owner.put(f"/organization/members/{member['user_id']}", json={"role": "viewer"}).status_code
        == 200
    )
    assert owner.post(f"/organization/members/{member['user_id']}/remove").status_code == 200
    assert finance.get("/organization").status_code == 404


def test_after_the_free_month_the_workspace_is_read_only(app, engine) -> None:
    owner = join(app, email="anil@kaverihomes.in")
    project = add_project(owner)
    with make_sessionmaker(engine)() as session:
        org = session.scalars(select(Organization).where(Organization.name == "Kaveri Homes")).one()
        org.trial_ends_on = date(2026, 10, 1)
        session.commit()

    assert owner.get("/auth/me").json()["organization"]["access"] == "read_only"
    assert owner.get(f"/projects/{project}").status_code == 200
    assert owner.get(f"/projects/{project}/documents").status_code == 200
    blocked = owner.post(
        "/projects", json={"name": "New", "krera_registration": "Z", "registered_on": "2026-01-01"}
    )
    assert blocked.status_code == 402
    case = {"forum": "krera", "case_number": "X", "relief": "refund", "complainant": "Z"}
    assert owner.post(f"/projects/{project}/disputes", json=case).status_code == 402


@pytest.mark.parametrize(
    ("gstin", "status"),
    [("29AAGCB7383J1Z4", 200), ("29aagcb7383j1z4", 200), ("29AAGCB7383J1Z5", 400), ("1234", 400)],
)
def test_the_firm_gstin_is_checked(app, gstin, status) -> None:
    owner = join(app, email="anil@kaverihomes.in")
    r = owner.put("/organization", json={"gstin": gstin})
    assert r.status_code == status, r.text
    if status == 200:
        assert r.json()["gstin"] == "29AAGCB7383J1Z4"
        assert r.json()["state"] == "Karnataka"
