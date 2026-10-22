import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from lekhara.app import create_app
from lekhara.config import Settings
from lekhara.db import Base, make_engine, make_sessionmaker
from lekhara.seed import DEMO_PASSWORD, seed

TODAY = date(2026, 10, 17)

POSTGRES = os.environ.get("LEKHARA_TEST_DATABASE_URL")
"""Set to a Postgres URL with rights to drop and create the schema, to run the tests on
Postgres instead of SQLite, with row-level security in force."""


def _postgres_engine():
    from lekhara import rls

    admin = make_engine(POSTGRES)
    with admin.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(admin)
    with admin.begin() as conn:
        rls.install(conn)
        rls.grant(conn, "lekhara_app", "lekhara-app-test")
    admin.dispose()
    host = POSTGRES.split("@", 1)[1]
    return make_engine(f"postgresql+psycopg://lekhara_app:lekhara-app-test@{host}")


@pytest.fixture(autouse=True)
def _no_breach_service(monkeypatch):
    """Tests never call the leaked-password service; test_security checks it with a stand-in."""
    from lekhara import passwords

    monkeypatch.setattr(passwords, "times_leaked", lambda password, timeout=2.0: 0)


@pytest.fixture
def engine():
    engine = _postgres_engine() if POSTGRES else make_engine("sqlite://")
    if not POSTGRES:
        Base.metadata.create_all(engine)
    with make_sessionmaker(engine)() as session:
        seed(session, TODAY)
    return engine


@pytest.fixture
def app(engine, tmp_path):
    return create_app(
        Settings(
            database_url="sqlite://",
            today=TODAY,
            auto_migrate=False,
            demo=True,
            storage_dir=str(tmp_path / "files"),
        ),
        engine=engine,
    )


@pytest.fixture
def client(app) -> TestClient:
    """Not signed in."""
    return TestClient(app)


def signed_in(app, email: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return client


@pytest.fixture
def owner(app) -> TestClient:
    return signed_in(app, "promoter@demo.lekhara")


@pytest.fixture
def cfo(app) -> TestClient:
    return signed_in(app, "cfo@demo.lekhara")


@pytest.fixture
def accounts(app) -> TestClient:
    return signed_in(app, "accounts@demo.lekhara")


@pytest.fixture
def architect(app) -> TestClient:
    return signed_in(app, "architect@demo.lekhara")


@pytest.fixture
def engineer(app) -> TestClient:
    return signed_in(app, "engineer@demo.lekhara")


@pytest.fixture
def ca(app) -> TestClient:
    return signed_in(app, "ca@demo.lekhara")
