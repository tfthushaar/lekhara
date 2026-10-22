from datetime import date
from decimal import Decimal

import bank_samples as samples
import pytest
from fastapi.testclient import TestClient

from lekhara.bank.narration import is_charge, is_interest, is_returned, payer
from lekhara.bank.reader import column_role, parse_amount, read_statement
from lekhara.db import make_sessionmaker
from lekhara.models import EscrowTxn, Project
from lekhara.services import ServiceError

PASSWORD = "a-long-password"
BUYERS = [
    ("A-101", "Priya Sharma"),
    ("A-102", "Rahul Kumar"),
    ("B-201", "Anand Rao"),
    ("B-202", "Meera Iyer"),
]


# Reading statements


@pytest.mark.parametrize(
    "header, role",
    [
        ("Date", "date"),
        ("Txn Date", "date"),
        ("Tran Date", "date"),
        ("Value Dt", "value_date"),
        ("Narration", "narration"),
        ("Transaction Remarks", "narration"),
        ("PARTICULARS", "narration"),
        ("Chq./Ref.No.", "reference"),
        ("Ref No./Cheque No.", "reference"),
        ("CHQNO", "reference"),
        ("Cheque Details", "reference"),
        ("Withdrawal Amt.", "debit"),
        ("Withdrawal Amount (INR )", "debit"),
        ("Withdrawal(DR)", "debit"),
        ("DR", "debit"),
        ("Deposit Amt.", "credit"),
        ("Deposits(CR)", "credit"),
        ("Amount (Rs.)", "amount"),
        ("Dr / Cr", "direction"),
        ("Closing Balance", "balance"),
        ("BAL", "balance"),
        ("Init.", None),
    ],
)
def test_column_names_from_every_bank(header, role) -> None:
    assert column_role(header) == role


def test_amounts_as_banks_write_them() -> None:
    assert parse_amount("1,23,456.00") == (Decimal("123456.00"), None)
    assert parse_amount("5,000.00 Cr") == (Decimal("5000.00"), "cr")
    assert parse_amount("250.00(Dr)") == (Decimal("250.00"), "dr")
    assert parse_amount("-") == (None, None)
    assert parse_amount(4950.5) == (Decimal("4950.50"), None)


@pytest.mark.parametrize(
    "make, filename, bank",
    [
        (samples.hdfc_xls, "Acct Statement_1234.xls", "HDFC Bank"),
        (samples.icici_csv, "OpTransactionHistory.csv", None),
        (samples.kotak_csv, "statement.csv", None),
        (samples.axis_html, "Axis statement.xls", "Axis Bank"),
    ],
)
def test_reads_each_layout(make, filename, bank) -> None:
    s = read_statement(filename, make())
    assert len(s.lines) == len(samples.COLLECTION_LINES)
    first = s.lines[0]
    assert first.on == date(2026, 4, 5) and first.credit == Decimal("495000.00")
    assert "PRIYA SHARMA" in first.narration
    assert s.lines[6].debit == Decimal("300000.00")
    assert s.balance_breaks == []
    assert s.closing == Decimal("5371234.00")
    if bank:
        assert s.bank == bank
    assert s.period_from == date(2026, 4, 1) or s.period_from == date(2026, 4, 5)


def test_newest_first_is_put_in_order() -> None:
    s = read_statement("statement.csv", samples.kotak_csv())
    assert s.reversed_order and s.lines[0].on < s.lines[-1].on


def test_details_above_the_table() -> None:
    s = read_statement("x.xls", samples.hdfc_xls())
    assert s.account == samples.COLLECTION and s.account_tail == "4321"
    assert (s.period_from, s.period_to) == (date(2026, 4, 1), date(2026, 9, 30))
    assert s.opening == 0
    rera = read_statement("x.xlsx", samples.sbi_xlsx())
    assert rera.bank == "State Bank of India" and rera.account == samples.RERA
    assert rera.lines[-1].debit == Decimal("17.70")


def test_the_same_line_has_the_same_key_in_every_download() -> None:
    a = read_statement("a.xls", samples.hdfc_xls())
    b = read_statement("b.csv", samples.icici_csv())
    assert [x.key for x in a.lines] == [x.key for x in b.lines]


def test_files_that_are_not_statements() -> None:
    with pytest.raises(ServiceError, match="could not be opened"):
        read_statement("statement.pdf", b"%PDF-1.4 ...")
    with pytest.raises(ServiceError, match="table of transactions"):
        read_statement("units.csv", b"Unit,Buyer\nA-101,Priya\n")


def test_pdf_statements() -> None:
    s = read_statement("Statement.pdf", samples.statement_pdf())
    assert len(s.lines) == len(samples.COLLECTION_LINES)
    assert s.lines[0].credit == Decimal("495000.00") and "PRIYA SHARMA" in s.lines[0].narration
    assert s.lines[0].narration.endswith("SBIN426095123456 LLP-SBIN426095123456")  # 2 lines
    assert s.lines[6].debit == Decimal("300000.00") and s.lines[7].debit == Decimal("500000.00")
    assert s.balance_breaks == [] and s.closing == Decimal("5371234.00")
    assert s.account == samples.COLLECTION and s.bank == "HDFC Bank"
    keys = [line.key for line in read_statement("a.xls", samples.hdfc_xls()).lines]
    assert [line.key for line in s.lines] == keys  # the same lines as the Excel download

    newest = read_statement("s.pdf", samples.statement_pdf(newest_first=True))
    assert newest.reversed_order and newest.lines[0].on == date(2026, 4, 5)
    assert newest.lines[6].debit == Decimal("300000.00")


def test_pdf_statements_with_a_password() -> None:
    from lekhara.bank.pdf import PasswordNeeded, looks_like_statement

    data = samples.statement_pdf(password="KAVE0104")
    assert looks_like_statement(data)
    with pytest.raises(PasswordNeeded):
        read_statement("s.pdf", data)
    with pytest.raises(PasswordNeeded):
        read_statement("s.pdf", data, ("wrong",))
    s = read_statement("s.pdf", data, ("wrong", "KAVE0104"))
    assert len(s.lines) == len(samples.COLLECTION_LINES)


def test_reading_narrations() -> None:
    own = ("Kaveri Homes LLP",)
    assert payer(samples.COLLECTION_LINES[0][1], own) == "PRIYA SHARMA"
    assert payer("BY TRANSFER-NEFT*SBIN0001234*N123456789*PRIYA SHARMA--") == "PRIYA SHARMA"
    assert payer("UPI/512345678901/PAYMENT/priyas@oksbi/State Bank Of India/X") == "priyas"
    assert payer("NEFT CR-ICIC0000001-ICICI BANK LTD-KAVERI HOMES LLP-ICIC123", own) is None
    assert is_interest("INT.PD:01-04-2026 TO 30-06-2026") and is_interest("CREDIT INTEREST")
    assert is_charge("SMS CHARGES INCL GST") and not is_charge("NEFT CR-PRIYA SHARMA")
    assert is_returned("CHQ RETURN - MICR CLG") and not is_returned("RTGS CR-HDFC")


# Bringing a statement in


def firm(app) -> tuple[TestClient, str, dict]:
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
    units = {}
    for label, buyer in BUYERS:
        r = client.post(
            f"/projects/{project}/units",
            json={
                "label": label,
                "carpet_area_sqft": "1100",
                "buyer_name": buyer,
                "booked_on": "01/03/2026",
                "agreement_value": "90 lakh",
            },
        )
        assert r.status_code == 201, r.text
        units[label] = r.json()["id"]
    client.post(f"/projects/{project}/units", json={"label": "A-103", "carpet_area_sqft": "1100"})
    return client, project, units


def upload(client, project, data, name="statement.xls") -> dict:
    r = client.post(
        f"/projects/{project}/bank-statements",
        files={"file": (name, data, "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    return client.get(f"/bank-statements/{r.json()['id']}").json()


def outcomes(view) -> list[str]:
    return [line["outcome"] for line in view["lines"]]


def test_collection_account_statement(app) -> None:
    client, project, units = firm(app)
    view = upload(client, project, samples.hdfc_xls())
    assert view["bank"] == "HDFC Bank" and view["account"] == "ending 4321"
    assert view["role"] is None and not view["can_apply"]
    assert any(a["code"] == "account.role" for a in view["alerts"])
    assert set(outcomes(view)) == {"waiting", "returned"}
    sid = view["id"]

    view = client.put(f"/bank-statements/{sid}/options", json={"role": "collections"}).json()
    lines = view["lines"]
    assert [ln["unit_label"] for ln in lines[:4]] == ["A-101", "A-102", "B-201", "B-202"]
    assert lines[0]["how"] == "buyer's name" and lines[1]["how"] == "unit number"
    assert lines[3]["loan"] and lines[3]["how"] == "buyer's name"
    assert lines[4]["outcome"] == "needs_unit" and lines[4]["payer"] == "SURESH TRADERS"
    assert lines[5]["outcome"] == lines[6]["outcome"] == "returned"
    assert lines[7]["outcome"] == "left_out" and lines[8]["outcome"] == "not_buyer"
    assert view["totals"]["buyer_payments"] == "5795000.00"
    assert any(a["code"] == "buyer.unmatched" for a in view["alerts"])

    view = client.put(
        f"/bank-statements/{sid}/options", json={"lines": {lines[4]["key"]: "not_buyer"}}
    ).json()
    assert view["lines"][4]["outcome"] == "not_buyer"
    assert not any(a["code"] == "buyer.unmatched" for a in view["alerts"])

    applied = client.post(f"/bank-statements/{sid}/apply").json()
    assert applied["status"] == "applied" and applied["can_undo"]
    payments = client.get(f"/units/{units['A-101']}").json()["receipts"]
    assert [(p["amount"], p["reference"]) for p in payments] == [("495000.00", "SBIN426095123456")]

    # The same statement again, in another bank layout of the same account, adds nothing, and
    # the account and the payer are recognised.
    again = upload(client, project, samples.icici_csv(), "again.csv")
    assert again["role"] == "collections"
    assert again["counts"]["to_add"] == 0
    assert again["lines"][4]["outcome"] == "not_buyer"

    undone = client.post(f"/bank-statements/{sid}/undo").json()
    assert undone["status"] == "undone"
    assert client.get(f"/units/{units['A-101']}").json()["receipts"] == []
    again = client.get(f"/bank-statements/{again['id']}").json()
    assert again["counts"]["to_add"] == 4


def test_rera_account_statement(app, engine) -> None:
    client, project, _ = firm(app)
    view = upload(client, project, samples.sbi_xlsx(), "rera.xlsx")
    sid = view["id"]
    view = client.put(f"/bank-statements/{sid}/options", json={"role": "rera"}).json()
    assert outcomes(view) == ["deposit", "deposit", "withdrawal", "interest", "charges"]
    client.post(f"/bank-statements/{sid}/apply")

    escrow = client.get(f"/projects/{project}/escrow").json()
    steps = {s["label"]: s["value"] for s in escrow["steps"]}
    assert steps["Balance in the RERA account"] == "651832.30"
    assert steps["Less: already withdrawn"] == "200000.00"
    assert escrow["deposits"]["deposited"] == "850000.00"

    # A later statement that opens where Lekhara says the account stands raises nothing; one
    # that does not is flagged.
    later = [(date(2026, 7, 15), "BY TRANSFER-INB-From collection account", "", None, "100000")]
    ok = upload(client, project, samples.sbi_xlsx(later, opening="651832.30"), "jul.xlsx")
    assert ok["role"] == "rera"
    assert not any(a["code"] == "rera.opening" for a in ok["alerts"])
    gap = upload(client, project, samples.sbi_xlsx(later, opening="751832.30"), "gap.xlsx")
    assert any(a["code"] == "rera.opening" for a in gap["alerts"])


def test_movements_already_in_from_tally_are_not_added_again(app, engine) -> None:
    client, project, _ = firm(app)
    with make_sessionmaker(engine)() as session:
        session.add(
            EscrowTxn(
                project_id=project,
                kind="deposit",
                amount=Decimal("500000"),
                txn_date=date(2026, 5, 1),
                reference="tally:guid-1:rera:rera account",
            )
        )
        session.commit()
    view = upload(client, project, samples.sbi_xlsx(), "rera.xlsx")
    view = client.put(f"/bank-statements/{view['id']}/options", json={"role": "rera"}).json()
    assert view["lines"][0]["outcome"] == "exists"
    assert view["counts"]["to_add"] == 4
    assert any(a["code"] == "rera.tally" for a in view["alerts"])


def test_buyers_paying_straight_into_the_rera_account(app) -> None:
    client, project, units = firm(app)
    data = samples.sbi_xlsx(samples.COLLECTION_LINES[:2], account="00000030999999999")
    view = upload(client, project, data, "rera.xlsx")
    view = client.put(
        f"/bank-statements/{view['id']}/options", json={"role": "rera", "buyers_pay_here": True}
    ).json()
    assert outcomes(view) == ["buyer_payment", "buyer_payment"]
    client.post(f"/bank-statements/{view['id']}/apply")
    assert len(client.get(f"/units/{units['A-102']}").json()["receipts"]) == 1
    escrow = client.get(f"/projects/{project}/escrow").json()
    assert escrow["deposits"]["deposited"] == "695000.00"


def test_choices_are_checked(app) -> None:
    client, project, units = firm(app)
    view = upload(client, project, samples.hdfc_xls())
    url = f"/bank-statements/{view['id']}/options"
    key = view["lines"][4]["key"]
    assert client.put(url, json={"role": "savings"}).status_code == 400
    assert client.put(url, json={"lines": {"bank:nope": "skip"}}).status_code == 400
    unsold = client.put(url, json={"lines": {key: "not-a-unit"}})
    assert unsold.status_code == 400
    assert client.post(f"/bank-statements/{view['id']}/apply").status_code == 400  # no role yet
    chosen = client.put(url, json={"role": "collections", "lines": {key: units["B-201"]}}).json()
    assert chosen["lines"][4]["unit_label"] == "B-201"
    assert chosen["lines"][4]["how"] == "chosen by you"


def test_who_can_bring_statements_in(app, owner, architect, engine) -> None:
    client, project, _ = firm(app)
    assert (
        architect.post(
            f"/projects/{project}/bank-statements",
            files={"file": ("s.xls", samples.hdfc_xls(), "application/octet-stream")},
        ).status_code
        == 404
    )
    sample = owner.get("/projects").json()
    assert sample  # the sample firm can bring statements into its own projects
    with make_sessionmaker(engine)() as session:
        p = session.get(Project, project)
        p.organization.trial_ends_on = date(2026, 10, 1)
        session.commit()
    blocked = client.post(
        f"/projects/{project}/bank-statements",
        files={"file": ("s.xls", samples.hdfc_xls(), "application/octet-stream")},
    )
    assert blocked.status_code == 402


# Bank rules


def rule(client, project, **fields):
    body = {"name": "A rule", "how": "phrase", **fields}
    return client.post(f"/projects/{project}/bank-rules", json=body)


def test_rules_place_lines_before_anything_remembered(app) -> None:
    client, project, units = firm(app)
    view = upload(client, project, samples.hdfc_xls())
    sid = view["id"]
    view = client.put(f"/bank-statements/{sid}/options", json={"role": "collections"}).json()
    assert view["lines"][4]["outcome"] == "needs_unit"  # SURESH TRADERS

    made = rule(client, project, name="Suresh Traders refunds", words="suresh traders",
                action="not_buyer", direction="out")  # fmt: skip
    assert made.status_code == 201 and made.json()["fits"] == 1
    view = client.get(f"/bank-statements/{sid}").json()
    line = view["lines"][4]
    assert line["outcome"] == "not_buyer" and line["rule"] == "Suresh Traders refunds"
    assert "by the rule Suresh Traders refunds" in line["note"]
    rules = client.get(f"/projects/{project}/bank-rules").json()["rules"]
    assert rules[0]["lines"] == "Money in"  # a buyer's payment only ever comes in

    # The first rule that fits decides; moving one up changes which.
    first = rule(client, project, name="Rahul", words="rahul", action="unit",
                 unit_id=units["B-201"]).json()  # fmt: skip
    second = rule(client, project, name="Flat A-102", words="flat a 102", action="unit",
                  unit_id=units["A-102"]).json()  # fmt: skip
    line = client.get(f"/bank-statements/{sid}").json()["lines"][1]
    assert (line["unit_label"], line["how"]) == ("B-201", "the rule Rahul")
    client.post(f"/projects/{project}/bank-rules/{second['id']}/up")
    line = client.get(f"/bank-statements/{sid}").json()["lines"][1]
    assert (line["unit_label"], line["how"]) == ("A-102", "the rule Flat A-102")

    # A choice made for the line itself still comes first.
    view = client.put(
        f"/bank-statements/{sid}/options", json={"lines": {line["key"]: units["B-202"]}}
    ).json()
    assert view["lines"][1]["unit_label"] == "B-202"

    # A bounced cheque stays paired with its return, whatever the rules say.
    rule(client, project, name="Cheques", words="chq", how="any", action="leave_out")
    view = client.get(f"/bank-statements/{sid}").json()
    assert view["lines"][5]["outcome"] == view["lines"][6]["outcome"] == "returned"

    client.post(f"/projects/{project}/bank-rules/{first['id']}/delete")
    client.post(f"/projects/{project}/bank-rules/{second['id']}/delete")
    view = client.get(f"/bank-statements/{sid}").json()
    assert view["lines"][1]["unit_label"] == "B-202"
    client.put(f"/bank-statements/{sid}/options", json={"lines": {line["key"]: None}})
    line = client.get(f"/bank-statements/{sid}").json()["lines"][1]
    assert (line["unit_label"], line["how"]) == ("B-202", "your earlier choice for this payer")
    # A rule comes before a payer remembered from an earlier choice.
    rule(client, project, name="Rahul", words="rahul", action="unit", unit_id=units["A-102"])
    line = client.get(f"/bank-statements/{sid}").json()["lines"][1]
    assert (line["unit_label"], line["how"]) == ("A-102", "the rule Rahul")


def test_rules_for_the_rera_account(app) -> None:
    client, project, _ = firm(app)
    lines = [
        *samples.RERA_LINES,
        (date(2026, 6, 30), "TO TRANSFER-SWEEP TO FD 55012", "", "100000", None),
        (date(2026, 6, 30), "BY TRANSFER-SWEEP FROM FD 55012", "", None, "100000"),
        (date(2026, 6, 30), "ANNUAL MAINTENANCE FEE DEBIT CARD", "", "590", None),
    ]
    view = upload(client, project, samples.sbi_xlsx(lines), "rera.xlsx")
    sid = view["id"]
    view = client.put(f"/bank-statements/{sid}/options", json={"role": "rera"}).json()
    assert outcomes(view)[5:] == ["withdrawal", "deposit", "withdrawal"]

    rule(client, project, name="FD sweeps", words="sweep", how="any", action="leave_out")
    rule(client, project, name="Card fee", words="maintenance fee", action="charges",
         max_amount="1,000")  # fmt: skip
    rule(client, project, name="Interest", words="credit interest", action="deposit")
    view = client.get(f"/bank-statements/{sid}").json()
    assert outcomes(view) == [
        "deposit", "deposit", "withdrawal", "deposit", "charges",
        "left_out", "left_out", "charges",
    ]  # fmt: skip
    assert view["lines"][7]["note"] == "By the rule Card fee."

    # Trying a rule shows the lines it would fit before it is saved.
    tried = client.post(
        f"/projects/{project}/bank-rules/try",
        json={"words": "transfer", "how": "any", "action": "leave_out", "direction": "out",
              "min_amount": "150000"},
    ).json()  # fmt: skip
    assert tried["fits"] == 1
    assert "Withdrawal to operating account" in tried["lines"][0]["narration"]


def test_rules_are_checked(app, architect) -> None:
    client, project, units = firm(app)
    other = client.post(
        "/projects",
        json={"name": "Kaveri Lakeside", "krera_registration": "PRM/K/2",
              "registered_on": "2025-04-01"},
    ).json()["id"]  # fmt: skip
    assert rule(client, project, words="x", action="unit").status_code == 400  # no unit
    unsold = client.get(f"/projects/{project}/units").json()
    a103 = next(u["id"] for u in unsold["units"] if u["label"] == "A-103")
    assert rule(client, project, words="x", action="unit", unit_id=a103).status_code == 400
    elsewhere = rule(client, other, words="x", action="unit", unit_id=units["A-101"])
    assert elsewhere.status_code == 400
    every = rule(client, project, words="x", action="unit", unit_id=units["A-101"],
                 every_project=True)  # fmt: skip
    assert every.status_code == 400
    upside_down = rule(client, project, words="x", action="leave_out", min_amount="500",
                       max_amount="100")  # fmt: skip
    assert upside_down.status_code == 400
    assert rule(client, project, words="  ", action="leave_out").status_code == 400

    # A rule for every project shows on each; one for a project only on its own.
    rule(client, project, name="Sweeps", words="sweep", action="leave_out", every_project=True)
    rule(client, project, name="Rahul", words="rahul", action="unit", unit_id=units["A-102"])
    assert [r["name"] for r in client.get(f"/projects/{other}/bank-rules").json()["rules"]] == [
        "Sweeps"
    ]
    assert architect.post(
        f"/projects/{project}/bank-rules", json={"name": "x", "words": "x", "action": "leave_out"}
    ).status_code in (403, 404)

    # A unit a rule names cannot be deleted out from under it.
    gone = client.post(f"/units/{units['A-102']}/delete")
    assert gone.status_code == 400 and "bank rule" in gone.json()["detail"]
