from email.message import EmailMessage

import bank_samples as samples
import pytest
from fastapi.testclient import TestClient
from tally_samples import full_xml_utf16

from lekhara import inbound, jobs
from lekhara.app import create_app
from lekhara.config import Settings
from lekhara.db import make_sessionmaker
from lekhara.models import InboundMessage, Job, Project
from lekhara.pdf import write_pdf

PASSWORD = "a-long-password"
DOMAIN = "in.lekhara.test"
SECRET = "inbound-secret"


@pytest.fixture
def mail_app(engine, tmp_path):
    from conftest import TODAY

    return create_app(
        Settings(
            database_url="sqlite://",
            today=TODAY,
            auto_migrate=False,
            demo=True,
            storage_dir=str(tmp_path / "files"),
            inbound_domain=DOMAIN,
            inbound_secret=SECRET,
            worker=False,
        ),
        engine=engine,
    )


def firm(app) -> tuple[TestClient, str, str]:
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
    for label, buyer in (("A-101", "Priya Sharma"), ("A-102", "Rahul Kumar")):
        client.post(
            f"/projects/{project}/units",
            json={
                "label": label,
                "carpet_area_sqft": "1100",
                "buyer_name": buyer,
                "booked_on": "01/03/2026",
                "agreement_value": "90 lakh",
            },
        )
    address = client.get(f"/projects/{project}/inbound").json()["address"]
    return client, project, address


def mail(to: str, files: list[tuple[str, bytes]], sender="anil@kaverihomes.in", **headers) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"Anil <{sender}>"
    msg["To"] = to
    msg["Subject"] = headers.pop("subject", "Statements")
    for name, value in headers.items():
        msg[name.replace("_", "-")] = value
    msg.set_content("Please find attached.")
    for filename, data in files:
        msg.add_attachment(data, maintype="application", subtype="octet-stream", filename=filename)
    return msg.as_bytes()


def post(app, raw: bytes, **kwargs):
    return TestClient(app).post(
        "/inbound/email",
        content=raw,
        headers={"Content-Type": "message/rfc822", "X-Lekhara-Inbound-Secret": SECRET},
        **kwargs,
    )


def run(app) -> None:
    jobs.run_pending(app.state.session_factory, app.state.storage, app.state.settings)


def items(client, project) -> list[dict]:
    return [
        i for m in client.get(f"/projects/{project}/inbound").json()["messages"] for i in m["items"]
    ]


def test_each_project_has_an_address(mail_app) -> None:
    client, project, address = firm(mail_app)
    assert address.endswith(f"@{DOMAIN}") and address.startswith("kaveri-heights-")
    assert client.get(f"/projects/{project}/inbound").json()["address"] == address


def test_the_endpoint_wants_the_secret(mail_app, app) -> None:
    _, _, address = firm(mail_app)
    raw = mail(address, [])
    assert TestClient(app).post("/inbound/email", content=raw).status_code == 404  # not set up
    wrong = TestClient(mail_app).post(
        "/inbound/email", content=raw, headers={"X-Lekhara-Inbound-Secret": "no"}
    )
    assert wrong.status_code == 403
    assert post(mail_app, mail(f"nobody@{DOMAIN}", [])).json() == {"status": "no_project"}
    assert post(mail_app, raw).json()["status"] == "done"  # nothing attached


def test_a_statement_from_the_team_comes_in_by_itself(mail_app) -> None:
    client, project, address = firm(mail_app)
    first = client.post(
        f"/projects/{project}/bank-statements",
        files={"file": ("s.csv", samples.icici_csv(samples.COLLECTION_LINES[:1]), "text/csv")},
    ).json()["id"]
    client.put(f"/bank-statements/{first}/options", json={"role": "collections"})

    r = post(mail_app, mail(address, [("Acct Statement.xls", samples.hdfc_xls())]))
    assert r.status_code == 202 and r.json()["status"] == "queued"
    run(mail_app)
    [item] = items(client, project)
    assert item["kind"] == "bank_statement" and item["link"].startswith("/bank/")
    # One payer could not be matched, so the statement came in except for that line.
    assert item["status"] == "review" and "Brought in" in item["note"]
    unit = next(
        u for u in client.get(f"/projects/{project}/units").json()["units"] if u["label"] == "A-101"
    )
    assert len(client.get(f"/units/{unit['id']}").json()["receipts"]) == 1


def test_someone_outside_the_team_waits(mail_app) -> None:
    client, project, address = firm(mail_app)
    data = write_pdf([["Fire NOC", "Karnataka Fire and Emergency Services"]], title="NOC")
    r = post(mail_app, mail(address, [("Fire NOC.pdf", data)], sender="contractor@builders.in"))
    assert r.json()["status"] == "held"
    run(mail_app)
    view = client.get(f"/projects/{project}/inbound").json()
    assert (
        view["messages"][0]["status"] == "held"
        and view["messages"][0]["items"][0]["status"] == "queued"
    )

    allowed = client.post(f"/inbound/{r.json()['id']}/allow", json={"trust": True}).json()
    item = allowed["messages"][0]["items"][0]
    assert item["status"] == "done" and item["link"].startswith("/documents/")
    doc = client.get(item["link"]).json()
    assert doc["category"] == "approval" and "contractor@builders.in" in doc["notes"]

    senders = client.get("/organization/inbound").json()["senders"]
    assert [s["address"] for s in senders] == ["contractor@builders.in"]
    again = post(
        mail_app,
        mail(
            address, [("RA bill 4.pdf", write_pdf([["RA bill"]]))], sender="contractor@builders.in"
        ),
    )
    assert again.json()["status"] == "queued"

    stranger = post(
        mail_app, mail(address, [("x.pdf", write_pdf([["x"]]))], sender="x@spam.example")
    )
    turned = client.post(f"/inbound/{stranger.json()['id']}/reject").json()
    assert (
        next(m for m in turned["messages"] if m["id"] == stranger.json()["id"])["status"]
        == "rejected"
    )


def test_a_forged_sender_is_not_trusted(mail_app) -> None:
    _, _, address = firm(mail_app)
    raw = mail(
        address,
        [("s.xls", samples.hdfc_xls())],
        Authentication_Results="mx.example; spf=fail smtp.mailfrom=kaverihomes.in; dkim=fail",
    )
    assert post(mail_app, raw).json()["status"] == "held"


def test_tally_sheets_and_documents(mail_app) -> None:
    client, project, address = firm(mail_app)
    bills = "Supplier,Bill No,Bill Date,Taxable Value\nBharat TMT Steel,BTS/1,05/04/2026,100000\n"
    raw = mail(
        address,
        [
            ("DayBook.xml", full_xml_utf16()),
            ("bills.csv", bills.encode()),
            ("Title deed.pdf", write_pdf([["Sale deed of the land"]])),
        ],
    )
    post(mail_app, raw)
    run(mail_app)
    by_name = {i["filename"]: i for i in items(client, project)}
    assert by_name["DayBook.xml"]["kind"] == "tally" and by_name["DayBook.xml"]["link"].startswith(
        "/tally/"
    )
    assert by_name["bills.csv"]["status"] == "review"
    assert by_name["bills.csv"]["link"].startswith("/imports/")
    assert "suppliers' bills" in by_name["bills.csv"]["note"]
    assert by_name["Title deed.pdf"]["kind"] == "document"


def test_a_protected_statement_waits_for_its_password(mail_app) -> None:
    client, project, address = firm(mail_app)
    data = samples.statement_pdf(password="KAVE0104")
    post(mail_app, mail(address, [("Statement.pdf", data)]))
    run(mail_app)
    [item] = items(client, project)
    assert item["status"] == "review" and "password" in item["note"] and item["can_retry"]

    assert (
        client.post(
            "/organization/statement-passwords",
            json={"label": "HDFC collection", "password": "KAVE0104"},
        ).status_code
        == 201
    )
    listed = client.get("/organization/inbound").json()["passwords"]
    assert [p["label"] for p in listed] == ["HDFC collection"] and "password" not in listed[0]
    retried = client.post(f"/inbound/items/{item['id']}/retry").json()
    item = retried["messages"][0]["items"][0]
    assert item["kind"] == "bank_statement" and item["link"].startswith("/bank/")
    assert "which account" in item["note"]
    statement = client.get(f"/bank-statements/{item['link'].split('/')[-1]}").json()
    assert len(statement["lines"]) == len(samples.COLLECTION_LINES)


def test_jobs_retry_then_give_up(mail_app) -> None:
    calls = []

    @jobs.handler("test.flaky")
    def flaky(ctx, payload):
        calls.append(payload)
        raise RuntimeError("down")

    factory = mail_app.state.session_factory
    with factory() as session:
        job = jobs.enqueue(session, "test.flaky", {"n": 1})
        session.commit()
        job_id = job.id
    run(mail_app)
    with factory() as session:
        job = session.get(Job, job_id)
        assert job.status == "queued" and job.attempts == 1 and "down" in job.last_error
        job.attempts = jobs.MAX_ATTEMPTS - 1
        job.run_after = job.created_at
        session.commit()
    run(mail_app)
    with factory() as session:
        assert session.get(Job, job_id).status == "failed"
    assert len(calls) == 2


def test_the_mailbox_address_is_read() -> None:
    host, port, user, password, folder, secure = inbound._mailbox(
        "imaps://in%40kaveri.in:p%40ss@imap.example.com/Lekhara"
    )
    assert (host, port, user, password, folder, secure) == (
        "imap.example.com",
        993,
        "in@kaveri.in",
        "p@ss",
        "Lekhara",
        True,
    )


def test_only_the_team_sees_a_project_mailbox(mail_app, architect, engine) -> None:
    client, project, _ = firm(mail_app)
    with make_sessionmaker(engine)() as session:
        assert session.get(Project, project).mail_token
        assert session.query(InboundMessage).count() == 0
    assert architect.get(f"/projects/{project}/inbound").status_code == 404


def test_an_emailed_gstr2b_waits_to_be_checked(mail_app) -> None:
    import gst_samples

    client, project, address = firm(mail_app)
    post(mail_app, mail(address, [("GSTR2B_092026.json", gst_samples.gstr2b_json())]))
    run(mail_app)
    [item] = items(client, project)
    assert item["status"] == "review" and item["link"].startswith("/gst/")
    assert "GSTR-2B" in item["note"]
