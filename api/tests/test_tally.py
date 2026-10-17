from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tally_samples import (
    DAYBOOK_CSV,
    full_xml_utf16,
    json_export,
    masters_only_xml,
    vouchers_only_xml,
)

from lekhara.db import make_sessionmaker
from lekhara.models import Vendor
from lekhara.registers import STANDARD_LINES
from lekhara.services import ServiceError
from lekhara.tally.book import parse_amount, parse_date, parse_quantity
from lekhara.tally.ledgers import CostLineRef, LandownerRef, suggest_line
from lekhara.tally.plan import Context, UnitRef, make_plan
from lekhara.tally.reader import detect
from lekhara.tally.service import read_book

PASSWORD = "a-long-password"
TODAY = date(2026, 10, 17)


def ctx(**kw) -> Context:
    base = {
        "as_of": TODAY,
        "registered_on": date(2025, 4, 1),
        "units": (UnitRef("u1", "A-101", "Priya Sharma"), UnitRef("u2", "A-102", "Ravi Kumar")),
        "vendors": (),
        "known_refs": frozenset(),
        "links": {},
    }
    base.update(kw)
    return Context(**base)


# Reading Tally's conventions


def test_tally_values() -> None:
    assert parse_amount("-21546.00") == D("-21546.00")
    assert parse_amount("1,234.50 Dr") == D("-1234.50")
    assert parse_amount("-100.00 USD @ 83.00/USD = -8300.00") == D("-8300.00")
    assert parse_amount("") == 0
    assert parse_date("20250401") == date(2025, 4, 1)
    assert parse_date("1-Apr-2025") == date(2025, 4, 1)
    assert parse_date("01-Apr-25") == date(2025, 4, 1)
    assert parse_quantity(" 125 Bag") == (D("125"), "Bag")


def test_file_kinds_are_recognised() -> None:
    assert detect("x.xml", full_xml_utf16()) == "xml"
    assert detect("x.json", json_export()) == "json"
    assert detect("x.csv", DAYBOOK_CSV.encode()) == "text"
    assert detect("x.pdf", b"%PDF-1.4 ...") == "pdf"
    assert detect("x.html", b"<!DOCTYPE html><html>") == "html"
    with pytest.raises(ServiceError, match="Alt\\+E"):
        read_book("daybook.pdf", b"%PDF-1.4 ...")


# The book


def test_utf16_xml_with_control_characters_is_read() -> None:
    kind, book = read_book("export.xml", full_xml_utf16())
    assert kind == "xml"
    assert book.company == "Kaveri Homes LLP"
    assert book.has_masters
    kinds = {name: ledger.kind for name, ledger in book.ledgers.items()}
    assert kinds["kaveri steel traders"] == "creditor"
    assert kinds["steel purchases"] == "purchase"  # "&#4; Purchase Accounts"
    assert kinds["civil works"] == "project_cost"  # the builder's own Site Expenses group
    assert kinds["cement purchases"] == "project_cost"  # work in progress
    assert kinds["hdfc rera collection a/c"] == "bank"
    assert kinds["a-101 priya sharma"] == "debtor"
    assert book.ledgers["tds receivable 194ia"].tax_kind == "tds"

    steel = book.ledgers["kaveri steel traders"]
    assert (steel.gstin, steel.pan, steel.state) == ("29AAGCB7383J1Z4", "AAGCB7383J", "Karnataka")
    assert (steel.msme_type, steel.udyam) == ("small", "UDYAM-KA-03-0012345")
    assert steel.opening_balance == D("-250000.00")  # a credit balance
    assert book.ledgers["deccan ready mix"].gstin == "27AAPFU0939F1ZV"  # newer GST details list


def test_vouchers_are_read_with_their_details() -> None:
    _, book = read_book("export.xml", full_xml_utf16())
    by_guid = {v.key: v for v in book.vouchers}
    purchase = by_guid["guid:guid-1"]
    assert purchase.base_type == "purchase"  # "Purchase - Steel" traced to its base type
    assert purchase.balance == 0
    lines = {e.ledger: e.amount for e in purchase.entries}
    assert lines["Kaveri Steel Traders"] == D("-118000.00")  # credit
    assert lines["Steel Purchases"] == D("100000.00")  # debit
    assert purchase.entries[1].cost_centres == [
        ("Primary Cost Category", "Kaveri Heights", D("100000.00"))
    ]
    assert purchase.entries[2].gst_rates == {"CGST": D("9")}

    payment = by_guid["guid:guid-2"]
    assert payment.entries[0].bills[0].kind == "agst ref"
    assert payment.entries[1].bank[0].utr == "UTR123"

    cement = by_guid["guid:guid-5"]
    assert cement.balance == 0  # the purchase ledger was inside the stock line
    assert cement.stock[0].quantity == D("125") and cement.stock[0].rate == D("400.00")
    assert by_guid["guid:guid-9"].cancelled


# The plan


def test_suppliers_bills_and_buyer_payments() -> None:
    _, book = read_book("export.xml", full_xml_utf16())
    plan = make_plan(book, ctx())

    vendors = {v.name: v for v in plan.vendors}
    assert set(vendors) == {"Kaveri Steel Traders", "Ramesh Shuttering", "Deccan Ready Mix"}
    assert vendors["Kaveri Steel Traders"].msme_category == "small"
    assert vendors["Kaveri Steel Traders"].registered is True
    assert vendors["Ramesh Shuttering"].registered is False

    bills = {b.bill_no: b for b in plan.bills}
    steel = bills["KST/1023"]
    assert (steel.taxable_value, steel.gst, steel.total) == (
        D("100000.00"),
        D("18000.00"),
        D("118000.00"),
    )
    assert steel.bill_date == date(2025, 4, 28) and steel.accepted_on == date(2025, 5, 1)
    assert steel.paid_on == date(2025, 5, 15)
    assert bills["J-12"].taxable_value == D("250000.00")  # a contractor's bill booked as a journal
    assert bills["J-12"].paid_on is None
    assert bills["DRM-77"].is_cement

    receipts = {r.ledger: r for r in plan.receipts}
    assert (receipts["A-101 Priya Sharma"].unit_label, receipts["A-101 Priya Sharma"].amount) == (
        "A-101",
        D("495000.00"),
    )
    assert receipts["A-101 Priya Sharma"].tds == D("5000.00")
    assert receipts["Ravi Kumar"].unit_label == "A-102"  # matched on the buyer's name
    assert receipts["Unknown Buyer X"].unit_id is None
    assert plan.counts["sales"] == 1


def test_missing_data_is_named() -> None:
    _, book = read_book("export.xml", full_xml_utf16())
    alerts = {a.code: a for a in make_plan(book, ctx()).alerts}
    assert alerts["vendor.no_gstin"].items == ["Ramesh Shuttering"]
    assert set(alerts["vendor.no_msme"].items) == {"Deccan Ready Mix", "Ramesh Shuttering"}
    assert alerts["bill.no_reference"].items == ["Journal J-12 of 31 May 2025"]
    assert alerts["bill.no_billwise"].items == ["Ramesh Shuttering"]
    assert alerts["receipt.unmatched"].level == "blocking"
    assert alerts["receipt.unmatched"].items == ["Unknown Buyer X"]
    assert "file.skipped" in alerts
    assert "file.cost_centres" in alerts

    linked = make_plan(book, ctx(links={"unknown buyer x": "ignore"}))
    assert "receipt.unmatched" not in {a.code for a in linked.alerts}
    no_units = {a.code for a in make_plan(book, ctx(units=())).alerts}
    assert "receipt.no_units" in no_units


def test_what_each_kind_of_file_lacks() -> None:
    _, vouchers = read_book("vouchers.xml", vouchers_only_xml())
    codes = {a.code for a in make_plan(vouchers, ctx()).alerts}
    assert "file.no_masters" in codes
    # Without masters, suppliers are recognised from how the vouchers use them.
    assert {v.name for v in make_plan(vouchers, ctx()).vendors} >= {"Kaveri Steel Traders"}

    _, masters = read_book("masters.xml", masters_only_xml())
    assert "file.no_vouchers" in {a.code for a in make_plan(masters, ctx()).alerts}

    _, daybook = read_book("daybook.csv", DAYBOOK_CSV.encode())
    assert daybook.source == "daybook" and daybook.summary_only
    plan = make_plan(daybook, ctx())
    assert "file.summary_report" in {a.code for a in plan.alerts}
    assert [b.total for b in plan.bills] == [D("118000.00")]
    assert [r.unit_label for r in plan.receipts] == ["A-101"]


def test_json_export() -> None:
    kind, book = read_book("export.json", json_export())
    assert kind == "json" and book.company == "Kaveri Homes LLP"
    plan = make_plan(book, ctx())
    assert [(b.bill_no, b.total) for b in plan.bills] == [("KST/1023", D("118000.00"))]
    assert plan.vendors[0].gstin == "29AAGCB7383J1Z4"


def test_a_cost_centre_narrows_the_import() -> None:
    _, book = read_book("export.xml", full_xml_utf16())
    plan = make_plan(book, ctx(cost_centre="Kaveri Heights"))
    assert [b.bill_no for b in plan.bills] == ["KST/1023"]


# Through the API


def firm_with_units(app) -> tuple[TestClient, str]:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={
            "name": "Anil",
            "email": "anil@kaverihomes.in",
            "password": PASSWORD,
            "firm": "Kaveri",
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
    sheet = (
        "Unit,Carpet area (sq ft),Buyer,Booked on,Agreement value\n"
        "A-101,1100,Priya Sharma,01/04/2025,92 lakh\nA-102,1150,Ravi Kumar,02/04/2025,95 lakh\n"
    )
    batch = client.post(
        f"/projects/{project}/imports/units", files={"file": ("u.csv", sheet.encode(), "text/csv")}
    ).json()["id"]
    client.post(f"/imports/{batch}/apply")
    return client, project


def upload(client, project, data: bytes, name="tally-export.xml"):
    return client.post(
        f"/projects/{project}/tally", files={"file": (name, data, "application/xml")}
    )


def test_import_review_link_apply_and_undo(app, engine) -> None:
    client, project = firm_with_units(app)
    r = upload(client, project, full_xml_utf16())
    assert r.status_code == 201, r.text
    review = client.get(f"/tally/{r.json()['id']}").json()
    assert review["source_label"] == "Tally XML" and review["company"] == "Kaveri Homes LLP"
    assert review["period"] == {"from": "2025-05-01", "to": "2025-06-30"}
    assert review["counts"]["vendors_new"] == 3
    assert review["counts"]["bills_new"] == 3 and review["counts"]["bills_paid"] == 1
    assert review["counts"]["receipts_new"] == 2 and review["counts"]["receipts_waiting"] == 1
    assert review["alerts"][0]["level"] == "blocking"
    assert [b["ledger"] for b in review["buyers"]] == ["Unknown Buyer X"]

    linked = client.put(
        f"/tally/{review['id']}/options",
        json={
            "links": {
                "Unknown Buyer X": next(u["id"] for u in review["units"] if u["label"] == "A-102")
            }
        },
    ).json()
    assert linked["counts"]["receipts_new"] == 3

    applied = client.post(f"/tally/{review['id']}/apply").json()
    assert applied["status"] == "applied"
    assert len(applied["result"]["bills_added"]) == 3
    assert len(applied["result"]["receipts_added"]) == 3
    with make_sessionmaker(engine)() as session:
        steel = session.scalars(
            select(Vendor).where(
                Vendor.name == "Kaveri Steel Traders", Vendor.organization_id != "demo"
            )
        ).one()
        assert (steel.msme_category, steel.udyam_number, steel.pan) == (
            "small",
            "UDYAM-KA-03-0012345",
            "AAGCB7383J",
        )
    collections = client.get(f"/projects/{project}/collections").json()
    assert collections["summary"]["received"] != "0"

    again = client.get(f"/tally/{upload(client, project, full_xml_utf16()).json()['id']}").json()
    assert again["counts"]["bills_new"] == 0 and again["counts"]["bills_known"] == 3
    assert again["counts"]["receipts_new"] == 0  # the buyer link is remembered, the payment known

    undone = client.post(f"/tally/{review['id']}/undo").json()
    assert undone["status"] == "undone"
    with make_sessionmaker(engine)() as session:
        assert (
            session.scalars(
                select(Vendor).where(
                    Vendor.name == "Kaveri Steel Traders", Vendor.organization_id != "demo"
                )
            ).first()
            is None
        )


def test_unreadable_files_get_instructions(app) -> None:
    client, project = firm_with_units(app)
    pdf = upload(client, project, b"%PDF-1.4 report", name="daybook.pdf")
    assert pdf.status_code == 400
    assert "PDF" in pdf.json()["detail"] and "XML" in pdf.json()["detail"]
    sheet = upload(client, project, b"Name,Phone\nA,1\n", name="contacts.csv")
    assert sheet.status_code == 400
    daybook = upload(client, project, DAYBOOK_CSV.encode(), name="daybook.csv")
    review = client.get(f"/tally/{daybook.json()['id']}").json()
    assert review["source_label"] == "Day Book report"
    assert review["found"]["totals_only"] is True


def test_who_can_import_from_tally(app, ca) -> None:
    client, _ = firm_with_units(app)
    assert upload(client, "sarjapur-greens", full_xml_utf16()).status_code == 403
    assert ca.get("/projects/sarjapur-greens/tally").status_code == 403


# Cost lines, the RERA account and landowners


STANDARD = tuple(
    CostLineRef(f"line-{code}", code, name, category) for code, name, category, _ in STANDARD_LINES
)


def test_expense_ledgers_are_matched_to_cost_lines_by_name() -> None:
    assert suggest_line("TMT Steel Fe500", "", STANDARD) == "line-CIVIL"
    assert suggest_line("Lift and elevator works", "", STANDARD) == "line-MEP"
    assert suggest_line("BBMP plan sanction fee", "", STANDARD) == "line-APPR"
    assert suggest_line("Architect fees", "", STANDARD) == "line-CONS"
    assert suggest_line("Vitrified tiles", "", STANDARD) == "line-FIN"
    assert suggest_line("Miscellaneous", "", STANDARD) is None
    assert suggest_line("Cement", "", ()) is None


def test_cost_incurred_and_paid() -> None:
    _, book = read_book("export.xml", full_xml_utf16())
    plan = make_plan(book, ctx(cost_lines=STANDARD))
    cash = plan.money
    incurred = sum(e.amount for e in cash.cost_entries if e.kind == "incurred")
    paid = sum(e.amount for e in cash.cost_entries if e.kind == "paid")
    # Steel 1,00,000 with GST 18,000; RA bill 2,50,000; cement 50,000 with GST 9,000.
    assert incurred == D("427000.00")
    # Paid to the steel supplier in full, and 1,00,000 to the shuttering contractor.
    assert paid == D("218000.00")
    assert {c.ledger: c.source for c in cash.cost_ledgers}["Steel Purchases"] == "suggested"

    no_gst = make_plan(book, ctx(cost_lines=STANDARD, gst_is_cost=False)).money
    assert sum(e.amount for e in no_gst.cost_entries if e.kind == "incurred") == D("400000.00")

    chosen = make_plan(
        book, ctx(cost_lines=STANDARD, links={"civil works": ("cost_line", "line-EXT")})
    ).money
    assert any(e.cost_line_id == "line-EXT" for e in chosen.cost_entries)


def test_rera_account_and_landowners() -> None:
    _, book = read_book("export.xml", full_xml_utf16())
    owners = (LandownerRef("lo1", "Lakshmamma", "ABCPL1234K"),)
    plan = make_plan(book, ctx(cost_lines=STANDARD, landowners=owners, jda=True))
    cash = plan.money
    assert [m.ledger for m in cash.bank_ledgers if m.target] == ["HDFC RERA Collection A/c"]
    assert sorted(e.amount for e in cash.escrow) == [D("100000.00"), D("300000.00"), D("495000.00")]
    assert {e.kind for e in cash.escrow} == {"deposit"}
    payment = cash.landowner_payments[0]
    assert (payment.landowner_id, payment.amount, payment.tds) == (
        "lo1",
        D("100000.00"),
        D("10000.00"),
    )
    # A landowner is not a supplier.
    assert "Lakshmamma (Landowner)" not in {v.name for v in plan.vendors}
    assert "paid.unattributed" not in {a.code for a in plan.alerts}

    codes = {a.code for a in make_plan(book, ctx()).alerts}
    assert "cost.no_lines" in codes
    assert "landowner.none" not in codes
    assert "landowner.none" in {a.code for a in make_plan(book, ctx(jda=True)).alerts}


def test_cost_lines_and_landowners_through_the_api(app) -> None:
    client, project = firm_with_units(app)
    assert client.post(f"/projects/{project}/cost-lines/standard").json() == {"added": 11}
    assert client.post(f"/projects/{project}/cost-lines/standard").json() == {"added": 0}
    lines = client.get(f"/projects/{project}/cost-lines").json()["lines"]
    assert [line["code"] for line in lines][:3] == ["LAND", "APPR", "CIVIL"]
    civil = next(line for line in lines if line["code"] == "CIVIL")
    assert (
        client.put(f"/cost-lines/{civil['id']}", json={"revised_budget": "45 crore"}).status_code
        == 200
    )
    budget = next(
        line
        for line in client.get(f"/projects/{project}/cost-lines").json()["lines"]
        if line["code"] == "CIVIL"
    )
    assert budget["revised_budget"] == "450000000.00"
    taken = client.post(
        f"/projects/{project}/cost-lines",
        json={"code": "civil", "name": "X", "category": "construction"},
    )
    assert taken.status_code == 400

    owner = client.post(
        f"/projects/{project}/landowners",
        json={"name": "Lakshmamma", "share_type": "area", "share_pct": "40", "pan": "abcpl1234k"},
    )
    assert owner.status_code == 201, owner.text
    bad = client.post(
        f"/projects/{project}/landowners",
        json={"name": "X", "share_type": "area", "share_pct": "40", "pan": "123"},
    )
    assert bad.status_code == 400


def test_tally_money_through_the_api(app) -> None:
    client, project = firm_with_units(app)
    client.post(f"/projects/{project}/cost-lines/standard")
    client.post(
        f"/projects/{project}/landowners",
        json={"name": "Lakshmamma", "share_type": "area", "share_pct": "40"},
    )
    review = client.get(f"/tally/{upload(client, project, full_xml_utf16()).json()['id']}").json()
    money = review["money"]
    assert money["counts"]["incurred"] == "427000.00"
    assert money["counts"]["deposits"] == "895000.00"
    assert money["counts"]["landowner_payments"] == 1
    assert {b["ledger"]: b["rera"] for b in money["bank_ledgers"]}[
        "HDFC RERA Collection A/c"
    ] is True

    sbi = client.put(
        f"/tally/{review['id']}/options",
        json={"links": {"Unknown Buyer X": "ignore", "SBI Current A/c": {"role": "ignore"}}},
    )
    assert sbi.status_code == 200
    client.post(f"/tally/{review['id']}/apply")
    summary = client.get(f"/projects/{project}/money").json()["summary"]
    assert (summary["incurred"], summary["paid"]) == ("427000.00", "218000.00")
    escrow = client.get(f"/projects/{project}/escrow").json()
    assert (
        escrow["deposits"]["deposited"] == "895000.00"
    )  # every rupee paid into the RERA account counts

    client.post(f"/tally/{review['id']}/undo")
    summary = client.get(f"/projects/{project}/money").json()["summary"]
    assert summary["incurred"] == "0.00"  # reversed, never deleted
    again = client.get(f"/tally/{upload(client, project, full_xml_utf16()).json()['id']}").json()
    assert again["money"]["counts"]["incurred"] == "427000.00"  # undone entries come back
