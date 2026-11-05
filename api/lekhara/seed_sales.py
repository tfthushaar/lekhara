"""Demo sales: price lists, channel partners, leads at every stage, site visits, holds, and the
bookings behind the demo's recent sales.

Bookings are attached only to units the demo already shows as sold, with the buyer, the price
and the receipts it already has, so nothing else in the demo changes. Uses its own random
numbers, so the rest of the seed comes out the same.
"""

import json
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara import sales
from lekhara.engines.sales import CommissionIn, commission
from lekhara.models import (
    Booking,
    ChannelPartner,
    Commission,
    Lead,
    LeadActivity,
    Organization,
    PriceList,
    Project,
    Receipt,
    SiteVisit,
    Unit,
    UnitHold,
    User,
    utcnow,
)
from lekhara.money import rupees
from lekhara.rules import KARNATAKA

PRICES = {
    "hebbal-heights": dict(base_rate=10400, floor_rise=35, floor_rise_from=2,
                           plc={"Corner": 150, "Park facing": 100}, car_park=350000,
                           amenities=250000, other_charges=185000, corpus_per_sqft=75,
                           maintenance_per_sqft_month="4.5", maintenance_months=12),
    "sarjapur-greens": dict(base_rate=8800, floor_rise=25, floor_rise_from=2,
                            plc={"Corner": 120, "Lake view": 150}, car_park=300000,
                            amenities=200000, other_charges=160000, corpus_per_sqft=60,
                            maintenance_per_sqft_month="4", maintenance_months=12),
    "whitefield-residences": dict(base_rate=9200, floor_rise=30, floor_rise_from=2,
                                  plc={"Corner": 120}, car_park=325000, amenities=225000,
                                  other_charges=175000, corpus_per_sqft=65,
                                  maintenance_per_sqft_month="4", maintenance_months=12),
}  # fmt: skip

PARTNERS = (
    # name, firm, K-RERA number, valid for (days from today; negative has lapsed), rate, GSTIN
    ("Ravi Kumar", "Square Feet Realty", "PRM/KA/RERA/1251/309/AG/DEMO/001", 900, "2", True),
    ("Meena Joshi", "Homeseekers Bangalore", "PRM/KA/RERA/1251/446/AG/DEMO/002", 1400, "1.5",
     True),
    ("Arif Khan", "", "PRM/KA/RERA/1251/310/AG/DEMO/003", 320, "2", False),
    ("Lakshmi Prasad", "North Bangalore Properties", "PRM/KA/RERA/1251/309/AG/DEMO/004", -25, "2",
     True),
)  # fmt: skip

FIRST = ("Rahul", "Divya", "Kiran", "Sneha", "Ajay", "Pooja", "Vivek", "Ananya", "Manoj",
         "Shruti", "Rohit", "Kavya", "Naveen", "Swathi", "Prakash", "Bhavana", "Sunil", "Rekha",
         "Abhishek", "Deepa", "Varun", "Meghana", "Girish", "Sowmya")  # fmt: skip
LAST = ("Srinivasan", "Chandra", "Venkatesh", "Ramesh", "Hosamani", "Bhandari", "Upadhya",
        "Acharya", "Kini", "Mallya", "Shenoy", "Adiga", "Rajan", "Gupta", "Agarwal",
        "Verma")  # fmt: skip

INTEREST = ("2 BHK", "3 BHK", "3 BHK, high floor", "2 BHK, park facing", "3 BHK, corner",
            "2 BHK, ready by 2028")  # fmt: skip
CALLS = (
    "Called. Wants to see the sample flat this weekend.",
    "Called. Asked about the payment plan and the bank tie-ups.",
    "Sent the brochure and the floor plans on WhatsApp.",
    "Called back. Comparing with two projects in Yelahanka.",
    "Shared the cost sheet for a 3 BHK on the fifth floor.",
    "Spoke to the spouse as well. Budget is the worry; asked about a smaller unit.",
    "Asked whether the home loan can be from SBI. Said yes, the project is approved.",
    "Wants to know the possession date in writing.",
)  # fmt: skip
FEEDBACK = (
    "Liked the layout and the ventilation. Wants to bring the parents next.",
    "Felt the kitchen is small. Asked for the 3 BHK plans.",
    "Very positive. Asked for a hold on a corner unit.",
    "Found the approach road narrow. Will think about it.",
    "Liked the clubhouse plans. Negotiating on the car park price.",
)  # fmt: skip
LOST = ("Bought elsewhere", "Budget too low", "Location too far from office",
        "Not reachable after three calls", "Postponed the purchase")  # fmt: skip

SOURCE_MIX = ("99acres", "99acres", "magicbricks", "housing", "nobroker", "website", "facebook",
              "facebook", "google", "whatsapp", "walk_in", "referral")  # fmt: skip
STAGE_MIX = ("new", "new", "contacted", "contacted", "contacted", "visit_planned", "visited",
             "visited", "negotiating", "lost", "lost")  # fmt: skip


def _at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour % 24, 15))


def seed_sales(
    session: Session, org: Organization, projects: list[Project], users: dict[str, User],
    today: date,
) -> None:  # fmt: skip
    rng = random.Random(31)
    team = [users[e].id for e in ("promoter@demo.lekhara", "cfo@demo.lekhara",
                                  "accounts@demo.lekhara") if e in users]  # fmt: skip
    by_id = {p.id: p for p in projects}

    for pid, prices in PRICES.items():
        if pid not in by_id:
            continue
        session.add(PriceList(
            project_id=pid,
            base_rate=Decimal(prices["base_rate"]),
            floor_rise=Decimal(prices["floor_rise"]),
            floor_rise_from=prices["floor_rise_from"],
            plc=json.dumps({k: str(v) for k, v in prices["plc"].items()}),
            car_park=Decimal(prices["car_park"]),
            amenities=Decimal(prices["amenities"]),
            other_charges=Decimal(prices["other_charges"]),
            corpus_per_sqft=Decimal(prices["corpus_per_sqft"]),
            maintenance_per_sqft_month=Decimal(prices["maintenance_per_sqft_month"]),
            maintenance_months=prices["maintenance_months"],
            updated_at=_at(today - timedelta(days=40), 11),
            updated_by=team[0] if team else None,
        ))  # fmt: skip

    partners = []
    for i, (name, firm, number, days, rate, gst) in enumerate(PARTNERS):
        p = ChannelPartner(
            organization_id=org.id, name=name, firm=firm or None,
            phone=f"+91 98860 4{i:04d}", email=f"{name.split()[0].lower()}@partners.example",
            krera_number=number, krera_valid_until=today + timedelta(days=days),
            commission_pct=Decimal(rate), payable_after_pct=Decimal("10"),
            gstin=_gstin(i) if gst else None, pan=f"ABCPK{1234 + i}{'FGHJ'[i]}",
        )  # fmt: skip
        session.add(p)
        partners.append(p)
    session.flush()

    order = ["hebbal-heights", "hebbal-heights", "sarjapur-greens", "whitefield-residences"]
    n = 0
    for project_id in order * 9:
        project = by_id.get(project_id)
        if project is None:
            continue
        n += 1
        source = rng.choice(SOURCE_MIX)
        partner = None
        if n % 7 == 0:
            source = "partner"
            partner = partners[n % 3]
        stage = rng.choice(STAGE_MIX)
        created = today - timedelta(days=rng.randint(2, 85))
        name = f"{FIRST[n % len(FIRST)]} {LAST[(n * 5) % len(LAST)]}"
        lead = Lead(
            organization_id=org.id, project_id=project.id, name=name,
            phone=f"+91 99000 1{n:04d}", phone_key=f"990001{n:04d}",
            email=f"{name.split()[0].lower()}{n}@mail.example" if n % 3 else None,
            source=source, partner_id=partner.id if partner else None,
            interest=rng.choice(INTEREST),
            budget=Decimal(rng.choice([95, 110, 125, 140, 160, 185])) * 100000,
            stage=stage, owner_user_id=team[n % len(team)] if team else None,
            created_on=created,
            lost_reason=rng.choice(LOST) if stage == "lost" else None,
        )  # fmt: skip
        if stage in sales.OPEN_STAGES:
            # Some follow-ups are late, so the list has something to chase.
            lead.next_follow_up_on = today + timedelta(days=rng.randint(-6, 7))
        session.add(lead)
        session.flush()
        session.add(LeadActivity(lead_id=lead.id, at=_at(created, 10), kind="note",
                                 detail=f"Came from {sales.SOURCES[source]}.",
                                 user_id=lead.owner_user_id))  # fmt: skip
        if stage == "new":
            continue
        for k in range(rng.randint(1, 3)):
            day = min(created + timedelta(days=1 + k * 3), today)
            session.add(LeadActivity(lead_id=lead.id, at=_at(day, 11 + k),
                                     kind=rng.choice(["call", "call", "whatsapp", "email"]),
                                     detail=rng.choice(CALLS),
                                     user_id=lead.owner_user_id))  # fmt: skip
        if stage in ("visit_planned",):
            day = today + timedelta(days=rng.randint(0, 5))
            session.add(SiteVisit(lead_id=lead.id, project_id=project.id, on=day,
                                  time=rng.choice(["10:30", "11:00", "15:00", "16:30"]),
                                  user_id=lead.owner_user_id))  # fmt: skip
        if stage in ("visited", "negotiating", "lost") and rng.random() < 0.8:
            day = min(created + timedelta(days=rng.randint(4, 12)), today - timedelta(days=1))
            feedback = rng.choice(FEEDBACK)
            session.add(SiteVisit(lead_id=lead.id, project_id=project.id, on=day, time="11:00",
                                  status="done", feedback=feedback,
                                  user_id=lead.owner_user_id))  # fmt: skip
            session.add(LeadActivity(lead_id=lead.id, at=_at(day, 13), kind="visit",
                                     detail=f"Visit on {day:%d %b %Y}: Done. {feedback}",
                                     user_id=lead.owner_user_id))  # fmt: skip
        if stage == "lost":
            session.add(LeadActivity(lead_id=lead.id, at=_at(today - timedelta(days=2), 17),
                                     kind="stage", detail="Negotiating to Lost.",
                                     user_id=lead.owner_user_id))  # fmt: skip
    session.flush()
    _holds(session, org, by_id, today)
    _bookings(session, org, by_id, partners, team, today, rng)


def _gstin(i: int) -> str:
    from lekhara.accounts import gstin_with_check

    return gstin_with_check(f"29ABCPK{1234 + i}{'FGHJ'[i]}1Z")


def _holds(session: Session, org: Organization, by_id: dict, today: date) -> None:
    """Two buyers deciding on Hebbal Heights units, each held for 48 hours."""
    project = by_id.get("hebbal-heights")
    if project is None:
        return
    negotiating = list(session.scalars(
        select(Lead).where(Lead.organization_id == org.id, Lead.project_id == project.id,
                           Lead.stage.in_(("visited", "negotiating"))).order_by(Lead.created_on)
    ))[:2]  # fmt: skip
    free = list(session.scalars(
        select(Unit).where(Unit.project_id == project.id, Unit.booked.is_(False),
                           Unit.owner_share == "developer").order_by(Unit.label.desc())
    ))[:2]  # fmt: skip
    hours = KARNATAKA.value("sales.hold_hours", today)
    for lead, unit, left in zip(negotiating, free, (hours - 6, 20), strict=False):
        lead.stage = "negotiating"
        session.add(UnitHold(unit_id=unit.id, lead_id=lead.id, user_id=lead.owner_user_id,
                             until=utcnow() + timedelta(hours=left)))  # fmt: skip
        session.add(LeadActivity(lead_id=lead.id, at=_at(today, 12), kind="note",
                                 detail=f"Unit {unit.label} held for {hours} hours.",
                                 user_id=lead.owner_user_id))  # fmt: skip


def _bookings(
    session: Session, org: Organization, by_id: dict, partners: list, team: list, today: date,
    rng: random.Random,
) -> None:  # fmt: skip
    """The leads behind the demo's sales of the last four months, booked through the sales
    desk, a few through channel partners."""
    n = 0
    for project_id in ("hebbal-heights", "sarjapur-greens", "whitefield-residences"):
        project = by_id.get(project_id)
        if project is None:
            continue
        units = list(session.scalars(
            select(Unit).where(Unit.project_id == project.id, Unit.booked.is_(True),
                               Unit.booked_on >= today - timedelta(days=120))
            .order_by(Unit.booked_on)
        ))  # fmt: skip
        for unit in units:
            n += 1
            receipt = session.scalars(
                select(Receipt).where(Receipt.unit_id == unit.id).order_by(Receipt.received_on)
            ).first()
            if receipt is None or unit.agreement_value is None:
                continue
            partner = partners[n % 3] if n % 3 == 1 else None
            if partner is not None and partner.krera_valid_until < unit.booked_on:
                partner = None
            created = unit.booked_on - timedelta(days=rng.randint(12, 40))
            lead = Lead(
                organization_id=org.id, project_id=project.id, name=unit.buyer_name,
                phone=f"+91 99000 2{n:04d}", phone_key=f"990002{n:04d}",
                source="partner" if partner else rng.choice(SOURCE_MIX),
                partner_id=partner.id if partner else None, interest=unit.label,
                stage="booked", owner_user_id=team[n % len(team)] if team else None,
                unit_id=unit.id, created_on=created,
            )  # fmt: skip
            session.add(lead)
            session.flush()
            visit_day = created + timedelta(days=5)
            session.add(SiteVisit(lead_id=lead.id, project_id=project.id, on=visit_day,
                                  time="11:00", status="done",
                                  feedback="Liked the unit. Asked for the cost sheet.",
                                  user_id=lead.owner_user_id))  # fmt: skip
            for at, kind, detail in (
                (_at(created, 10), "note", f"Came from {sales.SOURCES[lead.source]}."),
                (_at(visit_day, 13), "visit", f"Visit on {visit_day:%d %b %Y}: Done."),
                (_at(unit.booked_on, 16), "stage",
                 f"Booked unit {unit.label} at {unit.agreement_value:,.0f}."),
            ):  # fmt: skip
                session.add(LeadActivity(lead_id=lead.id, at=at, kind=kind, detail=detail,
                                         user_id=lead.owner_user_id))  # fmt: skip
            booking = Booking(
                project_id=project.id, unit_id=unit.id, lead_id=lead.id,
                partner_id=partner.id if partner else None, booked_on=unit.booked_on,
                buyer_name=unit.buyer_name, buyer_pan=f"AB{'CDEFGH'[n % 6]}PS{4000 + n}K",
                agreement_value=unit.agreement_value,
                cost_sheet=json.dumps(_sheet(project, unit, today)),
                booking_amount=receipt.amount, receipt_id=receipt.id, created_by=team[0],
            )  # fmt: skip
            session.add(booking)
            session.flush()
            if partner is None:
                continue
            c = commission(
                CommissionIn(unit.agreement_value, partner.commission_pct, bool(partner.gstin),
                             Decimal(0)),
                on=unit.booked_on, rules=KARNATAKA,
            )  # fmt: skip
            row = Commission(organization_id=org.id, partner_id=partner.id,
                             booking_id=booking.id, rate_pct=partner.commission_pct,
                             amount=c.amount, gst=c.gst, tds=c.tds)  # fmt: skip
            if n % 2 and unit.booked_on < today - timedelta(days=60):
                row.paid_on = unit.booked_on + timedelta(days=35)
                row.paid_by = team[0]
                row.reference = f"NEFT DEMO{4100 + n}"
            session.add(row)


def _sheet(project: Project, unit: Unit, today: date) -> dict:
    """The cost sheet for a demo sale, at the price the unit sold for."""
    gst_rate = KARNATAKA.value(
        {"affordable_1pc": "gst.rate.affordable", "commercial_12pc": "gst.rate.commercial"}.get(
            project.gst_regime, "gst.rate.residential"
        ),
        unit.booked_on,
    )
    value = unit.agreement_value
    return {
        "unit": unit.label,
        "carpet_area_sqft": unit.carpet_area_sqft,
        "agreement_lines": [
            {
                "label": "Basic price",
                "amount": f"{value:.2f}",
                "detail": f"{unit.carpet_area_sqft} sq ft, with car park and amenities",
            }
        ],  # fmt: skip
        "agreement_value": f"{value:.2f}",
        "rate_per_sqft": f"{rupees(value / unit.carpet_area_sqft):.2f}",
        "gst_rate": f"{gst_rate * 100:.0f}",
        "gst": f"{rupees(value * gst_rate):.2f}",
        "handover_lines": [],
    }
