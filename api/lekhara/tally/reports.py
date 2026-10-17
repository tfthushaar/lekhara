"""Tally reports exported to Excel or text: the Day Book, Ledger Vouchers, a list of ledgers,
the Trial Balance, and voucher sheets with one row per ledger line.

Reports carry less than XML: a condensed Day Book has one total per voucher and no supplier
invoice numbers, GSTINs or bill-wise details. The book records that, so the plan can say so.
"""

import re

from lekhara.services import ServiceError
from lekhara.tally.book import (
    Book,
    Entry,
    Group,
    Ledger,
    Voucher,
    base_type,
    classify,
    norm,
    parse_amount,
    parse_date,
)
from lekhara.tally.reader import HOW_TO_EXPORT

_COLUMNS = {
    "date": ("date", "voucher date", "vch date"),
    "particulars": ("particulars", "ledger", "ledger name", "account", "party name", "party"),
    "name": ("name", "ledger name", "name of ledger"),
    "vch_type": ("vch type", "voucher type", "voucher type name", "vch_type", "type"),
    "vch_no": ("vch no", "vch no.", "voucher no", "voucher no.", "voucher number", "vch number"),
    "group": ("under", "group", "parent", "group name", "under group"),
    "gstin": ("gstin", "gstin/uin", "gst no", "gst number", "gstin uin"),
    "pan": ("pan", "pan no", "pan no.", "it pan", "income tax number"),
    "opening": ("opening balance", "opening"),
    "closing": ("closing balance", "closing"),
    "narration": ("narration",),
    "drcr": ("dr/cr", "dr / cr", "ledger amount dr/cr", "dr cr"),
    "amount": ("amount", "ledger amount", "value"),
    "reference": (
        "ref no",
        "ref. no.",
        "reference",
        "reference no",
        "supplier invoice no",
        "bill no",
    ),
}
_SKIP_ROWS = ("opening balance", "closing balance", "current total", "total", "grand total")


def _key(header) -> str:
    return re.sub(r"[^a-z0-9/ ]+", " ", str(header).casefold()).strip().replace("  ", " ")


def _columns(row: list) -> dict[str, int]:
    found: dict[str, int] = {}
    for i, header in enumerate(row):
        key = _key(header)
        if not key:
            continue
        if "debit" in key and "debit" not in found:
            found["debit"] = i
            continue
        if "credit" in key and "credit" not in found:
            found["credit"] = i
            continue
        for name, options in _COLUMNS.items():
            if name not in found and key in {_key(o) for o in options}:
                found[name] = i
                break
    return found


def _find_header(rows: list[list]) -> tuple[int, dict[str, int]]:
    best, best_cols = -1, {}
    for i, row in enumerate(rows[:20]):
        cols = _columns(row)
        if len(cols) > len(best_cols):
            best, best_cols = i, cols
    return best, best_cols


def _cell(row: list, cols: dict[str, int], name: str):
    i = cols.get(name)
    if i is None or i >= len(row):
        return ""
    return row[i]


def _particulars(text) -> str:
    return re.sub(r"^(to|by)\s+", "", str(text or "").strip(), flags=re.IGNORECASE)


def from_rows(rows: list[list]) -> Book:
    header_at, cols = _find_header(rows)
    titles = norm(" ".join(str(c) for row in rows[: max(header_at, 0)] for c in row if c))
    is_vouchers = "vch_type" in cols and ({"debit", "credit", "amount"} & set(cols))
    if is_vouchers:
        source = "ledger_vouchers" if "ledger" in titles and "day book" not in titles else "daybook"
        return _vouchers(rows[header_at + 1 :], cols, source, titles)
    if "group" in cols and ({"name", "particulars"} & set(cols)):
        return _ledger_list(rows[header_at + 1 :], cols)
    if "particulars" in cols and {"debit", "credit"} <= set(cols):
        return _trial_balance(rows[header_at + 1 :], cols)
    raise ServiceError("This sheet is not a Tally report Lekhara can read. " + HOW_TO_EXPORT)


def _signed(row: list, cols: dict[str, int]):
    debit = parse_amount(_cell(row, cols, "debit"))
    credit = parse_amount(_cell(row, cols, "credit"))
    if "debit" in cols or "credit" in cols:
        return abs(debit) - abs(credit)
    amount = parse_amount(_cell(row, cols, "amount"))
    side = norm(str(_cell(row, cols, "drcr")))
    return -abs(amount) if side.startswith("cr") else abs(amount)


def _vouchers(rows: list[list], cols: dict[str, int], source: str, titles: str) -> Book:
    book = Book(source=source, company="")
    current: Voucher | None = None
    last_date = None
    for row in rows:
        particulars = _particulars(_cell(row, cols, "particulars"))
        if norm(particulars) in _SKIP_ROWS:
            continue
        on = parse_date(_cell(row, cols, "date")) or None
        type_name = str(_cell(row, cols, "vch_type") or "").strip()
        number = str(_cell(row, cols, "vch_no") or "").strip()
        amount = _signed(row, cols)
        same = (
            current is not None
            and (type_name, number) == (current.type_name, current.number)
            and (on is None or on == current.on)
        )
        if (type_name or number) and not same:
            last_date = on or last_date
            current = Voucher(
                key=f"vch:{norm(type_name)}:{number}:{last_date}:{norm(particulars)}",
                type_name=type_name,
                base_type=base_type(book, type_name),
                on=last_date,
                number=number,
                party=particulars,
                reference=str(_cell(row, cols, "reference") or "").strip(),
                narration=str(_cell(row, cols, "narration") or "").strip(),
                detailed=False,
            )
            book.vouchers.append(current)
            if particulars:
                current.entries.append(Entry(ledger=particulars, amount=amount, is_party=True))
        elif current is not None and particulars:
            current.entries.append(Entry(ledger=particulars, amount=amount))
            current.detailed = True
    for v in book.vouchers:
        for entry in v.entries:
            book.ledger(entry.ledger)
    book.summary_only = not any(v.detailed for v in book.vouchers)
    classify(book)
    return book


def _ledger_list(rows: list[list], cols: dict[str, int]) -> Book:
    book = Book(source="ledger_list", has_masters=True)
    name_col = "name" if "name" in cols else "particulars"
    for row in rows:
        name = str(_cell(row, cols, name_col) or "").strip()
        if not name or norm(name) in _SKIP_ROWS:
            continue
        group = str(_cell(row, cols, "group") or "").strip()
        book.ledgers[norm(name)] = Ledger(
            name=name,
            parent=group,
            gstin=str(_cell(row, cols, "gstin") or "").strip().upper(),
            pan=str(_cell(row, cols, "pan") or "").strip().upper(),
            opening_balance=-parse_amount(_cell(row, cols, "opening")),
        )
        if group and norm(group) not in book.groups:
            book.groups[norm(group)] = Group(name=group, parent="")
    classify(book)
    return book


def _trial_balance(rows: list[list], cols: dict[str, int]) -> Book:
    book = Book(source="trial_balance")
    for row in rows:
        name = _particulars(_cell(row, cols, "particulars"))
        if not name or norm(name) in _SKIP_ROWS:
            continue
        ledger = book.ledger(name)
        ledger.opening_balance = _signed(row, cols)
    classify(book)
    return book
