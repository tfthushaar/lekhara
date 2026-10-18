"""A GSTR-2B against the project's bills.

Each invoice in the return is matched to a bill by the supplier's GSTIN (or, for a supplier in
Lekhara without one, by the supplier's name) and the invoice number, written any way. What comes
out: invoices that agree; invoices whose amounts differ; invoices the GST system has and Lekhara
does not (they can be added as bills); bills in Lekhara for the return's month whose suppliers
have not reported them (the supplier has not filed, so the bill's credit, and its standing as
from a registered supplier for the 80% test, are at risk until they do); and suppliers whose
GSTIN Lekhara does not have yet.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lekhara.gst.reader import Invoice, Return, fold_number
from lekhara.money import ZERO, inr
from lekhara.tally.plan import Alert, _count

TOLERANCE = Decimal("1.00")


@dataclass(frozen=True)
class BillRef:
    id: str
    vendor_id: str
    vendor_name: str
    vendor_gstin: str | None
    bill_no: str
    bill_date: date
    taxable: Decimal
    gst: Decimal | None
    source_ref: str | None


@dataclass(frozen=True)
class VendorRef:
    id: str
    name: str
    gstin: str | None


@dataclass
class Line:
    invoice: Invoice
    outcome: str
    """matched, differs, missing (in Lekhara) or note (a credit or debit note)."""
    bill_id: str | None = None
    vendor_id: str | None = None
    note: str = ""


@dataclass
class Plan:
    lines: list[Line]
    unreported: list[BillRef]
    gstin_updates: list[tuple[VendorRef, str, str | None]]
    """A supplier matched by name, the GSTIN to give it, and the trade name in the return."""
    new_suppliers: dict[str, str]
    """GSTIN to trade name, for suppliers not in Lekhara at all."""
    alerts: list[Alert] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def _fold_name(name: str | None) -> str:
    text = re.sub(r"\b(private|pvt|limited|ltd|llp|and|co|m/s|ms)\b", " ", (name or "").casefold())
    return re.sub(r"[^a-z0-9]", "", text)


def period_month(period: str | None) -> tuple[int, int] | None:
    """(year, month) from an MMYYYY period, as the portal writes it."""
    m = re.fullmatch(r"(\d{2})(\d{4})", (period or "").strip())
    if not m or not 1 <= int(m.group(1)) <= 12:
        return None
    return int(m.group(2)), int(m.group(1))


def make_plan(
    ret: Return,
    bills: list[BillRef],
    vendors: list[VendorRef],
    *,
    firm_gstin: str | None,
) -> Plan:
    by_gstin = {v.gstin: v for v in vendors if v.gstin}
    by_name = {_fold_name(v.name): v for v in vendors if _fold_name(v.name)}
    bills_by_key: dict[tuple[str, str], BillRef] = {}
    for b in bills:
        bills_by_key[(b.vendor_id, fold_number(b.bill_no))] = b

    lines: list[Line] = []
    updates: dict[str, tuple[VendorRef, str, str | None]] = {}
    new_suppliers: dict[str, str] = {}
    matched_bills: set[str] = set()
    for inv in ret.invoices:
        vendor = by_gstin.get(inv.supplier_gstin)
        if vendor is None and inv.supplier_name:
            named = by_name.get(_fold_name(inv.supplier_name))
            if named is not None and not named.gstin:
                vendor = named
                updates[named.id] = (named, inv.supplier_gstin, inv.supplier_name)
        if vendor is None:
            new_suppliers.setdefault(inv.supplier_gstin, inv.supplier_name or inv.supplier_gstin)
        if inv.kind != "invoice":
            lines.append(Line(inv, "note", vendor_id=vendor.id if vendor else None))
            continue
        bill = bills_by_key.get((vendor.id, fold_number(inv.number))) if vendor else None
        if bill is None:
            lines.append(Line(inv, "missing", vendor_id=vendor.id if vendor else None))
            continue
        matched_bills.add(bill.id)
        differences = []
        if abs(bill.taxable - inv.taxable) > TOLERANCE:
            differences.append(
                f"taxable value {inr(bill.taxable)} in Lekhara, {inr(inv.taxable)} in the return"
            )
        if bill.gst is not None and abs(bill.gst - inv.gst) > TOLERANCE:
            differences.append(f"GST {inr(bill.gst)} in Lekhara, {inr(inv.gst)} in the return")
        lines.append(
            Line(
                inv,
                "differs" if differences else "matched",
                bill_id=bill.id,
                vendor_id=vendor.id,
                note="; ".join(differences),
            )
        )

    month = period_month(ret.period)
    unreported = []
    if month is not None:
        year, number = month
        for b in bills:
            if b.id in matched_bills or not b.vendor_gstin:
                continue
            if (b.bill_date.year, b.bill_date.month) == (year, number):
                unreported.append(b)

    plan = Plan(
        lines=lines,
        unreported=unreported,
        gstin_updates=list(updates.values()),
        new_suppliers=new_suppliers,
    )
    plan.counts = {
        "invoices": sum(1 for x in lines if x.invoice.kind == "invoice"),
        "matched": sum(1 for x in lines if x.outcome == "matched"),
        "differs": sum(1 for x in lines if x.outcome == "differs"),
        "missing": sum(1 for x in lines if x.outcome == "missing"),
        "notes": sum(1 for x in lines if x.outcome == "note"),
        "unreported": len(unreported),
        "no_credit": sum(1 for x in lines if x.invoice.itc_available is False),
    }
    plan.alerts = _alerts(ret, plan, firm_gstin)
    return plan


def _alerts(ret: Return, plan: Plan, firm_gstin: str | None) -> list[Alert]:
    alerts: list[Alert] = []
    if firm_gstin and ret.gstin and ret.gstin.upper() != firm_gstin.upper():
        alerts.append(
            Alert(
                "missing",
                "gst.other_gstin",
                "This return is for another GSTIN",
                f"The file is for {ret.gstin}; the firm's GSTIN in Lekhara is {firm_gstin}.",
                "Check that this is the right file, or correct the firm's GSTIN in Settings.",
            )
        )
    if plan.unreported:
        total = sum((b.taxable for b in plan.unreported), ZERO)
        alerts.append(
            Alert(
                "missing",
                "gst.unreported",
                f"{_count(len(plan.unreported), 'bill', 'bills')} not reported by the supplier",
                f"{inr(total)} of bills from registered suppliers for this month are in Lekhara "
                "but not in the GSTR-2B: the supplier has not filed them. Until they do, the "
                "credit on them, and their standing as from a registered supplier for the 80% "
                "test, are at risk.",
                "Ask each supplier to file the invoice in their GSTR-1, then download the next "
                "GSTR-2B.",
                [f"{b.vendor_name}: {b.bill_no}" for b in plan.unreported[:20]],
            )
        )
    differs = [x for x in plan.lines if x.outcome == "differs"]
    if differs:
        alerts.append(
            Alert(
                "missing",
                "gst.differs",
                f"{_count(len(differs), 'invoice', 'invoices')} with different amounts",
                "The supplier reported a different amount from the bill in Lekhara.",
                "Check the bill against the supplier's invoice, and correct whichever is wrong.",
                [
                    f"{x.invoice.supplier_name or x.invoice.supplier_gstin}: {x.invoice.number}"
                    for x in differs[:20]
                ],
            )
        )
    missing = [x for x in plan.lines if x.outcome == "missing"]
    if missing:
        alerts.append(
            Alert(
                "info",
                "gst.missing",
                f"{_count(len(missing), 'invoice', 'invoices')} not in Lekhara",
                "Suppliers reported these, but there is no bill for them in this project. They "
                "can be added as bills; leave them out if they belong to another project or if "
                "your bills come from Tally and the bill is still to be booked there.",
            )
        )
    if plan.gstin_updates:
        alerts.append(
            Alert(
                "info",
                "gst.gstins",
                f"GSTINs for {_count(len(plan.gstin_updates), 'supplier', 'suppliers')}",
                "These suppliers are in Lekhara without a GSTIN; the return gives it.",
                items=[f"{v.name}: {g}" for v, g, _ in plan.gstin_updates[:20]],
            )
        )
    if plan.counts.get("no_credit"):
        alerts.append(
            Alert(
                "info",
                "gst.no_credit",
                "Credit not available on "
                + _count(plan.counts["no_credit"], "invoice", "invoices"),
                "The GST system marks these as not giving input credit, for example where the "
                "place of supply or a time limit rules it out.",
            )
        )
    return alerts
