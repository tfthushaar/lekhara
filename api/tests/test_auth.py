from lekhara.auth import LoginThrottle, hash_password, verify_password
from lekhara.seed import DEMO_PASSWORD

WF = "whitefield-residences"
SG = "sarjapur-greens"


def test_passwords_are_hashed_and_checked() -> None:
    stored = hash_password("correct horse")
    assert stored.startswith("scrypt$")
    assert "correct horse" not in stored
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert not verify_password("anything", "not-a-hash")


def test_everything_but_health_and_rules_needs_sign_in(client) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/rules").status_code == 200
    for path in ("/today", "/projects", f"/projects/{WF}", f"/projects/{WF}/escrow"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json() == {"detail": "Sign in to continue."}


def test_wrong_password_is_refused(client) -> None:
    response = client.post(
        "/auth/login", json={"email": "promoter@demo.lekhara", "password": "guess"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "That email and password do not match."


def test_repeated_failures_are_throttled() -> None:
    throttle = LoginThrottle(limit=2, window_seconds=60)
    throttle.failed("a@b.c")
    throttle.check("a@b.c")
    throttle.failed("a@b.c")
    try:
        throttle.check("a@b.c")
    except Exception as exc:  # ServiceError
        assert getattr(exc, "status_code", None) == 429
    else:
        raise AssertionError("expected the throttle to refuse")


def test_email_is_case_insensitive(client) -> None:
    response = client.post(
        "/auth/login", json={"email": "  Promoter@Demo.Lekhara ", "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200


def test_me_describes_the_person(owner, ca) -> None:
    me = owner.get("/auth/me").json()
    assert me["kind"] == "team"
    assert me["role_label"] == "Owner"
    assert me["organizations"] == ["Demo Builders"]

    me = ca.get("/auth/me").json()
    assert me["kind"] == "certifier"
    assert me["role_label"] == "Chartered accountant"
    assert me["user"]["firm"] == "Menon and Associates"


def test_logout_ends_the_session(owner) -> None:
    assert owner.post("/auth/logout").status_code == 204
    assert owner.get("/today").status_code == 401


def test_demo_accounts_are_listed_only_in_demo_mode(client) -> None:
    body = client.get("/auth/demo").json()
    assert body["password"] == DEMO_PASSWORD
    assert {a["email"] for a in body["accounts"]} >= {"promoter@demo.lekhara", "ca@demo.lekhara"}


def test_certifier_today_lists_certificates_to_sign(ca, architect) -> None:
    body = ca.get("/today").json()
    assert body["kind"] == "certifier"
    assert body["organization"] == "Menon and Associates"
    keys = [i["key"] for i in body["items"]]
    assert len(keys) == 1 and keys[0].endswith(":ca")
    assert body["items"][0]["link"].startswith("/withdrawals/")

    # The architect has already signed the open Sarjapur withdrawal.
    assert architect.get("/today").json()["items"] == []


def test_certifiers_see_escrow_but_not_tax(ca) -> None:
    assert ca.get(f"/projects/{WF}").status_code == 200
    assert ca.get(f"/projects/{WF}/escrow").status_code == 200
    assert ca.get(f"/projects/{WF}/money").status_code == 200
    assert ca.get(f"/projects/{WF}/tax").status_code == 403
    assert ca.get(f"/projects/{WF}/units").status_code == 403
    detail = ca.get(f"/projects/{WF}").json()
    assert {o["area"] for o in detail["obligations"]} <= {"escrow"}
    assert detail["access"] == {"sample": False, "team": False, "certifies": ["ca"]}


def test_certifiers_cannot_start_withdrawals(ca) -> None:
    assert ca.get(f"/projects/{WF}/escrow").json()["can_start"] is False
    assert ca.post(f"/projects/{WF}/withdrawals", json={}).status_code == 403


def test_each_certifier_signs_only_their_own_certificate(owner, architect, engineer) -> None:
    request_id = owner.get(f"/projects/{SG}").json()["open_request_id"]
    response = engineer.post(f"/withdrawals/{request_id}/certificates/ca/sign", json={})
    assert response.status_code == 403
    assert response.json()["detail"] == "Only the project's chartered accountant can do this."
    assert owner.post(f"/withdrawals/{request_id}/certificates/ca/sign", json={}).status_code == 403
    assert (
        architect.put(
            f"/withdrawals/{request_id}/certificates/ca", json={"total_cost_incurred": "1"}
        ).status_code
        == 403
    )


def test_team_sees_start_button_and_no_sign_rights(owner) -> None:
    assert owner.get(f"/projects/{WF}/escrow").json()["can_start"] is True
    request_id = owner.get(f"/projects/{SG}").json()["open_request_id"]
    permissions = owner.get(f"/withdrawals/{request_id}").json()["permissions"]
    assert permissions["sign_roles"] == []
    assert permissions["edit_roles"] == []
