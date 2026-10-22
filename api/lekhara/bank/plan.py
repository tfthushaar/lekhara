"""What a bank statement brings into a project, line by line, and what the builder must know.

The RERA designated account's statement gives its deposits, withdrawals, interest and charges.
The account buyers pay into gives their payments, each matched to a unit from the narration
(the unit number, or the buyer's name), from the builder's earlier choice for the same payer, or
from the buyer's ledger in Tally. Money already in Lekhara, from an earlier statement or from
Tally, is recognised and not added twice. A payment that came back (a bounced cheque, a returned
transfer) is paired with the original and both are left out.

The firm's bank rules (`RuleRef`) say what lines with certain words are: a unit's buyer, not a
buyer, a line to leave out, or which kind of movement in the RERA account. The first rule that
fits a line decides it, after any choice made for the line itself and before the payers
remembered from earlier statements.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lekhara.bank import narration as words
from lekhara.bank.reader import Line, Statement
from lekhara.matching import matches, normal
from lekhara.money import ZERO, inr
from lekhara.tally.plan import Alert, UnitRef, _alnum, _count, _unit_pattern

MATCH_DAYS = 3
RETURN_DAYS = 15
STALE_DAYS = 45
KIND_ACTIONS = ("deposit", "interest", "withdrawal", "charges")
"""Rule actions that say which movement in the RERA account a line is."""


@dataclass(frozen=True)
class KnownReceipt:
    id: str
    unit_id: str
    on: date
    amount: Decimal
    source_ref: str | None


@dataclass(frozen=True)
class KnownTxn:
    id: str
    kind: str
    on: date
    amount: Decimal
    reference: str | None


@dataclass(frozen=True)
class RuleRef:
    name: str
    words: str
    how: str
    direction: str
    """in, out or any."""
    action: str
    unit_id: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None

    def fits(self, line: Line) -> bool:
        if (self.direction == "in" and not line.is_credit) or (
            self.direction == "out" and line.is_credit
        ):
            return False
        if self.min_amount is not None and line.amount < self.min_amount:
            return False
        if self.max_amount is not None and line.amount > self.max_amount:
            return False
        return matches(self.how, self.words, normal(line.narration))


@dataclass(frozen=True)
class Context:
    as_of: date
    role: str | None
    """rera, collections, or None until the builder says which account this is."""
    buyers_pay_here: bool
    units: tuple[UnitRef, ...]
    """Sold units, with their buyers."""
    payers: dict[str, str | None]
    """A remembered payer to their unit, or None for someone who is not a buyer."""
    tally_units: dict[str, str]
    """A buyer's ledger in Tally, normalised, to their unit."""
    choices: dict[str, str]
    """A line's key to a unit id, "not_buyer" or "skip"."""
    own_names: tuple[str, ...] = ()
    receipts: tuple[KnownReceipt, ...] = ()
    escrow: tuple[KnownTxn, ...] = ()
    rules: tuple[RuleRef, ...] = ()
    """The firm's bank rules for this project, in their order."""


@dataclass
class LinePlan:
    key: str
    index: int
    on: date
    narration: str
    reference: str | None
    channel: str | None
    payer: str | None
    debit: Decimal
    credit: Decimal
    balance: Decimal | None
    outcome: str
    """buyer_payment, deposit, withdrawal, interest, charges, not_buyer, returned, needs_unit,
    exists, left_out or waiting."""
    note: str = ""
    escrow_kind: str | None = None
    escrow_exists: bool = False
    receipt: bool = False
    receipt_exists: bool = False
    unit_id: str | None = None
    how: str | None = None
    candidates: list[str] = field(default_factory=list)
    loan: bool = False
    buyer_line: bool = False
    """A credit that could be a buyer's payment, so the builder can place it."""
    rule: str | None = None
    """The bank rule that decided the line."""

    @property
    def amount(self) -> Decimal:
        return self.credit if self.credit else self.debit


@dataclass
class Plan:
    lines: list[LinePlan]
    alerts: list[Alert]
    totals: dict[str, Decimal]
    counts: dict[str, int]

    @property
    def to_add(self) -> list[LinePlan]:
        return [
            p
            for p in self.lines
            if (p.receipt and not p.receipt_exists) or (p.escrow_kind and not p.escrow_exists)
        ]


def _live(refs: list[str | None]) -> set[str]:
    refs = [r for r in refs if r]
    undone = {r.removeprefix("undo:") for r in refs if r.startswith("undo:")}
    return {r for r in refs if not r.startswith("undo:") and r not in undone}


def _name_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.casefold()))


def match_units(text: str, units: tuple[UnitRef, ...]) -> tuple[list[UnitRef], str | None]:
    """Units the narration points at: by unit number, by the buyer's name, or both."""
    lowered = text.casefold()
    flat = _alnum(text)
    present = _name_words(text)
    by_label = [u for u in units if u.label and _unit_pattern(u.label).search(lowered)]
    by_buyer = []
    for u in units:
        if not u.buyer:
            continue
        tokens = [t for t in re.findall(r"[a-z]+", u.buyer.casefold()) if len(t) >= 2]
        whole = _alnum(u.buyer)
        if (tokens and all(t in present for t in tokens) and len(whole) >= 5) or (
            len(whole) >= 8 and whole in flat
        ):
            by_buyer.append(u)
    both = [u for u in by_label if u in by_buyer]
    if len(both) == 1:
        return both, "unit number and buyer's name"
    if len(by_label) == 1 and not by_buyer:
        return by_label, "unit number"
    if len(by_buyer) == 1 and not by_label:
        return by_buyer, "buyer's name"
    if len(by_label) == 1 and len(by_buyer) > 1 and by_label[0] in by_buyer:
        return by_label, "unit number and buyer's name"
    return (both or by_label or by_buyer), None


def _pair_returns(lines: list[Line]) -> dict[int, int]:
    """Each payment that came back, paired with the original: line index to line index."""
    paired: dict[int, int] = {}
    for line in lines:
        if not words.is_returned(line.narration):
            continue
        for earlier in reversed(lines[: line.index]):
            if earlier.index in paired or (line.on - earlier.on).days > RETURN_DAYS:
                continue
            if earlier.is_credit != line.is_credit and earlier.amount == line.amount:
                paired[line.index] = earlier.index
                paired[earlier.index] = line.index
                break
    return paired


def _buyer(
    p: LinePlan, line: Line, ctx: Context, units: dict[str, UnitRef], rule: RuleRef | None
) -> None:
    """Who a credit came from: a unit, someone who is not a buyer, or a question."""
    p.buyer_line = True
    choice = ctx.choices.get(line.key)
    key = words.payer_key(p.payer)
    if choice and choice not in ("not_buyer", "skip") and choice in units:
        p.unit_id, p.how = choice, "chosen by you"
    elif choice == "not_buyer":
        p.outcome, p.note = "not_buyer", "Marked by you as not a buyer's payment."
        return
    elif rule is not None and rule.action == "not_buyer":
        p.rule = rule.name
        p.outcome, p.note = "not_buyer", f"Not a buyer's payment, by the rule {rule.name}."
        return
    elif rule is not None and rule.action == "unit" and rule.unit_id in units:
        p.unit_id, p.how, p.rule = rule.unit_id, f"the rule {rule.name}", rule.name
    elif key and not p.loan and key in ctx.payers:
        unit = ctx.payers[key]
        if unit is None:
            p.outcome, p.note = "not_buyer", f"{p.payer} is not a buyer, as you chose before."
            return
        if unit in units:
            p.unit_id, p.how = unit, "your earlier choice for this payer"
    if p.unit_id is None and key and key in ctx.tally_units and ctx.tally_units[key] in units:
        p.unit_id, p.how = ctx.tally_units[key], "the buyer's ledger in Tally"
    if p.unit_id is None:
        found, how = match_units(line.narration, ctx.units)
        if len(found) == 1:
            p.unit_id, p.how = found[0].id, how
        else:
            p.candidates = [u.id for u in found]
    if p.unit_id is None:
        p.outcome = "needs_unit"
        p.note = (
            "Several units could match; choose one."
            if p.candidates
            else "A home-loan disbursement: choose the buyer's unit."
            if p.loan
            else "Choose the buyer's unit, or mark it as not a buyer's payment."
        )
        return
    p.outcome, p.receipt = "buyer_payment", True


def make_plan(statement: Statement, ctx: Context) -> Plan:
    units = {u.id: u for u in ctx.units}
    paired = _pair_returns(statement.lines)
    plans: list[LinePlan] = []
    for line in statement.lines:
        p = LinePlan(
            key=line.key,
            index=line.index,
            on=line.on,
            narration=line.narration,
            reference=words.utr(line.narration, line.reference),
            channel=words.channel(line.narration),
            payer=words.payer(line.narration, ctx.own_names),
            debit=line.debit,
            credit=line.credit,
            balance=line.balance,
            outcome="waiting",
            loan=words.is_loan(line.narration),
        )
        plans.append(p)
        choice = ctx.choices.get(line.key)
        if choice == "skip":
            p.outcome, p.note = "left_out", "Left out by you."
            continue
        if line.index in paired:
            other = statement.lines[paired[line.index]]
            p.outcome = "returned"
            p.note = (
                f"Came back on {other.on:%d %b %Y}; both left out."
                if other.index > line.index
                else f"Returns the payment of {other.on:%d %b %Y}; both left out."
            )
            continue
        rule = next((r for r in ctx.rules if r.fits(line)), None)
        if rule is not None and rule.action == "leave_out" and choice is None:
            p.rule = rule.name
            p.outcome, p.note = "left_out", f"Left out by the rule {rule.name}."
            continue
        if ctx.role is None:
            continue
        interest = words.is_interest(line.narration)
        kind_rule = rule if rule is not None and rule.action in KIND_ACTIONS else None
        if kind_rule is not None and kind_rule.action in ("deposit", "interest"):
            interest = kind_rule.action == "interest"
        if ctx.role == "rera":
            if line.is_credit:
                p.escrow_kind = "interest" if interest else "deposit"
                p.outcome = p.escrow_kind
                if kind_rule is not None:
                    p.rule, p.note = kind_rule.name, f"By the rule {kind_rule.name}."
                deposit_by_rule = kind_rule is not None and kind_rule.action == "deposit"
                if ctx.buyers_pay_here and not interest and not deposit_by_rule:
                    _buyer(p, line, ctx, units, rule)
                    if p.outcome in ("not_buyer", "needs_unit", "buyer_payment"):
                        # Still a deposit into the RERA account, whoever it came from.
                        p.escrow_kind = "deposit"
                        if p.outcome == "not_buyer":
                            p.outcome = "deposit"
            else:
                charge = words.is_charge(line.narration)
                if kind_rule is not None and kind_rule.action in ("withdrawal", "charges"):
                    charge = kind_rule.action == "charges"
                    p.rule, p.note = kind_rule.name, f"By the rule {kind_rule.name}."
                p.escrow_kind = "charges" if charge else "withdrawal"
                p.outcome = p.escrow_kind
        elif line.is_credit:
            if interest:
                p.outcome, p.note = "not_buyer", "Interest from the bank."
            else:
                _buyer(p, line, ctx, units, rule)
        else:
            p.outcome = "left_out"
            p.note = "Money out of the account; Lekhara needs only what buyers paid in."

    _recognise(plans, ctx)
    return Plan(
        lines=plans,
        alerts=_alerts(statement, plans, ctx),
        totals=_totals(statement, plans),
        counts=_counts(plans),
    )


def _recognise(plans: list[LinePlan], ctx: Context) -> None:
    """Mark what Lekhara already has: the same line from an earlier statement, or the same
    money recorded from Tally or by hand within a few days."""
    receipt_refs = _live([r.source_ref for r in ctx.receipts])
    escrow_refs = _live([t.reference for t in ctx.escrow])
    live_receipts = [r for r in ctx.receipts if not r.source_ref or r.source_ref in receipt_refs]
    live_escrow = [
        t
        for t in ctx.escrow
        if not (t.reference or "").startswith("undo:")
        and (not t.reference or t.reference in escrow_refs)
    ]
    claimed_r: set[str] = set()
    claimed_e: set[str] = set()
    for p in plans:
        if p.receipt:
            if p.key in receipt_refs:
                p.receipt_exists = True
            else:
                for r in live_receipts:
                    if (
                        r.id not in claimed_r
                        and not (r.source_ref or "").startswith("bank:")
                        and r.unit_id == p.unit_id
                        and r.amount == p.credit
                        and abs((r.on - p.on).days) <= MATCH_DAYS
                    ):
                        claimed_r.add(r.id)
                        p.receipt_exists = True
                        break
        if p.escrow_kind:
            if p.key in escrow_refs:
                p.escrow_exists = True
            else:
                for t in live_escrow:
                    if (
                        t.id not in claimed_e
                        and not (t.reference or "").startswith("bank:")
                        and t.kind == p.escrow_kind
                        and t.amount == p.amount
                        and abs((t.on - p.on).days) <= MATCH_DAYS
                    ):
                        claimed_e.add(t.id)
                        p.escrow_exists = True
                        break
        wanted = [x for x in (p.receipt, bool(p.escrow_kind)) if x]
        have = [x for x in (p.receipt_exists, p.escrow_exists) if x]
        if wanted and len(have) == len(wanted):
            p.note = p.note or "Already in Lekhara."
            p.outcome = "exists"


def _totals(statement: Statement, plans: list[LinePlan]) -> dict[str, Decimal]:
    def total(*outcomes) -> Decimal:
        return sum((p.amount for p in plans if p.outcome in outcomes), ZERO)

    return {
        "credits": sum((line.credit for line in statement.lines), ZERO),
        "debits": sum((line.debit for line in statement.lines), ZERO),
        "buyer_payments": total("buyer_payment"),
        "waiting": total("needs_unit"),
        "deposits": sum(
            (p.amount for p in plans if p.escrow_kind == "deposit" and not p.escrow_exists), ZERO
        ),
        "withdrawals": total("withdrawal"),
        "interest": total("interest"),
        "charges": total("charges"),
    }


def _counts(plans: list[LinePlan]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in plans:
        counts[p.outcome] = counts.get(p.outcome, 0) + 1
    counts["to_add"] = sum(
        1
        for p in plans
        if (p.receipt and not p.receipt_exists) or (p.escrow_kind and not p.escrow_exists)
    )
    return counts


def _alerts(statement: Statement, plans: list[LinePlan], ctx: Context) -> list[Alert]:
    alerts: list[Alert] = []
    if ctx.role is None:
        alerts.append(
            Alert(
                "blocking",
                "account.role",
                "Which account is this?",
                "The RERA designated account's statement gives deposits, withdrawals and "
                "interest; the account buyers pay into gives their payments. Lekhara remembers "
                "the choice for this account's next statements.",
                "Choose below.",
            )
        )
    waiting = [p for p in plans if p.outcome == "needs_unit"]
    if waiting:
        alerts.append(
            Alert(
                "blocking",
                "buyer.unmatched",
                f"{_count(len(waiting), 'payment', 'payments')} could not be matched to a unit",
                "They wait until you choose the unit; the rest can come in now. Lekhara "
                "remembers each payer for the next statement.",
                "Choose the unit for each below, or mark it as not a buyer's payment.",
                [f"{p.on:%d %b %Y}  {p.payer or p.narration[:60]}" for p in waiting[:20]],
            )
        )
    returned = [p for p in plans if p.outcome == "returned"]
    if returned:
        alerts.append(
            Alert(
                "info",
                "line.returned",
                f"{_count(len(returned) // 2 or 1, 'payment', 'payments')} came back",
                "A bounced cheque or a returned transfer is paired with the original payment, "
                "and both are left out.",
            )
        )
    if statement.balance_breaks:
        alerts.append(
            Alert(
                "missing",
                "file.balance_breaks",
                "The running balance jumps in places",
                f"At {_count(len(statement.balance_breaks), 'line', 'lines')} the balance does "
                "not follow from the line before, so some transactions may be missing from the "
                "download.",
                "Download the statement again for the whole period, as Excel or CSV.",
                [f"{statement.lines[i].on:%d %b %Y}" for i in statement.balance_breaks[:10]],
            )
        )
    if ctx.role == "rera":
        tally = [
            t
            for t in ctx.escrow
            if (t.reference or "").startswith("tally:")
            and statement.period_from
            and statement.period_to
            and statement.period_from <= t.on <= statement.period_to
        ]
        if tally:
            alerts.append(
                Alert(
                    "info",
                    "rera.tally",
                    "Tally has already brought in movements for these dates",
                    "Movements already in from Tally (the same amount within three days) are "
                    "recognised and not added again.",
                )
            )
        before = statement.period_from or statement.lines[0].on
        known = [t for t in ctx.escrow if t.on < before]
        balance = sum(
            (
                t.amount if t.kind in ("deposit", "interest") else -t.amount
                for t in known
                if t.kind in ("deposit", "interest", "withdrawal", "charges")
            ),
            ZERO,
        )
        if statement.opening is not None and abs(statement.opening - balance) > Decimal("1"):
            alerts.append(
                Alert(
                    "missing",
                    "rera.opening",
                    "The statement's opening balance differs from Lekhara's",
                    f"The statement opens at {inr(statement.opening)} on "
                    f"{before:%d %b %Y}; the RERA account in Lekhara stood at {inr(balance)} "
                    "the day before. Movements before this statement are missing or differ.",
                    "Import the earlier statements, back to when the account was opened.",
                )
            )
    last = statement.lines[-1].on
    if (ctx.as_of - last).days > STALE_DAYS:
        alerts.append(
            Alert(
                "info",
                "file.stale",
                f"The statement ends on {last:%d %b %Y}",
                "Bring in a newer statement to keep collections and the RERA account current.",
            )
        )
    if not statement.account:
        alerts.append(
            Alert(
                "info",
                "file.no_account",
                "The account number is not in the file",
                "Lekhara cannot recognise the account by itself, so it asks each time which "
                "account the statement is for.",
            )
        )
    return alerts
