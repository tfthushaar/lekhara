import re
from datetime import date, timedelta

import pytest
from conftest import signed_in
from fastapi.testclient import TestClient
from sqlalchemy import select

from lekhara.app import create_app
from lekhara.config import Settings
from lekhara.db import Base, make_engine, make_sessionmaker
from lekhara.engines.documents import (
    REQUIREMENTS,
    HeldDocument,
    checklist,
    record_check,
    snippets,
)
from lekhara.models import OutboundEmail
from lekhara.pdf import read_pages, write_pdf
from lekhara.seed import DEMO_ROOM_TOKEN, seed
from lekhara.storage import LocalStorage

TODAY = date(2026, 10, 17)
SG = "sarjapur-greens"
HB = "hebbal-heights"


def held(**kw) -> HeldDocument:
    base = {"document_id": "d1", "title": "Fire NOC", "category": "approval"}
    base.update(kw)
    return HeldDocument(**base)


# The engine


def test_checklist_states() -> None:
    reqs = [
        REQUIREMENTS[k] for k in ("fire_noc", "insurance", "plan_sanction", "title_deed", "jda")
    ]
    items = checklist(
        reqs,
        [
            held(document_id="a", requirement="fire_noc", expires_on=TODAY + timedelta(days=20)),
            held(document_id="b", requirement="insurance", expires_on=TODAY - timedelta(days=1)),
            held(
                document_id="c", requirement="plan_sanction", expires_on=TODAY + timedelta(days=400)
            ),
            held(
                document_id="d", requirement="plan_sanction", expires_on=TODAY + timedelta(days=9)
            ),
        ],
        {"jda": "Own land"},
        as_of=TODAY,
        notice_days=60,
    )
    status = {i.requirement.key: (i.status, i.document_id) for i in items}
    assert status == {
        "fire_noc": ("expiring", "a"),
        "insurance": ("expired", "b"),
        "plan_sanction": ("held", "c"),  # the latest-expiring copy counts
        "title_deed": ("missing", None),
        "jda": ("waived", None),
    }


def test_record_check_lists_what_is_missing() -> None:
    check = record_check(
        "sale_deeds",
        "Registered sale deeds",
        "sale_deed",
        "unit",
        [("u1", "Unit A"), ("u2", "Unit B")],
        [held(category="sale_deed", link_type="unit", link_id="u1")],
    )
    assert (check.needed, check.held, check.missing) == (2, 1, (("u2", "Unit B"),))


def test_snippets_show_the_words_around_each_match() -> None:
    text = "The promoter shall refund the amount.\nThe REFUND is due within sixty days."
    found = snippets(text, "refund")
    assert [s.match for s in found] == ["refund", "REFUND"]
    assert found[0].before == "The promoter shall "
    assert snippets(text, "nothing like this") == []


def test_storage_keeps_one_copy_per_content(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    key = storage.put(b"same bytes")
    assert storage.put(b"same bytes") == key
    assert storage.get(key) == b"same bytes"
    with pytest.raises(ValueError):
        storage.get("../../etc/passwd")


def test_pdf_text_comes_back_page_by_page() -> None:
    data = write_pdf([["First page"], ["Second page, Rs. 1,000 (demo)"]], title="Two pages")
    assert read_pages(data) == ["First page", "Second page, Rs. 1,000 (demo)"]
    assert read_pages(b"not a pdf") is None


# Through the API, with the demo vault


@pytest.fixture
def vault(tmp_path):
    files = tmp_path / "files"
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_sessionmaker(engine)() as session:
        seed(session, TODAY, LocalStorage(files))
    return create_app(
        Settings(
            database_url="sqlite://",
            today=TODAY,
            auto_migrate=False,
            demo=True,
            storage_dir=str(files),
        ),
        engine=engine,
    )


@pytest.fixture
def boss(vault) -> TestClient:
    return signed_in(vault, "promoter@demo.lekhara")


@pytest.fixture
def clerk(vault) -> TestClient:
    return signed_in(vault, "accounts@demo.lekhara")


def pdf(text: str) -> bytes:
    return write_pdf([[text]], title=text)


def upload(client, project, data, filename="file.pdf", **fields):
    return client.post(
        f"/projects/{project}/documents",
        files={"file": (filename, data, "application/octet-stream")},
        data={k: v for k, v in fields.items() if v is not None},
    )


def checklist_status(client, project) -> dict:
    d = client.get(f"/projects/{project}/documents").json()
    return {i["key"]: i["status"] for i in d["checklist"]}


def test_the_demo_vault(boss) -> None:
    d = boss.get(f"/projects/{SG}/documents").json()
    assert checklist_status(boss, SG)["insurance"] == "expired"
    records = {r["key"]: (r["held"], r["needed"]) for r in d["records"]}
    assert records["sale_deeds"] == (14, 20)
    assert records["order_copies"] == (1, 2)
    assert d["rooms"][0]["state"] == "open"

    hb = checklist_status(boss, HB)
    assert hb["title_deed"] == "missing"
    assert hb["environmental"] == "waived"
    assert "jda" not in hb and "oc" not in hb

    today = [i for i in boss.get("/today").json()["items"] if i["area"] == "documents"]
    lapsed = next(i for i in today if i["status"] == "overdue")
    assert lapsed["title"] == "Contractor's all-risk insurance has expired"
    assert lapsed["link"].startswith("/documents/")


def test_upload_answers_the_checklist_and_is_searchable(clerk) -> None:
    r = upload(
        clerk,
        HB,
        pdf("Mother deed for survey number 77/3, Hebbal (demo)"),
        filename="mother-deed.pdf",
        requirement="title_deed",
        document_date="2010-05-01",
    )
    assert r.status_code == 201, r.text
    doc = clerk.get(f"/documents/{r.json()['id']}").json()
    assert doc["title"] == "Title deed and mother deed"
    assert doc["category"] == "title"
    assert doc["pages"] == 1 and doc["text_status"] == "text"
    assert checklist_status(clerk, HB)["title_deed"] == "held"

    hits = clerk.get(f"/projects/{HB}/documents/search", params={"q": "77/3"}).json()["results"]
    assert hits[0]["page"] == 1
    assert hits[0]["snippets"][0]["match"] == "77/3"


def test_uploads_are_checked(clerk) -> None:
    assert upload(clerk, HB, b"MZ\x90\x00", filename="tool.exe").status_code == 400
    fake = upload(clerk, HB, b"<html>not a pdf</html>", filename="notice.pdf")
    assert fake.status_code == 400
    assert "does not look like a PDF" in fake.json()["detail"]
    assert upload(clerk, HB, b"", filename="empty.pdf").status_code == 400
    assert upload(clerk, HB, pdf("x"), category="nonsense").status_code == 400

    first = upload(clerk, HB, pdf("A letter"), filename="letter.pdf")
    assert first.status_code == 201
    again = upload(clerk, HB, pdf("A letter"), filename="copy-of-letter.pdf")
    assert again.status_code == 400
    assert "already in the vault" in again.json()["detail"]


def test_a_new_version_replaces_the_old_and_keeps_it(clerk) -> None:
    d = clerk.get(f"/projects/{HB}/documents").json()
    noc = next(i for i in d["checklist"] if i["key"] == "fire_noc")
    assert noc["status"] == "expiring"
    r = upload(
        clerk,
        HB,
        pdf("Fire NOC, renewed for two years (demo)"),
        replaces=noc["document_id"],
        expires_on="2028-10-31",
    )
    new = clerk.get(f"/documents/{r.json()['id']}").json()
    assert new["version"] == 2
    assert new["requirement"] == "fire_noc"
    assert [v["version"] for v in new["versions"]] == [2, 1]
    assert checklist_status(clerk, HB)["fire_noc"] == "held"
    titles = [x["title"] for x in clerk.get(f"/projects/{HB}/documents").json()["documents"]]
    assert titles.count("Fire NOC") == 1

    old = clerk.get(f"/documents/{noc['document_id']}/file")
    assert old.status_code == 200
    assert old.content.startswith(b"%PDF-")
    assert old.headers["content-disposition"].startswith("attachment;")


def test_editing_and_archiving(clerk) -> None:
    noc = next(
        i
        for i in clerk.get(f"/projects/{HB}/documents").json()["checklist"]
        if i["key"] == "fire_noc"
    )
    r = clerk.put(f"/documents/{noc['document_id']}", json={"expires_on": "2029-01-01"})
    assert r.json()["expiry"] == "held"
    keys = [i["key"] for i in clerk.get("/today").json()["items"] if i["project_id"] == HB]
    assert f"doc:{noc['document_id']}:expiry" not in keys

    assert clerk.post(f"/documents/{noc['document_id']}/archive").status_code == 200
    assert checklist_status(clerk, HB)["fire_noc"] == "missing"


def test_waiving_and_restoring_a_checklist_item(clerk) -> None:
    url = f"/projects/{HB}/checklist/title_deed"
    assert clerk.post(f"{url}/waive", json={}).status_code == 400
    assert clerk.post(f"{url}/waive", json={"reason": "Leasehold"}).status_code == 200
    assert checklist_status(clerk, HB)["title_deed"] == "waived"
    clerk.post(f"{url}/restore")
    assert checklist_status(clerk, HB)["title_deed"] == "missing"


def test_documents_filed_against_a_case(clerk) -> None:
    cases = clerk.get(f"/projects/{SG}/disputes").json()["cases"]
    case_id = next(c["id"] for c in cases if c["case_number"] == "AO/DEMO/051/2026")
    r = upload(
        clerk,
        SG,
        pdf("Order of the adjudicating officer, AO/DEMO/051/2026"),
        category="order",
        link_type="case",
        link_id=case_id,
    )
    assert r.status_code == 201, r.text
    linked = clerk.get("/documents", params={"link_type": "case", "link_id": case_id}).json()
    assert [x["category"] for x in linked["documents"]] == ["order"]
    records = clerk.get(f"/projects/{SG}/documents").json()["records"]
    assert next(x for x in records if x["key"] == "order_copies")["held"] == 2

    other = clerk.get(f"/projects/{HB}/documents").json()
    assert other  # a link to another project's record is refused:
    bad = upload(clerk, HB, pdf("Wrong project"), link_type="case", link_id=case_id)
    assert bad.status_code == 400


def test_data_rooms(vault, boss, clerk) -> None:
    docs = clerk.get(f"/projects/{SG}/documents").json()["documents"]
    ids = [x["id"] for x in docs[:2]]
    body = {"name": "Bank review", "expires_on": "2026-11-15", "document_ids": ids}
    assert clerk.post(f"/projects/{SG}/rooms", json=body).status_code == 403
    too_long = boss.post(f"/projects/{SG}/rooms", json={**body, "expires_on": "2027-06-01"})
    assert too_long.status_code == 400

    r = boss.post(f"/projects/{SG}/rooms", json=body)
    assert r.status_code == 201, r.text
    room_id, token = r.json()["id"], r.json()["token"]

    public = TestClient(vault)
    shared = public.get(f"/shared/{token}")
    assert shared.status_code == 200
    assert {x["id"] for x in shared.json()["documents"]} == set(ids)
    file = public.get(f"/shared/{token}/documents/{ids[0]}/file")
    assert file.status_code == 200 and file.content.startswith(b"%PDF-")
    outside = next(x["id"] for x in docs if x["id"] not in ids)
    assert public.get(f"/shared/{token}/documents/{outside}/file").status_code == 404

    room = boss.get(f"/rooms/{room_id}").json()
    assert (room["opens"], room["downloads"]) == (1, 1)

    fresh = boss.post(f"/rooms/{room_id}/link").json()["token"]
    assert public.get(f"/shared/{token}").status_code == 404
    assert public.get(f"/shared/{fresh}").status_code == 200

    boss.post(f"/rooms/{room_id}/revoke")
    assert public.get(f"/shared/{fresh}").status_code == 404
    assert public.get(f"/shared/{DEMO_ROOM_TOKEN}").status_code == 200


def test_certifiers_cannot_see_the_vault(vault) -> None:
    ca = signed_in(vault, "ca@demo.lekhara")
    assert ca.get(f"/projects/{SG}/documents").status_code == 403
    assert ca.get(f"/projects/{SG}/documents/search", params={"q": "deed"}).status_code == 403


def test_a_room_that_asks_who_is_visiting(vault, boss, clerk) -> None:
    docs = clerk.get(f"/projects/{SG}/documents").json()["documents"]
    ids = [x["id"] for x in docs[:2]]
    body = {
        "name": "Lender review",
        "expires_on": "2026-11-15",
        "document_ids": ids,
        "ask_visitor": True,
    }
    r = boss.post(f"/projects/{SG}/rooms", json=body)
    assert r.status_code == 201, r.text
    room_id, token = r.json()["id"], r.json()["token"]

    public = TestClient(vault)
    gate = public.get(f"/shared/{token}").json()
    assert gate["gate"] is True and "documents" not in gate
    assert public.get(f"/shared/{token}/documents/{ids[0]}/file").status_code == 403
    assert boss.get(f"/rooms/{room_id}").json()["visits"] == []

    bad = public.post(f"/shared/{token}/visitor", json={"name": "Asha", "email": "asha"})
    assert bad.status_code == 400
    visitor = public.post(
        f"/shared/{token}/visitor", json={"name": "Asha Nair", "email": "Asha@Bank.example"}
    ).json()["visitor"]
    public.headers["X-Lekhara-Visitor"] = visitor
    # The room stays shut until the code emailed to her is entered.
    waiting = public.get(f"/shared/{token}").json()
    assert waiting["gate"] is True and waiting["pending_email"] == "asha@bank.example"
    assert public.get(f"/shared/{token}/documents/{ids[0]}/file").status_code == 403
    wrong = public.post(f"/shared/{token}/visitor/verify", json={"code": "000000"})
    assert wrong.status_code == 400
    with vault.state.session_factory() as session:
        sent = session.scalars(
            select(OutboundEmail)
            .where(OutboundEmail.to_address == "asha@bank.example")
            .order_by(OutboundEmail.created_at.desc())
        ).first()
    code = re.search(r"is (\d{6})", sent.body).group(1)
    assert public.post(f"/shared/{token}/visitor/verify", json={"code": code}).status_code == 200
    shared = public.get(f"/shared/{token}").json()
    assert shared["gate"] is False and len(shared["documents"]) == 2
    assert public.get(f"/shared/{token}/documents/{ids[0]}/file").status_code == 200

    room = boss.get(f"/rooms/{room_id}").json()
    assert room["ask_visitor"] is True
    assert {v["visitor"] for v in room["visits"]} == {"Asha Nair <asha@bank.example>"}

    public.headers["X-Lekhara-Visitor"] = "someone-elses-token"
    assert public.get(f"/shared/{token}").json()["gate"] is True


# Watermarks, terms and the first-open email


def emails_to(app, address: str, kind: str | None = None) -> list[OutboundEmail]:
    with app.state.session_factory() as session:
        q = select(OutboundEmail).where(OutboundEmail.to_address == address)
        if kind:
            q = q.where(OutboundEmail.kind == kind)
        return list(session.scalars(q.order_by(OutboundEmail.created_at)))


def visit(app, token: str, name: str, email: str, **extra) -> TestClient:
    """A visitor who gives their name and email, and enters the code sent to them."""
    public = TestClient(app)
    r = public.post(f"/shared/{token}/visitor", json={"name": name, "email": email, **extra})
    assert r.status_code == 201, r.text
    public.headers["X-Lekhara-Visitor"] = r.json()["visitor"]
    code = re.search(r"is (\d{6})", emails_to(app, email, "room_code")[-1].body).group(1)
    assert public.post(f"/shared/{token}/visitor/verify", json={"code": code}).status_code == 200
    return public


def room(client, ids, **fields) -> tuple[str, str]:
    body = {"name": "Lender review", "expires_on": "2026-11-15", "document_ids": ids, **fields}
    r = client.post(f"/projects/{SG}/rooms", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"], r.json()["token"]


def test_pdfs_from_a_room_carry_who_opened_them(vault, boss) -> None:
    doc = upload(boss, SG, pdf("Encumbrance certificate for survey 42"), title="EC survey 42")
    doc_id = doc.json()["id"]
    room_id, token = room(boss, [doc_id], ask_visitor=True)
    asha = visit(vault, token, "Asha Nair", "asha@bank.example")
    file = asha.get(f"/shared/{token}/documents/{doc_id}/file")
    assert file.status_code == 200
    text = " ".join(read_pages(file.content))
    assert "Encumbrance certificate for survey 42" in text  # the document is still searchable
    assert "asha@bank.example, 17 Oct 2026" in text
    assert "Opened by Asha Nair (asha@bank.example)" in text and "Confidential" in text

    # Signed in, the team gets the file as it was filed.
    own = boss.get(f"/documents/{doc_id}/file")
    assert "asha@bank.example" not in " ".join(read_pages(own.content))

    # A room with no visitor names marks pages with who it was shared with.
    _, open_token = room(boss, [doc_id], audience="HDFC Bank")
    plain = TestClient(vault).get(f"/shared/{open_token}/documents/{doc_id}/file")
    assert "HDFC Bank, 17 Oct 2026" in " ".join(read_pages(plain.content))

    boss.put(f"/rooms/{room_id}", json={"watermark": False})
    unmarked = asha.get(f"/shared/{token}/documents/{doc_id}/file")
    assert unmarked.content == own.content


def test_a_room_with_terms(vault, boss, clerk) -> None:
    ids = [x["id"] for x in clerk.get(f"/projects/{SG}/documents").json()["documents"][:1]]
    nda = "Keep these documents confidential and use them only to assess the loan."
    no_names = boss.post(
        f"/projects/{SG}/rooms",
        json={"name": "NDA", "expires_on": "2026-11-15", "document_ids": ids, "terms": nda},
    )
    assert no_names.status_code == 400 and "name and email" in no_names.json()["detail"]
    room_id, token = room(boss, ids, ask_visitor=True, terms=nda)

    public = TestClient(vault)
    gate = public.get(f"/shared/{token}").json()
    assert gate["gate"] is True and gate["terms"] == nda
    refused = public.post(
        f"/shared/{token}/visitor", json={"name": "Asha Nair", "email": "asha@bank.example"}
    )
    assert refused.status_code == 400 and "Accept the terms" in refused.json()["detail"]
    asha = visit(vault, token, "Asha Nair", "asha@bank.example", accept_terms=True)
    assert asha.get(f"/shared/{token}").json()["gate"] is False

    # Changed terms are accepted again before anything more opens.
    boss.put(f"/rooms/{room_id}", json={"terms": nda + " Return or destroy them after."})
    again = asha.get(f"/shared/{token}").json()
    assert again["gate"] is True and again["accept_again"] is True
    assert asha.get(f"/shared/{token}/documents/{ids[0]}/file").status_code == 403
    assert asha.post(f"/shared/{token}/visitor/terms").status_code == 200
    assert asha.get(f"/shared/{token}").json()["gate"] is False

    with vault.state.session_factory() as session:
        from lekhara.models import DataRoomVisitor

        row = session.scalars(select(DataRoomVisitor).where(DataRoomVisitor.room_id == room_id))
        accepted = next(iter(row))
        assert accepted.accepted_terms.endswith("Return or destroy them after.")
        assert accepted.accepted_terms_at is not None

    off = boss.put(f"/rooms/{room_id}", json={"ask_visitor": False})
    assert off.status_code == 400  # terms stay tied to names
    assert boss.put(f"/rooms/{room_id}", json={"terms": ""}).json()["terms"] is None


def test_whoever_made_a_room_hears_of_each_first_open(vault, boss, clerk) -> None:
    ids = [x["id"] for x in clerk.get(f"/projects/{SG}/documents").json()["documents"][:1]]
    room_id, token = room(boss, ids, ask_visitor=True)
    before = len(emails_to(vault, "promoter@demo.lekhara", "room_opened"))
    asha = visit(vault, token, "Asha Nair", "asha@bank.example")
    asha.get(f"/shared/{token}")
    asha.get(f"/shared/{token}")
    told = emails_to(vault, "promoter@demo.lekhara", "room_opened")[before:]
    assert len(told) == 1
    assert told[0].subject == "Asha Nair opened Lender review"
    assert "asha@bank.example" in told[0].body and f"/rooms/{room_id}" in told[0].body

    visit(vault, token, "Vikram Shah", "vikram@bank.example").get(f"/shared/{token}")
    assert len(emails_to(vault, "promoter@demo.lekhara", "room_opened")[before:]) == 2

    boss.put(f"/rooms/{room_id}", json={"notify": False})
    visit(vault, token, "Meera Iyer", "meera@bank.example").get(f"/shared/{token}")
    assert len(emails_to(vault, "promoter@demo.lekhara", "room_opened")[before:]) == 2

    # A room that does not ask who is visiting sends one email, for its first open.
    _, open_token = room(boss, ids)
    public = TestClient(vault)
    public.get(f"/shared/{open_token}")
    public.get(f"/shared/{open_token}")
    last = emails_to(vault, "promoter@demo.lekhara", "room_opened")[before:]
    assert len(last) == 3 and "the only email it sends" in last[-1].body
