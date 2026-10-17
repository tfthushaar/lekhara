from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from horus.db import make_sessionmaker
from horus.engines.disputes import (
    CaseIn,
    CaseStatus,
    Forum,
    OrderIn,
    OrderKind,
    Payment,
    Relief,
    case_position,
)
from horus.models import AppendOnlyViolation, DisputePayment
from horus.rules import KARNATAKA

TODAY = date(2026, 10, 17)
SG = "sarjapur-greens"


def ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def case(**kw) -> CaseIn:
    base = {
        "case_id": "c1",
        "forum": Forum.KRERA,
        "case_number": "CMP/1/2026",
        "relief": Relief.REFUND,
        "status": CaseStatus.HEARING,
        "complainant": "A Buyer",
        "unit_label": "A-0101",
        "buyer_payments": (Payment(ago(365), D("100000")), Payment(ago(73), D("200000"))),
        "possession_due_on": ago(73),
    }
    base.update(kw)
    return CaseIn(**base)


def position(c: CaseIn):
    return case_position(c, as_of=TODAY, rules=KARNATAKA)


# The interest rate is SBI MCLR (8.95%, to confirm) plus 2%: 10.95% a year.


def test_refund_is_everything_paid_with_interest_from_each_payment() -> None:
    e = position(case()).estimate
    assert e.principal == D("300000")
    # 100000 for a year, and 200000 for 73 days, at 10.95%.
    assert e.interest == D("10950.00") + D("4380.00")
    assert e.total == D("315330.00")


def test_delay_interest_runs_from_the_promised_date_or_the_payment_if_later() -> None:
    p = position(
        case(
            relief=Relief.DELAY_INTEREST,
            buyer_payments=(Payment(ago(365), D("100000")), Payment(ago(10), D("50000"))),
        )
    )
    # 100000 from the promised date (73 days), and 50000 from its payment (10 days).
    assert p.estimate.interest == D("2190.00") + D("150.00")
    on_time = position(case(relief=Relief.DELAY_INTEREST, possession_due_on=TODAY))
    assert on_time.estimate.total == 0


def test_a_claim_without_interest_is_costed_at_the_amount_claimed() -> None:
    p = position(case(relief=Relief.DEFECTS, claim_amount=D("450000")))
    assert p.estimate.total == D("450000")
    assert p.at_stake == D("450000")


def test_a_running_order_stops_growing_once_it_is_paid_in_full() -> None:
    order = OrderIn("o1", ordered_on=ago(60), kind=OrderKind.REFUND, comply_by=ago(1))
    unpaid = position(case(orders=(order,)))
    assert unpaid.owed == unpaid.estimate.total
    assert unpaid.orders[0].overdue

    # Pay in full two days ago what was due then; nothing more accrues after that day.
    then = case_position(case(orders=(order,)), as_of=ago(2), rules=KARNATAKA).owed
    paid = position(case(orders=(order,), paid=(Payment(ago(2), then),)))
    assert paid.orders[0].due == then
    assert paid.owed == 0
    assert not paid.orders[0].overdue


def test_appeal_deadline_and_deposit_follow_the_forum() -> None:
    rera = OrderIn(
        "o1", ordered_on=ago(10), received_on=ago(8), kind=OrderKind.COMPENSATION, amount=D("100")
    )
    o = position(case(orders=(rera,))).orders[0]
    assert o.appeal_by == ago(8) + timedelta(days=60)
    assert o.appeal_deposit == D("100.00")

    penalty = OrderIn("o1", ordered_on=ago(10), kind=OrderKind.PENALTY, amount=D("100"))
    assert position(case(orders=(penalty,))).orders[0].appeal_deposit == D("30.00")

    consumer = position(case(forum=Forum.CONSUMER_DISTRICT, orders=(rera,))).orders[0]
    assert consumer.appeal_by == ago(8) + timedelta(days=45)
    assert consumer.appeal_deposit == D("50.00")

    civil = position(case(forum=Forum.CIVIL_COURT, orders=(rera,))).orders[0]
    assert civil.appeal_by is None


def test_an_appeal_stops_the_order_counting_as_overdue() -> None:
    order = OrderIn(
        "o1", ordered_on=ago(90), kind=OrderKind.COSTS, amount=D("25000"), comply_by=ago(30)
    )
    assert position(case(orders=(order,))).orders[0].overdue
    appealed = position(case(orders=(order,), appealed_on=ago(40), status=CaseStatus.APPEALED))
    assert not appealed.orders[0].overdue
    assert all(e.kind not in ("comply", "appeal") for e in appealed.events)


def test_settlement_is_what_is_left_to_pay_and_its_saving() -> None:
    p = position(
        case(
            status=CaseStatus.SETTLING,
            settlement_agreed=D("150000"),
            paid=(Payment(ago(5), D("50000")),),
        )
    )
    assert p.at_stake == D("100000")
    assert p.settlement_saving == D("315330.00") - D("150000")


def test_a_closed_case_costs_nothing_more_and_has_no_dates() -> None:
    p = position(case(status=CaseStatus.SETTLED, next_hearing_on=TODAY + timedelta(days=3)))
    assert p.at_stake == 0
    assert p.events == ()


def test_two_orders_due_the_same_day_show_one_date() -> None:
    orders = tuple(
        OrderIn(f"o{i}", ordered_on=ago(10), kind=OrderKind.COSTS, amount=D("100"), comply_by=TODAY)
        for i in range(2)
    )
    assert [e.kind for e in position(case(orders=orders)).events] == ["comply", "appeal"]


# Through the API


def test_disputes_register(owner) -> None:
    r = owner.get(f"/projects/{SG}/disputes").json()
    assert r["summary"]["open"] == 4
    assert r["summary"]["overdue_orders"] == 2
    assert r["patterns"]["filed_after_possession_due"] == 2
    statuses = {c["case_number"]: c["status"] for c in r["cases"]}
    assert statuses["CMP/DEMO/0290/2026"] == "settled"
    assert r["cases"][-1]["case_number"] == "CMP/DEMO/0290/2026"  # closed cases last

    today = {i["key"]: i for i in owner.get("/today").json()["items"] if i["area"] == "disputes"}
    overdue = next(i for i in today.values() if i["status"] == "overdue")
    assert overdue["amount"] == "275000.00"
    assert overdue["exposure"] is True
    assert overdue["link"].startswith("/cases/")
    appeal = next(i for i in today.values() if i["key"].endswith(":appeal"))
    assert appeal["owed_to"] == "Karnataka Real Estate Appellate Tribunal"


def test_a_case_from_notice_to_compliance(accounts) -> None:
    units = accounts.get(f"/projects/{SG}/disputes").json()["units"]
    r = accounts.post(
        f"/projects/{SG}/disputes",
        json={
            "forum": "krera",
            "case_number": "CMP/TEST/1/2026",
            "relief": "delay_interest",
            "unit": units[50],
            "reply_due_on": "2026-10-30",
        },
    )
    assert r.status_code == 201, r.text
    case_id = r.json()["id"]
    c = accounts.get(f"/cases/{case_id}").json()
    assert c["complainant"].startswith("Buyer")
    assert c["status"] == "notice"
    assert D(c["estimate"]["interest"]) > 0

    r = accounts.put(f"/cases/{case_id}", json={"reply_filed_on": "2026-10-17"})
    assert r.status_code == 200, r.text
    r = accounts.post(
        f"/cases/{case_id}/hearings",
        json={"held_on": "2026-10-17", "purpose": "First hearing", "order_reserved": True},
    )
    assert r.json()["status"] == "reserved"
    r = accounts.post(
        f"/cases/{case_id}/orders",
        json={"ordered_on": "2026-10-17", "kind": "delay_interest", "comply_by": "2026-12-16"},
    )
    order = r.json()["orders"][0]
    assert r.json()["status"] == "ordered"
    assert order["worked_out"] is True
    assert order["appeal_by"] == "2026-12-16"

    r = accounts.post(
        f"/cases/{case_id}/payments",
        json={"paid_on": "2026-10-17", "amount": order["outstanding"], "reference": "NEFT 1"},
    )
    assert r.json()["status"] == "complied"
    assert r.json()["owed"] == "0.00"
    assert r.json()["closed_on"] == "2026-10-17"


def test_a_settlement_closes_the_case_when_paid(owner) -> None:
    case_id = next(
        c["id"]
        for c in owner.get(f"/projects/{SG}/disputes").json()["cases"]
        if c["case_number"] == "CC/DEMO/218/2026"
    )
    # The details form always sends the status; an unchanged status still lets it move on.
    r = owner.put(f"/cases/{case_id}", json={"status": "notice", "settlement_agreed": "200000"})
    assert r.json()["status"] == "settling"
    assert r.json()["at_stake"] == "200000.00"
    assert r.json()["settlement"]["saving"] == "250000.00"
    r = owner.post(f"/cases/{case_id}/payments", json={"paid_on": "2026-10-17", "amount": "200000"})
    assert r.json()["status"] == "settled"


def test_case_input_is_checked(owner) -> None:
    bad_unit = owner.post(
        f"/projects/{SG}/disputes",
        json={"forum": "krera", "case_number": "X", "relief": "refund", "unit": "Z-9999"},
    )
    assert bad_unit.status_code == 400
    bad_forum = owner.post(
        f"/projects/{SG}/disputes",
        json={"forum": "moon", "case_number": "X", "relief": "refund", "complainant": "A"},
    )
    assert bad_forum.status_code == 400

    case_id = owner.get(f"/projects/{SG}/disputes").json()["cases"][0]["id"]
    future = owner.post(f"/cases/{case_id}/hearings", json={"held_on": "2026-11-01"})
    assert future.status_code == 400
    no_amount = owner.post(
        f"/cases/{case_id}/orders", json={"ordered_on": "2026-10-17", "kind": "compensation"}
    )
    assert no_amount.status_code == 400
    nothing_paid = owner.post(
        f"/cases/{case_id}/payments", json={"paid_on": "2026-10-17", "amount": "0"}
    )
    assert nothing_paid.status_code == 400


def test_certifiers_cannot_see_disputes(ca, owner) -> None:
    assert ca.get(f"/projects/{SG}/disputes").status_code == 403
    case_id = owner.get(f"/projects/{SG}/disputes").json()["cases"][0]["id"]
    assert ca.get(f"/cases/{case_id}").status_code == 403
    assert ca.put(f"/cases/{case_id}", json={"lawyer": "X"}).status_code == 403


def test_payments_under_orders_are_append_only(engine) -> None:
    with make_sessionmaker(engine)() as session:
        payment = session.scalars(select(DisputePayment)).first()
        payment.amount = D("1")
        with pytest.raises(AppendOnlyViolation):
            session.commit()
