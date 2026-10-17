from dataclasses import replace
from datetime import date
from decimal import Decimal as D

from lekhara.engines.escrow import (
    AccountTxn,
    CertifierRole,
    CheckStatus,
    LimitedBy,
    RequestStatus,
    TxnKind,
    can_submit,
    check_request,
    draft_certificates,
    escrow_position,
    ongoing_project_deposit_share,
    request_status,
)
from lekhara.engines.money import Category, CostLine, Entry, EntryKind, ReraHead, project_position
from lekhara.rules import KARNATAKA

TODAY = date(2026, 10, 17)


def money(progress: str = "55", civil_incurred: str = "4000", civil_paid: str = "3800"):
    lines = [
        CostLine("land", "L", "Land", Category.LAND, ReraHead.LAND, D("3000"), D("3000")),
        CostLine(
            "civil", "C", "Civil", Category.CONSTRUCTION, ReraHead.DEVELOPMENT, D("7000"), D("7000")
        ),
    ]
    entries = [
        Entry("land", EntryKind.INCURRED, D("3000"), date(2025, 1, 1)),
        Entry("land", EntryKind.PAID, D("3000"), date(2025, 1, 1)),
        Entry("civil", EntryKind.INCURRED, D(civil_incurred), date(2026, 9, 1)),
        Entry("civil", EntryKind.PAID, D(civil_paid), date(2026, 9, 1)),
    ]
    return project_position(
        lines, entries, as_of=TODAY, certified_progress_pct=D(progress), rules=KARNATAKA
    )


def txns(deposits: str = "9000", withdrawn: str = "5000", last: date = date(2026, 7, 1)):
    return [
        AccountTxn(TxnKind.DEPOSIT, D(deposits), date(2026, 1, 1)),
        AccountTxn(TxnKind.WITHDRAWAL, D(withdrawn), last),
    ]


def test_drawable_is_limited_by_cost() -> None:
    m = money()
    e = escrow_position(m, txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    # Basis is cost incurred and paid: land 3000 + civil min(4000, 3800) = 6800.
    assert e.basis_amount == D("6800")
    assert e.cumulative_limit == D("6800")
    assert e.withdrawn_to_date == D("5000")
    assert e.limit_remaining == D("1800")
    assert e.balance == D("4000")
    assert e.drawable_now == D("1800")
    assert e.limited_by == LimitedBy.COST
    assert e.proportion_pct == D("68.00")


def test_drawable_is_limited_by_balance() -> None:
    e = escrow_position(money(), txns(deposits="6000"), D("12000"), as_of=TODAY, rules=KARNATAKA)
    assert e.balance == D("1000")
    assert e.drawable_now == D("1000")
    assert e.limited_by == LimitedBy.BALANCE


def test_nothing_drawable_when_withdrawals_exceed_cost() -> None:
    e = escrow_position(money(), txns(withdrawn="8000"), D("12000"), as_of=TODAY, rules=KARNATAKA)
    assert e.limit_remaining == D("0")
    assert e.drawable_now == D("0")
    assert not e.suggest_withdrawal


def test_deposit_check() -> None:
    e = escrow_position(money(), txns(), D("14000"), as_of=TODAY, rules=KARNATAKA)
    assert e.required_deposits == D("9800.00")
    assert e.deposits == D("9000")
    assert e.deposit_shortfall == D("800.00")


def test_next_cycle_and_suggestion() -> None:
    e = escrow_position(money(), txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    assert e.last_withdrawal_on == date(2026, 7, 1)
    assert e.next_cycle_due_on == date(2026, 9, 29)
    assert not e.suggest_withdrawal  # 1,800 is below the 10 lakh suggestion threshold


def test_ongoing_project_deposit_share() -> None:
    assert ongoing_project_deposit_share(D("150"), D("100"), on=TODAY, rules=KARNATAKA) == D("0.70")
    assert ongoing_project_deposit_share(D("80"), D("100"), on=TODAY, rules=KARNATAKA) == D("1.00")


def signed_drafts(e, m, **overrides):
    drafts = draft_certificates(e, m)
    out = {}
    for role, cert in drafts.items():
        cert = replace(
            cert,
            signed=True,
            signer_name=f"{role.value} signer",
            signer_firm=f"{role.value} firm",
            issued_on=date(2026, 10, 10),
        )
        out[role] = replace(cert, **overrides.get(role, {}))
    return out


def run_checks(amount, certs, e, m, auditor="Statutory Auditors LLP"):
    return check_request(
        D(amount),
        certs,
        e,
        m,
        statutory_auditor_firm=auditor,
        as_of=TODAY,
        rules=KARNATAKA,
    )


def statuses(checks):
    return {c.code: c.status for c in checks}


def test_prepared_and_signed_drafts_pass() -> None:
    m = money()
    e = escrow_position(m, txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    checks = run_checks("1800", signed_drafts(e, m), e, m)
    assert all(c.status == CheckStatus.PASS for c in checks), checks
    assert can_submit(checks)
    status = request_status(checks, submitted=False, released=False, rejected=False)
    assert status == RequestStatus.READY


def test_unsigned_drafts_block_submission() -> None:
    m = money()
    e = escrow_position(m, txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    checks = run_checks("1800", draft_certificates(e, m), e, m)
    assert statuses(checks)["all_signed"] == CheckStatus.PENDING
    assert not can_submit(checks)
    status = request_status(checks, submitted=False, released=False, rejected=False)
    assert status == RequestStatus.AWAITING_SIGNATURES


def test_amount_above_drawable_fails() -> None:
    m = money()
    e = escrow_position(m, txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    s = statuses(run_checks("2500", signed_drafts(e, m), e, m))
    assert s["amount"] == CheckStatus.FAIL
    assert s["ca_covers_request"] == CheckStatus.FAIL


def test_engineer_figure_that_disagrees_fails() -> None:
    m = money()
    e = escrow_position(m, txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    certs = signed_drafts(
        e, m, **{CertifierRole.ENGINEER: {"development_cost_incurred": D("4300")}}
    )
    assert statuses(run_checks("1800", certs, e, m))["engineer_matches_books"] == CheckStatus.FAIL


def test_cost_ahead_of_progress_warns_but_does_not_block() -> None:
    m = money(progress="40", civil_incurred="4500", civil_paid="4500")
    e = escrow_position(m, txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    certs = signed_drafts(e, m, **{CertifierRole.ARCHITECT: {"completion_pct": D("50")}})
    checks = run_checks("1000", certs, e, m)
    # 4500 of 7000 is 64.29% incurred against 50% completion: a 14-point gap.
    assert statuses(checks)["progress_matches_cost"] == CheckStatus.WARN
    assert can_submit(checks)


def test_certificates_far_apart_warn() -> None:
    m = money()
    e = escrow_position(m, txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    certs = signed_drafts(e, m, **{CertifierRole.ARCHITECT: {"issued_on": date(2026, 8, 1)}})
    assert statuses(run_checks("1800", certs, e, m))["dated_together"] == CheckStatus.WARN


def test_certifying_ca_same_as_auditor_warns() -> None:
    m = money()
    e = escrow_position(m, txns(), D("12000"), as_of=TODAY, rules=KARNATAKA)
    certs = signed_drafts(e, m)
    s = statuses(run_checks("1800", certs, e, m, auditor="CA FIRM"))
    assert s["ca_independent"] == CheckStatus.WARN


def test_request_lifecycle() -> None:
    assert (
        request_status([], submitted=True, released=False, rejected=False)
        == RequestStatus.SUBMITTED
    )
    assert (
        request_status([], submitted=True, released=True, rejected=False) == RequestStatus.RELEASED
    )
    assert (
        request_status([], submitted=True, released=False, rejected=True) == RequestStatus.REJECTED
    )
