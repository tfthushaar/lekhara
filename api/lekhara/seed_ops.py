"""Demo data for running the firm: contractors and their running bills, bills waiting for
approval, a week of site reports with material, requests for material, snags, defects and
buyers' requests, and a construction loan.

Built through the same services the app uses, so the figures add up as they would for a real
firm. Uses its own random numbers, so the rest of the demo comes out the same.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import aftercare, contractors, lending, site
from lekhara.models import Bill, Project, Unit, UnitHandover, User, Vendor
from lekhara.storage import Storage

WORK = (
    "Shuttering and reinforcement for the 9th floor slab, Tower A. Columns cast up to the 9th.",
    "Concreting of the 9th floor slab, Tower A, 62 cubic metres. Curing on the 8th floor.",
    "Blockwork on the 6th floor, Tower B. Plumbing sleeves fixed on the 7th.",
    "Shuttering removed on the 7th floor. Electrical conduits laid in the 9th floor slab.",
    "Plastering inside, 4th floor, Tower B. Lift shaft wall up to the 10th.",
)
ISSUES = (
    None,
    "Ready-mix truck came two hours late.",
    None,
    "Water tanker did not come; curing done from the sump.",
    None,
)


def seed_ops(
    session: Session,
    projects: list[Project],
    users: dict[str, User],
    today: date,
    storage: Storage | None = None,
) -> None:
    rng = random.Random(53)
    by_id = {p.id: p for p in projects}
    owner = users["promoter@demo.lekhara"].id
    accounts = users["accounts@demo.lekhara"].id
    site_user = users["site@demo.lekhara"].id
    sales_user = users["sales@demo.lekhara"].id
    hb, sg, wf = by_id["hebbal-heights"], by_id["sarjapur-greens"], by_id["whitefield-residences"]

    # Contractors: a civil contractor on Hebbal Heights and an electrical one on Sarjapur Greens.
    civil = contractors.create_order(
        session,
        hb,
        {
            "contractor": "Shivashakti Constructions",
            "reference": "WO-CIVIL-01",
            "description": "Civil and structure, Towers A and B",
            "cost_line": "CIVIL",
            "amount": "42000000",
            "retention_pct": "5",
            "advance": "2000000",
            "deduct_cess": "yes",
            "committed_on": today - timedelta(days=240),
        },
        as_of=today,
        user_id=owner,
    )
    session.get(Vendor, civil.vendor_id).pan = "AAKFS4567Q"
    electrical = contractors.create_order(
        session,
        sg,
        {
            "contractor": "Ramesh Electricals",
            "reference": "WO-ELEC-02",
            "description": "Wiring and fittings, all towers",
            "amount": "4500000",
            "retention_pct": "5",
            "deduct_cess": "yes",
            "committed_on": today - timedelta(days=150),
        },
        as_of=today,
        user_id=owner,
    )
    session.get(Vendor, electrical.vendor_id).pan = "BQRPR2231K"
    session.commit()
    for n, (back, value) in enumerate(((95, "3850000"), (60, "4120000"), (25, "3640000"))):
        ra = contractors.add_running_bill(
            session,
            hb,
            civil,
            {
                "work_value": value,
                "gst": str(Decimal(value) * Decimal("0.18")),
                "period_to": today - timedelta(days=back),
            },
            as_of=today,
            user_id=accounts,
        )
        bill = session.get(Bill, ra.bill_id)
        if n == 0:
            contractors.pay(
                session,
                bill,
                {"paid_on": today - timedelta(days=back - 12), "reference": "NEFT DEMO7731"},
                as_of=today,
                user_id=owner,
                approver=True,
            )
        elif n == 1:
            contractors.approve(session, bill, user_id=owner)
    for back, value in ((40, "620000"), (12, "540000")):
        contractors.add_running_bill(
            session,
            sg,
            electrical,
            {
                "work_value": value,
                "gst": str(Decimal(value) * Decimal("0.18")),
                "period_to": today - timedelta(days=back),
            },
            as_of=today,
            user_id=accounts,
        )
    # One supplier's bill held, with a reason.
    held = session.scalars(
        select(Bill)
        .where(Bill.project_id == wf.id, Bill.paid_on.is_(None), Bill.excluded.is_(False))
        .order_by(Bill.bill_date)
    ).first()
    if held is not None:
        contractors.hold(
            session, held, "Quantity on the bill doesn't match the delivery challan.", user_id=owner
        )

    # The site: a week of reports on Hebbal Heights, the material used, and requests.
    for name, unit, level in (
        ("Cement", "bags", "200"),
        ("Steel", "tonnes", "5"),
        ("M-sand", "cubic metres", "20"),
        ("Solid blocks", "nos", "2000"),
    ):
        item = site.item_for(session, hb, name, unit)
        item.min_level = Decimal(level)
    session.commit()
    for name, qty, back in (
        ("Cement", "900", 9),
        ("Steel", "18", 9),
        ("M-sand", "60", 8),
        ("Solid blocks", "6000", 7),
    ):
        site.received(
            session,
            hb,
            {
                "item": name,
                "quantity": qty,
                "on": today - timedelta(days=back),
                "note": "Opening stock",
            },
            as_of=today,
            user_id=site_user,
        )
    day, n = today - timedelta(days=1), 0
    while n < 5:
        if day.weekday() != 6:
            site.save_report(
                session,
                storage,
                hb,
                {
                    "on": day,
                    "work_done": WORK[n],
                    "workers": str(rng.randint(38, 64)),
                    "issues": ISSUES[n],
                    "used": [
                        {"item": "Cement", "quantity": str(rng.choice((120, 140, 160)))},
                        {"item": "Steel", "quantity": str(rng.choice((2, 3)))},
                        {"item": "M-sand", "quantity": str(rng.choice((8, 10)))},
                    ],
                },
                [],
                as_of=today,
                user_id=site_user,
            )
            n += 1
        day -= timedelta(days=1)
    cement = site.request(
        session,
        hb,
        {
            "item": "Cement",
            "quantity": "500",
            "needed_by": today + timedelta(days=3),
            "note": "For the 10th floor slab",
        },
        as_of=today,
        user_id=site_user,
    )
    for supplier, rate in (
        ("Ultratech dealer, Yelahanka", "385"),
        ("Sri Balaji Traders", "372"),
        ("Ramco Cements depot", "390"),
    ):
        site.add_quote(session, cement, {"supplier": supplier, "rate": rate})
    site.request(
        session,
        hb,
        {"item": "Solid blocks", "quantity": "4000", "needed_by": today + timedelta(days=6)},
        as_of=today,
        user_id=site_user,
    )

    # After handover, on Sarjapur Greens: defects on units handed over, snags on the next ones.
    handed = list(
        session.scalars(
            select(Unit)
            .join(UnitHandover, UnitHandover.unit_id == Unit.id)
            .where(Unit.project_id == sg.id, UnitHandover.possession_on.is_not(None))
            .order_by(Unit.label)
        )
    )
    waiting = list(
        session.scalars(
            select(Unit)
            .join(UnitHandover, UnitHandover.unit_id == Unit.id)
            .where(
                Unit.project_id == sg.id,
                UnitHandover.possession_on.is_(None),
                Unit.booked.is_(True),
            )
            .order_by(Unit.label)
            .limit(3)
        )
    )
    for unit, (title, back) in zip(
        handed,
        (
            ("Seepage under the kitchen sink", 36),
            ("Master bedroom door doesn't close", 9),
            ("Crack in the balcony tiles", 4),
        ),
        strict=False,
    ):
        aftercare.add(
            session,
            sg,
            {
                "unit_id": unit.id,
                "kind": "defect",
                "title": title,
                "reported_on": today - timedelta(days=back),
            },
            as_of=today,
            user_id=sales_user,
        )
    for unit, title in zip(
        waiting,
        ("Paint touch-up in the living room", "Bathroom tap leaking", "Window handle missing"),
        strict=False,
    ):
        aftercare.add(
            session,
            sg,
            {"unit_id": unit.id, "kind": "snag", "title": title},
            as_of=today,
            user_id=site_user,
        )
    if handed:
        aftercare.add(
            session,
            sg,
            {
                "unit_id": handed[0].id,
                "kind": "request",
                "title": "Copy of the occupancy certificate",
                "detail": "Needed for the home loan bank.",
            },
            as_of=today,
            user_id=sales_user,
        )

    # A construction loan on Hebbal Heights.
    loan = lending.add_loan(
        session,
        hb,
        {
            "lender": "Canara Bank, MG Road",
            "sanctioned": "40 crore",
            "rate_pct": "10.75",
            "sanctioned_on": today - timedelta(days=300),
        },
    )
    for back, amount in ((280, "8 crore"), (170, "6 crore"), (60, "5 crore")):
        lending.add_move(
            session,
            loan,
            {"kind": "drawdown", "amount": amount, "on": today - timedelta(days=back)},
            as_of=today,
        )
    for back in (90, 60, 30):
        lending.add_move(
            session,
            loan,
            {"kind": "interest", "amount": "1700000", "on": today - timedelta(days=back)},
            as_of=today,
        )
    for ahead in (5, 35, 65):
        lending.add_move(
            session,
            loan,
            {
                "kind": "interest",
                "amount": "1700000",
                "on": today + timedelta(days=ahead),
                "note": "Planned",
            },
            as_of=today,
        )
    lending.add_move(
        session,
        loan,
        {
            "kind": "repayment",
            "amount": "2 crore",
            "on": today + timedelta(days=50),
            "note": "Planned",
        },
        as_of=today,
    )
    c = lending.add_condition(
        session, loan, {"text": "At least 40% of units sold", "due_on": today - timedelta(days=100)}
    )
    lending.meet_condition(session, c, as_of=today - timedelta(days=110))
    lending.add_condition(
        session,
        loan,
        {
            "text": "Architect's progress certificate for the quarter",
            "due_on": today + timedelta(days=10),
        },
    )
    lending.add_condition(
        session,
        loan,
        {"text": "Insurance renewal, contractor's all risk", "due_on": today + timedelta(days=40)},
    )
