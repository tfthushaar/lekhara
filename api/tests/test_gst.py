from datetime import date
from decimal import Decimal

import gst_samples as samples
from fastapi.testclient import TestClient

from lekhara.db import make_sessionmaker
from lekhara.gst.reader import fold_number, read_return
from lekhara.models import Bill, Organization, Vendor

PASSWORD = "a-long-password"


def test_reading_each_layout() -> None:
    b2b = read_return("GSTR2B.json", samples.gstr2b_json())
    assert b2b.form == "GSTR-2B" and b2b.gstin == samples.FIRM and b2b.period == "092026"
    invoices = [i for i in b2b.invoices if i.kind == "invoice"]
    assert len(invoices) == 4 and [i for i in b2b.invoices if i.kind == "credit_note"]
    first = invoices[0]
    assert first.supplier_name == "BHARAT TMT STEEL" and first.on == date(2026, 9, 5)
    assert first.taxable == Decimal("1200000.00") and first.gst == Decimal("216000.00")
    assert first.itc_available is True and first.reverse_charge is False

    excel = read_return("GSTR2B_092026.xlsx", samples.gstr2b_xlsx())
    assert excel.gstin == samples.FIRM and len(excel.invoices) == 4
    assert [(i.number, i.taxable, i.gst) for i in excel.invoices] == [
        (i.number, i.taxable, i.gst) for i in invoices
    ]

    older = read_return("2a.json", samples.gstr2a_json())
    assert older.form == "GSTR-2A" and older.invoices[3].igst == Decimal("9000.00")
    assert older.invoices[0].taxable == Decimal("1200000.00")


def test_invoice_numbers_match_however_written() -> None:
    assert fold_number("BTS/0001") == fold_number("bts-1") == fold_number("BTS 1")
    assert fold_number("2026/104") != fold_number("2026/14")


def firm(app, engine) -> tuple[TestClient, str]:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={
            "accept_terms": True,
            "name": "Anil",
            "email": "anil@kaverihomes.in",
            "password": PASSWORD,
            "firm": "Kaveri",
        },
    )
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    with make_sessionmaker(engine)() as session:
        org = session.query(Organization).filter_by(name="Kaveri").one()
        org.gstin = samples.FIRM
        session.commit()
    project = client.post(
        "/projects",
        json={
            "name": "Kaveri Heights",
            "krera_registration": "PRM/K/1",
            "registered_on": "2025-04-01",
        },
    ).json()["id"]
    client.post(
        f"/projects/{project}/suppliers", json={"name": "Bharat TMT Steel", "gstin": samples.STEEL}
    )
    client.post(f"/projects/{project}/suppliers", json={"name": "Ravi Electricals"})
    unrep = samples.gstin("29UNREP3456L1Z")
    client.post(
        f"/projects/{project}/suppliers", json={"name": "Slow Filer Traders", "gstin": unrep}
    )
    for supplier, no, day, taxable, gst in (
        ("Bharat TMT Steel", "BTS/1", "05/09/2026", "1200000", "216000"),
        ("Bharat TMT Steel", "BTS/2", "12/09/2026", "320000", "57600"),
        ("Ravi Electricals", "RE-77", "06/09/2026", "250000", "45000"),
        ("Slow Filer Traders", "SF-9", "15/09/2026", "80000", "14400"),
    ):
        r = client.post(
            f"/projects/{project}/bills",
            json={
                "supplier": supplier,
                "bill_no": no,
                "bill_date": day,
                "taxable_value": taxable,
                "gst_amount": gst,
            },
        )
        assert r.status_code == 201, r.text
    return client, project


def upload(client, project, data, name="GSTR2B.json") -> dict:
    r = client.post(f"/projects/{project}/gst", files={"file": (name, data, "application/json")})
    assert r.status_code == 201, r.text
    return client.get(f"/gst/{r.json()['id']}").json()


def test_checking_a_return_against_the_bills(app, engine) -> None:
    client, project = firm(app, engine)
    view = upload(client, project, samples.gstr2b_json())
    assert view["period_label"] == "September 2026" and view["add_missing"]
    c = view["counts"]
    assert (c["matched"], c["differs"], c["missing"], c["unreported"], c["notes"]) == (
        2,
        1,
        1,
        1,
        1,
    )
    codes = {a["code"] for a in view["alerts"]}
    assert {"gst.unreported", "gst.differs", "gst.missing", "gst.gstins"} <= codes
    assert view["unreported"][0]["bill_no"] == "SF-9"
    assert view["gstin_updates"] == [
        {
            "vendor_id": view["gstin_updates"][0]["vendor_id"],
            "name": "Ravi Electricals",
            "gstin": samples.RAVI,
        }
    ]
    assert view["new_suppliers"] == [{"gstin": samples.PLUMB, "name": "NEW PLUMBING CO"}]
    assert client.get("/review").json()["items"][0]["title"] == "A GSTR-2B to check"

    applied = client.post(f"/gst/{view['id']}/apply").json()
    assert applied["status"] == "applied" and len(applied["result"]["bills"]) == 1
    with make_sessionmaker(engine)() as session:
        ravi = session.query(Vendor).filter_by(name="Ravi Electricals").one()
        assert ravi.gstin == samples.RAVI and ravi.registered
        added = session.query(Bill).filter_by(bill_no="NP-1").one()
        assert added.taxable_value == Decimal("50000") and added.source_ref.startswith("gstr2b:")

    again = upload(client, project, samples.gstr2b_xlsx(), "GSTR2B.xlsx")
    assert again["counts"]["missing"] == 0 and again["counts"]["matched"] == 3
    assert not again["gstin_updates"] and not again["new_suppliers"]

    client.post(f"/gst/{view['id']}/undo")
    with make_sessionmaker(engine)() as session:
        assert session.query(Bill).filter_by(bill_no="NP-1").count() == 0
        assert session.query(Vendor).filter_by(gstin=samples.PLUMB).count() == 0
        assert session.query(Vendor).filter_by(name="Ravi Electricals").one().gstin is None


def test_firms_on_tally_do_not_add_bills_by_default(app, engine) -> None:
    client, project = firm(app, engine)
    with make_sessionmaker(engine)() as session:
        bill = session.query(Bill).filter_by(bill_no="BTS/1").one()
        bill.source_ref = "tally:guid-1"
        session.commit()
    view = upload(client, project, samples.gstr2b_json())
    assert not view["add_missing"]
    client.post(f"/gst/{view['id']}/apply")
    with make_sessionmaker(engine)() as session:
        assert session.query(Bill).filter_by(bill_no="NP-1").count() == 0
        assert session.query(Vendor).filter_by(gstin=samples.PLUMB).count() == 1  # still added
    chosen = upload(client, project, samples.gstr2b_json())
    assert client.put(f"/gst/{chosen['id']}/options", json={"add_missing": True}).json()[
        "add_missing"
    ]


def test_a_return_for_another_gstin(app, engine) -> None:
    client, project = firm(app, engine)
    other = samples.gstin("29OTHER1111A1Z")
    view = upload(client, project, samples.gstr2b_json(firm=other))
    assert "gst.other_gstin" in {a["code"] for a in view["alerts"]}


def test_files_that_are_not_returns(app, engine) -> None:
    client, project = firm(app, engine)
    r = client.post(
        f"/projects/{project}/gst", files={"file": ("x.json", b'{"hello": 1}', "application/json")}
    )
    assert r.status_code == 400 and "GSTR-2B" in r.json()["detail"]
