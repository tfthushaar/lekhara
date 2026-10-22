"""Asking again before sensitive steps, sessions that end when idle, seeing and ending sessions,
alerts by email, the firm's two-step rule, and passwords already leaked elsewhere."""

import time
from datetime import timedelta

from conftest import signed_in
from fastapi.testclient import TestClient
from sqlalchemy import select

from lekhara import auth, passwords, two_step
from lekhara.models import OutboundEmail, UserSession
from lekhara.passwords import times_leaked as real_times_leaked
from lekhara.seed import DEMO_PASSWORD


def _sessions(app):
    return app.state.session_factory()


def _age(app, email: str, *, confirmed: timedelta | None = None, seen: timedelta | None = None):
    """Makes the person's sessions look older than they are."""
    from lekhara.models import User

    with _sessions(app) as session:
        user = session.scalars(select(User).where(User.email == email)).one()
        for row in session.scalars(select(UserSession).where(UserSession.user_id == user.id)):
            if confirmed is not None:
                row.confirmed_at = auth._now() - confirmed
            if seen is not None:
                row.last_seen_at = auth._now() - seen
        session.commit()


def _mail_to(app, address: str) -> list[OutboundEmail]:
    with _sessions(app) as session:
        return list(
            session.scalars(select(OutboundEmail).where(OutboundEmail.to_address == address))
        )


def test_sensitive_steps_ask_again_after_a_while(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    # Just signed in: no second ask.
    assert owner.get("/organization/export").status_code == 200

    _age(app, "promoter@demo.lekhara", confirmed=timedelta(minutes=20))
    asked = owner.get("/organization/export")
    assert asked.status_code == 428 and "Confirm it is you" in asked.json()["detail"]
    room = owner.post(
        "/projects/sarjapur-greens/rooms",
        json={"name": "Bank", "expires_on": "2026-11-15", "document_ids": []},
    )
    assert room.status_code == 428

    assert owner.post("/auth/confirm", json={"password": "wrong"}).status_code == 401
    assert owner.post("/auth/confirm", json={"password": DEMO_PASSWORD}).status_code == 200
    assert owner.get("/organization/export").status_code == 200


def test_confirming_needs_the_code_when_two_step_is_on(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    secret = owner.post("/auth/two-step/start").json()["secret"].replace(" ", "")
    now = time.time()
    owner.post("/auth/two-step/confirm", json={"code": two_step.code_at(secret, int(now // 30))})
    _age(app, "promoter@demo.lekhara", confirmed=timedelta(minutes=20))
    no_code = owner.post("/auth/confirm", json={"password": DEMO_PASSWORD})
    assert no_code.status_code == 401
    later = two_step.code_at(secret, int(now // 30) + 1)
    two_step.time.time = lambda: now + 30  # the next step, so the code is fresh
    try:
        ok = owner.post("/auth/confirm", json={"password": DEMO_PASSWORD, "code": later})
    finally:
        two_step.time.time = time.time
    assert ok.status_code == 200


def test_a_session_left_idle_ends(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    assert owner.get("/auth/me").status_code == 200
    _age(app, "promoter@demo.lekhara", seen=timedelta(hours=13))
    assert owner.get("/auth/me").status_code == 401


def test_seeing_and_ending_sessions(app) -> None:
    laptop = signed_in(app, "promoter@demo.lekhara")
    phone = signed_in(app, "promoter@demo.lekhara")
    listed = laptop.get("/auth/sessions").json()["sessions"]
    assert len(listed) == 2 and sum(s["current"] for s in listed) == 1
    assert laptop.post("/auth/sessions/end-others").json()["ended"] == 1
    assert phone.get("/auth/me").status_code == 401
    assert laptop.get("/auth/me").status_code == 200


def test_a_new_browser_is_reported_by_email(app) -> None:
    def sign_in(agent: str) -> None:
        client = TestClient(app)
        r = client.post(
            "/auth/login",
            json={"email": "cfo@demo.lekhara", "password": DEMO_PASSWORD},
            headers={"X-Lekhara-User-Agent": agent},
        )
        assert r.status_code == 200

    chrome = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/141.0 Safari/537.36"
    sign_in(chrome)  # the first sign-in: nothing to compare with
    sign_in(chrome)
    assert _mail_to(app, "cfo@demo.lekhara") == []
    sign_in("Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36")
    sent = _mail_to(app, "cfo@demo.lekhara")
    assert len(sent) == 1 and "Chrome on Android" in sent[0].body


def test_owner_and_finance_hear_of_a_full_download(app) -> None:
    cfo = signed_in(app, "cfo@demo.lekhara")
    assert cfo.get("/organization/export").status_code == 200
    told = _mail_to(app, "promoter@demo.lekhara")
    assert any("downloaded everything" in m.subject for m in told)
    assert not any("downloaded everything" in m.subject for m in _mail_to(app, "cfo@demo.lekhara"))


def test_the_firm_can_require_two_step_sign_in(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    clerk = signed_in(app, "accounts@demo.lekhara")
    refused = owner.put("/organization/two-step-rule", json={"required": True})
    assert refused.status_code == 400 and "for yourself first" in refused.json()["detail"]

    secret = owner.post("/auth/two-step/start").json()["secret"].replace(" ", "")
    owner.post(
        "/auth/two-step/confirm", json={"code": two_step.code_at(secret, int(time.time() // 30))}
    )
    assert owner.put("/organization/two-step-rule", json={"required": True}).status_code == 200
    assert clerk.get("/auth/me").json()["two_step_needed"] is True
    blocked = clerk.get("/projects")
    assert blocked.status_code == 403
    assert blocked.headers["X-Lekhara-Two-Step"] == "required"

    clerk_secret = clerk.post("/auth/two-step/start").json()["secret"].replace(" ", "")
    clerk.post(
        "/auth/two-step/confirm",
        json={"code": two_step.code_at(clerk_secret, int(time.time() // 30))},
    )
    assert clerk.get("/projects").status_code == 200
    assert owner.get("/organization").json()["require_two_step"] is True


def test_leaked_passwords_are_refused(app, monkeypatch) -> None:
    def signup(email: str):
        return TestClient(app).post(
            "/auth/signup",
            json={"accept_terms": True, "name": "Anil", "email": email,
                  "password": "password1234", "firm": "Kaveri Homes"},
        )  # fmt: skip

    monkeypatch.setattr(passwords, "times_leaked", lambda password, timeout=2.0: 52_000)
    refused = signup("anil@kaveri.in")
    assert refused.status_code == 400 and "data breaches" in refused.json()["detail"]

    def unreachable(password, timeout=2.0):
        raise OSError("no network")

    monkeypatch.setattr(passwords, "times_leaked", unreachable)
    assert signup("anil@kaveri.in").status_code == 201  # never blocked by the service being down


def test_the_range_check_sends_only_a_hash_prefix(monkeypatch) -> None:
    import hashlib

    digest = hashlib.sha1(b"password1234", usedforsecurity=False).hexdigest().upper()
    asked = {}

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return f"{digest[5:]}:52000\r\n{'0' * 35}:1".encode()

    def urlopen(request, timeout):
        asked["url"] = request.full_url
        return Answer()

    monkeypatch.setattr(passwords.urllib.request, "urlopen", urlopen)
    # The real function (imported before the tests' stand-in replaced the module's).
    assert real_times_leaked("password1234") == 52000
    assert asked["url"] == passwords.RANGE_URL + digest[:5]  # only five characters leave
