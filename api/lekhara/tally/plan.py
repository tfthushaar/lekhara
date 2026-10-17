"""What a Tally book would add to a project, and what is missing for Lekhara to do its work.

- Suppliers: the Sundry Creditors on suppliers' bills, with GSTIN, registration type, PAN,
  state and MSME details from their ledger masters.
- Suppliers' bills: purchase vouchers, and journals that credit a supplier against an expense
  (how contractors' bills are often booked). The paid date comes from bill-wise payments
  (Agst Ref) adding up to the bill.
- Buyer payments: receipt vouchers crediting a Sundry Debtor, matched to a unit by its number
  or its buyer's name; the TDS a buyer deducted is taken from the TDS ledger on the voucher.

Every alert says what is affected and how to fix it, in Tally or in Lekhara.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from lekhara.tally.book import COST_KINDS, ZERO, Book, Voucher, norm
from lekhara.tally.reader import HOW_TO_EXPORT

PAID_TOLERANCE = Decimal("1.00")
STALE_DAYS = 45


@dataclass(frozen=True)
class UnitRef:
    id: str
    label: str
    buyer: str | None


@dataclass(frozen=True)
class VendorRef:
    id: str
    name: str
    gstin: str | None
    pan: str | None
    state: str | None
    msme_category: str
    udyam: str | None
    registered: bool


@dataclass(frozen=True)
class Context:
    as_of: date
    registered_on: date | None
    units: tuple[UnitRef, ...]
    vendors: tuple[VendorRef, ...]
    known_refs: frozenset[str]
    """Bills and buyer payments already brought in, by their Tally identity."""
    links: dict[str, str]
    """A buyer's ledger, normalised, to a unit id, or "ignore"."""
    cost_centre: str | None = None


@dataclass
class Alert:
    level: str
    """blocking (those rows wait until it is fixed), missing (brought in, but a check is
    incomplete) or info."""
    code: str
    title: str
    detail: str
    fix: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class VendorPlan:
    key: str
    name: str
    gstin: str | None
    registered: bool
    pan: str | None
    state: str | None
    msme_category: str | None
    """micro, small, medium or none; None when the file does not say."""
    udyam: str | None
    existing_id: str | None
    changes: dict[str, tuple] = field(default_factory=dict)
    bills: int = 0


@dataclass
class BillPlan:
    ref: str
    vendor_key: str
    vendor_name: str
    bill_no: str
    bill_date: date
    accepted_on: date
    taxable_value: Decimal
    gst: Decimal
    total: Decimal
    is_cement: bool
    paid_on: date | None
    voucher: str
    exists: bool


@dataclass
class ReceiptPlan:
    ref: str
    ledger: str
    unit_id: str | None
    unit_label: str | None
    amount: Decimal
    tds: Decimal
    received_on: date
    voucher: str
    exists: bool


@dataclass
class Buyer:
    ledger: str
    total: Decimal
    count: int
    suggestions: list[str]
    ignored: bool = False


@dataclass
class Plan:
    period: tuple[date | None, date | None]
    counts: dict[str, int]
    vendors: list[VendorPlan]
    bills: list[BillPlan]
    receipts: list[ReceiptPlan]
    buyers: list[Buyer]
    """Buyers' ledgers that could not be matched to a unit, or were set aside."""
    cost_centres: list[str]
    alerts: list[Alert]


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold())


def _unit_pattern(label: str) -> re.Pattern:
    chunks = re.findall(r"[a-z]+|\d+", label.casefold())
    body = r"[\s\-/_.]*".join(re.escape(c) for c in chunks)
    return re.compile(rf"(?<![a-z0-9]){body}(?![0-9])")


def _match_unit(ledger: str, voucher: Voucher, units: tuple[UnitRef, ...]) -> list[UnitRef]:
    text = " ".join(
        [ledger, voucher.narration, *(b.name for e in voucher.entries for b in e.bills)]
    ).casefold()
    by_label = [u for u in units if u.label and _unit_pattern(u.label).search(text)]
    if len(by_label) == 1:
        return by_label
    name = _alnum(ledger)
    by_buyer = [
        u for u in units if u.buyer and len(_alnum(u.buyer)) > 3 and _alnum(u.buyer) in name
    ]
    if by_label and by_buyer:
        both = [u for u in by_label if u in by_buyer]
        if len(both) == 1:
            return both
    return by_buyer or by_label


def _in_cost_centre(v: Voucher, cost_centre: str | None) -> bool:
    if not cost_centre:
        return True
    return any(norm(cc) == norm(cost_centre) for e in v.entries for _, cc, _ in e.cost_centres)


def make_plan(book: Book, ctx: Context) -> Plan:
    alerts: list[Alert] = []
    live = [v for v in book.vouchers if not v.cancelled and not v.optional]
    skipped = len(book.vouchers) - len(live)
    vouchers = [v for v in live if _in_cost_centre(v, ctx.cost_centre)]
    counts: dict[str, int] = defaultdict(int)
    for v in vouchers:
        counts[v.base_type] += 1
    dates = [v.on for v in vouchers if v.on]
    period = (min(dates) if dates else None, max(dates) if dates else None)
    cost_centres = sorted(
        {cc for v in live for e in v.entries for _, cc, _ in e.cost_centres if cc}
    )

    _file_alerts(book, ctx, vouchers, skipped, period, cost_centres, alerts)
    bills, vendor_names, billwise_off = _bills(book, vouchers, ctx, alerts)
    vendors = _vendors(book, vendor_names, bills, ctx, alerts)
    if billwise_off:
        alerts.append(
            Alert(
                "missing",
                "bill.no_billwise",
                "Payments could not be tied to bills for some suppliers",
                "Their bills are brought in as unpaid, so the MSME 45-day clock may warn about "
                "bills already paid.",
                "In Tally, turn on 'Maintain balances bill-by-bill' for these suppliers and pay "
                "against each bill (Agst Ref), or mark bills paid in Lekhara.",
                sorted(billwise_off),
            )
        )
    receipts, buyers = _receipts(book, vouchers, ctx, alerts)
    return Plan(period, dict(counts), vendors, bills, receipts, buyers, cost_centres, alerts)


def _file_alerts(book, ctx, vouchers, skipped, period, cost_centres, alerts) -> None:
    if not book.vouchers and book.source in ("xml", "json"):
        alerts.append(
            Alert(
                "missing",
                "file.no_vouchers",
                "This file has ledgers but no vouchers",
                "Suppliers' details can be read, but no bills or payments.",
                "Export the vouchers too: " + HOW_TO_EXPORT,
            )
        )
    if book.vouchers and not book.has_masters:
        alerts.append(
            Alert(
                "missing",
                "file.no_masters",
                "The ledger masters are not in this file",
                "Without them Lekhara has no GSTINs, MSME details or groups, and has worked out "
                "which ledgers are suppliers and buyers from how the vouchers use them.",
                "Export Masters (All Masters, with dependent masters) as XML and import that "
                "file as well.",
            )
        )
    if book.summary_only:
        alerts.append(
            Alert(
                "missing",
                "file.summary_report",
                "This report shows one total per voucher",
                "Taxable value and GST cannot be told apart, and there are no supplier invoice "
                "numbers or bill-wise details.",
                "For full detail, export vouchers as XML. " + HOW_TO_EXPORT,
            )
        )
    if period[1] and period[1] < ctx.as_of - timedelta(days=STALE_DAYS):
        alerts.append(
            Alert(
                "info",
                "file.stale",
                f"The vouchers stop on {period[1].strftime('%d %b %Y')}",
                "Anything entered in Tally after that is not in this file.",
                "Export again for the latest period when you are ready.",
            )
        )
    if period[0] and ctx.registered_on and period[0] > ctx.registered_on + timedelta(days=31):
        alerts.append(
            Alert(
                "info",
                "file.starts_late",
                f"The vouchers start on {period[0].strftime('%d %b %Y')}",
                "The project was registered earlier; older bills and payments are not in this "
                "file.",
                "Export the earlier years from Tally to bring in the project's full history.",
            )
        )
    unbalanced = [
        v.label for v in vouchers if v.detailed and len(v.entries) > 1 and abs(v.balance) > 1
    ]
    if unbalanced:
        alerts.append(
            Alert(
                "info",
                "file.unbalanced",
                _count(len(unbalanced), "voucher does", "vouchers do") + " not add up",
                "Their debits and credits differ, usually because a line was left out of the "
                "export. They are read as they are.",
                "Check these vouchers in Tally.",
                unbalanced[:20],
            )
        )
    if skipped:
        alerts.append(
            Alert(
                "info",
                "file.skipped",
                _count(
                    skipped,
                    "cancelled or optional voucher was",
                    "cancelled or optional vouchers were",
                )
                + " left out",
                "They do not affect the books in Tally either.",
            )
        )
    if cost_centres and not ctx.cost_centre:
        alerts.append(
            Alert(
                "info",
                "file.cost_centres",
                "This company uses cost centres",
                "If they are separate projects, choose this project's cost centre so that only "
                "its vouchers come in.",
                "",
                cost_centres[:20],
            )
        )


def _bills(book: Book, vouchers: list[Voucher], ctx: Context, alerts: list[Alert]):
    bills: list[BillPlan] = []
    vendor_names: dict[str, str] = {}
    refs_by_bill: dict[str, list[tuple[str, str]]] = {}
    no_reference: list[str] = []
    no_supplier: list[str] = []
    for v in vouchers:
        if v.base_type not in ("purchase", "journal"):
            continue
        creditors = [e for e in v.entries if book.kind(e.ledger) == "creditor" and e.amount < 0]
        cost = [e for e in v.entries if book.kind(e.ledger) in COST_KINDS and e.amount > 0]
        if v.base_type == "journal" and not (creditors and cost):
            continue
        if creditors:
            supplier = max(creditors, key=lambda e: -e.amount)
            name = supplier.ledger
            total = -sum((e.amount for e in creditors), ZERO)
            taxable = sum((e.amount for e in cost), ZERO)
            gst = sum(
                (
                    e.amount
                    for e in v.entries
                    if e.amount > 0
                    and book.kind(e.ledger) == "tax"
                    and book.ledger(e.ledger).tax_kind == "gst"
                ),
                ZERO,
            )
            if taxable == 0:
                taxable = total - gst
            new_refs = [b.name for b in supplier.bills if b.name and b.kind in ("new ref", "")]
        elif not v.detailed and v.party:
            name = v.party
            total = abs(v.entries[0].amount) if v.entries else ZERO
            taxable, gst, new_refs = total, ZERO, []
        else:
            no_supplier.append(v.label)
            continue
        if total <= 0:
            continue
        if not v.reference:
            no_reference.append(v.label)
        bill_no = v.reference or (new_refs[0] if new_refs else v.number) or "(no number)"
        texts = " ".join([*(s.item for s in v.stock), *(e.ledger for e in cost)]).casefold()
        ref = f"tally:{v.key}"
        vendor_key = _vendor_key(book, name)
        vendor_names[vendor_key] = name
        refs_by_bill[ref] = [(norm(name), norm(r)) for r in (new_refs or [bill_no])]
        bills.append(
            BillPlan(
                ref=ref,
                vendor_key=vendor_key,
                vendor_name=name,
                bill_no=bill_no[:64],
                bill_date=v.reference_date or v.on,
                accepted_on=v.on,
                taxable_value=taxable,
                gst=gst,
                total=total,
                is_cement="cement" in texts,
                paid_on=None,
                voucher=v.label,
                exists=ref in ctx.known_refs,
            )
        )
    billwise_off = _settle(book, vouchers, bills, refs_by_bill)
    if no_reference:
        alerts.append(
            Alert(
                "missing",
                "bill.no_reference",
                _count(len(no_reference), "bill has", "bills have") + " no supplier invoice number",
                "Lekhara has used Tally's voucher number instead, which will not match the "
                "supplier's invoice or GSTR-2B.",
                "In Tally, enter the supplier's invoice number in 'Supplier Invoice No.' "
                "(Reference) on each purchase.",
                no_reference[:20],
            )
        )
    if no_supplier:
        alerts.append(
            Alert(
                "info",
                "bill.no_supplier",
                _count(len(no_supplier), "purchase has", "purchases have") + " no supplier ledger",
                "They were paid straight from cash or bank, so they are not suppliers' bills "
                "for the 80% test or the MSME clock.",
                "",
                no_supplier[:20],
            )
        )
    return bills, vendor_names, billwise_off


def _settle(book: Book, vouchers: list[Voucher], bills: list[BillPlan], refs_by_bill) -> set[str]:
    """Paid dates from bill-wise payments. Returns suppliers whose payments could not be tied."""
    paid: dict[tuple[str, str], list[tuple[date, Decimal]]] = defaultdict(list)
    untied: set[str] = set()
    for v in vouchers:
        if v.base_type not in ("payment", "journal", "debit note", "contra"):
            continue
        for e in v.entries:
            if e.amount <= 0 or book.kind(e.ledger) != "creditor":
                continue
            against = [b for b in e.bills if b.kind == "agst ref" and b.name]
            if not against:
                untied.add(e.ledger)
            for b in against:
                paid[(norm(e.ledger), norm(b.name))].append((v.on, abs(b.amount)))
    for bill in bills:
        payments = sorted(p for key in refs_by_bill[bill.ref] for p in paid.get(key, []) if p[0])
        running = ZERO
        for on, amount in payments:
            running += amount
            if running >= bill.total - PAID_TOLERANCE:
                bill.paid_on = on
                break
    with_bills = {b.vendor_name for b in bills}
    return {name for name in untied if name in with_bills}


def _vendor_key(book: Book, name: str) -> str:
    ledger = book.ledger(name)
    return f"gstin:{ledger.gstin}" if ledger.gstin else f"name:{norm(name)}"


def _vendors(book, vendor_names, bills, ctx, alerts) -> list[VendorPlan]:
    by_gstin = {v.gstin: v for v in ctx.vendors if v.gstin}
    by_name = {norm(v.name): v for v in ctx.vendors}
    no_gstin, no_msme = [], []
    plans = []
    for key, name in sorted(vendor_names.items(), key=lambda kv: kv[1].casefold()):
        ledger = book.ledger(name)
        reg = norm(ledger.gst_registration_type)
        registered = bool(ledger.gstin) or reg in ("regular", "composition")
        if not ledger.gstin and reg not in ("unregistered", "consumer"):
            no_gstin.append(name)
        msme = {"micro": "micro", "small": "small", "medium": "medium", "not_msme": "none"}.get(
            ledger.msme_type
        )
        if msme is None:
            no_msme.append(name)
        existing = (by_gstin.get(ledger.gstin) if ledger.gstin else None) or by_name.get(norm(name))
        plan = VendorPlan(
            key=key,
            name=name,
            gstin=ledger.gstin or None,
            registered=registered,
            pan=ledger.pan or None,
            state=ledger.state or None,
            msme_category=msme,
            udyam=ledger.udyam or None,
            existing_id=existing.id if existing else None,
            bills=sum(1 for b in bills if b.vendor_key == key),
        )
        if existing:
            for attr, theirs in (
                ("gstin", plan.gstin),
                ("pan", plan.pan),
                ("state", plan.state),
                ("udyam", plan.udyam),
            ):
                ours = getattr(existing, attr)
                if theirs and not ours:
                    plan.changes[attr] = (ours, theirs)
            if (
                plan.msme_category
                and existing.msme_category == "none"
                and plan.msme_category != "none"
            ):
                plan.changes["msme_category"] = (existing.msme_category, plan.msme_category)
            if plan.registered and not existing.registered:
                plan.changes["registered"] = (False, True)
        plans.append(plan)
    if no_gstin:
        alerts.append(
            Alert(
                "missing",
                "vendor.no_gstin",
                _count(len(no_gstin), "supplier has", "suppliers have") + " no GSTIN",
                "The 80% test counts their purchases as from unregistered suppliers until a "
                "GSTIN is added.",
                "Add the GSTIN in each supplier's ledger in Tally (or on the supplier in "
                "Lekhara), or set the registration type to Unregistered if they are.",
                no_gstin[:30],
            )
        )
    if no_msme:
        alerts.append(
            Alert(
                "missing",
                "vendor.no_msme",
                _count(len(no_msme), "supplier has", "suppliers have") + " no MSME details",
                "Lekhara cannot tell whether the 45-day payment rule applies to them, so it "
                "treats them as not MSME.",
                "Record each supplier's MSME type and Udyam number in their ledger in Tally, or "
                "on the supplier in Lekhara.",
                no_msme[:30],
            )
        )
    return plans


def _receipts(book: Book, vouchers: list[Voucher], ctx: Context, alerts: list[Alert]):
    receipts: list[ReceiptPlan] = []
    unmatched: dict[str, Buyer] = {}
    for v in vouchers:
        if v.base_type != "receipt":
            continue
        debtors = [e for e in v.entries if book.kind(e.ledger) == "debtor" and e.amount < 0]
        if not debtors and not v.detailed and v.party:
            debtors_info = [(v.party, abs(v.entries[0].amount) if v.entries else ZERO)]
        else:
            debtors_info = [(e.ledger, -e.amount) for e in debtors]
        if not debtors_info:
            continue
        tds = sum(
            (
                e.amount
                for e in v.entries
                if e.amount > 0
                and book.kind(e.ledger) == "tax"
                and book.ledger(e.ledger).tax_kind == "tds"
            ),
            ZERO,
        )
        for i, (ledger, credited) in enumerate(debtors_info):
            share_tds = tds if i == 0 else ZERO
            ref = f"tally:{v.key}:{norm(ledger)}"
            link = ctx.links.get(norm(ledger))
            if link == "ignore":
                unmatched.setdefault(norm(ledger), Buyer(ledger, ZERO, 0, [], ignored=True))
                buyer = unmatched[norm(ledger)]
                buyer.total += credited
                buyer.count += 1
                continue
            unit = next((u for u in ctx.units if u.id == link), None) if link else None
            if unit is None:
                found = _match_unit(ledger, v, ctx.units)
                unit = found[0] if len(found) == 1 else None
                if unit is None:
                    buyer = unmatched.setdefault(
                        norm(ledger), Buyer(ledger, ZERO, 0, [u.label for u in found][:5])
                    )
                    buyer.total += credited
                    buyer.count += 1
            receipts.append(
                ReceiptPlan(
                    ref=ref,
                    ledger=ledger,
                    unit_id=unit.id if unit else None,
                    unit_label=unit.label if unit else None,
                    amount=credited - share_tds,
                    tds=share_tds,
                    received_on=v.on,
                    voucher=v.label,
                    exists=ref in ctx.known_refs,
                )
            )
    waiting = [b for b in unmatched.values() if not b.ignored]
    if waiting and not ctx.units:
        alerts.append(
            Alert(
                "blocking",
                "receipt.no_units",
                "This project has no units yet",
                "Buyers' payments are recorded against their units, so they wait until the units "
                "are in Lekhara.",
                "Import your units and buyers first (Units, Import from Excel), then open this "
                "import again.",
            )
        )
    elif waiting:
        alerts.append(
            Alert(
                "blocking",
                "receipt.unmatched",
                _count(len(waiting), "buyer", "buyers") + " could not be matched to a unit",
                "Their payments wait until you choose the unit for each, below. Lekhara "
                "remembers the choice for the next import.",
                "Choose the unit for each buyer, or set aside ledgers that are not buyers.",
                [b.ledger for b in waiting][:30],
            )
        )
    return receipts, sorted(unmatched.values(), key=lambda b: (b.ignored, b.ledger.casefold()))
