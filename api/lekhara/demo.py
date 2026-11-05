"""What the public demo adds, so every workflow can be tried with made-up data.

On a demo server (LEKHARA_DEMO=1):

- On the public demo (LEKHARA_SHARED_DEMO=1 as well), everyone signs in as the same demo
  accounts (@demo.lekhara), so steps that would lock the others out are refused for them:
  changing their password, turning on two-step sign-in, signing out everyone else, deleting
  the account, closing the firm, and changing who may do what. Anyone can sign up for a firm of
  their own in the demo to try those.
- Emails go nowhere. Each person reads the ones sent to them in the demo mailbox, and a data
  room visitor sees their code on the page.
- Each project offers sample files to bring in, made from the project's own units, suppliers
  and bills: a Tally export, the collection and RERA account statements, a GSTR-2B and a list
  of units, plus a K-RERA certificate for adding a new project. A sample email with a statement
  attached can be sent to the project's own address and is brought in at once.
"""

import csv
import io
import json
import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from email.message import EmailMessage
from xml.sax.saxutils import escape

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import inbound
from lekhara.accounts import gstin_with_check
from lekhara.config import Settings
from lekhara.imports import _csv
from lekhara.models import (
    Bill,
    EscrowTxn,
    InboundMessage,
    Organization,
    OutboundEmail,
    Project,
    Unit,
    Vendor,
)
from lekhara.pdf import write_pdf
from lekhara.records import UNITS
from lekhara.services import ServiceError
from lekhara.storage import Storage

DEMO_DOMAIN = "@demo.lekhara"
COLLECTION_ACCOUNT = "50100087654321"
RERA_ACCOUNT = "00000030123456789"


# The shared accounts


def is_demo_account(email: str | None) -> bool:
    return (email or "").casefold().endswith(DEMO_DOMAIN)


def guard(settings: Settings, email: str | None, what: str) -> None:
    """Refuses a step that would change things for everyone using a shared demo account."""
    if settings.shared_demo and is_demo_account(email):
        raise ServiceError(
            f"The demo's own accounts can't {what}, because everyone trying the demo uses them. "
            "Sign up for a firm of your own in the demo to try it.",
            403,
        )


def mailbox(session: Session, email: str, limit: int = 30) -> list[dict]:
    """The emails Lekhara would have sent to this address, newest first."""
    rows = session.scalars(
        select(OutboundEmail)
        .where(OutboundEmail.to_address == email)
        .order_by(OutboundEmail.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "at": r.created_at.replace(microsecond=0).isoformat(),
            "subject": r.subject,
            "body": r.body,
            "kind": r.kind,
        }
        for r in rows
    ]


# Sample files, made from the project's own records


@dataclass(frozen=True)
class Sample:
    name: str
    label: str
    detail: str
    goes_to: str
    content_type: str


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SAMPLES = (
    Sample(
        "tally-export.xml",
        "Tally export",
        "A supplier's bill and its payment, a contractor's bill and two buyers' payments, as "
        "TallyPrime exports them.",
        "Tally",
        "application/xml",
    ),
    Sample(
        "collection-account.csv",
        "Collection account statement",
        "Buyers' payments, a home-loan disbursement, a bounced cheque and a payment from "
        "someone who isn't a buyer.",
        "Bank statement",
        "text/csv",
    ),
    Sample(
        "rera-account.xlsx",
        "RERA account statement",
        "Deposits, a withdrawal, interest and bank charges.",
        "Bank statement",
        XLSX,
    ),
    Sample(
        "gstr-2b.json",
        "GSTR-2B",
        "Last month's supplier invoices as the GST portal gives them: one amount differs, one "
        "invoice has no bill, and there's a credit note.",
        "GST portal",
        "application/json",
    ),
    Sample(
        "units.csv",
        "Units and buyers",
        "Twelve more units and their buyers, in a new tower.",
        "Units and buyers",
        "text/csv",
    ),
)
CERTIFICATE = Sample(
    "krera-certificate.pdf",
    "K-RERA certificate",
    "A registration certificate for a new project, to add it from the certificate.",
    "New project",
    "application/pdf",
)


def _org(session: Session, project: Project) -> Organization:
    return session.get(Organization, project.organization_id)


def _firm(org: Organization) -> str:
    return (org.legal_name or org.name).upper()


def _booked(session: Session, project: Project) -> list[Unit]:
    return list(
        session.scalars(
            select(Unit)
            .where(Unit.project_id == project.id, Unit.booked, Unit.buyer_name.is_not(None))
            .order_by(Unit.label)
        )
    )


def _ref() -> str:
    return str(secrets.randbelow(10**12)).zfill(12)


def _lines_with_balances(lines, opening: Decimal):
    balance = opening
    for on, narration, ref, debit, credit in lines:
        balance = balance - Decimal(debit or 0) + Decimal(credit or 0)
        yield on, narration, ref, debit, credit, balance


def _inr(amount) -> str:
    whole, _, paise = f"{Decimal(amount):.2f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail]) + "." + paise if groups else f"{tail}.{paise}"


def collection_statement(session: Session, project: Project, as_of: date) -> bytes:
    """The account buyers pay into, as ICICI Bank's detailed statement in CSV."""
    org = _org(session, project)
    firm = _firm(org)
    units = _booked(session, project)
    lines = []
    day = as_of - timedelta(days=24)
    by_number = units[:3]
    for i, u in enumerate(by_number):
        first = (u.buyer_name or "").split()[0].upper()
        lines.append((day + timedelta(days=2 * i), f"IMPS-{_ref()}-{first}-UTIB-XXXXXXXX1234-"
                      f"FLAT {u.label}", _ref(), None, str(250000 + 50000 * i)))  # fmt: skip
    if len(units) > 3:
        u = units[3]
        lines.append((day + timedelta(days=7), f"NEFT CR-SBIN0001234-{u.buyer_name.upper()}-"
                      f"{firm}-SBIN{_ref()}", _ref(), None, "475000"))  # fmt: skip
    if len(units) > 4:
        u = units[4]
        narration = f"RTGS CR-HDFC0000001-HDFC BANK LTD-{firm}-HDFCR{_ref()} DISB "
        lines.append((day + timedelta(days=9), narration + u.buyer_name.upper(), _ref(), None,
                      "2500000"))  # fmt: skip
    lines += [
        (day + timedelta(days=11), f"NEFT CR-KKBK0000123-SURESH TRADERS-{firm}-KKBKH{_ref()}",
         _ref(), None, "75000"),
        (day + timedelta(days=13), "CHQ DEP - MICR CLG - BANGALORE", "000123", None, "300000"),
        (day + timedelta(days=15), "CHQ RETURN - MICR CLG - INSUFFICIENT FUNDS", "000123",
         "300000", None),
        (day + timedelta(days=18), f"TO TRANSFER-INB RERA account {RERA_ACCOUNT}", "", "1250000",
         None),
        (day + timedelta(days=22), f"INT.PD:{day:%d-%m-%Y} TO {as_of:%d-%m-%Y}", "", None, "1834"),
    ]  # fmt: skip
    lines.sort(key=lambda line: line[0])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["DETAILED STATEMENT"])
    w.writerow([f"Account Number: {COLLECTION_ACCOUNT} ( INR ) - {firm}"])
    w.writerow([f"Transaction Date from: {lines[0][0]:%d/%m/%Y} to {lines[-1][0]:%d/%m/%Y}"])
    w.writerow([])
    w.writerow(["S No.", "Value Date", "Transaction Date", "Cheque Number",
                "Transaction Remarks", "Withdrawal Amount (INR )", "Deposit Amount (INR )",
                "Balance (INR )"])  # fmt: skip
    opening = Decimal("1500000")
    for i, (on, narration, ref, debit, credit, balance) in enumerate(
        _lines_with_balances(lines, opening), start=1
    ):
        when = on.strftime("%d/%m/%Y")
        w.writerow([i, when, when, ref or "-", narration, debit or "0.00", credit or "0.00",
                    f"{balance:.2f}"])  # fmt: skip
    return out.getvalue().encode()


def _rera_balance(session: Session, project: Project, before: date) -> Decimal:
    total = Decimal("0")
    for t in session.scalars(
        select(EscrowTxn).where(EscrowTxn.project_id == project.id, EscrowTxn.txn_date < before)
    ):
        if t.kind in ("deposit", "interest"):
            total += t.amount
        elif t.kind in ("withdrawal", "charges"):
            total -= t.amount
    return total


def rera_statement(session: Session, project: Project, as_of: date) -> bytes:
    """The RERA designated account, as State Bank of India's statement in Excel."""
    firm = _firm(_org(session, project))
    start = as_of - timedelta(days=20)
    opening = _rera_balance(session, project, start)
    lines = [
        (start, f"BY TRANSFER-INB-From collection account {COLLECTION_ACCOUNT}", "", None,
         "1250000"),
        (start + timedelta(days=8), f"BY TRANSFER-NEFT*HDFC0000123*N{_ref()[:5]}*{firm}", "",
         None, "480000"),
        (start + timedelta(days=12), "TO TRANSFER-INB-Withdrawal to operating account per CA "
         "certificate", "", "800000", None),
        (start + timedelta(days=17), "CREDIT INTEREST", "", None, "2140"),
        (start + timedelta(days=17), "SMS CHARGES INCL GST", "", "17.70", None),
    ]  # fmt: skip
    book = Workbook()
    sheet = book.active
    for row in [
        ["Account Name", f": {firm} RERA DESIGNATED ACCOUNT"],
        ["Account Number", f": {RERA_ACCOUNT}"],
        ["Branch", f": {(project.escrow_bank or 'BENGALURU').upper()}"],
        ["IFS Code", ": SBIN0001234"],
        [f"Balance as on {start.day} {start:%b %Y}", f": {_inr(opening)}"],
        [],
        [f"Account Statement from {lines[0][0]:%d %b %Y} to {lines[-1][0]:%d %b %Y}"],
        [],
        ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit",
         "Balance"],
    ]:  # fmt: skip
        sheet.append(row)
    for on, narration, ref, debit, credit, balance in _lines_with_balances(lines, opening):
        when = f"{on.day} {on:%b %Y}"
        sheet.append([when, when, narration, ref, _inr(debit) if debit else "",
                      _inr(credit) if credit else "", _inr(balance)])  # fmt: skip
    sheet.append([])
    sheet.append(["**This is a computer generated statement and does not require a signature"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _registered_bills(session: Session, project: Project) -> list[tuple[Bill, Vendor]]:
    rows = session.execute(
        select(Bill, Vendor)
        .join(Vendor, Vendor.id == Bill.vendor_id)
        .where(Bill.project_id == project.id, Vendor.gstin.is_not(None))
        .order_by(Bill.bill_date)
    )
    return [(b, v) for b, v in rows]


def _gst_line(number: str, on: date, taxable: Decimal) -> dict:
    half = (taxable * Decimal("0.09")).quantize(Decimal("0.01"))
    return {
        "dt": on.strftime("%d-%m-%Y"), "val": float(taxable + 2 * half), "pos": "29",
        "rev": "N", "itcavl": "Y", "txval": float(taxable), "igst": 0, "cgst": float(half),
        "sgst": float(half), "cess": 0,
    }  # fmt: skip


def gstr2b(session: Session, project: Project, as_of: date) -> bytes:
    """Last month's GSTR-2B for the firm, as the GST portal's JSON: the project's bills from
    registered suppliers that month (one at a different amount, one left out as if its supplier
    had not filed), an invoice with no bill in Lekhara, and a credit note."""
    org = _org(session, project)
    bills = _registered_bills(session, project)
    months = sorted({(b.bill_date.year, b.bill_date.month) for b, _ in bills})
    year, month = (
        months[-1]
        if months
        else (
            (as_of.replace(day=1) - timedelta(days=1)).year,
            (as_of.replace(day=1) - timedelta(days=1)).month,
        )
    )
    chosen = [(b, v) for b, v in bills if (b.bill_date.year, b.bill_date.month) == (year, month)]
    if len(chosen) >= 3:
        chosen = chosen[:-1]  # its supplier has not filed it yet
    filed = date(year, month, 1) + timedelta(days=40)
    suppliers: dict[str, dict] = {}

    def block(ctin: str, name: str) -> dict:
        new = {"ctin": ctin, "trdnm": name, "supfildt": filed.strftime("%d-%m-%Y"),
               "supprd": f"{month:02d}{year}", "inv": []}  # fmt: skip
        return suppliers.setdefault(ctin, new)

    for i, (b, v) in enumerate(chosen):
        taxable = (
            b.taxable_value if i else (b.taxable_value * Decimal("0.98")).quantize(Decimal("1"))
        )
        line = {"inum": b.bill_no, "typ": "R", **_gst_line(b.bill_no, b.bill_date, taxable),
                "rsn": "", "diffprcnt": 1, "srctyp": "e-Invoice"}  # fmt: skip
        block(v.gstin, v.name.upper())["inv"].append(line)
    new_supplier = gstin_with_check("29AAKFN5678P1Z")
    block(new_supplier, "NEW HORIZON ELEVATORS")["inv"].append(
        {
            "inum": "NHE/2231",
            "typ": "R",
            **_gst_line("NHE/2231", date(year, month, 18), Decimal("640000")),
            "rsn": "",
            "diffprcnt": 1,
            "srctyp": "e-Invoice",
        }  # fmt: skip
    )
    notes = []
    if chosen:
        b, v = chosen[0]
        amounts = _gst_line(f"CN-{b.bill_no}", date(year, month, 25), Decimal("25000"))
        note = {"ntnum": f"CN-{b.bill_no}", "typ": "C", "suptyp": "R", **amounts}
        notes.append({"ctin": v.gstin, "trdnm": v.name.upper(), "nt": [note]})
    payload = {
        "chksum": "demo",
        "data": {
            "gstin": org.gstin or gstin_with_check("29AAECD4321K1Z"),
            "rtnprd": f"{month:02d}{year}",
            "version": "1.0",
            "gendt": date(year, month, 1).replace(day=14).strftime("%d-%m-%Y"),
            "itcsumm": {"itcavl": {"nonrevsup": {"igst": 0, "cgst": 0, "sgst": 0, "cess": 0}}},
            "docdata": {"b2b": list(suppliers.values()), "cdnr": notes},
        },
    }
    return json.dumps(payload, indent=1).encode()


def units_list(session: Session, project: Project, as_of: date) -> bytes:
    """Twelve more units and their buyers, in the Import centre's own columns."""
    from lekhara.seed import buyer_name

    taken = {u.label for u in session.scalars(select(Unit).where(Unit.project_id == project.id))}
    tower = next(t for t in "BCDEFGH" if not any(label.startswith(t) for label in taken))
    rows = []
    for i in range(12):
        floor, flat = 1 + i // 4, 1 + i % 4
        values = {
            "label": f"{tower}-{floor:02d}{flat:02d}",
            "tower": f"Tower {tower}",
            "carpet_area_sqft": str(980 + 60 * (i % 4)),
            "buyer_name": buyer_name(200 + i) if i % 3 != 2 else "",
            "booked_on": (as_of - timedelta(days=30 + 11 * i)).strftime("%d/%m/%Y")
            if i % 3 != 2
            else "",
            "agreement_value": str(8200000 + 150000 * i) if i % 3 != 2 else "",
        }
        rows.append([values.get(f.key, "") for f in UNITS.fields])
    return _csv(UNITS, rows)


def _entry(ledger: str, amount: Decimal, *, inner: str = "", party: bool = False) -> str:
    """One line of a Tally voucher. Tally writes a debit as a negative amount marked deemed
    positive, and a credit as a positive amount."""
    debit = amount < 0
    return (
        "  <ALLLEDGERENTRIES.LIST>"
        f"<LEDGERNAME>{ledger}</LEDGERNAME>"
        f"<ISDEEMEDPOSITIVE>{'Yes' if debit else 'No'}</ISDEEMEDPOSITIVE>"
        + ("<ISPARTYLEDGER>Yes</ISPARTYLEDGER>" if party else "")
        + f"<AMOUNT>{amount:.2f}</AMOUNT>{inner}</ALLLEDGERENTRIES.LIST>\n"
    )


def _bill(name: str, kind: str, amount: Decimal) -> str:
    return (
        f"<BILLALLOCATIONS.LIST><NAME>{name}</NAME><BILLTYPE>{kind}</BILLTYPE>"
        f"<AMOUNT>{amount:.2f}</AMOUNT></BILLALLOCATIONS.LIST>"
    )


def _voucher(kind: str, on: date, guid: str, number: str, entries: list[str], **head) -> str:
    tags = "".join(f"<{tag.upper()}>{value}</{tag.upper()}>" for tag, value in head.items())
    return (
        '<TALLYMESSAGE xmlns:UDF="TallyUDF">\n'
        f' <VOUCHER VCHTYPE="{kind}" ACTION="Create">\n'
        f"  <DATE>{on:%Y%m%d}</DATE><GUID>{guid}</GUID><VOUCHERTYPENAME>{kind}</VOUCHERTYPENAME>"
        f"<VOUCHERNUMBER>{number}</VOUCHERNUMBER>{tags}\n" + "".join(entries) + " </VOUCHER>\n"
        "</TALLYMESSAGE>\n"
    )


def _ledger(name: str, parent: str, extra: str = "") -> str:
    return f' <LEDGER NAME="{name}"><PARENT>{parent}</PARENT>{extra}</LEDGER>\n'


def tally_export(session: Session, project: Project, as_of: date) -> bytes:
    """A month of the project's books as TallyPrime exports them in XML: a supplier's bill and
    its payment, a contractor's bill booked as a journal, and two buyers' payments."""
    org = _org(session, project)
    supplier = session.scalars(
        select(Vendor).where(Vendor.organization_id == org.id, Vendor.gstin.is_not(None))
    ).first()
    name = escape(supplier.name if supplier else "Kaveri Steel Traders")
    gstin = supplier.gstin if supplier else gstin_with_check("29AAGCK7383J1Z")
    buyers = _booked(session, project)[5:7]
    day = as_of - timedelta(days=21)
    tag = f"demo-{as_of:%Y%m%d}-{secrets.token_hex(3)}"
    bill_no = f"KST/{1000 + secrets.randbelow(8999)}"
    total, cost, tax = Decimal("236000"), Decimal("200000"), Decimal("18000")

    masters = (
        '<TALLYMESSAGE xmlns:UDF="TallyUDF">\n'
        ' <GROUP NAME="Site Expenses" ACTION="Create"><PARENT>Direct Expenses</PARENT></GROUP>\n'
        + _ledger(name, "Sundry Creditors",
                  f"<GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE><PARTYGSTIN>{gstin}"
                  "</PARTYGSTIN><LEDSTATENAME>Karnataka</LEDSTATENAME>"
                  "<ISBILLWISEON>Yes</ISBILLWISEON>")
        + _ledger("Ramesh Shuttering", "Sundry Creditors")
        + _ledger("Steel Purchases", "&#4; Purchase Accounts")
        + _ledger("Civil Works", "Site Expenses")
        + _ledger("Input CGST 9%", "Duties &amp; Taxes", "<TAXTYPE>GST</TAXTYPE>")
        + _ledger("Input SGST 9%", "Duties &amp; Taxes", "<TAXTYPE>GST</TAXTYPE>")
        + _ledger("Collection A/c", "Bank Accounts")
        + _ledger("Current A/c", "Bank Accounts")
        + "".join(
            _ledger(f"{escape(u.label)} {escape(u.buyer_name)}", "Sundry Debtors") for u in buyers
        )
        + "</TALLYMESSAGE>\n"
    )  # fmt: skip
    centre = (
        "<CATEGORYALLOCATIONS.LIST><CATEGORY>Primary Cost Category</CATEGORY>"
        f"<COSTCENTREALLOCATIONS.LIST><NAME>{escape(project.name)}</NAME>"
        f"<AMOUNT>{-cost:.2f}</AMOUNT></COSTCENTREALLOCATIONS.LIST></CATEGORYALLOCATIONS.LIST>"
    )
    vouchers = [
        _voucher(
            "Purchase", day, f"{tag}-1", "1",
            [
                _entry(name, total, inner=_bill(bill_no, "New Ref", total), party=True),
                _entry("Steel Purchases", -cost, inner=centre),
                _entry("Input CGST 9%", -tax),
                _entry("Input SGST 9%", -tax),
            ],
            reference=bill_no, referencedate=f"{day:%Y%m%d}", partyledgername=name,
            partygstin=gstin,
        ),
        _voucher(
            "Payment", day + timedelta(days=9), f"{tag}-2", "5",
            [
                _entry(name, -total, inner=_bill(bill_no, "Agst Ref", -total)),
                _entry("Current A/c", total),
            ],
            partyledgername=name,
        ),
        _voucher(
            "Journal", day + timedelta(days=12), f"{tag}-3", "J-12",
            [
                _entry("Civil Works", Decimal("-150000")),
                _entry("Ramesh Shuttering", Decimal("150000")),
            ],
            narration="RA bill 3, shuttering",
        ),
    ]  # fmt: skip
    for i, u in enumerate(buyers):
        ledger = f"{escape(u.label)} {escape(u.buyer_name)}"
        amount = Decimal(300000 + 100000 * i)
        vouchers.append(
            _voucher(
                "Receipt", day + timedelta(days=14 + 2 * i), f"{tag}-r{i}", f"R-{20 + i}",
                [_entry(ledger, amount), _entry("Collection A/c", -amount)],
                partyledgername=ledger,
            )
        )  # fmt: skip
    company = escape(org.legal_name or org.name)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ENVELOPE>\n'
        " <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>\n"
        " <BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>All Masters</REPORTNAME>\n"
        f"  <STATICVARIABLES><SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY></STATICVARIABLES>\n"
        " </REQUESTDESC><REQUESTDATA>\n"
        + masters
        + "".join(vouchers)
        + "</REQUESTDATA></IMPORTDATA></BODY>\n</ENVELOPE>\n"
    ).encode("utf-8")


def krera_certificate(org: Organization, as_of: date) -> bytes:
    """Form C for a new demo project, as K-RERA issues it, with typed text Lekhara can read."""
    start = as_of.replace(day=1)
    end = date(start.year + 4, start.month, 1) - timedelta(days=1)
    number = f"PRM/KA/RERA/1251/309/PR/{start:%y%m%d}/008123"
    lines = [
        "FORM 'C'",
        "[See rule 6(a)]",
        "REGISTRATION CERTIFICATE OF PROJECT",
        "This registration is granted under section 5 of the Act to the following project under",
        f"project registration number {number}",
        "Project: Yelahanka Meadows, Sy. No. 88/1, situated at Doddaballapur Road, Yelahanka,",
        "Bengaluru Urban District, Karnataka 560064.",
        f"1. {org.legal_name or org.name} having its registered office at 21 Residency Road, "
        "Bengaluru.",
        "2. This registration is granted subject to the following conditions, namely:",
        f"(iii) The registration shall be valid for a period commencing from {start:%d/%m/%Y} "
        "and ending",
        f"with {end:%d/%m/%Y} unless renewed by the Real Estate Regulatory Authority.",
        "",
        "Made-up for the Lekhara demo.",
    ]
    return write_pdf([lines], title="Registration certificate (demo)")


MAKERS = {
    "tally-export.xml": tally_export,
    "collection-account.csv": collection_statement,
    "rera-account.xlsx": rera_statement,
    "gstr-2b.json": gstr2b,
    "units.csv": units_list,
}


def sample_file(session: Session, project: Project, name: str, as_of: date) -> tuple[Sample, bytes]:
    sample = next((s for s in SAMPLES if s.name == name), None)
    if sample is None:
        raise ServiceError("No such sample file.", 404)
    return sample, MAKERS[name](session, project, as_of)


# A sample email to the project's own address


def send_sample_email(
    session: Session,
    storage: Storage,
    settings: Settings,
    project: Project,
    sender: str,
    as_of: date,
) -> InboundMessage:
    """An email from the person to the project's forwarding address, with the collection
    account statement attached, brought in at once as a real one would be."""
    address = inbound.address_for(session, project, settings)
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = address
    msg["Subject"] = f"Statement for {as_of:%B %Y}"
    msg["Authentication-Results"] = (
        f"mx.demo.lekhara; dmarc=pass header.from={sender.rpartition('@')[2]}"
    )
    msg.set_content("Forwarding this month's statement from net banking.")
    msg.add_attachment(
        collection_statement(session, project, as_of),
        maintype="text",
        subtype="csv",
        filename=f"statement-{as_of:%Y-%m}.csv",
    )
    message = inbound.receive(session, storage, settings, msg.as_bytes(), envelope_to=[address])
    if message is None:
        raise ServiceError("The project's address could not be found.", 404)
    if message.status == "queued":
        inbound.process(session, storage, settings, message.id)
    return session.get(InboundMessage, message.id)
