from datetime import date

import pytest
from fastapi.testclient import TestClient

from horus.app import create_app
from horus.config import Settings
from horus.db import Base, make_engine, make_sessionmaker
from horus.seed import seed

TODAY = date(2026, 10, 17)


@pytest.fixture
def engine():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_sessionmaker(engine)() as session:
        seed(session, TODAY)
    return engine


@pytest.fixture
def client(engine) -> TestClient:
    app = create_app(
        Settings(database_url="sqlite://", today=TODAY, auto_migrate=False), engine=engine
    )
    return TestClient(app)
