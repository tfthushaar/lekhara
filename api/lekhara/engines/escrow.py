"""Escrow engine: the RERA designated account, withdrawals and their certificates.

Buyers' money goes into the designated account (70% of receipts). A withdrawal
is allowed in proportion to the cost of the project already incurred:

    cumulative limit = estimated cost x (cost incurred / estimated cost)

minus what has already been withdrawn, and never more than the account holds.
Three people certify each withdrawal: the architect (physical completion), the
engineer (development cost incurred) and the CA (total cost incurred and the
amount withdrawable). Lekhara prepares the drafts from the books and checks that
the figures agree with each other before anything goes to the bank.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from lekhara.engines.money import ProjectPosition
from lekhara.money import ZERO, percent
from lekhara.rules import RulesPack


class TxnKind(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    INTEREST = "interest"


@dataclass(frozen=True)
class AccountTxn:
    kind: TxnKind
    amount: Decimal
    on: date


class LimitedBy(StrEnum):
    COST = "cost"
    BALANCE = "balance"


@dataclass(frozen=True)
class EscrowPosition:
    as_of: date
    estimated_cost: Decimal
    cost_incurred: Decimal
    cost_basis: str
    basis_amount: Decimal
    proportion_pct: Decimal
    cumulative_limit: Decimal
    withdrawn_to_date: Decimal
    balance: Decimal
    limit_remaining: Decimal
    drawable_now: Decimal
    limited_by: LimitedBy
    receipts_from_buyers: Decimal
    deposit_share: Decimal
    required_deposits: Decimal
    deposits: Decimal
    deposit_shortfall: Decimal
    last_withdrawal_on: date | None
    next_cycle_due_on: date | None
    suggest_withdrawal: bool


def escrow_position(
    money: ProjectPosition,
    txns: list[AccountTxn],
    receipts_from_buyers: Decimal,
    *,
    as_of: date,
    rules: RulesPack,
    deposit_share: Decimal | None = None,
) -> EscrowPosition:
    txns = [t for t in txns if t.on <= as_of]
    deposits = sum((t.amount for t in txns if t.kind == TxnKind.DEPOSIT), ZERO)
    interest = sum((t.amount for t in txns if t.kind == TxnKind.INTEREST), ZERO)
    withdrawals = [t for t in txns if t.kind == TxnKind.WITHDRAWAL]
    withdrawn = sum((t.amount for t in withdrawals), ZERO)
    balance = deposits + interest - withdrawn

    cost_basis = rules.value("escrow.withdrawal_cost_basis", as_of)
    if cost_basis == "incurred_and_paid":
        basis_amount = sum((min(p.incurred, p.paid) for p in money.lines), ZERO)
    else:
        basis_amount = money.incurred

    estimated = money.anticipated_final_cost
    proportion_pct = percent(basis_amount, estimated)
    # estimated x (basis / estimated) is the basis amount itself; kept explicit for the certificate.
    cumulative_limit = basis_amount
    limit_remaining = max(cumulative_limit - withdrawn, ZERO)
    drawable = max(min(limit_remaining, balance), ZERO)
    limited_by = LimitedBy.BALANCE if balance < limit_remaining else LimitedBy.COST

    share = (
        deposit_share if deposit_share is not None else rules.value("escrow.deposit_share", as_of)
    )
    required = (receipts_from_buyers * share).quantize(Decimal("0.01"))

    last_withdrawal = max((t.on for t in withdrawals), default=None)
    cycle_days = rules.value("escrow.cycle_days", as_of)
    next_cycle = last_withdrawal + timedelta(days=cycle_days) if last_withdrawal else None

    return EscrowPosition(
        as_of=as_of,
        estimated_cost=estimated,
        cost_incurred=money.incurred,
        cost_basis=cost_basis,
        basis_amount=basis_amount,
        proportion_pct=proportion_pct,
        cumulative_limit=cumulative_limit,
        withdrawn_to_date=withdrawn,
        balance=balance,
        limit_remaining=limit_remaining,
        drawable_now=drawable,
        limited_by=limited_by,
        receipts_from_buyers=receipts_from_buyers,
        deposit_share=share,
        required_deposits=required,
        deposits=deposits,
        deposit_shortfall=max(required - deposits, ZERO),
        last_withdrawal_on=last_withdrawal,
        next_cycle_due_on=next_cycle,
        suggest_withdrawal=drawable >= rules.value("escrow.min_suggested_withdrawal", as_of),
    )


def ongoing_project_deposit_share(
    balance_receivables: Decimal, balance_cost_to_complete: Decimal, *, on: date, rules: RulesPack
) -> Decimal:
    """For a project already under way at registration: 70% of balance receivables go into the
    account when they exceed the balance cost to complete, otherwise all of them."""
    if balance_cost_to_complete <= 0:
        return rules.value("escrow.deposit_share", on)
    ratio = balance_receivables / balance_cost_to_complete
    if ratio > rules.value("escrow.ongoing_ratio_threshold", on):
        return rules.value("escrow.deposit_share", on)
    return Decimal("1.00")


# Withdrawal certificates


class CertifierRole(StrEnum):
    ARCHITECT = "architect"
    ENGINEER = "engineer"
    CA = "ca"


ROLE_ORDER = (CertifierRole.ARCHITECT, CertifierRole.ENGINEER, CertifierRole.CA)

ROLE_LABEL = {
    CertifierRole.ARCHITECT: "Architect",
    CertifierRole.ENGINEER: "Engineer",
    CertifierRole.CA: "Chartered accountant",
}

ROLE_CERTIFIES = {
    CertifierRole.ARCHITECT: "Physical completion of the project",
    CertifierRole.ENGINEER: "Development cost incurred",
    CertifierRole.CA: "Total cost incurred and the amount that can be withdrawn",
}


@dataclass(frozen=True)
class Certificate:
    role: CertifierRole
    signed: bool = False
    signer_name: str | None = None
    signer_firm: str | None = None
    issued_on: date | None = None
    completion_pct: Decimal | None = None
    development_cost_incurred: Decimal | None = None
    total_cost_incurred: Decimal | None = None
    withdrawable_amount: Decimal | None = None


def draft_certificates(
    escrow: EscrowPosition, money: ProjectPosition
) -> dict[CertifierRole, Certificate]:
    """Unsigned drafts prepared from the books, for each certifier to review."""
    return {
        CertifierRole.ARCHITECT: Certificate(
            role=CertifierRole.ARCHITECT, completion_pct=money.certified_progress_pct
        ),
        CertifierRole.ENGINEER: Certificate(
            role=CertifierRole.ENGINEER, development_cost_incurred=money.development.incurred
        ),
        CertifierRole.CA: Certificate(
            role=CertifierRole.CA,
            total_cost_incurred=escrow.basis_amount,
            withdrawable_amount=escrow.drawable_now,
        ),
    }


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    PENDING = "pending"


@dataclass(frozen=True)
class Check:
    code: str
    status: CheckStatus
    title: str
    detail: str


def _within(value: Decimal, expected: Decimal, tolerance: Decimal) -> bool:
    return abs(value - expected) <= abs(expected) * tolerance


def check_request(
    amount: Decimal,
    certificates: dict[CertifierRole, Certificate],
    escrow: EscrowPosition,
    money: ProjectPosition,
    *,
    statutory_auditor_firm: str | None,
    as_of: date,
    rules: RulesPack,
) -> list[Check]:
    """Everything the bank or the K-RERA auditor would check, before they see it."""
    tolerance = rules.value("escrow.figure_tolerance", as_of)
    checks: list[Check] = []

    if amount <= 0:
        checks.append(
            Check("amount", CheckStatus.FAIL, "Amount requested", "Enter an amount above zero.")
        )
    elif amount <= escrow.drawable_now:
        checks.append(
            Check(
                "amount",
                CheckStatus.PASS,
                "Amount is within what can be drawn",
                "The amount requested is covered by cost incurred and the account balance.",
            )
        )
    else:
        reason = (
            "the account balance" if escrow.limited_by == LimitedBy.BALANCE else "cost incurred"
        )
        checks.append(
            Check(
                "amount",
                CheckStatus.FAIL,
                "Amount is more than can be drawn",
                f"The most that can be drawn now is limited by {reason}.",
            )
        )

    architect = certificates.get(CertifierRole.ARCHITECT)
    engineer = certificates.get(CertifierRole.ENGINEER)
    ca = certificates.get(CertifierRole.CA)

    if engineer is None or engineer.development_cost_incurred is None:
        checks.append(
            Check(
                "engineer_matches_books",
                CheckStatus.PENDING,
                "Engineer's cost matches the books",
                "Waiting for the engineer's figure.",
            )
        )
    elif _within(engineer.development_cost_incurred, money.development.incurred, tolerance):
        checks.append(
            Check(
                "engineer_matches_books",
                CheckStatus.PASS,
                "Engineer's cost matches the books",
                "The development cost certified agrees with the books.",
            )
        )
    else:
        checks.append(
            Check(
                "engineer_matches_books",
                CheckStatus.FAIL,
                "Engineer's cost does not match the books",
                "The development cost certified differs from the books. "
                "Banks reject certificates that disagree with the accounts.",
            )
        )

    if ca is None or ca.total_cost_incurred is None:
        checks.append(
            Check(
                "ca_matches_books",
                CheckStatus.PENDING,
                "CA's cost matches the books",
                "Waiting for the CA's figure.",
            )
        )
    elif _within(ca.total_cost_incurred, escrow.basis_amount, tolerance):
        checks.append(
            Check(
                "ca_matches_books",
                CheckStatus.PASS,
                "CA's cost matches the books",
                "The total cost certified agrees with the books.",
            )
        )
    else:
        checks.append(
            Check(
                "ca_matches_books",
                CheckStatus.FAIL,
                "CA's cost does not match the books",
                "The total cost certified differs from the books.",
            )
        )

    if ca is None or ca.withdrawable_amount is None:
        checks.append(
            Check(
                "ca_covers_request",
                CheckStatus.PENDING,
                "CA's certificate covers the request",
                "Waiting for the CA's withdrawable amount.",
            )
        )
    elif ca.withdrawable_amount < amount:
        checks.append(
            Check(
                "ca_covers_request",
                CheckStatus.FAIL,
                "CA's certificate is below the amount requested",
                "Reduce the request to the amount the CA certifies, or ask the CA to review.",
            )
        )
    elif ca.withdrawable_amount > escrow.drawable_now:
        checks.append(
            Check(
                "ca_covers_request",
                CheckStatus.FAIL,
                "CA's withdrawable amount is more than can be drawn",
                "The certified amount is above what cost incurred and the balance allow.",
            )
        )
    else:
        checks.append(
            Check(
                "ca_covers_request",
                CheckStatus.PASS,
                "CA's certificate covers the request",
                "The amount certified as withdrawable covers the amount requested.",
            )
        )

    if architect is None or architect.completion_pct is None:
        checks.append(
            Check(
                "progress_matches_cost",
                CheckStatus.PENDING,
                "Progress and cost tell the same story",
                "Waiting for the architect's completion figure.",
            )
        )
    else:
        gap = money.development_incurred_pct - architect.completion_pct
        if gap >= rules.value("escrow.progress_gap_points", as_of):
            checks.append(
                Check(
                    "progress_matches_cost",
                    CheckStatus.WARN,
                    "Cost is running ahead of certified progress",
                    f"{money.development_incurred_pct}% of development cost is incurred against "
                    f"{architect.completion_pct}% completion. Expect questions from the bank and "
                    "the K-RERA auditor; keep an explanation ready.",
                )
            )
        else:
            checks.append(
                Check(
                    "progress_matches_cost",
                    CheckStatus.PASS,
                    "Progress and cost tell the same story",
                    "Certified completion and cost incurred are in line.",
                )
            )

    dates = [c.issued_on for c in certificates.values() if c.issued_on is not None]
    window = rules.value("escrow.certificate_window_days", as_of)
    if len(dates) < len(ROLE_ORDER):
        checks.append(
            Check(
                "dated_together",
                CheckStatus.PENDING,
                "Certificates are dated close together",
                "Waiting for all three certificates.",
            )
        )
    elif (max(dates) - min(dates)).days <= window:
        checks.append(
            Check(
                "dated_together",
                CheckStatus.PASS,
                "Certificates are dated close together",
                f"All three certificates are within {window} days of each other.",
            )
        )
    else:
        checks.append(
            Check(
                "dated_together",
                CheckStatus.WARN,
                "Certificates are far apart in time",
                f"The certificates are more than {window} days apart. "
                "The bank may ask for fresh ones.",
            )
        )

    if ca is not None and ca.signer_firm and statutory_auditor_firm:
        if ca.signer_firm.strip().casefold() == statutory_auditor_firm.strip().casefold():
            checks.append(
                Check(
                    "ca_independent",
                    CheckStatus.WARN,
                    "Certifying CA is also the statutory auditor",
                    "Some states require the certifying CA to be different from the statutory "
                    "auditor. Confirm the K-RERA position.",
                )
            )
        else:
            checks.append(
                Check(
                    "ca_independent",
                    CheckStatus.PASS,
                    "Certifying CA is independent of the statutory auditor",
                    "The certifying CA firm differs from the statutory auditor.",
                )
            )

    signed = sum(1 for role in ROLE_ORDER if (c := certificates.get(role)) and c.signed)
    checks.append(
        Check(
            "all_signed",
            CheckStatus.PASS if signed == len(ROLE_ORDER) else CheckStatus.PENDING,
            "All three certificates are signed",
            f"{signed} of {len(ROLE_ORDER)} signed.",
        )
    )
    return checks


class RequestStatus(StrEnum):
    AWAITING_SIGNATURES = "awaiting_signatures"
    READY = "ready"
    SUBMITTED = "submitted"
    RELEASED = "released"
    REJECTED = "rejected"


def request_status(
    checks: list[Check], *, submitted: bool, released: bool, rejected: bool
) -> RequestStatus:
    if rejected:
        return RequestStatus.REJECTED
    if released:
        return RequestStatus.RELEASED
    if submitted:
        return RequestStatus.SUBMITTED
    blocked = any(c.status in (CheckStatus.FAIL, CheckStatus.PENDING) for c in checks)
    return RequestStatus.AWAITING_SIGNATURES if blocked else RequestStatus.READY


def can_submit(checks: list[Check]) -> bool:
    return not any(c.status in (CheckStatus.FAIL, CheckStatus.PENDING) for c in checks)
