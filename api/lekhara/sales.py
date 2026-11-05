"""Sales, from the first enquiry to a booked unit, for firms with no CRM of their own.

- Leads come from the property portals, ads, WhatsApp, walk-ins, referrals and channel partners.
  The same person coming again from another source is the same lead, matched on the last ten
  digits of their phone number; the new source is noted against it.
- Each lead has one history of calls, messages and visits, and the next day to call. People
  record what happened; the lead's stage and its next follow-up move by themselves.
- Site visits are planned, then marked done (with what the buyer said), missed or called off.
- A unit can be held for a buyer who is deciding, for the hours the rules pack sets (48).
- Each project has a price list; any unit's cost sheet is worked out from it
  (engines.sales.cost_sheet), with a warning when the price falls below the guidance value.
- Booking makes the lead the unit's buyer: the unit is marked sold at the agreed value, the
  booking amount is the buyer's first receipt, and an allotment letter is ready to print. The
  project's payment plan then raises the demands, as for any other booking.
- A booking through a channel partner earns them a commission, but only while their K-RERA
  registration is valid. It falls due once the buyer has paid the share of the agreement value
  the partner's terms set, and is then marked paid.
"""

import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara import registers
from lekhara.engines.sales import (
    CommissionIn,
    PriceListIn,
    commission,
    commission_due,
    cost_sheet,
)
from lekhara.engines.tax import financial_year
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
from lekhara.money import ZERO, rupees
from lekhara.pdf import HEADING, write_pdf
from lekhara.rules import KARNATAKA, RulesPack
from lekhara.services import ServiceError

STAGES = {
    "new": "New",
    "contacted": "Contacted",
    "visit_planned": "Visit planned",
    "visited": "Visited",
    "negotiating": "Negotiating",
    "booked": "Booked",
    "lost": "Lost",
}
OPEN_STAGES = ("new", "contacted", "visit_planned", "visited", "negotiating")
SOURCES = {
    "99acres": "99acres",
    "magicbricks": "MagicBricks",
    "housing": "Housing.com",
    "nobroker": "NoBroker",
    "website": "Your website",
    "facebook": "Facebook or Instagram",
    "google": "Google",
    "whatsapp": "WhatsApp",
    "walk_in": "Walk-in",
    "referral": "Referral",
    "partner": "Channel partner",
    "other": "Other",
}
ACTIVITY = {
    "call": "Call",
    "whatsapp": "WhatsApp",
    "email": "Email",
    "meeting": "Meeting",
    "note": "Note",
    "visit": "Site visit",
    "stage": "Stage",
}
CALL_AGAIN_DAYS = 3
"""When a call is logged with no next date, the lead comes back this many days later."""
VISITS = {"planned": "Planned", "done": "Done", "no_show": "Didn't come", "cancelled": "Called off"}
_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def _now() -> datetime:
    return utcnow()


def phone_key(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else None


def _amount(value, label: str) -> Decimal | None:
    text = str(value if value is not None else "").replace(",", "").replace("₹", "").strip()
    if not text:
        return None
    lakh = re.fullmatch(r"([\d.]+)\s*(lakh|lac|l)", text, re.I)
    crore = re.fullmatch(r"([\d.]+)\s*(crore|cr)", text, re.I)
    try:
        if lakh:
            amount = Decimal(lakh.group(1)) * 100000
        elif crore:
            amount = Decimal(crore.group(1)) * 10000000
        else:
            amount = Decimal(text)
    except InvalidOperation:
        raise ServiceError(f"{label} is not an amount.") from None
    if amount < 0:
        raise ServiceError(f"{label} cannot be below zero.")
    return rupees(amount)


def _date(value, label: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ServiceError(f"{label} is not a date.") from None


# Leads


def _lead(session: Session, org: Organization, lead_id: str) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None or lead.organization_id != org.id:
        raise ServiceError("Lead not found.", 404)
    return lead


def get_lead(session: Session, lead_id: str) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise ServiceError("Lead not found.", 404)
    return lead


def note(session: Session, lead: Lead, kind: str, detail: str, user_id: str | None) -> None:
    session.add(LeadActivity(lead_id=lead.id, kind=kind, detail=detail[:2000], user_id=user_id))


def source_from(text: str | None) -> str:
    """Where a lead came from, as a portal or an ad export writes it."""
    t = re.sub(r"[^a-z0-9]", "", (text or "").lower())
    for needle, source in (
        ("99acres", "99acres"), ("magicbricks", "magicbricks"), ("housing", "housing"),
        ("nobroker", "nobroker"), ("facebook", "facebook"), ("instagram", "facebook"),
        ("fb", "facebook"), ("ig", "facebook"), ("meta", "facebook"), ("google", "google"),
        ("adwords", "google"), ("whatsapp", "whatsapp"), ("walk", "walk_in"),
        ("referr", "referral"), ("refer", "referral"), ("website", "website"), ("web", "website"),
        ("channelpartner", "partner"), ("broker", "partner"),
    ):  # fmt: skip
        if needle == t or (len(needle) > 3 and needle in t):
            return source
    return t if t in SOURCES else "other"


def add_lead(
    session: Session, org: Organization, fields: dict, *, as_of: date, user_id: str | None,
    commit: bool = True,
) -> tuple[Lead, bool]:  # fmt: skip
    """A new lead, or the existing one for the same phone number. Returns the lead and whether
    it is new."""
    name = (fields.get("name") or "").strip()
    phone = (fields.get("phone") or "").strip()
    email = (fields.get("email") or "").strip().lower() or None
    source = fields.get("source") or "other"
    if not name:
        raise ServiceError("Enter the person's name.")
    if source not in SOURCES:
        raise ServiceError("Choose where the lead came from.")
    key = phone_key(phone)
    if phone and key is None:
        raise ServiceError("Enter the phone number with all ten digits.")
    if key is None and email is None:
        raise ServiceError("Enter a phone number or an email, so you can reach them.")
    project_id = fields.get("project_id") or None
    if project_id:
        project = session.get(Project, project_id)
        if project is None or project.organization_id != org.id:
            raise ServiceError("Choose one of your projects.")
    partner_id = fields.get("partner_id") or None
    if partner_id:
        partner_for(session, org, partner_id)
        source = "partner"
    if key:
        existing = session.scalars(
            select(Lead).where(Lead.organization_id == org.id, Lead.phone_key == key)
        ).first()
        if existing is not None:
            note(session, existing, "note",
                 f"Came again, from {SOURCES[source]}"
                 + (f", asking about {fields['interest']}" if fields.get("interest") else "")
                 + ".", user_id)  # fmt: skip
            if existing.stage == "lost":
                existing.stage = "new"
                existing.lost_reason = None
            if commit:
                session.commit()
            return existing, False
    lead = Lead(
        organization_id=org.id,
        project_id=project_id,
        name=name[:200],
        phone=phone[:32] or None,
        phone_key=key,
        email=email,
        source=source,
        partner_id=partner_id,
        interest=(fields.get("interest") or "").strip()[:200] or None,
        budget=_amount(fields.get("budget"), "The budget"),
        stage="new",
        owner_user_id=fields.get("owner_user_id") or user_id,
        next_follow_up_on=_date(fields.get("next_follow_up_on"), "The follow-up date") or as_of,
        created_on=_date(fields.get("created_on"), "The date it came in") or as_of,
    )
    session.add(lead)
    session.flush()
    note(session, lead, "note", f"Came from {SOURCES[source]}.", user_id)
    if commit:
        session.commit()
    return lead, True


def update_lead(
    session: Session, lead: Lead, fields: dict, *, as_of: date, user_id: str | None
) -> Lead:
    if "stage" in fields and fields["stage"]:
        stage = fields["stage"]
        if stage not in STAGES or stage == "booked":
            raise ServiceError("Choose a stage. A lead is marked booked when its unit is booked.")
        if lead.stage == "booked":
            raise ServiceError("This lead has booked; its booking is on the unit's page.")
        if stage == "lost" and not (fields.get("lost_reason") or "").strip():
            raise ServiceError("Say why the lead was lost, so the reasons can be counted.")
        if stage != lead.stage:
            note(session, lead, "stage", f"{STAGES[lead.stage]} to {STAGES[stage]}.", user_id)
            if stage == "lost":
                lead.next_follow_up_on = None
            elif lead.stage == "lost":
                lead.next_follow_up_on = as_of
            lead.stage = stage
        lead.lost_reason = (
            (fields.get("lost_reason") or "").strip()[:300] or None if (stage == "lost") else None
        )
    for key in ("interest",):
        if key in fields:
            setattr(lead, key, (fields[key] or "").strip()[:200] or None)
    if "budget" in fields:
        lead.budget = _amount(fields["budget"], "The budget")
    if "next_follow_up_on" in fields:
        lead.next_follow_up_on = _date(fields["next_follow_up_on"], "The follow-up date")
    if fields.get("owner_user_id"):
        lead.owner_user_id = fields["owner_user_id"]
    if "project_id" in fields and fields["project_id"]:
        project = session.get(Project, fields["project_id"])
        if project is None or project.organization_id != lead.organization_id:
            raise ServiceError("Choose one of your projects.")
        lead.project_id = project.id
    session.commit()
    return lead


def log_activity(
    session: Session, lead: Lead, fields: dict, *, as_of: date, user_id: str | None
) -> LeadActivity:
    kind = fields.get("kind") or "note"
    detail = (fields.get("detail") or "").strip()
    if kind not in ACTIVITY or kind in ("stage", "visit"):
        raise ServiceError("Choose a call, a message, a meeting or a note.")
    if not detail:
        raise ServiceError("Write what was said or done.")
    row = LeadActivity(lead_id=lead.id, kind=kind, detail=detail[:2000], user_id=user_id)
    session.add(row)
    if lead.stage == "new" and kind in ("call", "whatsapp", "email", "meeting"):
        lead.stage = "contacted"
    lead.next_follow_up_on = _date(
        fields.get("next_follow_up_on"), "The follow-up date"
    ) or as_of + timedelta(days=CALL_AGAIN_DAYS)
    session.commit()
    return row


# Site visits


def plan_visit(
    session: Session, lead: Lead, fields: dict, *, as_of: date, user_id: str | None
) -> SiteVisit:
    on = _date(fields.get("on"), "The visit date")
    if on is None:
        raise ServiceError("Choose the day of the visit.")
    project_id = fields.get("project_id") or lead.project_id
    project = session.get(Project, project_id) if project_id else None
    if project is None or project.organization_id != lead.organization_id:
        raise ServiceError("Choose which project they will visit.")
    visit = SiteVisit(
        lead_id=lead.id,
        project_id=project.id,
        on=on,
        time=(fields.get("time") or "").strip()[:16] or None,
        user_id=user_id,
    )
    session.add(visit)
    lead.project_id = lead.project_id or project.id
    if lead.stage in ("new", "contacted"):
        lead.stage = "visit_planned"
    lead.next_follow_up_on = on
    note(session, lead, "visit", f"Visit to {project.name} planned for {on:%d %b %Y}.", user_id)
    session.commit()
    return visit


def record_visit(
    session: Session, visit: SiteVisit, fields: dict, *, as_of: date, user_id: str | None
) -> SiteVisit:
    status = fields.get("status")
    if status not in ("done", "no_show", "cancelled"):
        raise ServiceError("Say whether they came.")
    visit.status = status
    visit.feedback = (fields.get("feedback") or "").strip()[:2000] or None
    lead = session.get(Lead, visit.lead_id)
    if status == "done":
        if lead.stage in ("new", "contacted", "visit_planned"):
            lead.stage = "visited"
        lead.next_follow_up_on = as_of + timedelta(days=2)
    elif lead.stage == "visit_planned":
        lead.stage = "contacted"
        lead.next_follow_up_on = as_of + timedelta(days=1)
    note(session, lead, "visit", f"Visit on {visit.on:%d %b %Y}: {VISITS[status]}."
         + (f" {visit.feedback}" if visit.feedback else ""), user_id)  # fmt: skip
    session.commit()
    return visit


# Holds


def active_hold(session: Session, unit: Unit) -> UnitHold | None:
    return session.scalars(
        select(UnitHold).where(
            UnitHold.unit_id == unit.id, UnitHold.released_at.is_(None), UnitHold.until > _now()
        )
    ).first()


def hold_unit(
    session: Session, lead: Lead, unit: Unit, *, as_of: date, user_id: str | None,
    rules: RulesPack = KARNATAKA,
) -> UnitHold:  # fmt: skip
    project = session.get(Project, unit.project_id)
    if project.organization_id != lead.organization_id:
        raise ServiceError("Unit not found.", 404)
    if unit.booked:
        raise ServiceError(f"Unit {unit.label} is sold.")
    if unit.owner_share == "landowner":
        raise ServiceError(f"Unit {unit.label} is the landowner's to sell.")
    hold = active_hold(session, unit)
    if hold is not None and hold.lead_id != lead.id:
        other = session.get(Lead, hold.lead_id)
        raise ServiceError(f"Unit {unit.label} is held for {other.name} until "
                           f"{hold.until:%d %b, %H:%M} UTC.")  # fmt: skip
    hours = rules.value("sales.hold_hours", as_of)
    if hold is None:
        hold = UnitHold(unit_id=unit.id, lead_id=lead.id, user_id=user_id, until=_now())
        session.add(hold)
    hold.until = _now() + timedelta(hours=hours)
    if lead.stage in OPEN_STAGES[:4]:
        lead.stage = "negotiating"
    lead.next_follow_up_on = as_of + timedelta(days=2)
    note(session, lead, "note", f"Unit {unit.label} held for {hours} hours.", user_id)
    session.commit()
    return hold


def release_hold(session: Session, hold: UnitHold, *, user_id: str | None) -> None:
    hold.released_at = _now()
    note(session, session.get(Lead, hold.lead_id), "note",
         f"Hold on unit {session.get(Unit, hold.unit_id).label} released.", user_id)  # fmt: skip
    session.commit()


# Prices and cost sheets


def price_list(session: Session, project: Project) -> PriceList | None:
    return session.scalars(select(PriceList).where(PriceList.project_id == project.id)).first()


def prices_in(row: PriceList) -> PriceListIn:
    return PriceListIn(
        base_rate=row.base_rate,
        floor_rise=row.floor_rise,
        floor_rise_from=row.floor_rise_from,
        plc={k: Decimal(v) for k, v in json.loads(row.plc or "{}").items()},
        car_park=row.car_park,
        amenities=row.amenities,
        other_charges=row.other_charges,
        corpus_per_sqft=row.corpus_per_sqft,
        maintenance_per_sqft_month=row.maintenance_per_sqft_month,
        maintenance_months=row.maintenance_months,
    )


def set_price_list(
    session: Session, project: Project, fields: dict, *, user_id: str | None
) -> PriceList:
    base = _amount(fields.get("base_rate"), "The base rate")
    if not base:
        raise ServiceError("Enter the base rate per square foot.")
    plc: dict[str, str] = {}
    for line in str(fields.get("plc") or "").splitlines():
        if not line.strip():
            continue
        name, _, rate = line.rpartition(":")
        if not name.strip() or _amount(rate, f"The charge for {name.strip()}") is None:
            raise ServiceError("Write each location charge as a name, a colon and the rate a sq "
                               "ft, one to a line: Corner: 100")  # fmt: skip
        plc[name.strip()[:60]] = str(_amount(rate, name))
    row = price_list(session, project) or PriceList(project_id=project.id, base_rate=base)
    row.base_rate = base
    row.floor_rise = _amount(fields.get("floor_rise"), "The floor rise") or ZERO
    row.floor_rise_from = int(fields.get("floor_rise_from") or 1)
    row.plc = json.dumps(plc)
    for key, label in (("car_park", "The car park price"), ("amenities", "The amenities charge"),
                       ("other_charges", "The other charges"), ("corpus_per_sqft", "The corpus"),
                       ("maintenance_per_sqft_month", "The maintenance")):  # fmt: skip
        setattr(row, key, _amount(fields.get(key), label) or ZERO)
    row.maintenance_months = int(fields.get("maintenance_months") or 0)
    row.updated_at = _now()
    row.updated_by = user_id
    session.add(row)
    session.commit()
    return row


def sheet_for(
    session: Session, project: Project, unit: Unit, *, plc=(), discount=None, as_of: date,
    rules: RulesPack = KARNATAKA,
):  # fmt: skip
    row = price_list(session, project)
    if row is None:
        raise ServiceError("Set this project's price list first, on the Sales tab.")
    return cost_sheet(
        unit_label=unit.label,
        carpet_area_sqft=unit.carpet_area_sqft,
        guidance_value=unit.guidance_value,
        prices=prices_in(row),
        gst_regime=project.gst_regime,
        plc=list(plc),
        discount_per_sqft=_amount(discount, "The discount") or ZERO,
        on=as_of,
        rules=rules,
    )


def sheet_json(sheet) -> dict:
    def m(value: Decimal) -> str:
        return f"{value:.2f}"

    return {
        "unit": sheet.unit_label,
        "carpet_area_sqft": sheet.carpet_area_sqft,
        "agreement_lines": [
            {"label": x.label, "amount": m(x.amount), "detail": x.detail}
            for x in sheet.agreement_lines
        ],
        "agreement_value": m(sheet.agreement_value),
        "rate_per_sqft": m(sheet.rate_per_sqft),
        "gst_rate": f"{sheet.gst_rate * 100:.0f}",
        "gst": m(sheet.gst),
        "handover_lines": [
            {"label": x.label, "amount": m(x.amount), "detail": x.detail}
            for x in sheet.handover_lines
        ],
        "stamp_duty": m(sheet.registration.stamp_duty),
        "cess": m(sheet.registration.cess),
        "registration_fee": m(sheet.registration.registration_fee),
        "agreement_stamp_duty": m(sheet.agreement_stamp_duty),
        "total": m(sheet.total),
        "tds_rate": f"{sheet.tds_rate * 100:.0f}",
        "tds": m(sheet.tds),
        "guidance_value": m(sheet.guidance_value),
        "below_guidance": sheet.below_guidance,
        "guidance_gap": m(sheet.guidance_gap),
        "guidance_tax": m(sheet.guidance_tax),
    }


# Booking


def book(
    session: Session, lead: Lead, unit: Unit, fields: dict, *, as_of: date, user_id: str | None,
    rules: RulesPack = KARNATAKA,
) -> Booking:  # fmt: skip
    project = session.get(Project, unit.project_id)
    if project.organization_id != lead.organization_id:
        raise ServiceError("Unit not found.", 404)
    if lead.stage == "booked":
        raise ServiceError(f"{lead.name} has already booked.")
    if unit.booked:
        raise ServiceError(f"Unit {unit.label} is sold.")
    if unit.owner_share == "landowner":
        raise ServiceError(f"Unit {unit.label} is the landowner's to sell.")
    hold = active_hold(session, unit)
    if hold is not None and hold.lead_id != lead.id:
        raise ServiceError(f"Unit {unit.label} is held for someone else.")
    pan = (fields.get("buyer_pan") or "").strip().upper()
    if pan and not _PAN.match(pan):
        raise ServiceError("A PAN is ten characters, like ABCDE1234F.")
    aadhaar = re.sub(r"\D", "", fields.get("aadhaar_last4") or "")
    if aadhaar and len(aadhaar) != 4:
        raise ServiceError("Enter only the last four digits of the Aadhaar number.")
    booked_on = _date(fields.get("booked_on"), "The booking date") or as_of
    amount = _amount(fields.get("booking_amount"), "The booking amount")
    if not amount:
        raise ServiceError("Enter the booking amount received.")
    sheet = sheet_for(
        session,
        project,
        unit,
        plc=fields.get("plc") or (),
        discount=fields.get("discount_per_sqft"),
        as_of=booked_on,
        rules=rules,
    )
    partner_id = fields.get("partner_id") or lead.partner_id
    partner = None
    if partner_id:
        org = session.get(Organization, lead.organization_id)
        partner = partner_for(session, org, partner_id)
        if partner.krera_valid_until is None or partner.krera_valid_until < booked_on:
            lapsed = (f"lapsed on {partner.krera_valid_until:%d %b %Y}"
                      if partner.krera_valid_until else "is not recorded")  # fmt: skip
            raise ServiceError(
                f"{partner.name}'s K-RERA agent registration {lapsed}, so the booking can't be "
                "credited to them. Record the renewal on their page, or book without a partner."
            )
    unit.booked = True
    unit.buyer_name = lead.name
    unit.buyer_phone = lead.phone
    unit.buyer_email = lead.email
    unit.booked_on = booked_on
    unit.agreement_value = sheet.agreement_value
    receipt = registers.create_receipt(
        session, project, unit,
        {"amount": amount, "received_on": booked_on,
         "reference": (fields.get("reference") or "Booking amount")[:200]},
        user_id=user_id,
    )  # fmt: skip
    booking = Booking(
        project_id=project.id,
        unit_id=unit.id,
        lead_id=lead.id,
        partner_id=partner.id if partner else None,
        booked_on=booked_on,
        buyer_name=lead.name,
        buyer_pan=pan or None,
        aadhaar_last4=aadhaar or None,
        buyer_address=(fields.get("buyer_address") or "").strip()[:1000] or None,
        agreement_value=sheet.agreement_value,
        cost_sheet=json.dumps(sheet_json(sheet)),
        booking_amount=amount,
        receipt_id=receipt.id,
        created_by=user_id,
    )
    session.add(booking)
    session.flush()
    if partner is not None:
        start, end = financial_year(booked_on)
        paid_this_year = session.scalar(
            select(func.coalesce(func.sum(Commission.amount), 0)).where(
                Commission.partner_id == partner.id,
                Commission.paid_on.between(start, end),
            )
        )
        c = commission(
            CommissionIn(sheet.agreement_value, partner.commission_pct, bool(partner.gstin),
                         Decimal(paid_this_year or 0)),
            on=booked_on, rules=rules,
        )  # fmt: skip
        session.add(Commission(organization_id=lead.organization_id, partner_id=partner.id,
                               booking_id=booking.id, rate_pct=partner.commission_pct,
                               amount=c.amount, gst=c.gst, tds=c.tds))  # fmt: skip
    if hold is not None:
        hold.released_at = _now()
    lead.stage = "booked"
    lead.unit_id = unit.id
    lead.project_id = project.id
    lead.next_follow_up_on = None
    note(session, lead, "stage", f"Booked unit {unit.label} at {sheet.agreement_value:,.0f}.",
         user_id)  # fmt: skip
    session.commit()
    return booking


def booking_for_unit(session: Session, unit: Unit) -> Booking | None:
    return session.scalars(
        select(Booking).where(Booking.unit_id == unit.id).order_by(Booking.created_at.desc())
    ).first()


def cost_sheet_pdf(sheet, *, project: Project, unit: Unit, org: Organization, as_of: date) -> bytes:
    """The cost sheet to hand a buyer: what the unit costs, what is paid at handover, and what
    they pay the government at registration."""
    from lekhara.packs import rupees as inr
    from lekhara.packs import when

    lines = [
        f"{HEADING}Cost sheet: {project.name}, unit {unit.label}",
        f"{org.legal_name or org.name}. Prepared on {when(as_of)}; "
        "prices can change until booking.",
        f"{unit.tower}, carpet area {sheet.carpet_area_sqft} sq ft. "
        f"K-RERA registration {project.krera_registration}.",
        "",
        f"{HEADING}The unit",
    ]
    for line in sheet.agreement_lines:
        detail = f" ({line.detail})" if line.detail else ""
        lines.append(f"{line.label}{detail}: {inr(line.amount)}")
    lines += [
        f"Agreement value: {inr(sheet.agreement_value)}, "
        f"or {inr(sheet.rate_per_sqft)} a sq ft of carpet area",
        f"GST at {sheet.gst_rate * 100:.0f}%: {inr(sheet.gst)}",
    ]
    if sheet.handover_lines:
        lines += ["", f"{HEADING}Paid at handover"]
        for line in sheet.handover_lines:
            detail = f" ({line.detail})" if line.detail else ""
            lines.append(f"{line.label}{detail}: {inr(line.amount)}")
    reg = sheet.registration
    lines += [
        "",
        f"{HEADING}Paid to the government",
        f"Stamp duty on the agreement for sale: {inr(sheet.agreement_stamp_duty)}",
        f"Stamp duty on the sale deed: {inr(reg.stamp_duty)}",
        f"Cess: {inr(reg.cess)}",
        f"Registration fee: {inr(reg.registration_fee)}",
        "",
        f"{HEADING}All in: {inr(sheet.total)}",
    ]
    if sheet.tds > 0:
        lines += [
            "",
            f"You deduct TDS of {sheet.tds_rate * 100:.0f}% ({inr(sheet.tds)} in all) from what "
            "you pay us, deposit it with the tax department, and send us Form 16B.",
        ]
    lines += [
        "",
        "Stamp duty and the registration fee are estimates at today's rates and the guidance "
        "value; the sub-registrar's figure on the day is final.",
    ]
    return write_pdf([lines], title=f"Cost sheet, {project.name} {unit.label}")


def allotment_letter(session: Session, booking: Booking) -> bytes:
    from lekhara.packs import rupees as inr
    from lekhara.packs import when

    project = session.get(Project, booking.project_id)
    unit = session.get(Unit, booking.unit_id)
    org = session.get(Organization, project.organization_id)
    sheet = json.loads(booking.cost_sheet or "{}")
    firm = org.legal_name or org.name
    lines = [
        f"{HEADING}Allotment letter",
        f"{firm}",
        f"Date: {when(booking.booked_on)}",
        "",
        f"To: {booking.buyer_name}",
        *([booking.buyer_address] if booking.buyer_address else []),
        "",
        f"We are pleased to allot you unit {unit.label}, {unit.tower}, in {project.name}, "
        f"K-RERA registration {project.krera_registration}, with a carpet area of "
        f"{unit.carpet_area_sqft} sq ft.",
        "",
        f"{HEADING}What you pay",
    ]
    for line in sheet.get("agreement_lines", []):
        lines.append(f"{line['label']}: {inr(Decimal(line['amount']))}")
    lines += [
        f"Agreement value: {inr(Decimal(sheet.get('agreement_value', booking.agreement_value)))}",
        f"GST at {sheet.get('gst_rate', '5')}%: {inr(Decimal(sheet.get('gst', '0')))}",
    ]
    for line in sheet.get("handover_lines", []):
        lines.append(f"{line['label']} (at handover): {inr(Decimal(line['amount']))}")
    lines += [
        "",
        f"We have received {inr(booking.booking_amount)} as the booking amount. The rest falls "
        "due by the payment plan in your agreement for sale, and we will write to you as each "
        "stage falls due.",
        "",
        "Stamp duty and the registration fee are paid by you when the sale deed is registered.",
    ]
    if Decimal(sheet.get("tds", "0")) > 0:
        lines.append(
            f"As the price is above the threshold, you deduct TDS at {sheet.get('tds_rate')}% "
            "from each payment, deposit it, and give us the certificate."
        )
    lines += ["", f"For {firm}", "", "Authorised signatory: ______________________________"]
    return write_pdf([lines], title=f"Allotment letter, {project.name} {unit.label}")


# Channel partners and their commission


def partner_for(session: Session, org: Organization, partner_id: str) -> ChannelPartner:
    p = session.get(ChannelPartner, partner_id)
    if p is None or p.organization_id != org.id:
        raise ServiceError("Channel partner not found.", 404)
    return p


def save_partner(
    session: Session, org: Organization, fields: dict, partner: ChannelPartner | None = None
) -> ChannelPartner:
    name = (fields.get("name") or "").strip()
    if not name:
        raise ServiceError("Enter the partner's name.")
    try:
        rate = Decimal(str(fields.get("commission_pct") or "0").strip("% "))
        after = Decimal(str(fields.get("payable_after_pct") or "10").strip("% "))
    except InvalidOperation:
        raise ServiceError("Enter the commission as a percentage, like 2.") from None
    if not 0 < rate <= 10:
        raise ServiceError("Enter the commission as a percentage of the agreement value, "
                           "between 0 and 10.")  # fmt: skip
    if not 0 <= after <= 100:
        raise ServiceError("Enter when it falls due as a share of the agreement value paid.")
    gstin = (fields.get("gstin") or "").strip().upper() or None
    if gstin:
        from lekhara.accounts import check_gstin

        gstin = check_gstin(gstin)
    pan = (fields.get("pan") or "").strip().upper() or None
    if pan and not _PAN.match(pan):
        raise ServiceError("A PAN is ten characters, like ABCDE1234F.")
    partner = partner or ChannelPartner(organization_id=org.id)
    partner.name = name[:200]
    partner.firm = (fields.get("firm") or "").strip()[:200] or None
    partner.phone = (fields.get("phone") or "").strip()[:32] or None
    partner.email = (fields.get("email") or "").strip().lower()[:320] or None
    partner.krera_number = (fields.get("krera_number") or "").strip()[:100] or None
    partner.krera_valid_until = _date(fields.get("krera_valid_until"), "The registration's end")
    partner.commission_pct = rate
    partner.payable_after_pct = after
    partner.gstin = gstin
    partner.pan = pan
    session.add(partner)
    session.commit()
    return partner


def received_for(session: Session, unit_id: str) -> Decimal:
    return Decimal(
        session.scalar(
            select(func.coalesce(func.sum(Receipt.amount), 0)).where(
                Receipt.unit_id == unit_id, Receipt.cancellation_id.is_(None)
            )
        )
        or 0
    )


def commission_state(session: Session, c: Commission) -> str:
    """pending (the buyer has not yet paid enough), due or paid."""
    if c.paid_on:
        return "paid"
    booking = session.get(Booking, c.booking_id)
    partner = session.get(ChannelPartner, c.partner_id)
    if commission_due(received_for(session, booking.unit_id), booking.agreement_value,
                      partner.payable_after_pct):  # fmt: skip
        return "due"
    return "pending"


def pay_commission(
    session: Session, c: Commission, fields: dict, *, as_of: date, user_id: str | None
) -> None:
    state = commission_state(session, c)
    if state == "pending":
        raise ServiceError("Not due yet: the buyer has not paid enough of the agreement value.")
    if state == "paid":
        return
    c.paid_on = _date(fields.get("paid_on"), "The payment date") or as_of
    c.paid_by = user_id
    c.reference = (fields.get("reference") or "").strip()[:200] or None
    session.commit()


# What the views show


def lead_price(unit: Unit, prices: PriceListIn, regime: str, as_of: date, rules: RulesPack) -> str:
    sheet = cost_sheet(
        unit_label=unit.label,
        carpet_area_sqft=unit.carpet_area_sqft,
        guidance_value=unit.guidance_value,
        prices=prices,
        gst_regime=regime,
        on=as_of,
        rules=rules,
    )
    return f"{sheet.agreement_value:.2f}"


def _user_names(session: Session, ids) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.name for u in session.scalars(select(User).where(User.id.in_(ids)))}


def lead_row(lead: Lead, names: dict[str, str], as_of: date) -> dict:
    return {
        "id": lead.id,
        "name": lead.name,
        "phone": lead.phone,
        "phone_key": lead.phone_key,
        "email": lead.email,
        "source": lead.source,
        "source_label": SOURCES.get(lead.source, lead.source),
        "stage": lead.stage,
        "stage_label": STAGES[lead.stage],
        "interest": lead.interest,
        "budget": f"{lead.budget:.2f}" if lead.budget is not None else None,
        "owner": names.get(lead.owner_user_id),
        "next_follow_up_on": lead.next_follow_up_on.isoformat() if lead.next_follow_up_on else None,
        "follow_up_late": bool(
            lead.next_follow_up_on and lead.next_follow_up_on < as_of and lead.stage in OPEN_STAGES
        ),
        "created_on": lead.created_on.isoformat(),
        "project_id": lead.project_id,
    }


def project_view(
    session: Session, project: Project, *, as_of: date, stage: str | None, can_edit: bool
) -> dict:
    org = session.get(Organization, project.organization_id)
    leads = list(
        session.scalars(
            select(Lead)
            .where(Lead.organization_id == org.id, Lead.project_id == project.id)
            .order_by(Lead.next_follow_up_on.is_(None), Lead.next_follow_up_on, Lead.created_at)
        )
    )
    names = _user_names(session, [x.owner_user_id for x in leads])
    funnel = Counter(x.stage for x in leads)
    visits = list(
        session.scalars(
            select(SiteVisit).where(SiteVisit.project_id == project.id).order_by(SiteVisit.on)
        )
    )
    lead_names = {x.id: x.name for x in leads}
    for v in visits:
        if v.lead_id not in lead_names:
            other = session.get(Lead, v.lead_id)
            lead_names[v.lead_id] = other.name if other else ""
    bookings = list(
        session.scalars(
            select(Booking)
            .where(Booking.project_id == project.id)
            .order_by(Booking.booked_on.desc())
            .limit(20)
        )
    )
    units = list(
        session.scalars(
            select(Unit).where(Unit.project_id == project.id).order_by(Unit.tower, Unit.label)
        )
    )
    holds = {
        h.unit_id: h
        for h in session.scalars(
            select(UnitHold).where(
                UnitHold.released_at.is_(None),
                UnitHold.until > _now(),
                UnitHold.unit_id.in_([u.id for u in units]),
            )  # fmt: skip
        )
    }
    unsold = [u for u in units if not u.booked and u.owner_share == "developer"]
    by_source: dict[str, dict] = {}
    visited = {v.lead_id for v in visits if v.status == "done"}
    for x in leads:
        row = by_source.setdefault(
            x.source,
            {"source": x.source, "label": SOURCES.get(x.source, x.source),
             "leads": 0, "visited": 0, "booked": 0},
        )  # fmt: skip
        row["leads"] += 1
        row["visited"] += 1 if x.id in visited else 0
        row["booked"] += 1 if x.stage == "booked" else 0
    row = price_list(session, project)
    partners = list(
        session.scalars(
            select(ChannelPartner)
            .where(ChannelPartner.organization_id == org.id, ChannelPartner.active)
            .order_by(ChannelPartner.name)
        )
    )
    shown = [x for x in leads if (stage is None and x.stage in OPEN_STAGES) or x.stage == stage]
    months: Counter = Counter()
    for b in session.scalars(select(Booking).where(Booking.project_id == project.id)):
        months[b.booked_on.strftime("%Y-%m")] += 1
    return {
        "project_id": project.id,
        "can_edit": can_edit,
        "stage": stage,
        "stages": [{"value": k, "label": v, "count": funnel.get(k, 0)} for k, v in STAGES.items()],
        "sources": [{"value": k, "label": v} for k, v in SOURCES.items()],
        "leads": [lead_row(x, names, as_of) for x in shown],
        "call_today": [
            lead_row(x, names, as_of)
            for x in leads
            if x.stage in OPEN_STAGES and x.next_follow_up_on and x.next_follow_up_on <= as_of
        ],
        "follow_ups_late": sum(
            1
            for x in leads
            if x.next_follow_up_on and x.next_follow_up_on < as_of and x.stage in OPEN_STAGES
        ),  # fmt: skip
        "visits": [
            {
                "id": v.id,
                "lead_id": v.lead_id,
                "lead": lead_names.get(v.lead_id, ""),
                "on": v.on.isoformat(),
                "time": v.time,
                "status": v.status,
                "status_label": VISITS[v.status],
                "feedback": v.feedback,
            }
            for v in visits
            if v.status == "planned" and v.on >= as_of - timedelta(days=1)
        ][:20],  # fmt: skip
        "conversion": {
            "leads": len(leads),
            "visited": len(visited),
            "booked": funnel.get("booked", 0),
        },
        "by_source": sorted(by_source.values(), key=lambda r: -r["leads"]),
        "bookings_by_month": [{"month": k, "count": v} for k, v in sorted(months.items())][-12:],
        "inventory": {
            "unsold": len(unsold),
            "unsold_value": f"{sum((u.list_price for u in unsold), ZERO):.2f}",
            "units": [
                {
                    "id": u.id,
                    "label": u.label,
                    "tower": u.tower,
                    "carpet_area_sqft": u.carpet_area_sqft,
                    "list_price": f"{u.list_price:.2f}",
                    "held_for": lead_names.get(holds[u.id].lead_id)
                    or (session.get(Lead, holds[u.id].lead_id).name)
                    if u.id in holds
                    else None,
                    "held_until": holds[u.id].until.isoformat() if u.id in holds else None,
                }
                for u in unsold
            ],
        },  # fmt: skip
        "bookings": [
            {
                "id": b.id,
                "unit_id": b.unit_id,
                "unit": session.get(Unit, b.unit_id).label,
                "buyer": b.buyer_name,
                "booked_on": b.booked_on.isoformat(),
                "agreement_value": f"{b.agreement_value:.2f}",
                "partner": session.get(ChannelPartner, b.partner_id).name if b.partner_id else None,
            }
            for b in bookings
        ],  # fmt: skip
        "price_list": None
        if row is None
        else {
            "base_rate": f"{row.base_rate:.2f}",
            "floor_rise": f"{row.floor_rise:.2f}",
            "floor_rise_from": row.floor_rise_from,
            "plc": json.loads(row.plc or "{}"),
            "car_park": f"{row.car_park:.2f}",
            "amenities": f"{row.amenities:.2f}",
            "other_charges": f"{row.other_charges:.2f}",
            "corpus_per_sqft": f"{row.corpus_per_sqft:.2f}",
            "maintenance_per_sqft_month": f"{row.maintenance_per_sqft_month:.2f}",
            "maintenance_months": row.maintenance_months,
        },
        "partners": [{"id": p.id, "name": p.name, "firm": p.firm} for p in partners],
    }


def lead_view(session: Session, lead: Lead, *, as_of: date, can_edit: bool) -> dict:
    activities = list(
        session.scalars(
            select(LeadActivity)
            .where(LeadActivity.lead_id == lead.id)
            .order_by(LeadActivity.at.desc())
        )
    )
    visits = list(
        session.scalars(
            select(SiteVisit).where(SiteVisit.lead_id == lead.id).order_by(SiteVisit.on.desc())
        )
    )
    names = _user_names(session, [lead.owner_user_id, *(a.user_id for a in activities)])
    project = session.get(Project, lead.project_id) if lead.project_id else None
    projects = list(
        session.scalars(
            select(Project)
            .where(Project.organization_id == lead.organization_id)
            .order_by(Project.name)
        )
    )
    units = []
    plc: list[str] = []
    row = price_list(session, project) if project else None
    prices = prices_in(row) if row else None
    if project is not None:
        holds = {
            h.unit_id: h
            for h in session.scalars(
                select(UnitHold).where(UnitHold.released_at.is_(None), UnitHold.until > _now())
            )
        }
        for u in session.scalars(
            select(Unit)
            .where(Unit.project_id == project.id, Unit.booked.is_(False),
                   Unit.owner_share == "developer")
            .order_by(Unit.tower, Unit.label)
        ):  # fmt: skip
            hold = holds.get(u.id)
            units.append({"id": u.id, "label": u.label, "tower": u.tower,
                          "carpet_area_sqft": u.carpet_area_sqft,
                          "price": lead_price(u, prices, project.gst_regime, as_of, KARNATAKA)
                          if prices else None,
                          "held_by_this_lead": bool(hold and hold.lead_id == lead.id),
                          "held_by_other": bool(hold and hold.lead_id != lead.id),
                          "hold_id": hold.id if hold and hold.lead_id == lead.id else None,
                          "held_until": hold.until.isoformat() if hold else None})  # fmt: skip
        plc = list(json.loads(row.plc or "{}")) if row else []
    booking = None
    if lead.unit_id:
        b = booking_for_unit(session, session.get(Unit, lead.unit_id))
        if b is not None:
            booking = {"id": b.id, "unit_id": b.unit_id, "unit": session.get(Unit, b.unit_id).label,
                       "booked_on": b.booked_on.isoformat(),
                       "agreement_value": f"{b.agreement_value:.2f}"}  # fmt: skip
    partner = session.get(ChannelPartner, lead.partner_id) if lead.partner_id else None
    team = _team(session, lead.organization_id)
    return {
        **lead_row(lead, names, as_of),
        "can_edit": can_edit,
        "project": {"id": project.id, "name": project.name} if project else None,
        "projects": [{"id": p.id, "name": p.name} for p in projects],
        "partner": {"id": partner.id, "name": partner.name} if partner else None,
        "lost_reason": lead.lost_reason,
        "has_prices": row is not None,
        "call_again_on": (as_of + timedelta(days=CALL_AGAIN_DAYS)).isoformat(),
        "planned_visit": next(
            (
                {"id": v.id, "on": v.on.isoformat(), "time": v.time}
                for v in reversed(visits)
                if v.status == "planned"
            ),
            None,
        ),
        "activities": [
            {
                "at": a.at.replace(microsecond=0).isoformat(),
                "kind": a.kind,
                "kind_label": ACTIVITY.get(a.kind, a.kind),
                "detail": a.detail,
                "by": names.get(a.user_id),
            }
            for a in activities
        ],  # fmt: skip
        "visits": [
            {
                "id": v.id,
                "on": v.on.isoformat(),
                "time": v.time,
                "status": v.status,
                "status_label": VISITS[v.status],
                "feedback": v.feedback,
                "project": session.get(Project, v.project_id).name,
            }
            for v in visits
        ],  # fmt: skip
        "units": units,
        "plc": plc,
        "booking": booking,
        "team": team,
        "partners": [
            {"id": p.id, "name": p.name}
            for p in session.scalars(
                select(ChannelPartner).where(
                    ChannelPartner.organization_id == lead.organization_id, ChannelPartner.active
                )
            )
        ],
    }


def _team(session: Session, organization_id: str) -> list[dict]:
    from lekhara.models import Membership

    rows = session.execute(
        select(User.id, User.name)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == organization_id)
        .order_by(User.name)
    )
    return [{"id": i, "name": n} for i, n in rows]


def partners_view(session: Session, org: Organization, *, as_of: date, can_edit: bool) -> dict:
    partners = list(
        session.scalars(
            select(ChannelPartner)
            .where(ChannelPartner.organization_id == org.id)
            .order_by(ChannelPartner.active.desc(), ChannelPartner.name)
        )
    )
    out, to_pay, waiting = [], [], []
    for p in partners:
        rows = list(session.scalars(select(Commission).where(Commission.partner_id == p.id)))
        states = [commission_state(session, c) for c in rows]
        pairs = list(zip(rows, states, strict=True))
        paid = sum((c.amount + c.gst - c.tds for c, st in pairs if st == "paid"), ZERO)
        for c, st in pairs:
            if st == "due":
                to_pay.append({**_commission_row(session, c, st), "partner": p.name})
            elif st == "pending":
                waiting.append({**_commission_row(session, c, st), "partner": p.name})
        leads = session.scalar(
            select(func.count()).select_from(Lead).where(Lead.partner_id == p.id)
        )
        out.append({
            "id": p.id, "name": p.name, "firm": p.firm, "phone": p.phone, "email": p.email,
            "krera_number": p.krera_number,
            "krera_valid_until": p.krera_valid_until.isoformat() if p.krera_valid_until else None,
            "krera_lapsed": p.krera_valid_until is None or p.krera_valid_until < as_of,
            "commission_pct": f"{p.commission_pct}", "payable_after_pct": f"{p.payable_after_pct}",
            "gstin": p.gstin, "pan": p.pan, "active": p.active,
            "leads": leads or 0, "bookings": len(rows), "paid": f"{paid:.2f}",
        })  # fmt: skip
    return {"can_edit": can_edit, "partners": out, "to_pay": to_pay, "waiting": waiting}


def _commission_row(session: Session, c: Commission, state: str) -> dict:
    booking = session.get(Booking, c.booking_id)
    unit = session.get(Unit, booking.unit_id)
    project = session.get(Project, booking.project_id)
    return {
        "id": c.id,
        "project": project.name,
        "unit": unit.label,
        "unit_id": unit.id,
        "buyer": booking.buyer_name,
        "booked_on": booking.booked_on.isoformat(),
        "agreement_value": f"{booking.agreement_value:.2f}",
        "rate_pct": f"{c.rate_pct}",
        "amount": f"{c.amount:.2f}",
        "gst": f"{c.gst:.2f}",
        "tds": f"{c.tds:.2f}",
        "payable": f"{c.amount + c.gst - c.tds:.2f}",
        "state": state,
        "paid_on": c.paid_on.isoformat() if c.paid_on else None,
        "reference": c.reference,
    }
