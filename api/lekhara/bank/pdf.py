"""Bank statements as PDF, the way banks email them.

The text of each page is read line by line. A transaction line starts with a date and ends with
the running balance; the amount just before the balance is the transaction. Whether it went in
or out is read from the balance itself (the balance after a deposit is the one before plus the
amount), so the reader needs no knowledge of each bank's columns. Narrations that run onto the
next line are joined. Statements protected by a password (most emailed ones are) are opened with
the passwords the firm has given Lekhara.
"""

import re
from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from lekhara.bank.reader import (
    CENT,
    HOW_TO_DOWNLOAD,
    Line,
    Statement,
    assemble,
    parse_amount,
    parse_date,
)
from lekhara.services import ServiceError

_DATE = r"\d{1,2}[-/. ](?:\d{1,2}|[A-Za-z]{3,9})[-/. ]\d{2,4}"
_START = re.compile(rf"^\s*(?:\d{{1,4}}\s+)?({_DATE})\b")
_ANOTHER_DATE = re.compile(rf"^\s*({_DATE})\b")
_AMOUNT = re.compile(r"(?<![\w.,/-])(\(?-?\d{1,3}(?:,\d{2,3})*(?:\.\d{2})\)?|\(?-?\d+\.\d{2}\)?)"
                     r"(\s*\(?(?:cr|dr)\b\.?\)?)?", re.IGNORECASE)  # fmt: skip
_FOOTER = re.compile(
    r"closing balance|opening balance|statement summary|page \d+|\btotal\b|end of statement|"
    r"computer generated|grand total|carried forward|brought forward",
    re.IGNORECASE,
)
_CREDIT_WORDS = re.compile(
    r"\b(by|cr|credit|dep|deposit|neft cr|rtgs cr|imps cr|int\.?\s*pd|interest)\b", re.I
)
_DEBIT_WORDS = re.compile(r"\b(to|dr|debit|wdl|withdrawal|atm|chgs?|charges?|paid)\b", re.I)


class PasswordNeeded(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            "This statement is protected by a password. Add the password under Settings, "
            "Statement passwords, and Lekhara opens it and every later one."
        )


def open_pdf(data: bytes, passwords: tuple[str, ...] = ()) -> PdfReader:
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, ValueError, OSError):
        raise ServiceError(f"This PDF could not be opened. {HOW_TO_DOWNLOAD}") from None
    if reader.is_encrypted:
        for password in ("", *passwords):
            try:
                if reader.decrypt(password):
                    return reader
            except (PdfReadError, ValueError, NotImplementedError):
                continue
        raise PasswordNeeded()
    return reader


def text_lines(reader: PdfReader) -> list[str]:
    lines: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception:  # noqa: BLE001 - pypdf raises many kinds of errors on odd pages
            text = page.extract_text() or ""
        lines.extend(line.rstrip() for line in text.splitlines() if line.strip())
    return lines


def looks_like_statement(data: bytes) -> bool:
    """Worth trying as a statement: a protected PDF (most emailed statements are), or one whose
    first page talks about a statement and a balance."""
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, ValueError, OSError):
        return False
    if reader.is_encrypted:
        return True
    try:
        first = (reader.pages[0].extract_text() or "").casefold() if reader.pages else ""
    except Exception:  # noqa: BLE001
        return False
    return "balance" in first and ("statement" in first or "account" in first)


def _amounts(text: str) -> list[tuple[Decimal, str | None, int]]:
    """Each amount in the text, with any Cr or Dr written by it, and where it starts."""
    found = []
    for m in _AMOUNT.finditer(text):
        value, side = parse_amount(m.group(1) + (m.group(2) or ""))
        if value is not None:
            found.append((value, side, m.start()))
    return found


def _side(prev: Decimal | None, amount: Decimal, balance: Decimal, words: str, marker) -> str:
    if prev is not None:
        if abs(prev + amount - balance) <= CENT:
            return "cr"
        if abs(prev - amount - balance) <= CENT:
            return "dr"
    if marker in ("cr", "dr"):
        return marker
    if _CREDIT_WORDS.search(words) and not _DEBIT_WORDS.search(words):
        return "cr"
    if _DEBIT_WORDS.search(words):
        return "dr"
    return "cr"


def read_pdf_statement(filename: str, data: bytes, passwords: tuple[str, ...] = ()) -> Statement:
    reader = open_pdf(data, passwords)
    rows = text_lines(reader)
    if not rows:
        raise ServiceError(
            "This PDF has no text in it: it is a scan or a picture. " + HOW_TO_DOWNLOAD
        )
    above: list[str] = []
    below: list[str] = []
    raw: list[dict] = []
    opening: Decimal | None = None
    for row in rows:
        start = _START.match(row)
        if start and not _FOOTER.search(row) and _amounts(row[start.end() :]):
            on = parse_date(start.group(1))
            rest = row[start.end() :]
            value_date = _ANOTHER_DATE.match(rest)
            text = rest[value_date.end() :] if value_date else rest
            amounts = _amounts(text)
            if on is None or not amounts:
                continue
            balance, balance_side, _ = amounts[-1]
            if balance_side == "dr":
                balance = -abs(balance)
            moving = [a for a in amounts[:-1] if a[0] != 0]
            words = re.sub(r"\s{2,}", " ", text[: amounts[0][2]].strip())
            if not moving:
                # Only one figure: the balance carried forward, or the opening balance.
                if not raw and re.search(r"opening|b/f|brought forward", text, re.I):
                    opening = balance
                continue
            amount, marker, _ = moving[-1]
            raw.append(
                {
                    "on": on,
                    "value_date": parse_date(value_date.group(1)) if value_date else None,
                    "words": words,
                    "amount": abs(amount),
                    "marker": marker,
                    "balance": balance,
                }
            )
            continue
        if not raw:
            above.append(row.strip())
            if re.search(r"opening balance", row, re.I):
                found = _amounts(row)
                if found:
                    value, side, _ = found[-1]
                    opening = -abs(value) if side == "dr" else value
            continue
        if not _amounts(row) and not _FOOTER.search(row):
            raw[-1]["words"] = f"{raw[-1]['words']} {row.strip()}".strip()
        else:
            below.append(row.strip())
    if not raw:
        raise ServiceError("Lekhara could not find transactions in this PDF. " + HOW_TO_DOWNLOAD)
    newest_first = len(raw) > 1 and raw[0]["on"] > raw[-1]["on"]
    if newest_first:
        raw.reverse()
    lines: list[Line] = []
    previous = opening
    for entry in raw:
        side = _side(previous, entry["amount"], entry["balance"], entry["words"], entry["marker"])
        lines.append(
            Line(
                index=len(lines),
                on=entry["on"],
                narration=entry["words"],
                reference="",
                debit=entry["amount"] if side == "dr" else Decimal("0"),
                credit=entry["amount"] if side == "cr" else Decimal("0"),
                balance=entry["balance"],
                value_date=entry["value_date"],
            )
        )
        previous = entry["balance"]
    for line in lines:
        line.narration = _tidy(line.narration, line.on)
    statement = assemble(
        lines,
        above=above,
        below=below,
        filename=filename,
        columns={
            "date": "Date",
            "narration": "Narration",
            "amount": "Amount",
            "balance": "Balance",
        },
        opening_from_line=opening,
    )
    statement.reversed_order = newest_first
    return statement


_DATE_TOKEN = re.compile(rf"^{_DATE}$")


def _tidy(narration: str, on) -> str:
    """Take out what the neighbouring columns put into the narration: the value date and a dash
    standing for no cheque number."""
    kept = []
    for token in narration.split():
        if token == "-":
            continue
        if _DATE_TOKEN.match(token):
            when = parse_date(token)
            if when is not None and abs((when - on).days) <= 5:
                continue
        kept.append(token)
    return " ".join(kept)
