"""Demo data: a fictional developer with three Bengaluru projects.

Every date is relative to `today`, so the demo always looks current. The three
projects are built to show each part of Lekhara:

- Whitefield Residences: JDA area share. Money waiting in the RERA account,
  close to the 80% supplier limit, GST on development rights to plan for, two
  sales below guidance value, an MSME bill due soon.
- Hebbal Heights: own land. Spending ahead of certified progress, deposits
  short, below the 80% supplier minimum, a late quarterly report, an overdue
  MSME payment, labour cess outstanding.
- Sarjapur Greens: JDA revenue share, nearly complete. Possession is late, the
  annual audit is overdue, TDS short on a landowner payment, overruns beyond
  contingency, and a withdrawal waiting for the CA's signature.

Run: python -m lekhara.seed   (resets the database first)
"""

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from lekhara.auth import hash_password
from lekhara.config import get_settings
from lekhara.db import Base, make_engine, make_sessionmaker
from lekhara.engines.documents import REQUIREMENTS
from lekhara.engines.tax import financial_year
from lekhara.legal import VERSION
from lekhara.migrate import upgrade
from lekhara.models import (
    Acceptance,
    Approval,
    Bill,
    ChecklistWaiver,
    Commitment,
    CostLineRow,
    DataRoomVisit,
    DemandRow,
    DisputeCase,
    DisputeHearing,
    DisputeOrder,
    DisputePayment,
    EscrowTxn,
    Filing,
    Landowner,
    LandownerPaymentRow,
    LedgerEntry,
    Membership,
    Organization,
    PaymentMilestone,
    ProgressCertificate,
    Project,
    ProjectAccess,
    Receipt,
    Unit,
    UnitHandover,
    User,
    Vendor,
    WithdrawalCertificate,
    WithdrawalRequest,
)
from lekhara.pdf import write_pdf
from lekhara.rules import KARNATAKA
from lekhara.storage import LocalStorage, Storage

CR = Decimal("10000000")
LAKH = Decimal("100000")


def cr(x: str) -> Decimal:
    return (Decimal(x) * CR).quantize(Decimal("0.01"))


def lakh(x: str) -> Decimal:
    return (Decimal(x) * LAKH).quantize(Decimal("0.01"))


DEMO_PASSWORD = "lekhara-demo"


@dataclass(frozen=True)
class DemoAccount:
    email: str
    name: str
    label: str
    org_role: str | None = None
    certifier_role: str | None = None
    firm: str | None = None


DEMO_ACCOUNTS = (
    DemoAccount("promoter@demo.lekhara", "Ravi Kumar", "Owner (promoter)", org_role="owner"),
    DemoAccount("cfo@demo.lekhara", "Meera Rao", "Finance (CFO)", org_role="finance"),
    DemoAccount("accounts@demo.lekhara", "Prakash N", "Accounts", org_role="accounts"),
    DemoAccount(
        "architect@demo.lekhara",
        "A. Kulkarni",
        "Architect",
        certifier_role="architect",
        firm="Studio Kaveri Architects",
    ),
    DemoAccount(
        "engineer@demo.lekhara",
        "R. Hegde",
        "Engineer",
        certifier_role="engineer",
        firm="Sound Structures Consultants",
    ),
    DemoAccount(
        "ca@demo.lekhara",
        "S. Menon",
        "Chartered accountant",
        certifier_role="ca",
        firm="Menon and Associates",
    ),
)


@lru_cache
def _demo_password_hash() -> str:
    # One hash for every demo account keeps seeding fast; real accounts each get their own salt.
    return hash_password(DEMO_PASSWORD)


def seed_people(session: Session, org: Organization, projects: list[Project]) -> dict[str, User]:
    users: dict[str, User] = {}
    for account in DEMO_ACCOUNTS:
        user = User(
            name=account.name,
            email=account.email,
            password_hash=_demo_password_hash(),
            firm=account.firm,
            email_verified_at=datetime(2026, 1, 1),
        )
        session.add(user)
        session.flush()
        users[account.email] = user
        if account.org_role:
            session.add(Membership(user_id=user.id, organization_id=org.id, role=account.org_role))
        if account.certifier_role:
            for project in projects:
                session.add(
                    ProjectAccess(
                        user_id=user.id, project_id=project.id, role=account.certifier_role
                    )
                )
        # The demo accounts have accepted the current terms, as a real account would have.
        for document in ("terms", "privacy"):
            session.add(
                Acceptance(
                    user_id=user.id, organization_id=org.id, document=document, version=VERSION
                )
            )
    session.flush()
    return users


@dataclass
class LineSpec:
    code: str
    name: str
    category: str
    head: str
    budget: str
    committed: str
    incurred: str
    paid: str


def _quarter_ends(start: date, end: date) -> list[date]:
    out = []
    for year in range(start.year, end.year + 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qe = date(year, month, day)
            if start <= qe <= end:
                out.append(qe)
    return out


class Seeder:
    def __init__(self, session: Session, today: date) -> None:
        self.s = session
        self.today = today
        self.rng = random.Random(17)
        self.org = Organization(id="demo", name="Demo Builders", is_sample=True, access="active")
        session.add(self.org)
        self.vendors: dict[str, Vendor] = {}

    def ago(self, days: int) -> date:
        return self.today - timedelta(days=days)

    def ahead(self, days: int) -> date:
        return self.today + timedelta(days=days)

    def vendor(
        self, name: str, registered: bool, msme: str = "none", agreement: bool = True
    ) -> Vendor:
        if name not in self.vendors:
            v = Vendor(
                organization_id=self.org.id,
                name=name,
                gstin=f"29DEMO{len(self.vendors):04d}Z1Z" if registered else None,
                registered=registered,
                msme_category=msme,
                written_agreement=agreement,
            )
            self.s.add(v)
            self.vendors[name] = v
        return self.vendors[name]

    def project(self, **kwargs) -> Project:
        p = Project(organization_id=self.org.id, city="Bengaluru", **kwargs)
        self.s.add(p)
        return p

    def lines(self, p: Project, specs: list[LineSpec]) -> None:
        span = max((self.today - p.registered_on).days, 120)
        for i, spec in enumerate(specs):
            line = CostLineRow(
                project_id=p.id,
                code=spec.code,
                name=spec.name,
                category=spec.category,
                rera_head=spec.head,
                original_budget=cr(spec.budget),
                revised_budget=cr(spec.budget),
                position=i,
            )
            self.s.add(line)
            self.s.flush()
            if spec.category == "contingency":
                continue
            self._commitment(p, line, cr(spec.committed), self.ago(span - 30))
            # Spread incurred and paid over time so point-in-time positions are meaningful.
            offsets = [int(span * 0.8), int(span * 0.5), int(span * 0.2), 20]
            self._entries(p, line.id, "incurred", cr(spec.incurred), offsets)
            self._entries(p, line.id, "paid", cr(spec.paid), [o - 10 for o in offsets])
            if spec.category == "construction" and Decimal(spec.incurred) > 0:
                held = (cr(spec.incurred) * Decimal("0.05")).quantize(Decimal("0.01"))
                self._entries(p, line.id, "retention_held", held, [20])

    def _commitment(self, p: Project, line: CostLineRow, amount: Decimal, on: date) -> None:
        """The line's main work order, in the commitments register and the ledger."""
        if amount == 0:
            return
        order = Commitment(
            project_id=p.id,
            cost_line_id=line.id,
            reference=f"WO/{line.code}/001",
            description=f"Main contract: {line.name.lower()}",
            amount=amount,
            committed_on=on,
        )
        self.s.add(order)
        self.s.flush()
        self.s.add(
            LedgerEntry(
                project_id=p.id,
                cost_line_id=line.id,
                kind="commitment",
                amount=amount,
                entry_date=on,
                reference=f"commitment:{order.id}:commitment",
            )
        )

    def _entries(self, p: Project, line_id: str, kind: str, total: Decimal, offsets: list[int]):
        if total == 0:
            return
        parts = len(offsets)
        share = (total / parts).quantize(Decimal("0.01"))
        amounts = [share] * (parts - 1) + [total - share * (parts - 1)]
        for amount, offset in zip(amounts, offsets, strict=True):
            self.s.add(
                LedgerEntry(
                    project_id=p.id,
                    cost_line_id=line_id,
                    kind=kind,
                    amount=amount,
                    entry_date=self.ago(max(offset, 1)),
                )
            )

    def progress(self, p: Project, pct: str, previous: str) -> None:
        self.s.add(
            ProgressCertificate(
                project_id=p.id,
                completion_pct=Decimal(previous),
                as_of=self.ago(110),
                certified_by="Project architect",
            )
        )
        self.s.add(
            ProgressCertificate(
                project_id=p.id,
                completion_pct=Decimal(pct),
                as_of=self.ago(18),
                certified_by="Project architect",
            )
        )

    def payment_plan(self, p: Project) -> list[PaymentMilestone]:
        steps = [
            ("On booking", "booking", None, 7),
            ("On signing the agreement", "agreement", None, 30),
            ("On completion of the foundation", "progress", "10", 15),
            ("On completion of the plinth", "progress", "20", 15),
            ("On completion of the 4th floor slab", "progress", "35", 15),
            ("On completion of the 8th floor slab", "progress", "50", 15),
            ("On completion of the terrace slab", "progress", "65", 15),
            ("On completion of brickwork and plastering", "progress", "80", 15),
            ("On completion of flooring and finishes", "progress", "90", 15),
            ("On possession", "possession", None, 15),
        ]
        plan = [
            PaymentMilestone(
                project_id=p.id,
                sequence=i + 1,
                name=name,
                share_pct=Decimal("10"),
                trigger=trigger,
                progress_pct=Decimal(pct) if pct else None,
                due_days=due_days,
            )
            for i, (name, trigger, pct, due_days) in enumerate(steps)
        ]
        for m in plan:
            self.s.add(m)
        self.s.flush()
        return plan

    def units(
        self,
        p: Project,
        *,
        towers: list[str],
        per_tower: int,
        landowner_share: Decimal,
        booked_share: Decimal,
        price_per_sqft: int,
        guidance_per_sqft: int,
        plan: list[PaymentMilestone],
        progress_before: Decimal,
        raise_up_to_pct: Decimal,
        overdue_every: int,
        gst_rate: Decimal = Decimal("0.05"),
        below_guidance: int = 0,
    ) -> Decimal:
        """Creates units, the demands raised on buyers and what they paid. Returns cash received.

        Progress milestones up to `raise_up_to_pct` have been demanded. A milestone certified
        since then is left for Lekhara to show as ready to raise. Every `overdue_every`-th buyer
        has not paid their latest demand.
        """
        units: list[Unit] = []
        for tower in towers:
            for n in range(per_tower):
                floor, flat = divmod(n, 4)
                area = self.rng.choice([1050, 1180, 1265, 1340, 1450])
                units.append(
                    Unit(
                        project_id=p.id,
                        label=f"{tower}-{floor + 1:02d}{flat + 1:02d}",
                        tower=f"Tower {tower}",
                        carpet_area_sqft=area,
                        owner_share="developer",
                        list_price=Decimal(area * price_per_sqft),
                        guidance_value=Decimal(area * guidance_per_sqft),
                    )
                )
        landowner_count = int(len(units) * landowner_share)
        for u in units[-landowner_count:] if landowner_count else []:
            u.owner_share = "landowner"
        developer_units = [u for u in units if u.owner_share == "developer"]
        booked_count = int(len(developer_units) * booked_share)
        total = Decimal("0")
        for i, u in enumerate(developer_units[:booked_count]):
            u.booked = True
            u.booked_on = self.ago(self.rng.randint(40, 600))
            u.buyer_name = f"Buyer {i + 1:03d}"
            discount = Decimal(self.rng.choice([0, 1, 2, 3])) / 100
            if i < below_guidance:
                u.booked_on = self.ago(30 + i * 9)
                discount = Decimal("0")
                u.list_price = u.guidance_value * Decimal("0.84")
            u.agreement_value = (u.list_price * (1 - discount)).quantize(Decimal("1"))
        for u in units:
            self.s.add(u)
        self.s.flush()
        for index, u in enumerate(developer_units[:booked_count]):
            raised: list[DemandRow] = []
            for m in plan:
                if m.trigger == "booking":
                    raised_on = u.booked_on
                elif m.trigger == "agreement":
                    raised_on = u.booked_on + timedelta(days=20)
                elif m.trigger == "progress" and m.progress_pct <= raise_up_to_pct:
                    crossed = self.ago(150) if m.progress_pct <= progress_before else self.ago(18)
                    raised_on = max(crossed, u.booked_on + timedelta(days=25))
                else:
                    continue
                if raised_on > self.today:
                    continue
                amount = (u.agreement_value * m.share_pct / 100).quantize(Decimal("0.01"))
                demand = DemandRow(
                    project_id=p.id,
                    unit_id=u.id,
                    milestone_id=m.id,
                    amount=amount,
                    gst=(amount * gst_rate).quantize(Decimal("0.01")),
                    raised_on=raised_on,
                    due_on=raised_on + timedelta(days=m.due_days),
                    certified_progress_pct=m.progress_pct,
                )
                self.s.add(demand)
                raised.append(demand)
            unpaid = 0
            if index % overdue_every == 0:
                unpaid = 2 if index % (overdue_every * 4) == 0 else 1
            ordered = sorted(raised, key=lambda d: d.raised_on)
            for n, demand in enumerate(ordered):
                if n >= len(ordered) - unpaid and demand.due_on < self.today:
                    continue
                paid_on = demand.raised_on + timedelta(days=self.rng.randint(3, 14))
                paid_on = min(paid_on, self.ago(1))
                tds = (
                    (demand.amount * Decimal("0.01")).quantize(Decimal("1"))
                    if u.agreement_value > Decimal("5000000")
                    else Decimal("0")
                )
                cash = demand.amount + demand.gst - tds
                self.s.add(
                    Receipt(
                        project_id=p.id,
                        unit_id=u.id,
                        amount=cash,
                        received_on=max(paid_on, demand.raised_on),
                        tds_deducted=tds,
                    )
                )
                total += cash
        return total

    def handover(
        self,
        p: Project,
        plan: list[PaymentMilestone],
        *,
        possession_raised: int,
        possession_paid: int,
        ekhata_final: int,
        ekhata_draft: int,
        deeds: int,
        appointments: int,
        registered: int,
        handed_over: int,
        overdue_every: int,
        gst_rate: Decimal = Decimal("0.05"),
    ) -> None:
        """Puts the project's booked units at every step between OC and possession."""
        self.s.flush()
        final = next(m for m in plan if m.trigger == "possession")
        units = list(
            self.s.scalars(
                select(Unit)
                .where(Unit.project_id == p.id, Unit.booked.is_(True))
                .order_by(Unit.label)
            )
        )
        ready = 0
        for i, u in enumerate(units):
            if i < possession_raised:
                amount = (u.agreement_value * final.share_pct / 100).quantize(Decimal("0.01"))
                gst = (amount * gst_rate).quantize(Decimal("0.01"))
                self.s.add(
                    DemandRow(
                        project_id=p.id,
                        unit_id=u.id,
                        milestone_id=final.id,
                        amount=amount,
                        gst=gst,
                        raised_on=self.ago(15),
                        due_on=self.today,
                    )
                )
                if i < possession_paid:
                    tds = (
                        (amount * Decimal("0.01")).quantize(Decimal("1"))
                        if u.agreement_value > Decimal("5000000")
                        else Decimal("0")
                    )
                    self.s.add(
                        Receipt(
                            project_id=p.id,
                            unit_id=u.id,
                            amount=amount + gst - tds,
                            received_on=self.ago(6 + i % 5),
                            tds_deducted=tds,
                        )
                    )
            if i < ekhata_final:
                status = "final"
            elif i < ekhata_final + ekhata_draft:
                status = "draft"
            else:
                status = "applied"
            record = UnitHandover(
                unit_id=u.id, ekhata_status=status, khata_type="A" if status == "final" else None
            )
            clear = status == "final" and i < possession_paid and i % overdue_every != 0
            if clear:
                if ready < deeds:
                    record.deed_drafted_on = self.ago(12)
                if ready < appointments:
                    record.appointment_on = self.ago(9) if ready < registered else self.ahead(4)
                if ready < registered:
                    record.registered_on = self.ago(9 - ready % 6)
                    record.document_no = f"BNG-DEMO-2026-{4100 + ready:06d}"
                if ready < handed_over:
                    record.possession_on = self.ago(5)
                ready += 1
            self.s.add(record)

    def case(
        self,
        p: Project,
        unit: Unit | None,
        *,
        forum: str,
        number: str,
        relief: str,
        status: str,
        filed_on: date,
        summary: str,
        complainant: str | None = None,
        user_id: str | None = None,
        hearings: tuple[tuple[date, str, str], ...] = (),
        orders: tuple[dict, ...] = (),
        payments: tuple[tuple[date, Decimal, str], ...] = (),
        **fields,
    ) -> DisputeCase:
        row = DisputeCase(
            project_id=p.id,
            unit_id=unit.id if unit else None,
            forum=forum,
            case_number=number,
            relief=relief,
            status=status,
            filed_on=filed_on,
            summary=summary,
            complainant=complainant or (unit.buyer_name if unit else ""),
            created_by_user_id=user_id,
            **fields,
        )
        self.s.add(row)
        self.s.flush()
        for held_on, purpose, outcome in hearings:
            self.s.add(
                DisputeHearing(case_id=row.id, held_on=held_on, purpose=purpose, outcome=outcome)
            )
        for order in orders:
            self.s.add(DisputeOrder(case_id=row.id, **order))
        for paid_on, amount, reference in payments:
            self.s.add(
                DisputePayment(case_id=row.id, paid_on=paid_on, amount=amount, reference=reference)
            )
        return row

    def escrow(
        self,
        p: Project,
        receipts: Decimal,
        *,
        deposit_short: Decimal,
        interest: Decimal,
        balance: Decimal,
        last_withdrawal_days: int,
    ) -> Decimal:
        # Deposit 70% of each month's receipts at that month's end, as a compliant developer
        # would. The last month carries any rounding and the deliberate shortfall.
        self.s.flush()
        by_month: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
        for r in self.s.scalars(select(Receipt).where(Receipt.project_id == p.id)):
            by_month[(r.received_on.year, r.received_on.month)] += r.amount
        months = sorted(by_month)
        required = (sum(by_month.values(), Decimal("0")) * Decimal("0.70")).quantize(
            Decimal("0.01")
        )
        deposits = Decimal("0")
        events: list[tuple[date, Decimal]] = []
        for i, (year, month) in enumerate(months):
            if i < len(months) - 1:
                amount = (by_month[(year, month)] * Decimal("0.70")).quantize(Decimal("0.01"))
            else:
                amount = required - deposits - deposit_short
            month_end = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
            on = min(month_end, self.ago(1))
            self.s.add(EscrowTxn(project_id=p.id, kind="deposit", amount=amount, txn_date=on))
            events.append((on, amount))
            deposits += amount
        self.s.add(
            EscrowTxn(project_id=p.id, kind="interest", amount=interest, txn_date=self.ago(15))
        )
        # Withdrawals: one at the end of each quarter, each within what the account then held,
        # and a last one that leaves enough for the balance today to be at least `balance`
        # once later deposits and interest come in. The balance never runs below zero.
        last_on = self.ago(last_withdrawal_days)
        later = sum((a for on, a in events if on > last_on), Decimal("0"))
        later += interest if self.ago(15) > last_on else Decimal("0")
        keep = max(balance - later, Decimal("0"))
        held = Decimal("0")
        for on, amount in events:
            if on > last_on:
                break
            held += amount
            if on.month not in (3, 6, 9, 12) or on > last_on - timedelta(days=30):
                continue
            draw = (held * Decimal("0.8")).quantize(Decimal("0.01"))
            self.s.add(
                EscrowTxn(
                    project_id=p.id,
                    kind="withdrawal",
                    amount=draw,
                    txn_date=on,
                    reference=f"Withdrawal, quarter to {on.isoformat()}",
                )
            )
            held -= draw
        if self.ago(15) <= last_on:
            held += interest
        last = held - keep
        assert last > 0, f"{p.name}: nothing left for the last withdrawal"
        self.s.add(
            EscrowTxn(
                project_id=p.id,
                kind="withdrawal",
                amount=last,
                txn_date=last_on,
                reference="Last withdrawal",
            )
        )
        return last

    def bills(
        self,
        p: Project,
        *,
        registered: list[tuple[str, str]],
        unregistered: list[tuple[str, str]],
        rcm_services: str = "0",
        excluded: str = "0",
    ) -> None:
        fy_start, _ = financial_year(self.today)
        span = max((self.today - fy_start).days - 2, 10)
        n = 0

        def add(vendor: Vendor, amount: Decimal, **flags) -> None:
            nonlocal n
            n += 1
            when = fy_start + timedelta(days=1 + (n * 37) % span)
            self.s.add(
                Bill(
                    project_id=p.id,
                    vendor=vendor,
                    bill_no=f"{p.id[:3].upper()}-{n:04d}",
                    bill_date=when,
                    accepted_on=when,
                    taxable_value=amount,
                    paid_on=when + timedelta(days=20)
                    if when + timedelta(days=20) < self.today
                    else None,
                    **flags,
                )
            )

        self.s.flush()
        for name, amount in registered:
            add(self.vendor(name, True), cr(amount), is_cement="Cement" in name)
        for name, amount in unregistered:
            add(self.vendor(name, False), cr(amount))
        if Decimal(rcm_services) > 0:
            add(self.vendor("Shield Security Services", False), cr(rcm_services), rcm_paid=True)
        if Decimal(excluded) > 0:
            add(self.vendor("BESCOM", True), cr(excluded), excluded=True)

    def msme_bill(
        self, p: Project, vendor: Vendor, no: str, amount: Decimal, accepted_days_ago: int
    ) -> None:
        self.s.flush()
        self.s.add(
            Bill(
                project_id=p.id,
                vendor=vendor,
                bill_no=no,
                bill_date=self.ago(accepted_days_ago + 2),
                accepted_on=self.ago(accepted_days_ago),
                taxable_value=amount,
            )
        )

    def filings(self, p: Project, *, skip_latest_due_qpr: bool, audit_done: bool) -> None:
        due_quarters = [
            qe
            for qe in _quarter_ends(p.registered_on, self.today)
            if qe + timedelta(days=15) <= self.today
        ]
        for qe in due_quarters:
            if skip_latest_due_qpr and qe == due_quarters[-1]:
                continue
            self.s.add(
                Filing(
                    project_id=p.id,
                    kind="qpr",
                    period_end=qe,
                    filed_on=min(qe + timedelta(days=11), self.today),
                    reference=f"QPR {qe.isoformat()}",
                )
            )
        fy_start, _ = financial_year(self.today)
        year_end = fy_start - timedelta(days=1)
        while audit_done and year_end > p.registered_on:
            self.s.add(
                Filing(
                    project_id=p.id,
                    kind="annual_audit",
                    period_end=year_end,
                    filed_on=min(year_end + timedelta(days=150), self.today),
                    reference=f"Audit FY ending {year_end.isoformat()}",
                )
            )
            year_end = date(year_end.year - 1, 3, 31)

    def approvals(self, p: Project, specs: list[tuple]) -> None:
        """(name, authority, reference, applied days ago, granted days ago, valid days ahead);
        None where a date is not known yet."""
        for name, authority, reference, applied, granted, valid in specs:
            self.s.add(
                Approval(
                    project_id=p.id,
                    name=name,
                    authority=authority,
                    reference=reference,
                    applied_on=self.ago(applied) if applied is not None else None,
                    granted_on=self.ago(granted) if granted is not None else None,
                    valid_until=self.ahead(valid) if valid is not None else None,
                )
            )


def seed(session: Session, today: date, storage: Storage | None = None) -> None:
    sd = Seeder(session, today)

    # Whitefield Residences: JDA area share, 45% to the landowner.
    wf = sd.project(
        id="whitefield-residences",
        name="Whitefield Residences",
        locality="Whitefield",
        krera_registration="PRM/KA/RERA/DEMO/WF/2024",
        registered_on=sd.ago(820),
        spv_name="Whitefield Residences LLP",
        gst_regime="residential_5pc",
        land_structure="jda_area_share",
        possession_due_on=sd.ahead(430),
        statutory_auditor_firm="Rao and Iyer, Chartered Accountants",
        escrow_bank="Canara Bank, MG Road",
        development_rights_value=cr("118.8"),
        cess_paid=lakh("71.5"),
    )
    session.flush()
    sd.lines(
        wf,
        [
            LineSpec(
                "LAND", "Land, deposit and registration", "land", "land", "12", "12", "12", "12"
            ),
            LineSpec(
                "APPR",
                "Approvals, premium FAR and fees",
                "approvals",
                "land",
                "9",
                "9",
                "8.5",
                "8.5",
            ),
            LineSpec(
                "CIVIL",
                "Civil and structure",
                "construction",
                "development",
                "78",
                "76",
                "52",
                "49",
            ),
            LineSpec(
                "MEP",
                "Mechanical, electrical and plumbing",
                "construction",
                "development",
                "26",
                "27.2",
                "12",
                "11",
            ),
            LineSpec("FIN", "Finishes", "construction", "development", "22", "18", "6", "5.5"),
            LineSpec(
                "EXT",
                "External works and amenities",
                "construction",
                "development",
                "10",
                "6",
                "1.5",
                "1.4",
            ),
            LineSpec("FINC", "Finance cost", "finance", "development", "9", "9", "5", "5"),
            LineSpec(
                "MKT", "Sales and marketing", "marketing", "development", "6", "5", "3.2", "3"
            ),
            LineSpec("OH", "Project overheads", "overheads", "development", "4", "4", "2.4", "2.4"),
            LineSpec("CONT", "Contingency", "contingency", "development", "4", "0", "0", "0"),
        ],
    )
    sd.progress(wf, "56", "47")
    receipts = sd.units(
        wf,
        towers=["A", "B"],
        per_tower=120,
        landowner_share=Decimal("0.45"),
        booked_share=Decimal("0.79"),
        price_per_sqft=9200,
        guidance_per_sqft=7600,
        plan=sd.payment_plan(wf),
        progress_before=Decimal("47"),
        raise_up_to_pct=Decimal("35"),
        overdue_every=9,
        below_guidance=2,
    )
    last = sd.escrow(
        wf,
        receipts,
        deposit_short=Decimal("0"),
        interest=lakh("60"),
        balance=cr("8.4"),
        last_withdrawal_days=80,
    )
    session.add(
        Landowner(
            project_id=wf.id,
            name="Venkatesh Gowda and family",
            share_type="area",
            share_pct=Decimal("45"),
            refundable_deposit=cr("10"),
        )
    )
    sd.bills(
        wf,
        registered=[
            ("UltraBuild Cement Dealers", "4.2"),
            ("Bharat TMT Steel", "7.8"),
            ("Deccan Ready Mix", "3.9"),
            ("Prakash Electricals", "2.6"),
            ("Kaveri Plumbing Supplies", "1.9"),
            ("Southern Tiles and Stone", "2.4"),
        ],
        unregistered=[
            ("Local labour contractor (Manju)", "2.1"),
            ("Shettihalli aggregates", "1.6"),
            ("Ramesh shuttering hire", "1.0"),
        ],
        rcm_services="0.5",
        excluded="1.2",
    )
    sd.msme_bill(
        wf, sd.vendor("Sri Lakshmi Fabricators", True, "micro"), "SLF-118", lakh("9.4"), 40
    )
    sd.filings(wf, skip_latest_due_qpr=False, audit_done=True)
    sd.approvals(
        wf,
        [
            (
                "Land conversion (DC conversion)",
                "Deputy Commissioner",
                "ALN/DC/2022/311",
                1200,
                1100,
                None,
            ),
            ("Building plan sanction", "Planning authority", "LP/DEMO/2024", 960, 880, 400),
            ("Commencement certificate", "Planning authority", "CC/DEMO/2024/77", 870, 840, None),
            (
                "Consent to establish",
                "Karnataka State Pollution Control Board",
                "KSPCB/CFE/2024/5521",
                900,
                860,
                960,
            ),
            (
                "Fire NOC (provisional)",
                "Karnataka State Fire and Emergency Services",
                "KSFES/NOC/2024/1187",
                900,
                850,
                300,
            ),
            (
                "Height clearance",
                "Airports Authority of India",
                "AAI/NOC/2024/BLR/2290",
                950,
                900,
                1500,
            ),
            ("Power supply sanction", "BESCOM", None, 60, None, None),
            ("Water supply and sewerage", "BWSSB", None, 45, None, None),
            (
                "Fire NOC (final)",
                "Karnataka State Fire and Emergency Services",
                None,
                None,
                None,
                None,
            ),
            (
                "Consent to operate",
                "Karnataka State Pollution Control Board",
                None,
                None,
                None,
                None,
            ),
            ("Occupancy certificate", "Planning authority", None, None, None, None),
        ],
    )
    session.flush()
    released = WithdrawalRequest(
        project_id=wf.id,
        amount=last,
        created_on=sd.ago(95),
        submitted_on=sd.ago(88),
        released_on=sd.ago(80),
        released_amount=last,
        bank_reference=f"CNB-RTGS-{sd.ago(80):%Y%m%d}-0417",
    )
    # The certificates carry the figures the books showed when they were signed.
    from lekhara import services

    signed_money = services._money(session, wf, sd.ago(92), KARNATAKA)
    signed_escrow = services._escrow(session, wf, signed_money, sd.ago(92), KARNATAKA)
    figures = {
        "architect": {"completion_pct": signed_money.certified_progress_pct},
        "engineer": {"development_cost_incurred": signed_money.development.incurred},
        "ca": {"total_cost_incurred": signed_escrow.basis_amount, "withdrawable_amount": last},
    }
    for account in DEMO_ACCOUNTS:
        if not account.certifier_role:
            continue
        released.certificates.append(
            WithdrawalCertificate(
                role=account.certifier_role,
                signed=True,
                signer_name=account.name,
                signer_firm=account.firm,
                issued_on=sd.ago(92),
                **figures[account.certifier_role],
            )
        )
    session.add(released)

    # Hebbal Heights: own land.
    hb = sd.project(
        id="hebbal-heights",
        name="Hebbal Heights",
        locality="Hebbal",
        krera_registration="PRM/KA/RERA/DEMO/HB/2025",
        registered_on=sd.ago(470),
        spv_name="Hebbal Heights Private Limited",
        gst_regime="residential_5pc",
        land_structure="own",
        possession_due_on=sd.ahead(900),
        statutory_auditor_firm="Menon and Associates",
        escrow_bank="State Bank of India, Hebbal",
        development_rights_value=None,
        cess_paid=lakh("22"),
    )
    session.flush()
    sd.lines(
        hb,
        [
            LineSpec("LAND", "Land", "land", "land", "38", "38", "38", "38"),
            LineSpec("APPR", "Approvals and fees", "approvals", "land", "7", "7", "6.2", "6.2"),
            LineSpec(
                "CIVIL",
                "Civil and structure",
                "construction",
                "development",
                "48",
                "47",
                "26",
                "24",
            ),
            LineSpec(
                "MEP",
                "Mechanical, electrical and plumbing",
                "construction",
                "development",
                "18",
                "9",
                "4",
                "3.6",
            ),
            LineSpec("FIN", "Finishes", "construction", "development", "13", "2", "0.5", "0.4"),
            LineSpec(
                "EXT",
                "External works and amenities",
                "construction",
                "development",
                "4",
                "0",
                "0",
                "0",
            ),
            LineSpec("FINC", "Finance cost", "finance", "development", "5", "5", "2.4", "2.4"),
            LineSpec(
                "MKT", "Sales and marketing", "marketing", "development", "3", "3", "1.8", "1.7"
            ),
            LineSpec(
                "OH", "Project overheads", "overheads", "development", "1.5", "1.5", "0.9", "0.9"
            ),
            LineSpec("CONT", "Contingency", "contingency", "development", "2.5", "0", "0", "0"),
        ],
    )
    sd.progress(hb, "26", "18")
    receipts = sd.units(
        hb,
        towers=["A", "B"],
        per_tower=80,
        landowner_share=Decimal("0"),
        booked_share=Decimal("0.44"),
        price_per_sqft=10400,
        guidance_per_sqft=8800,
        plan=sd.payment_plan(hb),
        progress_before=Decimal("18"),
        raise_up_to_pct=Decimal("20"),
        overdue_every=6,
    )
    sd.escrow(
        hb,
        receipts,
        deposit_short=cr("1.8"),
        interest=lakh("20"),
        balance=cr("4.5"),
        last_withdrawal_days=40,
    )
    sd.bills(
        hb,
        registered=[
            ("Bharat TMT Steel", "5.1"),
            ("UltraBuild Cement Dealers", "3.6"),
            ("Deccan Ready Mix", "3.2"),
            ("Prakash Electricals", "1.4"),
            ("Kaveri Plumbing Supplies", "1.1"),
        ],
        unregistered=[
            ("Local labour contractor (Manju)", "2.2"),
            ("Shettihalli aggregates", "1.5"),
            ("Ramesh shuttering hire", "0.9"),
        ],
    )
    sd.msme_bill(hb, sd.vendor("Kaveri Steel Traders", True, "small"), "KST-2291", lakh("18.6"), 52)
    sd.msme_bill(
        hb, sd.vendor("Nandi Electricals", True, "micro", agreement=False), "NE-77", lakh("4.2"), 10
    )
    sd.filings(hb, skip_latest_due_qpr=True, audit_done=True)
    sd.approvals(
        hb,
        [
            ("Building plan sanction", "Planning authority", "LP/HB/2025/0912", 600, 520, 1300),
            ("Commencement certificate", "Planning authority", "CC/HB/2025/031", 510, 490, None),
            ("Environmental clearance", "SEIAA, Karnataka", "SEIAA/36/CON/2025", 640, 560, None),
            (
                "Consent to establish",
                "Karnataka State Pollution Control Board",
                "KSPCB/CFE/2025/0418",
                560,
                520,
                40,
            ),
            (
                "Fire NOC (provisional)",
                "Karnataka State Fire and Emergency Services",
                "KSFES/NOC/2025/0204",
                540,
                500,
                230,
            ),
        ],
    )

    # Sarjapur Greens: JDA revenue share, nearly complete, possession late.
    sg = sd.project(
        id="sarjapur-greens",
        name="Sarjapur Greens",
        locality="Sarjapur Road",
        krera_registration="PRM/KA/RERA/DEMO/SG/2023",
        registered_on=sd.ago(1180),
        spv_name="Sarjapur Greens LLP",
        gst_regime="residential_5pc",
        land_structure="jda_revenue_share",
        possession_due_on=sd.ago(64),
        statutory_auditor_firm="Rao and Iyer, Chartered Accountants",
        escrow_bank="HDFC Bank, Koramangala",
        development_rights_value=cr("42"),
        cess_paid=lakh("72.2"),
        oc_status="received",
        oc_received_on=sd.ago(20),
        oc_reference="GBA/OC/DEMO/SG/2026",
    )
    session.flush()
    sd.lines(
        sg,
        [
            LineSpec("LAND", "JDA registration and stamp duty", "land", "land", "2", "2", "2", "2"),
            LineSpec("APPR", "Approvals and fees", "approvals", "land", "6", "6", "6", "6"),
            LineSpec(
                "CIVIL",
                "Civil and structure",
                "construction",
                "development",
                "42",
                "43.5",
                "41",
                "39.5",
            ),
            LineSpec(
                "MEP",
                "Mechanical, electrical and plumbing",
                "construction",
                "development",
                "16",
                "15.8",
                "14.5",
                "13.9",
            ),
            LineSpec("FIN", "Finishes", "construction", "development", "14", "15.2", "12.6", "12"),
            LineSpec(
                "EXT",
                "External works and amenities",
                "construction",
                "development",
                "5",
                "4.8",
                "4.1",
                "3.9",
            ),
            LineSpec("FINC", "Finance cost", "finance", "development", "5", "5", "4.8", "4.8"),
            LineSpec(
                "MKT", "Sales and marketing", "marketing", "development", "3.5", "3.5", "3.2", "3.1"
            ),
            LineSpec("OH", "Project overheads", "overheads", "development", "2", "2", "1.8", "1.8"),
            LineSpec("CONT", "Contingency", "contingency", "development", "0.5", "0", "0", "0"),
        ],
    )
    sd.progress(sg, "91", "84")
    sg_plan = sd.payment_plan(sg)
    receipts = sd.units(
        sg,
        towers=["A", "B", "C"],
        per_tower=40,
        landowner_share=Decimal("0"),
        booked_share=Decimal("0.88"),
        price_per_sqft=8800,
        guidance_per_sqft=7200,
        plan=sg_plan,
        progress_before=Decimal("84"),
        raise_up_to_pct=Decimal("90"),
        overdue_every=7,
        below_guidance=1,
    )
    sd.handover(
        sg,
        sg_plan,
        possession_raised=60,
        possession_paid=45,
        ekhata_final=40,
        ekhata_draft=30,
        deeds=32,
        appointments=28,
        registered=20,
        handed_over=16,
        overdue_every=7,
    )
    sd.escrow(
        sg,
        receipts,
        deposit_short=Decimal("0"),
        interest=cr("1.1"),
        balance=cr("21.5"),
        last_withdrawal_days=70,
    )
    sd.approvals(
        sg,
        [
            ("Building plan sanction", "Planning authority", "LP/SG/2023/0127", 1300, 1220, None),
            ("Commencement certificate", "Planning authority", "CC/SG/2023/014", 1210, 1190, None),
            (
                "Fire NOC (final)",
                "Karnataka State Fire and Emergency Services",
                "KSFES/FNOC/2026/0045",
                150,
                120,
                610,
            ),
            (
                "Consent to operate",
                "Karnataka State Pollution Control Board",
                "KSPCB/CFO/2025/0877",
                420,
                385,
                -20,
            ),
            ("Occupancy certificate", "Planning authority", "OC/SG/2026/0021", 130, 100, None),
        ],
    )
    owner = Landowner(
        project_id=sg.id,
        name="Lakshmamma Trust",
        share_type="revenue",
        share_pct=Decimal("30"),
        refundable_deposit=Decimal("0"),
    )
    session.add(owner)
    session.flush()
    for i, days in enumerate((150, 120, 90, 60, 30)):
        amount = lakh("118")
        session.add(
            LandownerPaymentRow(
                landowner_id=owner.id,
                amount=amount,
                paid_on=sd.ago(days),
                tds_deducted=Decimal("0") if i == 3 else (amount * Decimal("0.10")),
                note="Revenue share for the month",
            )
        )
    sd.bills(
        sg,
        registered=[
            ("Southern Tiles and Stone", "2.9"),
            ("Prakash Electricals", "1.7"),
            ("Kaveri Plumbing Supplies", "1.4"),
            ("Deccan Ready Mix", "2.2"),
        ],
        unregistered=[("Ramesh shuttering hire", "0.8")],
    )
    sd.filings(sg, skip_latest_due_qpr=False, audit_done=False)

    # The people: the developer's team and the three certifiers on every project.
    session.flush()
    users = seed_people(session, sd.org, [wf, hb, sg])
    by_role = {a.certifier_role: a for a in DEMO_ACCOUNTS if a.certifier_role}
    for row in released.certificates:
        row.signed_by_user_id = users[by_role[row.role].email].id

    # An open withdrawal on Sarjapur Greens: architect and engineer have signed; the CA has not.
    from lekhara import services

    request = services.create_withdrawal(
        session, sg, None, today, user_id=users["accounts@demo.lekhara"].id
    )
    request.created_on = sd.ago(3)
    for row in request.certificates:
        if row.role in ("architect", "engineer"):
            account = by_role[row.role]
            row.signed = True
            row.signer_name = account.name
            row.signer_firm = account.firm
            row.signed_by_user_id = users[account.email].id
            row.issued_on = sd.ago(2 if row.role == "architect" else 1)
    session.flush()

    # Disputes. Sarjapur Greens is past its promised possession date and buyers have gone to
    # K-RERA and the consumer commission; Whitefield has a boundary suit from a neighbour.
    sg_units = list(
        session.scalars(
            select(Unit).where(Unit.project_id == sg.id, Unit.booked.is_(True)).order_by(Unit.label)
        )
    )
    at = lambda i: sg_units[min(i, len(sg_units) - 1)]  # noqa: E731
    clerk = users["accounts@demo.lekhara"].id
    sd.case(
        sg,
        at(72),
        forum="krera",
        number="CMP/DEMO/0412/2026",
        relief="delay_interest",
        status="hearing",
        filed_on=sd.ago(40),
        notice_received_on=sd.ago(35),
        reply_due_on=sd.ago(21),
        reply_filed_on=sd.ago(22),
        next_hearing_on=sd.ahead(9),
        lawyer="R. Narayan, Advocate",
        summary=(
            "Asks for interest for every month of delay from the promised possession date, and "
            "possession with a final e-Khata."
        ),
        hearings=((sd.ago(12), "First hearing", "Reply taken on record. Rejoinder to be filed."),),
        user_id=clerk,
    )
    sd.case(
        sg,
        at(85),
        forum="krera",
        number="CMP/DEMO/0377/2026",
        relief="refund",
        status="ordered",
        filed_on=sd.ago(150),
        notice_received_on=sd.ago(140),
        reply_due_on=sd.ago(116),
        reply_filed_on=sd.ago(118),
        lawyer="R. Narayan, Advocate",
        summary="Wants to leave the project and get back everything paid, citing the delay.",
        hearings=(
            (sd.ago(95), "First hearing", "Reply taken on record."),
            (sd.ago(60), "Arguments", "Arguments heard. Order reserved."),
        ),
        orders=(
            {
                "ordered_on": sd.ago(25),
                "received_on": sd.ago(22),
                "kind": "refund",
                "comply_by": sd.ago(25) + timedelta(days=60),
                "summary": (
                    "Refund the amount paid with interest at SBI MCLR plus 2% from each payment "
                    "until it is refunded, within 60 days."
                ),
            },
        ),
        user_id=clerk,
    )
    sd.case(
        sg,
        at(91),
        forum="consumer_district",
        number="CC/DEMO/218/2026",
        relief="defects",
        status="notice",
        filed_on=sd.ago(30),
        notice_received_on=sd.ago(10),
        reply_due_on=sd.ahead(5),
        next_hearing_on=sd.ahead(25),
        claim_amount=lakh("4.5"),
        summary="Seepage in the master bedroom and the balcony; asks for repairs and compensation.",
        user_id=clerk,
    )
    sd.case(
        sg,
        at(78),
        forum="adjudicating_officer",
        number="AO/DEMO/051/2026",
        relief="compensation",
        status="ordered",
        filed_on=sd.ago(200),
        notice_received_on=sd.ago(190),
        reply_filed_on=sd.ago(170),
        claim_amount=lakh("10"),
        lawyer="S. Hegde and Associates",
        summary="Compensation for rent paid and hardship during the delay.",
        hearings=(
            (sd.ago(120), "First hearing", "Reply taken on record."),
            (sd.ago(85), "Arguments", "Order reserved."),
        ),
        orders=(
            {
                "ordered_on": sd.ago(70),
                "received_on": sd.ago(66),
                "kind": "compensation",
                "amount": lakh("2.5"),
                "comply_by": sd.ago(10),
                "summary": "Compensation of 2.5 lakh within 60 days.",
            },
            {
                "ordered_on": sd.ago(70),
                "received_on": sd.ago(66),
                "kind": "costs",
                "amount": Decimal("25000"),
                "comply_by": sd.ago(10),
                "summary": "Costs of the proceedings.",
            },
        ),
        user_id=clerk,
    )
    sd.case(
        sg,
        at(64),
        forum="krera",
        number="CMP/DEMO/0290/2026",
        relief="delay_interest",
        status="settled",
        filed_on=sd.ago(120),
        notice_received_on=sd.ago(110),
        reply_filed_on=sd.ago(90),
        settlement_offered=lakh("1.6"),
        settlement_agreed=lakh("1.85"),
        closed_on=sd.ago(28),
        summary="Settled for interest for the delay; terms filed and the complaint withdrawn.",
        payments=((sd.ago(30), lakh("1.85"), "NEFT DEMO0290"),),
        user_id=clerk,
    )
    sd.case(
        wf,
        None,
        forum="civil_court",
        number="OS/DEMO/1123/2026",
        relief="other",
        status="hearing",
        complainant="M. Kumar (adjoining plot)",
        filed_on=sd.ago(60),
        notice_received_on=sd.ago(50),
        reply_due_on=sd.ago(20),
        reply_filed_on=sd.ago(30),
        next_hearing_on=sd.ahead(20),
        lawyer="S. Hegde and Associates",
        summary="Suit for an injunction over the boundary wall on the eastern side.",
        user_id=clerk,
    )
    session.commit()
    if storage is not None:
        seed_documents(session, storage, today, users)


DEMO_ROOM_TOKEN = "demo-sarjapur-finance-review"
"""Opens the demo data room at /shared/demo-sarjapur-finance-review."""


def _slug(title: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in title.lower()).split())


def seed_documents(session: Session, storage: Storage, today: date, users: dict[str, User]):
    """Each project's papers in the vault: most present, some missing, some about to lapse."""
    from lekhara import services

    uploader = users["accounts@demo.lekhara"].id

    def ago(n: int) -> date:
        return today - timedelta(days=n)

    def ahead(n: int) -> date:
        return today + timedelta(days=n)

    def add(p: Project, title: str, lines: list[str], **fields):
        data = write_pdf([[p.name, "", title, "", *lines]], title=title)
        return services.store_document(
            session,
            storage,
            p,
            data=data,
            filename=f"{_slug(title)}.pdf",
            fields={"title": title, **fields},
            max_bytes=20_000_000,
            user_id=uploader,
        )

    def papers(p: Project, *, skip: set[str], expiry: dict[str, date]) -> dict[str, str]:
        texts = {
            "krera_registration": [
                "Karnataka Real Estate Regulatory Authority",
                f"Registration number {p.krera_registration}",
                f"Promoter: {p.spv_name}",
                "Granted under section 5 of the Real Estate (Regulation and Development) "
                "Act, 2016.",
            ],
            "title_deed": [
                "Sale deed in favour of the landowners, with the mother deed.",
                "Schedule: land in survey numbers 41/2 and 42/1 (demo).",
                "The chain of title for thirty years is attached.",
            ],
            "encumbrance": [
                "Form 15. Encumbrance certificate for thirteen years.",
                "No encumbrance found in the period searched.",
            ],
            "jda": [
                "Joint development agreement between the landowners and the developer.",
                "The developer bears the cost of construction and approvals.",
                "Registered at the office of the sub-registrar.",
            ],
            "plan_sanction": [
                "Building plan sanction (demo).",
                "Sanction number LP/DEMO/2024.",
                "The sanction is valid for five years from the date of issue.",
            ],
            "commencement": [
                "Commencement certificate.",
                "Construction may begin as per the sanctioned plan.",
            ],
            "environmental": [
                "State Environment Impact Assessment Authority, Karnataka.",
                "Environmental clearance for a residential project.",
                "Built-up area 32,000 square metres.",
            ],
            "fire_noc": [
                "Karnataka State Fire and Emergency Services.",
                "No objection certificate for a high-rise residential building.",
                "Valid for two years from the date of issue.",
            ],
            "escrow_letter": [
                "Letter from the bank confirming the designated account.",
                "Account: RERA designated collection account (demo).",
                "70% of the amounts realised from allottees will be deposited here.",
            ],
            "insurance": [
                "Contractor's all-risk insurance policy.",
                "Sum insured: Rs. 180 crore (demo).",
                "Period of insurance: twelve months.",
            ],
            "oc": [
                "Occupancy certificate.",
                f"Reference {p.oc_reference}.",
                "Issued on completion of the building as per the sanctioned plan.",
            ],
        }
        ids = {}
        for key, lines in texts.items():
            if key in skip:
                continue
            doc = add(
                p,
                REQUIREMENTS[key].title,
                lines,
                requirement=key,
                document_date={"krera_registration": p.registered_on, "oc": p.oc_received_on}.get(
                    key, ago(400)
                ),
                expires_on=expiry.get(key),
                reference=p.krera_registration if key == "krera_registration" else None,
            )
            ids[key] = doc.id
        return ids

    wf = session.get(Project, "whitefield-residences")
    hb = session.get(Project, "hebbal-heights")
    sg = session.get(Project, "sarjapur-greens")

    # Whitefield: no encumbrance certificate yet; the insurance renews next month.
    old_policy = add(
        wf,
        "Contractor's all-risk insurance",
        ["Contractor's all-risk insurance policy.", "Period of insurance: twelve months."],
        requirement="insurance",
        document_date=ago(360),
        expires_on=ago(310),
    )
    papers(
        wf,
        skip={"encumbrance", "environmental", "oc", "insurance"},
        expiry={"plan_sanction": ahead(400), "fire_noc": ahead(300)},
    )
    add(
        wf,
        "Contractor's all-risk insurance",
        ["Contractor's all-risk insurance policy, renewed.", "Period of insurance: twelve months."],
        replaces=old_policy.id,
        document_date=ago(310),
        expires_on=ahead(50),
    )
    released = session.scalars(
        select(WithdrawalRequest).where(
            WithdrawalRequest.project_id == wf.id, WithdrawalRequest.released_on.is_not(None)
        )
    ).first()
    if released is not None:
        add(
            wf,
            "Signed certificates as sent to the bank",
            ["Form 1 (architect), Form 2 (engineer) and Form 3 (CA), signed."],
            category="certificate",
            link_type="withdrawal",
            link_id=released.id,
            document_date=released.submitted_on or released.created_on,
        )

    # Hebbal: the title deed is missing; the fire NOC runs out soon; no environmental clearance
    # is needed at this size.
    papers(
        hb,
        skip={"title_deed", "environmental", "jda", "oc"},
        expiry={"plan_sanction": ahead(700), "fire_noc": ahead(25), "insurance": ahead(200)},
    )
    session.add(
        ChecklistWaiver(
            project_id=hb.id,
            requirement="environmental",
            reason="Built-up area is about 18,400 square metres, under the 20,000 threshold.",
            waived_on=ago(300),
            waived_by_user_id=uploader,
        )
    )

    # Sarjapur: everything, including the OC; the insurance has lapsed.
    sg_ids = papers(
        sg,
        skip=set(),
        expiry={"plan_sanction": ahead(250), "fire_noc": ahead(500), "insurance": ago(5)},
    )
    units = {u.id: u for u in session.scalars(select(Unit).where(Unit.project_id == sg.id))}
    records = sorted(
        session.scalars(select(UnitHandover).where(UnitHandover.unit_id.in_(units))),
        key=lambda h: units[h.unit_id].label,
    )
    for h in [r for r in records if r.registered_on][:14]:
        label = units[h.unit_id].label
        add(
            sg,
            f"Sale deed, unit {label}",
            [f"Sale deed for unit {label}, registered as document {h.document_no}."],
            category="sale_deed",
            link_type="unit",
            link_id=h.unit_id,
            reference=h.document_no,
            document_date=h.registered_on,
        )
    for h in [r for r in records if r.ekhata_status == "final"][:32]:
        label = units[h.unit_id].label
        add(
            sg,
            f"e-Khata, unit {label}",
            [f"Final e-Khata for unit {label}.", f"Khata type: {h.khata_type or 'A'}."],
            category="ekhata",
            link_type="unit",
            link_id=h.unit_id,
            reference=f"KHATA/DEMO/{label}",
            document_date=ago(30),
        )
    refund = session.scalars(
        select(DisputeCase).where(DisputeCase.case_number == "CMP/DEMO/0377/2026")
    ).first()
    if refund is not None:
        add(
            sg,
            "K-RERA order, CMP/DEMO/0377/2026",
            [
                f"Complaint by {refund.complainant}.",
                "The promoter shall refund the amount paid by the complainant with interest at "
                "SBI MCLR plus 2% from the date of each payment until it is refunded.",
                "The refund shall be made within sixty days of this order.",
            ],
            category="order",
            link_type="case",
            link_id=refund.id,
            document_date=ago(25),
        )

    # A data room for a lender, opened twice.
    room, _ = services.create_room(
        session,
        sg,
        {
            "name": "Construction finance review",
            "audience": "Demo Capital, construction finance team",
            "expires_on": ahead(21),
            "document_ids": [
                sg_ids[k]
                for k in ("krera_registration", "title_deed", "jda", "plan_sanction", "oc")
            ],
        },
        as_of=today,
        user_id=users["promoter@demo.lekhara"].id,
    )
    room.token_hash = services._token_hash(DEMO_ROOM_TOKEN)
    room.created_on = ago(6)
    start = datetime.combine(ago(5), datetime.min.time())
    session.add_all(
        [
            DataRoomVisit(room_id=room.id, action="open", at=start + timedelta(hours=10)),
            DataRoomVisit(
                room_id=room.id,
                action="download",
                document_id=sg_ids["title_deed"],
                at=start + timedelta(hours=10, minutes=4),
            ),
            DataRoomVisit(room_id=room.id, action="open", at=start + timedelta(days=3, hours=16)),
        ]
    )
    session.commit()


def reset_and_seed(database_url: str, today: date, storage_dir: str | None = None) -> None:
    engine = make_engine(database_url)
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    upgrade(engine)
    storage = LocalStorage(storage_dir) if storage_dir else None
    with make_sessionmaker(engine)() as session:
        seed(session, today, storage)


def main() -> None:
    settings = get_settings()
    reset_and_seed(settings.database_url, settings.as_of(), settings.storage_dir)
    print(f"Demo data loaded into {settings.database_url} for {settings.as_of().isoformat()}.")


if __name__ == "__main__":
    main()
