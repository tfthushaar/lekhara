"""Bank statements laid out the way each bank's net banking exports them, for tests.

Built from the layouts banks print (title rows, the column names, how amounts and dates are
written, the summary below); replace or add real exports from design partners beside them.
"""

import csv
import io
from datetime import date
from decimal import Decimal

import xlwt
from openpyxl import Workbook

COLLECTION = "50100087654321"
RERA = "00000030123456789"

# (date, narration, reference, debit, credit)
COLLECTION_LINES = [
    (date(2026, 4, 5), "NEFT CR-SBIN0001234-PRIYA SHARMA-KAVERI HOMES LLP-SBIN426095123456",
     "SBIN426095123456", None, "495000"),
    (date(2026, 4, 10), "IMPS-609912345678-RAHUL K-UTIB-XXXXXXXX1234-FLAT A-102",
     "609912345678", None, "200000"),
    (date(2026, 4, 15), "UPI-ANAND RAO-anand.rao@okicici-ICIC0001234-610512345678-B201 BOOKING",
     "610512345678", None, "100000"),
    (date(2026, 4, 20), "RTGS CR-HDFC0000001-HDFC BANK LTD-KAVERI HOMES LLP-HDFCR52026042012345 "
     "DISB MEERA IYER", "HDFCR52026042012345", None, "5000000"),
    (date(2026, 4, 25), "NEFT CR-KKBK0000123-SURESH TRADERS-KAVERI HOMES LLP-KKBKH26115123456",
     "KKBKH26115123456", None, "75000"),
    (date(2026, 4, 28), "CHQ DEP - MICR CLG - BANGALORE", "000123", None, "300000"),
    (date(2026, 4, 30), "CHQ RETURN - MICR CLG - INSUFFICIENT FUNDS", "000123", "300000", None),
    (date(2026, 4, 30), "TO TRANSFER-INB RERA account 00000030123456789", "", "500000", None),
    (date(2026, 6, 30), "INT.PD:01-04-2026 TO 30-06-2026", "", None, "1234"),
]  # fmt: skip

RERA_LINES = [
    (date(2026, 4, 30), "BY TRANSFER-INB-From collection account 50100087654321", "", None,
     "500000"),
    (date(2026, 5, 15), "BY TRANSFER-NEFT*HDFC0000123*N12345*KAVERI HOMES LLP", "", None,
     "350000"),
    (date(2026, 5, 31), "TO TRANSFER-INB-Withdrawal to operating account per CA certificate",
     "", "200000", None),
    (date(2026, 6, 30), "CREDIT INTEREST", "", None, "1850"),
    (date(2026, 6, 30), "SMS CHARGES INCL GST", "", "17.70", None),
]  # fmt: skip


def _with_balances(lines, opening: Decimal):
    balance = opening
    out = []
    for on, narration, ref, debit, credit in lines:
        balance = balance - Decimal(debit or 0) + Decimal(credit or 0)
        out.append((on, narration, ref, debit, credit, balance))
    return out


def hdfc_xls(lines=COLLECTION_LINES, account=COLLECTION, opening="0") -> bytes:
    """HDFC Bank: title rows, a row of stars, the table, then the statement summary."""
    book = xlwt.Workbook()
    sheet = book.add_sheet("Sheet 1")
    top = [
        "HDFC BANK Ltd.",
        "KAVERI HOMES LLP",
        "Account Branch : MG ROAD BANGALORE",
        f"Account No : {account}   CURRENT ACCOUNT",
        "RTGS/NEFT IFSC : HDFC0000123",
        "Statement From : 01/04/2026 To : 30/09/2026",
        "",
    ]
    r = 0
    for text in top:
        sheet.write(r, 0, text)
        r += 1
    headers = [
        "Date",
        "Narration",
        "Chq./Ref.No.",
        "Value Dt",
        "Withdrawal Amt.",
        "Deposit Amt.",
        "Closing Balance",
    ]
    for c, h in enumerate(headers):
        sheet.write(r, c, h)
    r += 1
    for c in range(len(headers)):
        sheet.write(r, c, "********")
    r += 1
    rows = _with_balances(lines, Decimal(opening))
    for on, narration, ref, debit, credit, balance in rows:
        values = [
            on.strftime("%d/%m/%y"),
            narration,
            ref,
            on.strftime("%d/%m/%y"),
            float(debit) if debit else "",
            float(credit) if credit else "",
            float(balance),
        ]
        for c, v in enumerate(values):
            sheet.write(r, c, v)
        r += 1
    r += 1
    sheet.write(r, 0, "STATEMENT SUMMARY  :-")
    r += 1
    for c, h in enumerate(
        ["Opening Balance", "Dr Count", "Cr Count", "Debits", "Credits", "Closing Bal"]
    ):
        sheet.write(r, c, h)
    r += 1
    sheet.write(r, 0, float(opening))
    sheet.write(r, 5, float(rows[-1][5]))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _inr(amount) -> str:
    """1,23,456.00, as Indian banks print it."""
    whole, _, paise = f"{Decimal(amount):.2f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail]) + "." + paise if groups else f"{tail}.{paise}"


def sbi_xlsx(lines=RERA_LINES, account=RERA, opening="0") -> bytes:
    """State Bank of India: account details above, dates like 1 Apr 2026, amounts as text."""
    book = Workbook()
    sheet = book.active
    for row in [
        ["Account Name", ": KAVERI HOMES LLP RERA DESIGNATED ACCOUNT"],
        ["Account Number", f": {account}"],
        ["Branch", ": MG ROAD BANGALORE"],
        ["IFS Code", ": SBIN0001234"],
        ["Balance as on 1 Apr 2026", f": {_inr(opening)}"],
        [],
        [f"Account Statement from {lines[0][0]:%d %b %Y} to {lines[-1][0]:%d %b %Y}"],
        [],
        ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit",
         "Balance"],
    ]:  # fmt: skip
        sheet.append(row)
    for on, narration, ref, debit, credit, balance in _with_balances(lines, Decimal(opening)):
        when = f"{on.day} {on:%b %Y}"
        sheet.append(
            [
                when,
                when,
                narration,
                ref,
                _inr(debit) if debit else "",
                _inr(credit) if credit else "",
                _inr(balance),
            ]
        )
    sheet.append([])
    sheet.append(["**This is a computer generated statement and does not require a signature"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def icici_csv(lines=COLLECTION_LINES, account=COLLECTION) -> bytes:
    """ICICI Bank: a detailed statement with zero for no amount."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["DETAILED STATEMENT"])
    w.writerow([f"Account Number: {account} ( INR ) - KAVERI HOMES LLP"])
    w.writerow(["Transaction Date from: 01/04/2026 to 30/09/2026"])
    w.writerow([])
    w.writerow(
        [
            "S No.",
            "Value Date",
            "Transaction Date",
            "Cheque Number",
            "Transaction Remarks",
            "Withdrawal Amount (INR )",
            "Deposit Amount (INR )",
            "Balance (INR )",
        ]
    )
    for i, (on, narration, ref, debit, credit, balance) in enumerate(
        _with_balances(lines, Decimal(0)), start=1
    ):
        when = on.strftime("%d/%m/%Y")
        w.writerow(
            [i, when, when, ref or "-", narration, debit or "0.00", credit or "0.00", balance]
        )
    return out.getvalue().encode()


def kotak_csv(lines=COLLECTION_LINES, account=COLLECTION) -> bytes:
    """Kotak: one amount with Dr or Cr beside it, newest first."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"Account No.,{account}"])
    w.writerow([])
    w.writerow(["Sl. No.", "Transaction Date", "Value Date", "Description", "Chq / Ref No.",
                "Amount", "Dr / Cr", "Balance", "Dr / Cr"])  # fmt: skip
    rows = _with_balances(lines, Decimal(0))
    for i, (on, narration, ref, debit, credit, balance) in enumerate(reversed(rows), start=1):
        when = on.strftime("%d-%m-%Y")
        w.writerow([i, when, when, narration, ref, _inr(debit or credit), "DR" if debit else "CR",
                    _inr(balance), "CR"])  # fmt: skip
    return out.getvalue().encode()


def axis_html(lines=COLLECTION_LINES, account="917020012345678") -> bytes:
    """Axis Bank: an "Excel" download that is really a web page."""
    rows = "".join(
        f"<tr><td>{on:%d-%m-%Y}</td><td>{ref}</td><td>{narration}</td>"
        f"<td>{debit or ''}</td><td>{credit or ''}</td><td>{balance}</td><td>1234</td></tr>"
        for on, narration, ref, debit, credit, balance in _with_balances(lines, Decimal(0))
    )
    return (
        "<html><body><table>"
        f"<tr><td>Statement of Axis Account No :{account} for the period "
        "(From : 01-04-2026 To : 30-09-2026)</td></tr>"
        "<tr><th>Tran Date</th><th>CHQNO</th><th>PARTICULARS</th><th>DR</th><th>CR</th>"
        "<th>BAL</th><th>SOL</th></tr>"
        f"{rows}</table></body></html>"
    ).encode()
