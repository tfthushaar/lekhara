"""The book a Tally export holds: groups, ledgers, cost centres, voucher types and vouchers.

Conventions, as in Tally's own samples:
- dates are YYYYMMDD (reports also use forms like 1-Apr-2025);
- in a ledger line, a debit has a negative AMOUNT with ISDEEMEDPOSITIVE set to Yes. Here every
  amount is turned round so that a debit is positive and a credit negative;
- a ledger's opening balance is negative when it is a debit, and is turned round the same way.

Ledgers are classified by walking their group up to one of Tally's reserved groups. Builders'
own groups for work in progress or project cost are treated as project cost.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lekhara.tally.reader import Node

ZERO = Decimal("0")

_MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTHS = {m: i + 1 for i, m in enumerate(_MONTH_NAMES)}

RESERVED_GROUPS = {
    "sundry creditors": "creditor",
    "sundry debtors": "debtor",
    "bank accounts": "bank",
    "bank od a/c": "bank",
    "bank occ a/c": "bank",
    "cash-in-hand": "cash",
    "duties & taxes": "tax",
    "purchase accounts": "purchase",
    "sales accounts": "sales",
    "direct expenses": "expense",
    "indirect expenses": "expense",
    "direct incomes": "income",
    "indirect incomes": "income",
    "fixed assets": "fixed_asset",
    "capital account": "capital",
    "reserves & surplus": "capital",
    "loans (liability)": "loan",
    "secured loans": "loan",
    "unsecured loans": "loan",
    "current assets": "asset",
    "loans & advances (asset)": "asset",
    "deposits (asset)": "asset",
    "investments": "asset",
    "stock-in-hand": "stock",
    "current liabilities": "liability",
    "provisions": "liability",
    "misc. expenses (asset)": "asset",
    "suspense a/c": "suspense",
    "branch / divisions": "other",
}
PROJECT_COST_WORDS = (
    "work in progress",
    "work-in-progress",
    "wip",
    "project cost",
    "construction cost",
    "construction expenses",
    "site expenses",
    "project expenses",
)
COST_KINDS = {"purchase", "expense", "fixed_asset", "project_cost"}

BASE_TYPES = (
    "contra",
    "payment",
    "receipt",
    "journal",
    "sales",
    "purchase",
    "credit note",
    "debit note",
    "memorandum",
    "reversing journal",
    "stock journal",
    "physical stock",
    "delivery note",
    "receipt note",
    "rejections in",
    "rejections out",
    "sales order",
    "purchase order",
    "job work in order",
    "job work out order",
    "material in",
    "material out",
    "attendance",
    "payroll",
)


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def yes(text: str | None) -> bool:
    return norm(text) in ("yes", "true", "1")


def parse_amount(text) -> Decimal:
    """Tally's amount text: '-21546.00', '1,234.50 Dr', or a foreign-currency amount ending in
    '= -8300.00'. Blank is zero."""
    if text is None:
        return ZERO
    if isinstance(text, int | float | Decimal):
        return Decimal(str(text))
    raw = str(text).strip()
    if "=" in raw:
        raw = raw.rsplit("=", 1)[1]
    sign = 1
    lowered = raw.casefold()
    if lowered.endswith("dr"):
        raw, sign = raw[:-2], -1
    elif lowered.endswith("cr"):
        raw = raw[:-2]
    raw = re.sub(r"[^0-9.\-()]", "", raw)
    if raw.startswith("(") and raw.endswith(")"):
        raw, sign = raw[1:-1], -sign
    if raw in ("", "-", "."):
        return ZERO
    try:
        return Decimal(raw) * sign
    except InvalidOperation:
        return ZERO


def parse_date(text) -> date | None:
    if text is None or text == "":
        return None
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    raw = str(text).strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", raw)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", raw)
        if m:
            y, mo, d = (int(x) for x in m.groups())
        else:
            m = re.fullmatch(r"(\d{1,2})[-/. ]([A-Za-z]{3,9}|\d{1,2})[-/. ,]*(\d{2,4})", raw)
            if not m:
                return None
            d, month, year = m.groups()
            d, y = int(d), int(year)
            mo = int(month) if month.isdigit() else _MONTHS.get(month[:3].casefold(), 0)
            if y < 100:
                y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_quantity(text: str | None) -> tuple[Decimal, str]:
    """' 1 nos' or '12.5 MT' to (quantity, unit)."""
    m = re.match(r"\s*(-?[\d,]*\.?\d+)\s*(.*)", text or "")
    if not m:
        return ZERO, ""
    return Decimal(m.group(1).replace(",", "")), m.group(2).strip()


# What a book holds


@dataclass
class Group:
    name: str
    parent: str


@dataclass
class Ledger:
    name: str
    parent: str = ""
    kind: str = "unknown"
    """creditor, debtor, bank, cash, tax, purchase, sales, expense, income, fixed_asset,
    project_cost, capital, loan, asset, liability, stock, suspense, other or unknown."""
    tax_kind: str = ""
    """gst, tds, tcs or other, for ledgers under Duties & Taxes."""
    gstin: str = ""
    gst_registration_type: str = ""
    pan: str = ""
    state: str = ""
    address: str = ""
    email: str = ""
    phone: str = ""
    msme_type: str = ""
    """micro, small, medium, not_msme, or blank when the export says nothing."""
    msme_recorded: bool = False
    udyam: str = ""
    opening_balance: Decimal = ZERO
    """Positive for a debit balance."""
    bill_wise: bool | None = None
    from_masters: bool = True


@dataclass
class BillRef:
    name: str
    kind: str
    """new ref, agst ref, advance or on account."""
    amount: Decimal


@dataclass
class BankDetail:
    instrument_number: str = ""
    instrument_date: date | None = None
    transaction_type: str = ""
    utr: str = ""
    favouring: str = ""
    amount: Decimal = ZERO


@dataclass
class Entry:
    ledger: str
    amount: Decimal
    """Positive for a debit, negative for a credit."""
    is_party: bool = False
    bills: list[BillRef] = field(default_factory=list)
    bank: list[BankDetail] = field(default_factory=list)
    cost_centres: list[tuple[str, str, Decimal]] = field(default_factory=list)
    """(category, cost centre, amount)."""
    gst_rates: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class StockLine:
    item: str
    quantity: Decimal
    unit: str
    rate: Decimal
    amount: Decimal


@dataclass
class Voucher:
    key: str
    """The voucher's identity in Tally: its GUID, or its type, number and date."""
    type_name: str
    base_type: str
    on: date | None
    number: str = ""
    reference: str = ""
    """The supplier's invoice number, on a purchase."""
    reference_date: date | None = None
    party: str = ""
    party_gstin: str = ""
    narration: str = ""
    cancelled: bool = False
    optional: bool = False
    entries: list[Entry] = field(default_factory=list)
    stock: list[StockLine] = field(default_factory=list)
    detailed: bool = True
    """False for a voucher read from a report that shows only its total."""

    @property
    def label(self) -> str:
        when = self.on.strftime("%d %b %Y") if self.on else "no date"
        return f"{self.type_name} {self.number or '(no number)'} of {when}"

    @property
    def balance(self) -> Decimal:
        return sum((e.amount for e in self.entries), ZERO)


@dataclass
class Book:
    source: str
    """xml, json, or the kind of report: daybook, ledger_vouchers, trial_balance, ledger_list."""
    company: str = ""
    groups: dict[str, Group] = field(default_factory=dict)
    ledgers: dict[str, Ledger] = field(default_factory=dict)
    """By normalised name."""
    cost_centres: list[tuple[str, str]] = field(default_factory=list)
    """(name, category)."""
    voucher_types: dict[str, str] = field(default_factory=dict)
    """Normalised name to parent."""
    stock_items: int = 0
    vouchers: list[Voucher] = field(default_factory=list)
    has_masters: bool = False
    summary_only: bool = False
    """True for a report export that has totals but not every ledger line."""

    def ledger(self, name: str) -> Ledger:
        key = norm(name)
        if key not in self.ledgers:
            self.ledgers[key] = Ledger(name=name.strip(), from_masters=False)
        return self.ledgers[key]

    def kind(self, name: str) -> str:
        return self.ledger(name).kind


# Classification


def _clean_name(text: str) -> str:
    return re.sub(r"^[\s\x00-\x1f]+", "", text or "").strip()


def classify(book: Book) -> None:
    for ledger in book.ledgers.values():
        ledger.kind = _kind_by_groups(book, ledger)
        if ledger.kind == "unknown":
            ledger.kind = _kind_by_name(ledger.name)
        if ledger.kind == "tax":
            ledger.tax_kind = _tax_kind(ledger.name)
    _kinds_from_vouchers(book)


def _kind_by_groups(book: Book, ledger: Ledger) -> str:
    seen: set[str] = set()
    group = norm(ledger.parent)
    while group and group not in seen:
        seen.add(group)
        if any(word in group for word in PROJECT_COST_WORDS):
            return "project_cost"
        if group in RESERVED_GROUPS:
            return RESERVED_GROUPS[group]
        parent = book.groups.get(group)
        group = norm(parent.parent) if parent else ""
    return "unknown"


def _kind_by_name(name: str) -> str:
    n = norm(name)
    if any(
        w in n for w in ("cgst", "sgst", "igst", "utgst", "gst ", "gst-", "tds", "tcs")
    ) or n.endswith("gst"):
        return "tax"
    if "bank" in n or re.search(r"\b(a/c|ac)\s*(no\.?)?\s*\d{4,}", n):
        return "bank"
    if n in ("cash", "petty cash") or n.startswith("cash "):
        return "cash"
    return "unknown"


def _tax_kind(name: str) -> str:
    n = norm(name)
    if "tds" in n:
        return "tds"
    if "tcs" in n:
        return "tcs"
    if any(w in n for w in ("gst", "cess", "igst", "cgst", "sgst", "utgst")):
        return "gst"
    return "other"


def _kinds_from_vouchers(book: Book) -> None:
    """For ledgers the file has no master for, guess from how vouchers use them."""
    for v in book.vouchers:
        for entry in v.entries:
            ledger = book.ledger(entry.ledger)
            if ledger.kind != "unknown":
                continue
            if (
                v.base_type in ("purchase", "journal")
                and entry.amount < 0
                and (entry.is_party or norm(entry.ledger) == norm(v.party))
            ):
                ledger.kind = "creditor"
            elif (
                v.base_type == "receipt"
                and entry.amount < 0
                and (entry.is_party or norm(entry.ledger) == norm(v.party))
            ):
                ledger.kind = "debtor"
            elif (
                v.base_type == "payment"
                and entry.amount > 0
                and norm(entry.ledger) == norm(v.party)
            ):
                ledger.kind = "creditor"


def base_type(book: Book, type_name: str) -> str:
    seen: set[str] = set()
    name = norm(type_name)
    while name and name not in seen:
        if name in BASE_TYPES:
            return name
        seen.add(name)
        name = norm(book.voucher_types.get(name, ""))
    n = norm(type_name)
    for base in (
        "debit note",
        "credit note",
        "purchase",
        "payment",
        "receipt",
        "journal",
        "contra",
        "sales",
    ):
        if base in n:
            return base
    return "other"


# From XML or JSON nodes


def _msme(node: Node) -> tuple[str, str, bool]:
    """MSME details sit under different tags across Tally releases; look for any tag naming MSME
    or Udyam."""
    category, udyam, recorded = "", "", False
    for child in node.walk():
        name = child.name
        text = child.text
        if not text:
            continue
        if "udyam" in name or re.fullmatch(r"UDYAM-[A-Z]{2}-\d{2}-\d{7}", text.upper()):
            udyam = text.upper()
            recorded = True
        if "msme" in name:
            recorded = True
            lowered = text.casefold()
            for size in ("micro", "small", "medium"):
                if size in lowered:
                    category = size
            if lowered in ("no", "not applicable", "none", "not registered"):
                category = category or "not_msme"
    return category, udyam, recorded


def _ledger(node: Node) -> Ledger:
    name = _clean_name(
        node.attrs.get("name") or node.get("name") or next(iter(node.texts("name.list")), "")
    )
    details = node.all("ledgstregdetails")
    latest = details[-1] if details else None
    msme_type, udyam, recorded = _msme(node)
    mailing = node.all("ledmailingdetails")
    billwise = node.get("isbillwiseon")
    return Ledger(
        name=name,
        parent=_clean_name(node.get("parent")),
        gstin=(node.get("partygstin", "gstin") or (latest.get("gstin") if latest else "")).upper(),
        gst_registration_type=node.get("gstregistrationtype")
        or (latest.get("gstregistrationtype") if latest else ""),
        pan=node.get("incometaxnumber", "pan", "panno").upper(),
        state=node.get("ledstatename", "ledgerstatename", "statename")
        or (latest.get("state") if latest else "")
        or (mailing[-1].get("state") if mailing else ""),
        address=", ".join(node.texts("address.list", "address")),
        email=node.get("email"),
        phone=node.get("ledgermobile", "ledgerphone"),
        msme_type=msme_type,
        msme_recorded=recorded,
        udyam=udyam,
        opening_balance=-parse_amount(node.get("openingbalance")),
        bill_wise=yes(billwise) if billwise else None,
    )


def _entry(node: Node) -> Entry:
    entry = Entry(
        ledger=_clean_name(node.get("ledgername")),
        amount=-parse_amount(node.get("amount")),
        is_party=yes(node.get("ispartyledger")),
    )
    for bill in node.all("billallocations"):
        if bill.get("name") or bill.get("billtype"):
            entry.bills.append(
                BillRef(
                    name=bill.get("name"),
                    kind=norm(bill.get("billtype")),
                    amount=-parse_amount(bill.get("amount")),
                )
            )
    for bank in node.all("bankallocations"):
        entry.bank.append(
            BankDetail(
                instrument_number=bank.get("instrumentnumber"),
                instrument_date=parse_date(bank.get("instrumentdate")),
                transaction_type=bank.get("transactiontype"),
                utr=bank.get("uniquereferencenumber", "utrnumber"),
                favouring=bank.get("paymentfavouring"),
                amount=-parse_amount(bank.get("amount")),
            )
        )
    for category in node.all("categoryallocations"):
        for cc in category.all("costcentreallocations"):
            entry.cost_centres.append(
                (category.get("category"), cc.get("name"), -parse_amount(cc.get("amount")))
            )
    for cc in node.all("costcentreallocations"):
        entry.cost_centres.append(("", cc.get("name"), -parse_amount(cc.get("amount"))))
    for rate in node.all("ratedetails"):
        head = rate.get("gstratedutyhead")
        if head and rate.get("gstrate"):
            entry.gst_rates[head] = parse_amount(rate.get("gstrate"))
    return entry


def _voucher(book: Book, node: Node) -> Voucher:
    type_name = node.get("vouchertypename") or node.attrs.get("vchtype", "")
    on = parse_date(node.get("date"))
    number = node.get("vouchernumber")
    party = _clean_name(node.get("partyledgername", "partyname"))
    guid = node.get("guid") or node.attrs.get("remoteid", "")
    key = f"guid:{guid}" if guid else f"vch:{norm(type_name)}:{number}:{on}:{norm(party)}"
    voucher = Voucher(
        key=key,
        type_name=type_name,
        base_type=base_type(book, type_name),
        on=on,
        number=number,
        reference=node.get("reference"),
        reference_date=parse_date(node.get("referencedate")),
        party=party,
        party_gstin=node.get("partygstin").upper(),
        narration=node.get("narration"),
        cancelled=yes(node.get("iscancelled")) or yes(node.get("isdeleted")),
        optional=yes(node.get("isoptional")),
    )
    lines = node.all("allledgerentries") or node.all("ledgerentries")
    voucher.entries = [_entry(e) for e in lines if e.get("ledgername")]
    stock_nodes = node.all("allinventoryentries") or node.all("inventoryentries")
    for item in stock_nodes:
        quantity, unit = parse_quantity(item.get("billedqty", "actualqty"))
        rate, _ = parse_quantity(item.get("rate").split("/")[0] if item.get("rate") else "")
        voucher.stock.append(
            StockLine(
                item=_clean_name(item.get("stockitemname")),
                quantity=quantity,
                unit=unit,
                rate=rate,
                amount=-parse_amount(item.get("amount")),
            )
        )
    if voucher.balance != 0:
        # In invoice mode the purchase or sales ledger sits inside the stock lines.
        for item in stock_nodes:
            for allocation in item.all("accountingallocations"):
                if allocation.get("ledgername"):
                    voucher.entries.append(_entry(allocation))
    return voucher


def from_nodes(source: str, objects: list[Node], meta: dict[str, str]) -> Book:
    book = Book(
        source=source,
        company=_clean_name(
            meta.get("svcurrentcompany")
            or meta.get("remotecmpname")
            or meta.get("companyname")
            or ""
        ),
    )
    vouchers = []
    for node in objects:
        if node.name == "group":
            name = _clean_name(node.attrs.get("name") or node.get("name"))
            book.groups[norm(name)] = Group(name=name, parent=_clean_name(node.get("parent")))
            book.has_masters = True
        elif node.name == "ledger":
            ledger = _ledger(node)
            if ledger.name:
                book.ledgers[norm(ledger.name)] = ledger
                book.has_masters = True
        elif node.name == "costcentre":
            name = _clean_name(node.attrs.get("name") or node.get("name"))
            book.cost_centres.append((name, node.get("category")))
            book.has_masters = True
        elif node.name == "vouchertype":
            name = _clean_name(node.attrs.get("name") or node.get("name"))
            book.voucher_types[norm(name)] = _clean_name(node.get("parent"))
            book.has_masters = True
        elif node.name == "stockitem":
            book.stock_items += 1
            book.has_masters = True
        elif node.name == "voucher":
            vouchers.append(node)
    book.vouchers = [_voucher(book, node) for node in vouchers]
    for v in book.vouchers:
        for entry in v.entries:
            book.ledger(entry.ledger)
    classify(book)
    return book
