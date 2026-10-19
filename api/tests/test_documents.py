from datetime import date, timedelta

import pytest
from conftest import signed_in
from fastapi.testclient import TestClient

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
    shared = public.get(f"/shared/{token}").json()
    assert shared["gate"] is False and len(shared["documents"]) == 2
    assert public.get(f"/shared/{token}/documents/{ids[0]}/file").status_code == 200

    room = boss.get(f"/rooms/{room_id}").json()
    assert room["ask_visitor"] is True
    assert {v["visitor"] for v in room["visits"]} == {"Asha Nair <asha@bank.example>"}

    public.headers["X-Lekhara-Visitor"] = "someone-elses-token"
    assert public.get(f"/shared/{token}").json()["gate"] is True
