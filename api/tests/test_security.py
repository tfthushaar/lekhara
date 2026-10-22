"""Limits per network address, and two-step sign-in with an authenticator app."""

import time
from datetime import date

from fastapi.testclient import TestClient

from lekhara import two_step
from lekhara.app import create_app
from lekhara.config import Settings

PASSWORD = "a-long-password"


def signup(client: TestClient, email: str):
    return client.post(
        "/auth/signup",
        json={
            "accept_terms": True,
            "name": "Anil",
            "email": email,
            "password": PASSWORD,
            "firm": "Kaveri Homes",
        },
    )


def test_limits_per_network_address(engine, tmp_path) -> None:
    app = create_app(
        Settings(
            database_url="sqlite://",
            today=date(2026, 10, 17),
            auto_migrate=False,
            storage_dir=str(tmp_path / "files"),
            signups_per_hour=2,
            resets_per_hour=2,
            failed_logins_per_address=3,
        ),
        engine=engine,
    )
    client = TestClient(app)
    assert signup(client, "a@kaveri.in").status_code == 201
    assert signup(client, "b@kaveri.in").status_code == 201
    third = signup(client, "c@kaveri.in")
    assert third.status_code == 429 and "this network" in third.json()["detail"]

    for email in ("x@kaveri.in", "y@kaveri.in"):
        assert client.post("/auth/forgot", json={"email": email}).status_code == 200
    assert client.post("/auth/forgot", json={"email": "z@kaveri.in"}).status_code == 429

    # Failed sign-ins are counted across emails from one address.
    for email in ("p@kaveri.in", "q@kaveri.in", "r@kaveri.in"):
        assert client.post("/auth/login", json={"email": email, "password": "x"}).status_code == 401
    blocked = client.post("/auth/login", json={"email": "a@kaveri.in", "password": PASSWORD})
    assert blocked.status_code == 429


def test_codes_follow_rfc_6238() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert two_step.code_at(secret, 59 // 30) == "287082"
    assert two_step.code_at(secret, 1111111109 // 30) == "081804"


def test_two_step_sign_in(app, monkeypatch) -> None:
    client = TestClient(app)
    token = signup(client, "anil@kaveri.in").json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.get("/auth/two-step").json()["on"] is False

    started = client.post("/auth/two-step/start").json()
    secret = started["secret"].replace(" ", "")
    assert started["uri"].startswith("otpauth://totp/Lekhara%3Aanil%40kaveri.in?secret=")
    wrong = client.post("/auth/two-step/confirm", json={"code": "000000"})
    assert wrong.status_code == 400
    now = time.time()
    code = two_step.code_at(secret, int(now // 30))
    recovery = client.post("/auth/two-step/confirm", json={"code": code}).json()["recovery_codes"]
    assert len(recovery) == 8
    assert client.get("/auth/two-step").json() == {
        **client.get("/auth/two-step").json(),
        "on": True,
        "recovery_left": 8,
    }

    fresh = TestClient(app)
    first = fresh.post("/auth/login", json={"email": "anil@kaveri.in", "password": PASSWORD}).json()
    assert first["two_step"] is True and "token" not in first
    ticket = first["ticket"]
    # The code just used to turn it on cannot be used again.
    again = fresh.post("/auth/login/two-step", json={"ticket": ticket, "code": code})
    assert again.status_code == 401
    monkeypatch.setattr(two_step.time, "time", lambda: now + 60)
    later = two_step.code_at(secret, int((now + 60) // 30))
    done = fresh.post("/auth/login/two-step", json={"ticket": ticket, "code": later})
    assert done.status_code == 200 and done.json()["token"]
    reused = fresh.post("/auth/login/two-step", json={"ticket": ticket, "code": later})
    assert reused.status_code == 401  # the ticket is spent

    # A recovery code works once.
    ticket = fresh.post(
        "/auth/login", json={"email": "anil@kaveri.in", "password": PASSWORD}
    ).json()["ticket"]
    ok = fresh.post("/auth/login/two-step", json={"ticket": ticket, "code": recovery[0]})
    assert ok.status_code == 200
    assert client.get("/auth/two-step").json()["recovery_left"] == 7

    assert client.post("/auth/two-step/disable", json={"password": "wrong"}).status_code == 401
    assert client.post("/auth/two-step/disable", json={"password": PASSWORD}).status_code == 200
    plain = fresh.post("/auth/login", json={"email": "anil@kaveri.in", "password": PASSWORD})
    assert plain.json()["token"]


class FakeClamd:
    """A stand-in for clamd: reads one INSTREAM and answers FOUND for the EICAR test string."""

    def __init__(self) -> None:
        import socket
        import threading

        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.port = self.server.getsockname()[1]
        self.scanned = 0
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        import struct

        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                conn.recv(10)  # zINSTREAM\0
                data = b""
                while True:
                    size = struct.unpack(">I", self._read(conn, 4))[0]
                    if size == 0:
                        break
                    data += self._read(conn, size)
                self.scanned += 1
                found = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data
                conn.sendall(b"stream: Eicar-Signature FOUND\0" if found else b"stream: OK\0")

    @staticmethod
    def _read(conn, n: int) -> bytes:
        out = b""
        while len(out) < n:
            out += conn.recv(n - len(out))
        return out


EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def test_uploads_are_checked_for_viruses(engine, tmp_path) -> None:
    from lekhara import scan

    clamd = FakeClamd()
    settings = Settings(
        database_url="sqlite://",
        today=date(2026, 10, 17),
        auto_migrate=False,
        demo=True,
        storage_dir=str(tmp_path / "files"),
        clamav_url=f"tcp://127.0.0.1:{clamd.port}",
    )
    scan.check(settings, b"a clean file")
    try:
        scan.check(settings, EICAR, "invoice.pdf")
        raise AssertionError("an infected file was let through")
    except scan.Infected as exc:
        assert "invoice.pdf carries a virus (Eicar-Signature)" in exc.message

    client = TestClient(create_app(settings, engine=engine))
    token = signup(client, "anil@kaveri.in").json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    project = client.post(
        "/projects",
        json={
            "name": "Kaveri Heights",
            "krera_registration": "PRM/K/9",
            "registered_on": "2025-04-01",
        },
    ).json()["id"]
    r = client.post(
        f"/projects/{project}/imports/units",
        files={"file": ("units.csv", EICAR, "text/csv")},
    )
    assert r.status_code == 400 and "carries a virus" in r.json()["detail"]
    assert clamd.scanned >= 3

    down = Settings(**{**settings.model_dump(), "clamav_url": "tcp://127.0.0.1:9"})
    try:
        scan.check(down, b"anything")
        raise AssertionError("an unchecked file was let through")
    except scan.ServiceError as exc:
        assert exc.status_code == 503


def test_postgres_keeps_firms_apart_even_without_the_code(engine) -> None:
    """With the code's own checks out of the way, a session restricted to one firm still cannot
    read or write another's rows."""
    import pytest
    from sqlalchemy import select

    from lekhara import rls
    from lekhara.db import make_sessionmaker
    from lekhara.models import Organization, Project, Unit

    if engine.dialect.name != "postgresql":
        pytest.skip("Row-level security is a Postgres feature.")
    make = make_sessionmaker(engine)
    with make() as session:
        sample = session.scalars(select(Organization).where(Organization.is_sample)).first()
        other = Organization(name="Another Builder", access="active")
        session.add(other)
        session.flush()
        project = Project(
            organization_id=other.id,
            name="Elsewhere",
            locality="",
            city="Bengaluru",
            krera_registration="PRM/X/1",
            registered_on=date(2025, 4, 1),
            spv_name="",
            gst_regime="residential_5pc",
            land_structure="own",
        )
        session.add(project)
        session.flush()
        session.add(
            Unit(
                project_id=project.id,
                label="Z-1",
                tower="",
                carpet_area_sqft=1000,
                owner_share="developer",
                list_price=1,
                guidance_value=1,
            )
        )
        session.commit()
        other_id, project_id, sample_id = other.id, project.id, sample.id

    with make() as session:
        rls.restrict(session, {sample_id}, set())
        assert session.scalars(select(Unit).where(Unit.project_id == project_id)).all() == []
        assert session.get(Organization, other_id) is None
        assert session.scalars(select(Unit)).first() is not None  # the sample is still visible
        session.add(
            Unit(
                project_id=project_id,
                label="Z-2",
                tower="",
                carpet_area_sqft=1000,
                owner_share="developer",
                list_price=1,
                guidance_value=1,
            )
        )
        with pytest.raises(Exception, match="row-level security"):
            session.commit()
        session.rollback()

    with make() as session:
        rls.restrict(session, {other_id}, set())
        assert len(session.scalars(select(Unit).where(Unit.project_id == project_id)).all()) == 1


def test_the_api_does_not_describe_itself_unless_asked(engine, tmp_path) -> None:
    def client(**extra):
        settings = Settings(database_url="sqlite://", auto_migrate=False,
                            storage_dir=str(tmp_path / "files"), **extra)  # fmt: skip
        return TestClient(create_app(settings, engine=engine))

    closed = client()
    assert closed.get("/docs").status_code == 404
    assert closed.get("/openapi.json").status_code == 404
    assert client(api_docs=True).get("/openapi.json").status_code == 200
