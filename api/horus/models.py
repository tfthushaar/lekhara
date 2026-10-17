"""Database models.

Ledger entries and escrow account transactions are append-only: a correction is
a new reversing row, never an edit or a delete.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from horus.db import Base, Money, Percent


def _id() -> str:
    return uuid4().hex


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))

    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    locality: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    krera_registration: Mapped[str] = mapped_column(String(100))
    registered_on: Mapped[date] = mapped_column(Date)
    spv_name: Mapped[str] = mapped_column(String(200))
    gst_regime: Mapped[str] = mapped_column(String(32))
    land_structure: Mapped[str] = mapped_column(String(32))
    """own, jda_area_share or jda_revenue_share."""
    possession_due_on: Mapped[date | None] = mapped_column(Date)
    statutory_auditor_firm: Mapped[str | None] = mapped_column(String(200))
    escrow_bank: Mapped[str | None] = mapped_column(String(200))
    development_rights_value: Mapped[Decimal | None] = mapped_column(Money)
    cess_paid: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    oc_status: Mapped[str] = mapped_column(String(16), default="none", server_default="none")
    """none, applied, partial or received."""
    oc_received_on: Mapped[date | None] = mapped_column(Date)
    oc_reference: Mapped[str | None] = mapped_column(String(200))
    association_formed_on: Mapped[date | None] = mapped_column(Date)
    common_areas_conveyed_on: Mapped[date | None] = mapped_column(Date)

    organization: Mapped[Organization] = relationship(back_populates="projects")
    cost_lines: Mapped[list["CostLineRow"]] = relationship(
        back_populates="project", order_by="CostLineRow.position"
    )


class CostLineRow(Base):
    __tablename__ = "cost_lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32))
    rera_head: Mapped[str] = mapped_column(String(32))
    original_budget: Mapped[Decimal] = mapped_column(Money)
    revised_budget: Mapped[Decimal] = mapped_column(Money)
    position: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="cost_lines")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    cost_line_id: Mapped[str] = mapped_column(ForeignKey("cost_lines.id"))
    kind: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Money)
    entry_date: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProgressCertificate(Base):
    """Certified physical progress, consumed from the architect's or engineer's certificate."""

    __tablename__ = "progress_certificates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    completion_pct: Mapped[Decimal] = mapped_column(Percent)
    as_of: Mapped[date] = mapped_column(Date)
    certified_by: Mapped[str] = mapped_column(String(200))


class EscrowTxn(Base):
    __tablename__ = "escrow_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Money)
    txn_date: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(200))


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    registered: Mapped[bool] = mapped_column(Boolean)
    msme_category: Mapped[str] = mapped_column(String(16), default="none")
    written_agreement: Mapped[bool] = mapped_column(Boolean, default=True)


class Bill(Base):
    """A supplier's bill: feeds the 80% test and the MSME clock."""

    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"))
    bill_no: Mapped[str] = mapped_column(String(64))
    bill_date: Mapped[date] = mapped_column(Date)
    accepted_on: Mapped[date] = mapped_column(Date)
    taxable_value: Mapped[Decimal] = mapped_column(Money)
    is_cement: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    rcm_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_on: Mapped[date | None] = mapped_column(Date)

    vendor: Mapped[Vendor] = relationship()


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    label: Mapped[str] = mapped_column(String(32))
    tower: Mapped[str] = mapped_column(String(32))
    carpet_area_sqft: Mapped[int] = mapped_column(Integer)
    owner_share: Mapped[str] = mapped_column(String(16))
    """developer or landowner."""
    booked: Mapped[bool] = mapped_column(Boolean, default=False)
    list_price: Mapped[Decimal] = mapped_column(Money)
    agreement_value: Mapped[Decimal | None] = mapped_column(Money)
    guidance_value: Mapped[Decimal] = mapped_column(Money)
    buyer_name: Mapped[str | None] = mapped_column(String(200))
    booked_on: Mapped[date | None] = mapped_column(Date)


class Receipt(Base):
    """Money received from a buyer."""

    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    received_on: Mapped[date] = mapped_column(Date)
    tds_deducted: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))


class Landowner(Base):
    __tablename__ = "landowners"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    share_type: Mapped[str] = mapped_column(String(16))
    """area or revenue."""
    share_pct: Mapped[Decimal] = mapped_column(Percent)
    refundable_deposit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))

    payments: Mapped[list["LandownerPaymentRow"]] = relationship(
        back_populates="landowner", order_by="LandownerPaymentRow.paid_on"
    )


class LandownerPaymentRow(Base):
    __tablename__ = "landowner_payments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    landowner_id: Mapped[str] = mapped_column(ForeignKey("landowners.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    paid_on: Mapped[date] = mapped_column(Date)
    tds_deducted: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    monetary_consideration: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(200))

    landowner: Mapped[Landowner] = relationship(back_populates="payments")


class Filing(Base):
    """A filing made: a quarterly progress report or an annual project audit."""

    __tablename__ = "filings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    period_end: Mapped[date] = mapped_column(Date)
    filed_on: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(200))


class WithdrawalRequest(Base):
    __tablename__ = "withdrawal_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    created_on: Mapped[date] = mapped_column(Date)
    submitted_on: Mapped[date | None] = mapped_column(Date)
    released_on: Mapped[date | None] = mapped_column(Date)
    released_amount: Mapped[Decimal | None] = mapped_column(Money)
    bank_reference: Mapped[str | None] = mapped_column(String(200))
    rejected_on: Mapped[date | None] = mapped_column(Date)
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    submitted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    released_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    certificates: Mapped[list["WithdrawalCertificate"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )

    @property
    def is_open(self) -> bool:
        return self.released_on is None and self.rejected_on is None


class WithdrawalCertificate(Base):
    __tablename__ = "withdrawal_certificates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("withdrawal_requests.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    signed: Mapped[bool] = mapped_column(Boolean, default=False)
    signer_name: Mapped[str | None] = mapped_column(String(200))
    signer_firm: Mapped[str | None] = mapped_column(String(200))
    issued_on: Mapped[date | None] = mapped_column(Date)
    completion_pct: Mapped[Decimal | None] = mapped_column(Percent)
    development_cost_incurred: Mapped[Decimal | None] = mapped_column(Money)
    total_cost_incurred: Mapped[Decimal | None] = mapped_column(Money)
    withdrawable_amount: Mapped[Decimal | None] = mapped_column(Money)
    signed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    request: Mapped[WithdrawalRequest] = relationship(back_populates="certificates")


# Collections


class PaymentMilestone(Base):
    """One step of a project's payment plan."""

    __tablename__ = "payment_milestones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    share_pct: Mapped[Decimal] = mapped_column(Percent)
    trigger: Mapped[str] = mapped_column(String(16))
    """booking, agreement, progress or possession."""
    progress_pct: Mapped[Decimal | None] = mapped_column(Percent)
    due_days: Mapped[int] = mapped_column(Integer, default=15)


class DemandRow(Base):
    """A demand raised on a buyer for one milestone."""

    __tablename__ = "demands"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"), index=True)
    milestone_id: Mapped[str] = mapped_column(ForeignKey("payment_milestones.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    gst: Mapped[Decimal] = mapped_column(Money)
    raised_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    certified_progress_pct: Mapped[Decimal | None] = mapped_column(Percent)
    """The certified progress that triggered the demand, if a stage triggered it."""
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


# Registration and handover


class UnitHandover(Base):
    """Where one unit stands on the way from booking to a registered, handed-over home."""

    __tablename__ = "unit_handovers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"), unique=True, index=True)
    ekhata_status: Mapped[str] = mapped_column(String(16), default="none")
    """none, applied, draft or final."""
    khata_type: Mapped[str | None] = mapped_column(String(1))
    """A or B."""
    deed_drafted_on: Mapped[date | None] = mapped_column(Date)
    appointment_on: Mapped[date | None] = mapped_column(Date)
    registered_on: Mapped[date | None] = mapped_column(Date)
    document_no: Mapped[str | None] = mapped_column(String(64))
    possession_on: Mapped[date | None] = mapped_column(Date)
    updated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


# People and access


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    firm: Mapped[str | None] = mapped_column(String(200))
    """The certifier's firm, printed on every certificate they sign."""
    phone: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")
    project_access: Mapped[list["ProjectAccess"]] = relationship(back_populates="user")


class Membership(Base):
    """A member of the developer's own team: owner, finance, accounts or viewer."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))

    user: Mapped[User] = relationship(back_populates="memberships")


class ProjectAccess(Base):
    """An outside person's access to one project: today the architect, engineer or CA."""

    __tablename__ = "project_access"
    __table_args__ = (UniqueConstraint("user_id", "project_id", "role"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))

    user: Mapped[User] = relationship(back_populates="project_access")


class UserSession(Base):
    """A signed-in session. Only a hash of the token is stored."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AppendOnlyViolation(RuntimeError):
    pass


def _forbid(_mapper, _connection, target) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} rows are append-only; add a reversing entry instead"
    )


for _model in (LedgerEntry, EscrowTxn):
    event.listen(_model, "before_update", _forbid)
    event.listen(_model, "before_delete", _forbid)
