import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tally_samples import MASTERS, VOUCHERS, envelope

from lekhara.db import make_sessionmaker
from lekhara.models import Organization, TallyImport

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "connector"))
import lekhara_connector as program  # noqa: E402

PASSWORD = "a-long-password"
SERVER = "http://lekhara.test"
TALLY = "http://localhost:9000"


def firm(app) -> tuple[TestClient, str]:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={
            "accept_terms": True,
            "name": "Anil",
            "email": "anil@kaverihomes.in",
            "password": PASSWORD,
            "firm": "Kaveri Homes LLP",
        },
    )
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    project = client.post(
        "/projects",
        json={
            "name": "Kaveri Heights",
            "krera_registration": "PRM/K/1",
            "registered_on": "2025-04-01",
        },
    ).json()["id"]
    return client, project


def masters() -> bytes:
    return envelope(MASTERS).encode("utf-16")


def vouchers() -> bytes:
    return envelope(VOUCHERS).encode("utf-16")


def code_for(client, project) -> str:
    r = client.post(f"/projects/{project}/connectors")
    assert r.status_code == 201, r.text
    return r.json()["code"]


def send(app, key, **files):
    return TestClient(app).post(
        "/connector/tally",
        headers={"X-Lekhara-Connector": key},
        files={name: (f"{name}.xml", data, "application/xml") for name, data in files.items()},
        data={"company": "Kaveri Homes LLP"},
    )


def test_linking_and_syncing(app) -> None:
    client, project = firm(app)
    code = code_for(client, project)
    plain = TestClient(app)
    assert plain.post("/connector/link", json={"code": "WRONG-CODE"}).status_code == 400
    linked = plain.post(
        "/connector/link", json={"code": code.lower(), "name": "ACCOUNTS-PC"}
    ).json()
    key = linked["key"]
    assert key.startswith("lkc_") and linked["project"] == "Kaveri Heights"
    assert plain.post("/connector/link", json={"code": code}).status_code == 400  # once only

    assert plain.get("/connector/config").status_code == 401
    assert plain.get("/connector/config", headers={"X-Lekhara-Connector": key}).status_code == 200

    first = send(app, key, masters=masters(), vouchers=vouchers())
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "applied"
    imported = client.get(f"/tally/{first.json()['import_id']}").json()
    assert imported["status"] == "applied" and imported["found"]["vouchers"] > 0

    again = send(app, key, vouchers=vouchers())  # the masters from before are used again
    assert again.json()["status"] == "unchanged"

    listed = client.get(f"/projects/{project}/connectors").json()["connectors"]
    assert listed[0]["name"] == "ACCOUNTS-PC" and listed[0]["company"] == "Kaveri Homes LLP"
    assert listed[0]["last_sync_at"] and listed[0]["status"] == "active"

    client.post(f"/connectors/{listed[0]['id']}/unlink")
    assert send(app, key, vouchers=vouchers()).status_code == 401
    assert client.get(f"/projects/{project}/connectors").json()["connectors"] == []


def test_choices_wait_in_the_review_queue(app) -> None:
    client, project = firm(app)
    key = (
        TestClient(app)
        .post("/connector/link", json={"code": code_for(client, project)})
        .json()["key"]
    )
    send(app, key, masters=masters(), vouchers=vouchers())
    titles = [i["title"] for i in client.get("/review").json()["items"]]
    assert "Choices for the connected Tally" in titles


def test_a_read_only_firm_takes_no_new_data(app, engine) -> None:
    client, project = firm(app)
    key = (
        TestClient(app)
        .post("/connector/link", json={"code": code_for(client, project)})
        .json()["key"]
    )
    with make_sessionmaker(engine)() as session:
        org = session.query(Organization).filter_by(name="Kaveri Homes LLP").one()
        org.trial_ends_on = date(2026, 10, 1)
        session.commit()
    assert send(app, key, masters=masters(), vouchers=vouchers()).status_code == 402


def test_only_the_team_can_link(app, architect) -> None:
    client, project = firm(app)
    assert architect.post(f"/projects/{project}/connectors").status_code == 404


# The program on the Tally computer


class Fakes:
    """Tally on this computer, and Lekhara, for the connector to talk to."""

    def __init__(self, app) -> None:
        self.client = TestClient(app)
        self.tally_up = True
        self.requests: list[str] = []
        self.ids: tuple[int, int] | None = (40, 900)  # the company's AlterIDs; None: no answer

    def __call__(self, method, url, body, headers):
        if url.startswith(TALLY):
            if not self.tally_up:
                raise OSError("connection refused")
            request = body.decode()
            if "LekharaAlterIds" in request:
                self.requests.append("ids")
                if self.ids is None:
                    return 200, b"<ENVELOPE></ENVELOPE>"  # an older Tally
                return 200, f'"{self.ids[0]}","{self.ids[1]}"\r\n'.encode()
            self.requests.append("masters" if "List of Accounts" in request else "daybook")
            return 200, masters() if "List of Accounts" in request else vouchers()
        path = url.removeprefix(SERVER)
        r = self.client.request(method, path, content=body, headers=headers)
        return r.status_code, r.content


@pytest.fixture
def clock():
    class Clock:
        moment = datetime(2026, 10, 17, 10, 0)

        def now(self):
            return self.moment

        def today(self):
            return self.moment.date()

    return Clock()


def test_the_connector_program(app, tmp_path, clock) -> None:
    client, project = firm(app)
    fakes = Fakes(app)
    said: list[str] = []
    connector = program.Connector(
        tmp_path, http=fakes, today=clock.today, now=clock.now, log=said.append
    )
    with pytest.raises(program.LekharaError):
        connector.sync_once()
    connector.link(code_for(client, project), SERVER)
    assert connector.linked and (tmp_path / "connector.json").exists()

    message = connector.sync_once()
    assert message.startswith("Brought in") and fakes.requests == ["ids", "masters", "daybook"]
    assert connector.config["full_at"] and connector.config["masters_at"]
    assert connector.config["alter_ids"] == [40, 900]
    with make_sessionmaker(app.state.session_factory.kw["bind"])() as session:
        assert session.query(TallyImport).count() >= 1

    # Nothing changed in Tally: only the two numbers are asked for, nothing is exported.
    clock.moment += timedelta(minutes=5)
    assert connector.sync_once() == "No change in Tally since the last sync."
    assert fakes.requests[-1] == "ids" and fakes.requests.count("daybook") == 1

    # A voucher changed: the day book is exported, the masters are not.
    fakes.ids = (40, 901)
    clock.moment += timedelta(minutes=5)
    connector.sync_once()
    assert fakes.requests[-2:] == ["ids", "daybook"] and fakes.requests.count("masters") == 1

    # A master changed: both.
    fakes.ids = (41, 901)
    clock.moment += timedelta(minutes=5)
    connector.sync_once()
    assert fakes.requests[-3:] == ["ids", "masters", "daybook"]

    # An older Tally that cannot answer: the connector exports and compares as before.
    fakes.ids = None
    clock.moment += timedelta(minutes=5)
    assert connector.sync_once() == "No change in Tally since the last sync."
    assert fakes.requests[-2:] == ["ids", "daybook"]
    fakes.ids = (41, 901)

    fakes.tally_up = False
    clock.moment += timedelta(minutes=5)
    assert "did not answer" in connector.sync_once()
    seen = client.get(f"/projects/{project}/connectors").json()["connectors"][0]
    assert "did not answer" in seen["last_state"]

    fakes.tally_up = True
    clock.moment += timedelta(hours=25)
    connector.sync_once()
    assert fakes.requests[-3:] == ["ids", "masters", "daybook"]  # the nightly full sync

    connector.unlink()
    assert not connector.linked and not (tmp_path / "connector.json").exists()


def test_financial_year() -> None:
    assert program.financial_year_start(date(2026, 10, 17)) == date(2026, 4, 1)
    assert program.financial_year_start(date(2027, 2, 1)) == date(2026, 4, 1)
