"""Our admin console: staff only, with two-step sign-in; trials, payments, and support access
only with the firm's consent, read-only and in the firm's access log."""

import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from lekhara import staff, two_step
from lekhara.db import make_sessionmaker
from lekhara.models import User

PASSWORD = "a-long-password"
PROJECT = {"name": "Kaveri Heights", "krera_registration": "PRM/K/1", "registered_on": "2025-04-01"}


def sign_up(app, email: str, firm: str) -> TestClient:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={"accept_terms": True, "name": firm.split()[0], "email": email,
              "password": PASSWORD, "firm": firm},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return client


def make_staff(engine, email: str) -> None:
    with make_sessionmaker(engine)() as session:
        session.scalars(select(User).where(User.email == email)).one().is_staff = True
        session.commit()


def turn_on_two_step(client: TestClient) -> None:
    secret = client.post("/auth/two-step/start").json()["secret"].replace(" ", "")
    code = two_step.code_at(secret, int(time.time() // 30))
    assert client.post("/auth/two-step/confirm", json={"code": code}).status_code == 200


def test_only_staff_with_two_step_reach_the_console(app, engine) -> None:
    builder = sign_up(app, "anil@kaveri.in", "Kaveri Homes")
    assert builder.get("/staff/firms").status_code == 404  # no sign it exists

    us = sign_up(app, "meera@lekhara.in", "Lekhara")
    make_staff(engine, "meera@lekhara.in")
    blocked = us.get("/staff/firms")
    assert blocked.status_code == 403 and "two-step" in blocked.json()["detail"]
    turn_on_two_step(us)

    firms = us.get("/staff/firms").json()["firms"]
    kaveri = next(f for f in firms if f["name"] == "Kaveri Homes")
    assert kaveri["access"] == "trial" and kaveri["people"] == 1 and kaveri["projects"] == 0
    # Search finds a firm by a member's email as well as by its name.
    found = us.get("/staff/firms", params={"q": "anil@"}).json()["firms"]
    assert [f["name"] for f in found] == ["Kaveri Homes"]

    detail = us.get(f"/staff/firms/{kaveri['id']}").json()
    assert detail["members"][0]["email"] == "anil@kaveri.in"
    assert detail["members"][0]["role"] == "Owner"


def test_trials_and_payments(app, engine) -> None:
    builder = sign_up(app, "anil@kaveri.in", "Kaveri Homes")
    us = sign_up(app, "meera@lekhara.in", "Lekhara")
    make_staff(engine, "meera@lekhara.in")
    turn_on_two_step(us)
    firm = next(f for f in us.get("/staff/firms").json()["firms"] if f["name"] == "Kaveri Homes")

    no_reason = us.post(f"/staff/firms/{firm['id']}/trial", json={"ends_on": "30/11/2026"})
    assert no_reason.status_code == 400 and "why" in no_reason.json()["detail"]
    extended = us.post(
        f"/staff/firms/{firm['id']}/trial",
        json={"ends_on": "30/11/2026", "reason": "Waiting for their Tally export"},
    ).json()
    assert extended["trial_ends_on"] == "2026-11-30" and extended["access"] == "trial"
    assert builder.get("/auth/me").json()["organization"]["trial_ends_on"] == "2026-11-30"

    # A payment for a period already over: paid, but read-only, saying so.
    old = {"amount": "11,800", "paid_on": "01/09/2026", "method": "bank_transfer",
           "reference": "UTR123", "covers_from": "01/09/2026",
           "covers_to": "30/09/2026"}  # fmt: skip
    paid = us.post(f"/staff/firms/{firm['id']}/payments", json=old).json()
    assert paid["access"] == "read_only" and paid["paid_until"] == "2026-09-30"
    refused = builder.post(
        "/projects",
        json=PROJECT,
    )  # fmt: skip
    assert refused.status_code == 402 and "paid to 30 September 2026" in refused.json()["detail"]

    current = {**old, "reference": "UTR456", "paid_on": "01/10/2026",
               "covers_from": "01/10/2026", "covers_to": "31/10/2026"}  # fmt: skip
    paid = us.post(f"/staff/firms/{firm['id']}/payments", json=current).json()
    assert paid["access"] == "active" and paid["paid_until"] == "2026-10-31"
    assert [p["reference"] for p in paid["payments"]] == ["UTR456", "UTR123"]
    assert {e["action"] for e in paid["staff_log"]} == {
        "staff_trial_extended",
        "staff_payment_recorded",
    }

    # Removing one recorded by mistake.
    later = paid["payments"][0]["id"]
    after = us.post(f"/staff/payments/{later}/delete").json()
    assert after["paid_until"] == "2026-09-30" and after["access"] == "read_only"

    # The firm sees what we did in its own access log.
    log = builder.get("/organization/access-log").json()["events"]
    assert {"staff_trial_extended", "staff_payment_recorded", "staff_payment_removed"} <= {
        e["action"] for e in log
    }


def test_support_needs_consent_is_read_only_and_logged(app, engine) -> None:
    builder = sign_up(app, "anil@kaveri.in", "Kaveri Homes")
    builder.post(
        "/projects",
        json=PROJECT,
    )  # fmt: skip
    us = sign_up(app, "meera@lekhara.in", "Lekhara")
    make_staff(engine, "meera@lekhara.in")
    turn_on_two_step(us)
    firm = next(f for f in us.get("/staff/firms").json()["firms"] if f["name"] == "Kaveri Homes")

    refused = us.post(f"/staff/firms/{firm['id']}/support")
    assert refused.status_code == 403 and "not allowed" in refused.json()["detail"]

    assert builder.get("/organization/support").json()["allowed_until"] is None
    assert builder.post("/organization/support", json={"days": 5}).status_code == 400
    allowed = builder.post("/organization/support", json={"days": 3}).json()
    assert allowed["allowed_until"] and allowed["allowed_by"] == "Kaveri"

    opened = us.post(f"/staff/firms/{firm['id']}/support").json()
    support = TestClient(app)
    support.headers["Authorization"] = f"Bearer {opened['token']}"
    me = support.get("/auth/me").json()
    assert (
        me["support"]["firm"] == "Kaveri Homes" and me["role_label"] == "Lekhara support, read-only"
    )
    projects = support.get("/projects").json()
    assert any(p["name"] == "Kaveri Heights" for p in projects)
    change = support.post(
        "/projects",
        json={**PROJECT, "name": "Not allowed", "krera_registration": "PRM/K/2"},
    )  # fmt: skip
    assert change.status_code == 403 and "look but not change" in change.json()["detail"]
    assert support.get("/organization/support").json()["can_manage"] is False
    # Support is not staff while it looks: the console is closed to that session.
    assert support.get("/staff/firms").status_code == 404

    log = builder.get("/organization/access-log").json()["events"]
    views = [e for e in log if e["action"] == "support_view"]
    assert views and views[0]["who"] == "meera@lekhara.in"
    assert any(e["detail"] == "/projects" for e in views)
    assert {"support_allowed", "support_opened"} <= {e["action"] for e in log}

    # Withdrawing the consent ends the session at once.
    builder.post("/organization/support/withdraw")
    assert support.get("/projects").status_code == 401
    assert us.post(f"/staff/firms/{firm['id']}/support").status_code == 403


def test_staff_from_the_command_line(engine, monkeypatch, capsys) -> None:
    from lekhara import config, db

    monkeypatch.setattr(config, "get_settings", lambda: config.Settings(database_url="sqlite://"))
    monkeypatch.setattr(db, "make_engine", lambda url: engine)
    assert staff.main(["add", "nobody@lekhara.in"]) == 1
    assert staff.main(["add", "promoter@demo.lekhara"]) == 0
    assert "two-step" in capsys.readouterr().out
    staff.main(["list"])
    assert "promoter@demo.lekhara" in capsys.readouterr().out
    assert staff.main(["remove", "promoter@demo.lekhara"]) == 0
    assert staff.main(["wrong"]) == 2
