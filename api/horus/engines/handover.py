"""Registration and handover: what stands between each buyer and a registered home.

Every booked unit moves through the same steps, in order. The first step not yet
done is the unit's blocker. Since July 2025 a verified e-Khata is needed before
a sale deed can be registered in Bengaluru, which is why the e-Khata step comes
before the deed and the appointment.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from horus.money import ZERO, rupees
from horus.rules import RulesPack


class Stage(StrEnum):
    OC = "oc"
    EKHATA = "ekhata"
    FINAL_DEMAND = "final_demand"
    PAYMENT = "payment"
    DEED = "deed"
    APPOINTMENT = "appointment"
    REGISTRATION = "registration"
    POSSESSION = "possession"
    DONE = "done"


STAGES = (
    Stage.OC,
    Stage.EKHATA,
    Stage.FINAL_DEMAND,
    Stage.PAYMENT,
    Stage.DEED,
    Stage.APPOINTMENT,
    Stage.REGISTRATION,
    Stage.POSSESSION,
)

STAGE_LABEL = {
    Stage.OC: "Occupancy certificate",
    Stage.EKHATA: "Final e-Khata",
    Stage.FINAL_DEMAND: "Final demand raised",
    Stage.PAYMENT: "Paid in full",
    Stage.DEED: "Sale deed drafted",
    Stage.APPOINTMENT: "Registration appointment",
    Stage.REGISTRATION: "Registered",
    Stage.POSSESSION: "Possession handed over",
}

BLOCKER_TEXT = {
    Stage.OC: "Waiting for the occupancy certificate",
    Stage.EKHATA: "Waiting for the final e-Khata",
    Stage.FINAL_DEMAND: "Final demand not raised",
    Stage.PAYMENT: "Buyer still owes money",
    Stage.DEED: "Sale deed to be drafted",
    Stage.APPOINTMENT: "Book the registration appointment",
    Stage.REGISTRATION: "Appointment booked, to be registered",
    Stage.POSSESSION: "Registered; hand over possession",
    Stage.DONE: "Handed over",
}


@dataclass(frozen=True)
class UnitHandoverIn:
    unit_id: str
    label: str
    buyer: str | None
    agreement_value: Decimal
    guidance_value: Decimal
    ekhata_status: str
    """none, applied, draft or final."""
    khata_type: str | None
    final_demand_raised: bool
    balance_due: Decimal
    deed_drafted_on: date | None = None
    appointment_on: date | None = None
    registered_on: date | None = None
    document_no: str | None = None
    possession_on: date | None = None


@dataclass(frozen=True)
class RegistrationCost:
    base: Decimal
    stamp_duty: Decimal
    cess: Decimal
    registration_fee: Decimal

    @property
    def total(self) -> Decimal:
        return self.stamp_duty + self.cess + self.registration_fee


@dataclass(frozen=True)
class UnitReadiness:
    unit: UnitHandoverIn
    done: tuple[Stage, ...]
    blocker: Stage
    cost: RegistrationCost


@dataclass(frozen=True)
class HandoverPosition:
    oc_received: bool
    oc_received_on: date | None
    units: tuple[UnitReadiness, ...]
    by_blocker: dict[Stage, int]
    registered: int
    handed_over: int
    money_waiting: Decimal
    conveyance_due_on: date | None
    common_areas_conveyed_on: date | None


def registration_cost(
    agreement_value: Decimal, guidance_value: Decimal, *, on: date, rules: RulesPack
) -> RegistrationCost:
    """Stamp duty and fees are worked out on the higher of the price and the guidance value."""
    base = max(agreement_value, guidance_value)
    duty = rupees(base * rules.value("reg.stamp_duty_rate", on))
    return RegistrationCost(
        base=base,
        stamp_duty=duty,
        cess=rupees(duty * rules.value("reg.stamp_cess_share", on)),
        registration_fee=rupees(base * rules.value("reg.registration_fee_rate", on)),
    )


def _done(u: UnitHandoverIn, oc_received: bool) -> list[Stage]:
    checks = {
        Stage.OC: oc_received,
        Stage.EKHATA: u.ekhata_status == "final",
        Stage.FINAL_DEMAND: u.final_demand_raised,
        Stage.PAYMENT: u.final_demand_raised and u.balance_due <= 0,
        Stage.DEED: u.deed_drafted_on is not None,
        Stage.APPOINTMENT: u.appointment_on is not None,
        Stage.REGISTRATION: u.registered_on is not None,
        Stage.POSSESSION: u.possession_on is not None,
    }
    return [stage for stage in STAGES if checks[stage]]


def _add_months(d: date, months: int) -> date:
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    last_day = (date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day))


def handover_position(
    units: list[UnitHandoverIn],
    *,
    oc_received_on: date | None,
    common_areas_conveyed_on: date | None,
    on: date,
    rules: RulesPack,
) -> HandoverPosition:
    oc_received = oc_received_on is not None and oc_received_on <= on
    readiness = []
    by_blocker: dict[Stage, int] = {stage: 0 for stage in [*STAGES, Stage.DONE]}
    for u in units:
        done = _done(u, oc_received)
        blocker = next((stage for stage in STAGES if stage not in done), Stage.DONE)
        by_blocker[blocker] += 1
        readiness.append(
            UnitReadiness(
                unit=u,
                done=tuple(done),
                blocker=blocker,
                cost=registration_cost(u.agreement_value, u.guidance_value, on=on, rules=rules),
            )
        )
    conveyance_due = None
    if oc_received:
        conveyance_due = _add_months(oc_received_on, rules.value("rera.s17_conveyance_months", on))
    return HandoverPosition(
        oc_received=oc_received,
        oc_received_on=oc_received_on,
        units=tuple(readiness),
        by_blocker=by_blocker,
        registered=sum(1 for r in readiness if r.unit.registered_on is not None),
        handed_over=sum(1 for r in readiness if r.unit.possession_on is not None),
        money_waiting=sum(
            (r.unit.balance_due for r in readiness if r.unit.registered_on is None), ZERO
        ),
        conveyance_due_on=conveyance_due,
        common_areas_conveyed_on=common_areas_conveyed_on,
    )
