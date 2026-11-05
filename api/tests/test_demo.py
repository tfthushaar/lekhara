"""The public demo: shared accounts kept safe, the mailbox, sample files that bring in cleanly,
a sample email, and the Vercel entry point that builds the demo on start."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import TODAY, signed_in
from fastapi.testclient import TestClient

from lekhara.app import create_app
from lekhara.config import Settings
from lekhara.pdf import write_pdf

HB = "hebbal-heights"
SG = "sarjapur-greens"
API = Path(__file__).resolve().parents[1]


@pytest.fixture
def shared(engine, tmp_path):
    """The public demo, where everyone signs in as the same demo accounts."""
    return create_app(
        Settings(database_url="sqlite://", today=TODAY, auto_migrate=False, demo=True,
                 shared_demo=True, storage_dir=str(tmp_path / "files")),
        engine=engine,
    )  # fmt: skip


def own_firm(app) -> TestClient:
    client = TestClient(app)
    token = client.post(
        "/auth/signup",
        json={"accept_terms": True, "name": "Anil", "email": "anil@example.com",
              "password": "a-long-password", "firm": "Kaveri Homes"},
    ).json()["token"]  # fmt: skip
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def test_the_shared_accounts_cannot_be_locked(shared) -> None:
    owner = signed_in(shared, "promoter@demo.lekhara")
    me = owner.get("/auth/me").json()
    member = next(
        m["user_id"] for m in owner.get("/organization").json()["members"]
        if m["email"] == "cfo@demo.lekhara"
    )  # fmt: skip
    refused = [
        owner.post("/auth/two-step/start"),
        owner.post("/auth/sessions/end-others"),
        owner.post("/auth/delete-account", json={"password": "lekhara-demo"}),
        owner.put("/organization/two-step-rule", json={"required": True}),
        owner.post("/organization/close", json={"confirm": me["organization"]["name"]}),
        owner.put(f"/organization/members/{member}", json={"role": "viewer"}),
        owner.post(f"/organization/members/{member}/remove"),
        TestClient(shared).post("/auth/forgot", json={"email": "cfo@demo.lekhara"}),
    ]
    for r in refused:
        assert r.status_code == 403 and "everyone trying the demo" in r.json()["detail"], r.text
    # Everything else works as usual, and a firm of one's own can try the rest.
    assert owner.get("/today").status_code == 200
    assert own_firm(shared).post("/auth/two-step/start").status_code == 200


def test_the_mailbox_and_a_visitors_code(app) -> None:
    mine = own_firm(app)
    mail = mine.get("/demo/mailbox").json()
    assert mail["email"] == "anil@example.com"
    assert any("Confirm" in m["subject"] for m in mail["emails"])

    owner = signed_in(app, "promoter@demo.lekhara")
    doc = owner.post(
        f"/projects/{SG}/documents",
        files={"file": ("ec.pdf", write_pdf([["Encumbrance certificate"]]), "application/pdf")},
    )
    ids = [doc.json()["id"]]
    room = owner.post(
        f"/projects/{SG}/rooms",
        json={"name": "Lender pack", "expires_on": "2026-11-15", "document_ids": ids,
              "ask_visitor": True},
    ).json()  # fmt: skip
    visitor = TestClient(app)
    r = visitor.post(
        f"/shared/{room['token']}/visitor", json={"name": "Asha", "email": "asha@x.in"}
    )
    code = r.json()["demo_code"]
    assert re.fullmatch(r"\d{6}", code)
    visitor.headers["X-Lekhara-Visitor"] = r.json()["visitor"]
    assert (
        visitor.post(f"/shared/{room['token']}/visitor/verify", json={"code": code}).status_code
        == 200
    )


def test_off_the_demo_none_of_it_is_there(engine, tmp_path) -> None:
    live = create_app(
        Settings(database_url="sqlite://", today=TODAY, auto_migrate=False,
                 storage_dir=str(tmp_path / "files")),
        engine=engine,
    )  # fmt: skip
    client = own_firm(live)
    assert client.get("/demo/mailbox").status_code == 404
    assert client.get("/auth/me").json()["demo"] is False


def upload(client, path, name, data) -> str:
    r = client.post(path, files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_every_sample_file_brings_in_cleanly(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    names = [s["name"] for s in owner.get(f"/projects/{HB}/demo/samples").json()["samples"]]
    files = {}
    for name in names:
        r = owner.get(f"/projects/{HB}/demo/samples/{name}")
        assert r.status_code == 200 and r.content, name
        files[name] = r.content

    batch = upload(owner, f"/projects/{HB}/imports/units", "units.csv", files["units.csv"])
    assert owner.get(f"/imports/{batch}").json()["counts"]["add"] == 12

    tally = owner.get(
        f"/tally/{upload(owner, f'/projects/{HB}/tally', 'tally.xml', files['tally-export.xml'])}"
    ).json()
    assert tally["counts"]["bills_new"] == 2 and tally["counts"]["receipts_new"] == 2

    sid = upload(owner, f"/projects/{HB}/bank-statements", "c.csv", files["collection-account.csv"])
    lines = owner.put(f"/bank-statements/{sid}/options", json={"role": "collections"}).json()
    outcomes = [line["outcome"] for line in lines["lines"]]
    assert outcomes.count("buyer_payment") == 5 and outcomes.count("returned") == 2
    assert "needs_unit" in outcomes and "not_buyer" in outcomes
    hows = {line["how"] for line in lines["lines"] if line["how"]}
    assert hows == {"unit number", "buyer's name"}

    rid = upload(owner, f"/projects/{HB}/bank-statements", "r.xlsx", files["rera-account.xlsx"])
    rera = owner.put(f"/bank-statements/{rid}/options", json={"role": "rera"}).json()
    assert [line["outcome"] for line in rera["lines"]] == [
        "deposit", "deposit", "withdrawal", "interest", "charges"
    ]  # fmt: skip
    assert not any(a["code"] == "rera.opening" for a in rera["alerts"])

    gst = owner.get(f"/gst/{upload(owner, f'/projects/{HB}/gst', 'g.json', files['gstr-2b.json'])}")
    counts = gst.json()["counts"]
    assert counts["matched"] >= 1 and counts["differs"] == 1 and counts["missing"] == 1
    assert counts["notes"] == 1 and gst.json()["ims"]["check"] == 1

    certificate = owner.get("/demo/samples/krera-certificate.pdf")
    read = owner.post(
        "/projects/from-certificate",
        files={"file": ("c.pdf", certificate.content, "application/pdf")},
    ).json()
    assert read["fields"]["name"] == "Yelahanka Meadows" and read["missing"] == []

    assert owner.get(f"/projects/{HB}/demo/samples/nothing.csv").status_code == 404


def test_a_sample_email_is_brought_in(app) -> None:
    accounts = signed_in(app, "accounts@demo.lekhara")
    r = accounts.post(f"/projects/{HB}/demo/sample-email")
    assert r.status_code == 200 and r.json()["status"] == "done"
    box = accounts.get(f"/projects/{HB}/inbound").json()
    item = box["messages"][0]["items"][0]
    assert item["kind"] == "bank_statement" and item["status"] in ("done", "review")
    architect = signed_in(app, "architect@demo.lekhara")
    assert architect.post(f"/projects/{HB}/demo/sample-email").status_code in (403, 404)


def test_the_vercel_entry_point_builds_the_demo(tmp_path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LEKHARA_")}
    env.update({"TMPDIR": str(tmp_path), "TMP": str(tmp_path), "TEMP": str(tmp_path),
                "VERCEL_PROJECT_PRODUCTION_URL": "lekhara-demo.vercel.app",
                "LEKHARA_PASSWORD_BREACH_CHECK": "0"})  # fmt: skip
    script = (
        "from fastapi.testclient import TestClient\n"
        "from lekhara.vercel import app\n"
        "from lekhara.config import get_settings\n"
        "c = TestClient(app)\n"
        "d = c.get('/auth/demo').json()\n"
        "r = c.post('/auth/login', json={'email': 'promoter@demo.lekhara', "
        "'password': d['password']})\n"
        "c.headers['Authorization'] = 'Bearer ' + r.json()['token']\n"
        "assert c.get('/today').status_code == 200\n"
        "assert c.post('/auth/two-step/start').status_code == 403\n"
        "s = get_settings()\n"
        "print(s.web_url, s.worker, s.database_url)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", script], cwd=API, env=env, capture_output=True, text=True,
        timeout=180,
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-2000:]
    web_url, worker, url = out.stdout.split()
    assert web_url == "https://lekhara-demo.vercel.app" and worker == "False"
    assert (
        url.endswith("lekhara-demo/lekhara.db")
        and (tmp_path / "lekhara-demo" / "lekhara.db").exists()
    )


def test_the_nightly_reset_needs_the_cron_secret(shared, monkeypatch) -> None:
    calls = []
    shared.state.reset_demo = lambda: calls.append(1)
    client = TestClient(shared)
    assert client.post("/demo/reset").status_code == 404  # no secret set: no reset at all
    monkeypatch.setenv("CRON_SECRET", "a-secret")
    assert client.post("/demo/reset", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.post("/demo/reset", headers={"Authorization": "Bearer a-secret"})
    assert ok.status_code == 200 and calls == [1]
