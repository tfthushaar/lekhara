"""Demo data: a fictional developer with three Bengaluru projects.

Every date is relative to `today`, so the demo always looks current. The three
projects are built to show each part of Horus:

- Whitefield Residences: JDA area share. Money waiting in the RERA account,
  close to the 80% supplier limit, GST on development rights to plan for, two
  sales below guidance value, an MSME bill due soon.
- Hebbal Heights: own land. Spending ahead of certified progress, deposits
  short, below the 80% supplier minimum, a late quarterly report, an overdue
  MSME payment, labour cess outstanding.
- Sarjapur Greens: JDA revenue share, nearly complete. Possession is late, the
  annual audit is overdue, TDS short on a landowner payment, overruns beyond
  contingency, and a withdrawal waiting for the CA's signature.

Run: python -m horus.seed   (resets the database first)
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from horus.config import get_settings
from horus.db import Base, make_engine, make_sessionmaker
from horus.engines.tax import financial_year
from horus.models import (
    Bill,
    CostLineRow,
    EscrowTxn,
    Filing,
    Landowner,
    LandownerPaymentRow,
    LedgerEntry,
    Organization,
    ProgressCertificate,
    Project,
    Receipt,
    Unit,
    Vendor,
    WithdrawalCertificate,
    WithdrawalRequest,
)

CR = Decimal("10000000")
LAKH = Decimal("100000")


def cr(x: str) -> Decimal:
    return (Decimal(x) * CR).quantize(Decimal("0.01"))


def lakh(x: str) -> Decimal:
    return (Decimal(x) * LAKH).quantize(Decimal("0.01"))


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
        self.org = Organization(id="demo", name="Demo Builders")
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
            self._entries(p, line.id, "commitment", cr(spec.committed), [span - 30])
            # Spread incurred and paid over time so point-in-time positions are meaningful.
            offsets = [int(span * 0.8), int(span * 0.5), int(span * 0.2), 20]
            self._entries(p, line.id, "incurred", cr(spec.incurred), offsets)
            self._entries(p, line.id, "paid", cr(spec.paid), [o - 10 for o in offsets])
            if spec.category == "construction" and Decimal(spec.incurred) > 0:
                held = (cr(spec.incurred) * Decimal("0.05")).quantize(Decimal("0.01"))
                self._entries(p, line.id, "retention_held", held, [20])

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
        collected_share: Decimal,
        below_guidance: int = 0,
    ) -> Decimal:
        """Creates units and buyer receipts. Returns total receipts."""
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
        for u in developer_units[:booked_count]:
            paid = (u.agreement_value * collected_share).quantize(Decimal("1"))
            first = (paid * Decimal("0.3")).quantize(Decimal("1"))
            for amount, when in ((first, u.booked_on), (paid - first, self.ago(25))):
                self.s.add(
                    Receipt(
                        project_id=p.id,
                        unit_id=u.id,
                        amount=amount,
                        received_on=max(when, u.booked_on),
                        tds_deducted=(amount * Decimal("0.01")).quantize(Decimal("1"))
                        if u.agreement_value > Decimal("5000000")
                        else Decimal("0"),
                    )
                )
            total += paid
        return total

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
        deposits = (receipts * Decimal("0.70")).quantize(Decimal("0.01")) - deposit_short
        withdrawn = deposits + interest - balance
        self.s.add(
            EscrowTxn(project_id=p.id, kind="deposit", amount=deposits, txn_date=self.ago(30))
        )
        self.s.add(
            EscrowTxn(project_id=p.id, kind="interest", amount=interest, txn_date=self.ago(15))
        )
        earlier = (withdrawn * Decimal("0.75")).quantize(Decimal("0.01"))
        self.s.add(
            EscrowTxn(
                project_id=p.id,
                kind="withdrawal",
                amount=earlier,
                txn_date=self.ago(last_withdrawal_days + 120),
                reference="Earlier withdrawals",
            )
        )
        last = withdrawn - earlier
        self.s.add(
            EscrowTxn(
                project_id=p.id,
                kind="withdrawal",
                amount=last,
                txn_date=self.ago(last_withdrawal_days),
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
        previous_end = fy_start - timedelta(days=1)
        if audit_done and previous_end > p.registered_on:
            self.s.add(
                Filing(
                    project_id=p.id,
                    kind="annual_audit",
                    period_end=previous_end,
                    filed_on=min(previous_end + timedelta(days=150), self.today),
                    reference=f"Audit FY ending {previous_end.isoformat()}",
                )
            )


def seed(session: Session, today: date) -> None:
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
        collected_share=Decimal("0.62"),
        below_guidance=2,
    )
    last = sd.escrow(
        wf,
        receipts,
        deposit_short=Decimal("0"),
        interest=lakh("60"),
        balance=cr("6.4"),
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
    session.flush()
    released = WithdrawalRequest(
        project_id=wf.id,
        amount=last,
        created_on=sd.ago(95),
        submitted_on=sd.ago(88),
        released_on=sd.ago(80),
        released_amount=last,
        bank_reference="Last withdrawal",
    )
    for role, firm in (
        ("architect", "Studio Kaveri Architects"),
        ("engineer", "Sound Structures Consultants"),
        ("ca", "Menon and Associates"),
    ):
        released.certificates.append(
            WithdrawalCertificate(
                role=role,
                signed=True,
                signer_name="Signed",
                signer_firm=firm,
                issued_on=sd.ago(92),
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
        collected_share=Decimal("0.38"),
    )
    sd.escrow(
        hb,
        receipts,
        deposit_short=cr("1.8"),
        interest=lakh("20"),
        balance=cr("4.1"),
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
    receipts = sd.units(
        sg,
        towers=["A", "B", "C"],
        per_tower=40,
        landowner_share=Decimal("0"),
        booked_share=Decimal("0.88"),
        price_per_sqft=8800,
        guidance_per_sqft=7200,
        collected_share=Decimal("0.90"),
        below_guidance=1,
    )
    sd.escrow(
        sg,
        receipts,
        deposit_short=Decimal("0"),
        interest=cr("1.1"),
        balance=cr("5.7"),
        last_withdrawal_days=70,
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

    # An open withdrawal on Sarjapur Greens, waiting for the CA.
    session.flush()
    from horus import services

    request = services.create_withdrawal(session, sg, None, today)
    request.created_on = sd.ago(3)
    for row in request.certificates:
        if row.role == "architect":
            row.signed, row.signer_name, row.signer_firm = (
                True,
                "A. Kulkarni",
                "Studio Kaveri Architects",
            )
            row.issued_on = sd.ago(2)
        elif row.role == "engineer":
            row.signed, row.signer_name, row.signer_firm = (
                True,
                "R. Hegde",
                "Sound Structures Consultants",
            )
            row.issued_on = sd.ago(1)
    session.commit()


def reset_and_seed(database_url: str, today: date) -> None:
    engine = make_engine(database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with make_sessionmaker(engine)() as session:
        seed(session, today)


def main() -> None:
    settings = get_settings()
    reset_and_seed(settings.database_url, settings.as_of())
    print(f"Demo data loaded into {settings.database_url} for {settings.as_of().isoformat()}.")


if __name__ == "__main__":
    main()
