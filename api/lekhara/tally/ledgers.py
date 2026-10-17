"""Tally ledgers that stand for something in a project, and the money they carry.

- Expense ledgers map to cost lines. Lekhara suggests one from the ledger's name (cement and
  steel to civil works, lifts to MEP, sanction fees to approvals); the builder confirms or
  changes it once and it is remembered.
- One bank ledger is the RERA designated account; its debits are deposits and its credits
  withdrawals (interest credited by the bank is interest).
- Ledgers for landowners carry their payments, with the TDS cut on each.

Cost incurred is every debit to a mapped expense ledger, and, where the project's GST scheme
gives no input credit, the GST on the same voucher. Cost paid is what was paid straight from
bank or cash, and payments to suppliers spread over the cost lines of their bills.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lekhara.tally.book import COST_KINDS, ZERO, Book, Voucher, norm

RERA_WORDS = ("rera", "escrow", "designated", "70%", "70 %", "seventy")

SUGGESTIONS = (
    ("LAND", ("land", "jda", "conversion", "khata transfer", "registration of land")),
    (
        "APPR",
        (
            "approval",
            "sanction",
            "plan fee",
            "bbmp",
            "bda",
            "bmrda",
            "gba",
            "noc",
            "betterment",
            "scrutiny",
            "licence",
            "license",
            "premium far",
            "tdr",
        ),
    ),
    (
        "MEP",
        (
            "electric",
            "plumb",
            "lift",
            "elevator",
            "dg set",
            "generator",
            "transformer",
            "fire fighting",
            "firefighting",
            "hvac",
            "stp",
            "wtp",
            "pump",
            "cable",
            "wiring",
        ),
    ),
    (
        "FIN",
        (
            "tile",
            "paint",
            "granite",
            "marble",
            "door",
            "window",
            "sanitary",
            "fitting",
            "flooring",
            "kitchen",
            "false ceiling",
            "glass",
            "upvc",
        ),
    ),
    ("EXT", ("landscap", "compound wall", "road", "external", "amenit", "club", "garden")),
    (
        "CONS",
        (
            "architect",
            "structural",
            "consult",
            "professional fee",
            "legal",
            "design fee",
            "soil test",
            "survey",
        ),
    ),
    ("FINC", ("interest", "bank charge", "processing fee", "loan", "finance cost")),
    (
        "MKT",
        ("advertis", "marketing", "brokerage", "commission", "promotion", "hoarding", "brochure"),
    ),
    (
        "OH",
        (
            "salary",
            "salaries",
            "rent",
            "office",
            "admin",
            "printing",
            "stationery",
            "telephone",
            "travel",
            "security",
        ),
    ),
    (
        "CIVIL",
        (
            "cement",
            "steel",
            "tmt",
            "sand",
            "aggregate",
            "jelly",
            "brick",
            "block",
            "concrete",
            "rmc",
            "ready mix",
            "shuttering",
            "formwork",
            "labour",
            "contract",
            "civil",
            "excavation",
            "earth work",
            "masonry",
            "plaster",
            "waterproof",
            "construction",
            "site",
            "material",
            "purchase",
        ),
    ),
)
_CODE_CATEGORY = {
    "LAND": "land",
    "APPR": "approvals",
    "MEP": "construction",
    "FIN": "construction",
    "EXT": "construction",
    "CONS": "construction",
    "FINC": "finance",
    "MKT": "marketing",
    "OH": "overheads",
    "CIVIL": "construction",
}


@dataclass(frozen=True)
class CostLineRef:
    id: str
    code: str
    name: str
    category: str


@dataclass(frozen=True)
class LandownerRef:
    id: str
    name: str
    pan: str | None


@dataclass
class Mapped:
    """A ledger and what it stands for: chosen by the builder, suggested, or nothing yet."""

    ledger: str
    target: str | None
    source: str
    """chosen, suggested or none."""
    total: Decimal = ZERO


@dataclass
class CostEntryPlan:
    ref: str
    cost_line_id: str
    kind: str
    """incurred or paid."""
    amount: Decimal
    on: date
    voucher: str
    exists: bool = False


@dataclass
class EscrowPlan:
    ref: str
    kind: str
    """deposit, withdrawal or interest."""
    amount: Decimal
    on: date
    voucher: str
    exists: bool = False


@dataclass
class LandownerPaymentPlan:
    ref: str
    landowner_id: str
    ledger: str
    amount: Decimal
    tds: Decimal
    on: date
    monetary: bool
    voucher: str
    exists: bool = False


@dataclass
class Money:
    cost_ledgers: list[Mapped] = field(default_factory=list)
    bank_ledgers: list[Mapped] = field(default_factory=list)
    landowner_ledgers: list[Mapped] = field(default_factory=list)
    cost_entries: list[CostEntryPlan] = field(default_factory=list)
    escrow: list[EscrowPlan] = field(default_factory=list)
    landowner_payments: list[LandownerPaymentPlan] = field(default_factory=list)
    unmapped_spend: Decimal = ZERO
    unattributed: list[str] = field(default_factory=list)
    """Suppliers whose payments could not be spread over cost lines."""


def suggest_line(ledger: str, parent: str, lines: tuple[CostLineRef, ...]) -> str | None:
    if not lines:
        return None
    text = f"{norm(ledger)} {norm(parent)}"
    for code, words in SUGGESTIONS:
        if not any(w in text for w in words):
            continue
        by_code = next((line for line in lines if line.code.upper() == code), None)
        if by_code:
            return by_code.id
        by_name = next((line for line in lines if any(w in norm(line.name) for w in words)), None)
        if by_name:
            return by_name.id
        by_category = next((line for line in lines if line.category == _CODE_CATEGORY[code]), None)
        if by_category:
            return by_category.id
    return None


def _mapped(book: Book, names: set[str], role: str, links: dict, suggest) -> dict[str, Mapped]:
    out = {}
    for name in sorted(names, key=str.casefold):
        link = links.get(norm(name))
        if link and link[0] == role:
            out[norm(name)] = Mapped(name, link[1], "chosen")
        elif link and link[0] == "ignore":
            out[norm(name)] = Mapped(name, None, "ignored")
        elif link:
            continue
        else:
            target = suggest(name)
            out[norm(name)] = Mapped(name, target, "suggested" if target else "none")
    return out


def money(
    book: Book,
    vouchers: list[Voucher],
    *,
    lines: tuple[CostLineRef, ...],
    landowners: tuple[LandownerRef, ...],
    links: dict[str, tuple[str, str | None]],
    gst_is_cost: bool,
    known_refs: frozenset[str],
) -> Money:
    result = Money()
    kind = book.kind

    # What each ledger stands for
    cost_names = {e.ledger for v in vouchers for e in v.entries if kind(e.ledger) in COST_KINDS}
    cost_map = _mapped(
        book,
        cost_names,
        "cost_line",
        links,
        lambda name: (
            None
            if kind(name) == "fixed_asset"
            else suggest_line(name, book.ledger(name).parent, lines)
        ),
    )
    bank_names = {e.ledger for v in vouchers for e in v.entries if kind(e.ledger) == "bank"}
    rera_suggested = [n for n in bank_names if any(w in norm(n) for w in RERA_WORDS)]
    bank_map = _mapped(
        book,
        bank_names,
        "rera_account",
        links,
        lambda name: "rera" if len(rera_suggested) == 1 and name == rera_suggested[0] else None,
    )
    owner_by_name = {norm(o.name): o for o in landowners}

    def owner_for(name: str) -> str | None:
        n = norm(name)
        hit = [o for key, o in owner_by_name.items() if key and (key in n or n in key)]
        return hit[0].id if len(hit) == 1 else None

    owner_names = {
        e.ledger
        for v in vouchers
        for e in v.entries
        if (links.get(norm(e.ledger)) or ("",))[0] == "landowner"
        or (landowners and owner_for(e.ledger))
    }
    owner_map = _mapped(book, owner_names, "landowner", links, owner_for)
    owners = {k: m.target for k, m in owner_map.items() if m.target}

    # Cost incurred, voucher by voucher
    creditor_weights: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for v in vouchers:
        if v.base_type in ("sales", "receipt", "sales order", "purchase order", "memorandum"):
            continue
        mapped_lines = [
            (e, cost_map[norm(e.ledger)].target)
            for e in v.entries
            if norm(e.ledger) in cost_map and cost_map[norm(e.ledger)].target
        ]
        for e in v.entries:
            m = cost_map.get(norm(e.ledger))
            if m is not None and not m.target and m.source != "ignored" and e.amount > 0:
                result.unmapped_spend += e.amount
                m.total += e.amount
        if not mapped_lines:
            continue
        gst = ZERO
        if gst_is_cost:
            gst = sum(
                (
                    e.amount
                    for e in v.entries
                    if e.amount > 0
                    and kind(e.ledger) == "tax"
                    and book.ledger(e.ledger).tax_kind == "gst"
                ),
                ZERO,
            )
        base = sum((e.amount for e, _ in mapped_lines if e.amount > 0), ZERO)
        by_line: dict[str, Decimal] = defaultdict(Decimal)
        for e, line_id in mapped_lines:
            share = (gst * e.amount / base) if (gst and base and e.amount > 0) else ZERO
            by_line[line_id] += e.amount + share
            cost_map[norm(e.ledger)].total += e.amount
        for line_id, amount in by_line.items():
            amount = amount.quantize(Decimal("0.01"))
            if amount == 0:
                continue
            ref = f"tally:{v.key}:cost:{line_id}:incurred"
            result.cost_entries.append(
                CostEntryPlan(ref, line_id, "incurred", amount, v.on, v.label, ref in known_refs)
            )
        creditors = [e for e in v.entries if kind(e.ledger) == "creditor" and e.amount < 0]
        paid_from_bank = [
            e for e in v.entries if kind(e.ledger) in ("bank", "cash") and e.amount < 0
        ]
        if creditors:
            for c in creditors:
                for line_id, amount in by_line.items():
                    creditor_weights[norm(c.ledger)][line_id] += amount
        elif paid_from_bank:
            for line_id, amount in by_line.items():
                amount = amount.quantize(Decimal("0.01"))
                ref = f"tally:{v.key}:cost:{line_id}:paid"
                result.cost_entries.append(
                    CostEntryPlan(ref, line_id, "paid", amount, v.on, v.label, ref in known_refs)
                )

    # Cost paid through suppliers: each payment spread over the cost lines of their bills
    for v in vouchers:
        if v.base_type not in ("payment", "journal", "contra"):
            continue
        for e in v.entries:
            if e.amount <= 0 or kind(e.ledger) != "creditor" or norm(e.ledger) in owners:
                continue
            weights = creditor_weights.get(norm(e.ledger))
            total = sum(weights.values(), ZERO) if weights else ZERO
            if not weights or total <= 0:
                if e.ledger not in result.unattributed:
                    result.unattributed.append(e.ledger)
                continue
            for line_id, weight in weights.items():
                amount = (e.amount * weight / total).quantize(Decimal("0.01"))
                ref = f"tally:{v.key}:paid:{norm(e.ledger)}:{line_id}"
                result.cost_entries.append(
                    CostEntryPlan(ref, line_id, "paid", amount, v.on, v.label, ref in known_refs)
                )

    # The RERA designated account
    rera = {k for k, m in bank_map.items() if m.target}
    for v in vouchers:
        for e in v.entries:
            if norm(e.ledger) not in rera or e.amount == 0:
                continue
            others = [x for x in v.entries if x is not e]
            interest = e.amount > 0 and any(
                "interest" in norm(x.ledger) and kind(x.ledger) == "income" for x in others
            )
            txn_kind = "interest" if interest else "deposit" if e.amount > 0 else "withdrawal"
            ref = f"tally:{v.key}:rera:{norm(e.ledger)}"
            bank_map[norm(e.ledger)].total += abs(e.amount)
            result.escrow.append(
                EscrowPlan(ref, txn_kind, abs(e.amount), v.on, v.label, ref in known_refs)
            )

    # Landowners
    for v in vouchers:
        debits = [e for e in v.entries if norm(e.ledger) in owners and e.amount > 0]
        if not debits or v.base_type in ("sales", "receipt"):
            continue
        tds = sum(
            (
                -e.amount
                for e in v.entries
                if e.amount < 0
                and kind(e.ledger) == "tax"
                and book.ledger(e.ledger).tax_kind == "tds"
            ),
            ZERO,
        )
        gross = sum((e.amount for e in debits), ZERO)
        deposit = bool(re.search(r"refundable|security deposit|deposit", norm(v.narration)))
        for e in debits:
            share = (tds * e.amount / gross).quantize(Decimal("0.01")) if gross else ZERO
            ref = f"tally:{v.key}:landowner:{norm(e.ledger)}"
            owner_map[norm(e.ledger)].total += e.amount
            result.landowner_payments.append(
                LandownerPaymentPlan(
                    ref,
                    owners[norm(e.ledger)],
                    e.ledger,
                    e.amount,
                    share,
                    v.on,
                    not deposit,
                    v.label,
                    ref in known_refs,
                )
            )

    result.cost_ledgers = list(cost_map.values())
    result.bank_ledgers = list(bank_map.values())
    result.landowner_ledgers = list(owner_map.values())
    return result
