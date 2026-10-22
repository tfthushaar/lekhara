"""Database models.

Ledger entries and escrow account transactions are append-only: a correction is
a new reversing row, never an edit or a delete.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lekhara.db import Base, Money, Percent


def _id() -> str:
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Organization(Base):
    """A builder firm: one workspace and one subscription."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    created_on: Mapped[date | None] = mapped_column(Date)
    access: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    """trial, active (paid) or suspended."""
    trial_ends_on: Mapped[date | None] = mapped_column(Date)
    paid_until: Mapped[date | None] = mapped_column(Date)
    """The last day paid for; None for a firm that is active with no end (the demo, pilots)."""
    require_two_step: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    """Everyone in the firm must use two-step sign-in, as its owner decided."""
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    """The sample projects every signed-in person can look at, read-only."""
    closing_on: Mapped[date | None] = mapped_column(Date)
    """When an owner asked to close the firm's account; its data is deleted after a wait."""
    delete_after: Mapped[date | None] = mapped_column(Date)

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
    mail_token: Mapped[str | None] = mapped_column(String(32), unique=True)
    """The project's own forwarding address is <mail_token>@ the inbound domain."""

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
    pan: Mapped[str | None] = mapped_column(String(10))
    state: Mapped[str | None] = mapped_column(String(64))
    udyam_number: Mapped[str | None] = mapped_column(String(32))


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
    gst_amount: Mapped[Decimal | None] = mapped_column(Money)
    source_ref: Mapped[str | None] = mapped_column(String(200), index=True)
    """Where the bill came from, such as a Tally voucher, so it is never brought in twice."""
    cost_line_id: Mapped[str | None] = mapped_column(ForeignKey("cost_lines.id"))
    """For a bill typed in or imported from a sheet: the cost line it is cost incurred against.
    Bills from Tally leave it empty, since Tally's ledgers carry their cost."""

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
    buyer_phone: Mapped[str | None] = mapped_column(String(32))
    buyer_email: Mapped[str | None] = mapped_column(String(320))
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
    reference: Mapped[str | None] = mapped_column(String(200))
    """UTR, cheque or receipt number."""
    source_ref: Mapped[str | None] = mapped_column(String(200), index=True)
    cancellation_id: Mapped[str | None] = mapped_column(
        ForeignKey("booking_cancellations.id"), index=True
    )
    """Set when the booking it was paid for was cancelled: it stays in the project's money,
    but no longer counts towards the unit's current buyer."""


class Landowner(Base):
    __tablename__ = "landowners"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    share_type: Mapped[str] = mapped_column(String(16))
    """area or revenue."""
    share_pct: Mapped[Decimal] = mapped_column(Percent)
    refundable_deposit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    pan: Mapped[str | None] = mapped_column(String(10))

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
    source_ref: Mapped[str | None] = mapped_column(String(200), index=True)

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


class Approval(Base):
    """An approval, consent or no-objection certificate the project needs: when it was applied
    for, when it was granted and until when it holds."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    authority: Mapped[str | None] = mapped_column(String(200))
    reference: Mapped[str | None] = mapped_column(String(200))
    applied_on: Mapped[date | None] = mapped_column(Date)
    granted_on: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500))


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
    cancellation_id: Mapped[str | None] = mapped_column(
        ForeignKey("booking_cancellations.id"), index=True
    )
    """Set when the booking it was raised on was cancelled."""


class BookingCancellation(Base):
    """A booking that was cancelled: who the buyer was, what was refunded and why. The buyer's
    demands and payments point here, so the unit can be sold again."""

    __tablename__ = "booking_cancellations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"), index=True)
    cancelled_on: Mapped[date] = mapped_column(Date)
    buyer_name: Mapped[str | None] = mapped_column(String(200))
    booked_on: Mapped[date | None] = mapped_column(Date)
    agreement_value: Mapped[Decimal | None] = mapped_column(Money)
    refunded: Mapped[Decimal | None] = mapped_column(Money)
    refunded_on: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(500))
    case_id: Mapped[str | None] = mapped_column(ForeignKey("dispute_cases.id"))
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class HandoverItem(Base):
    """One item of handing the project over to the residents' association: done when, and a
    note."""

    __tablename__ = "handover_items"
    __table_args__ = (UniqueConstraint("project_id", "key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(48))
    done_on: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500))


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


# Disputes and orders


class DisputeCase(Base):
    """A case brought against a project: at K-RERA, a consumer commission or a court."""

    __tablename__ = "dispute_cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"))
    forum: Mapped[str] = mapped_column(String(32))
    case_number: Mapped[str] = mapped_column(String(100))
    relief: Mapped[str] = mapped_column(String(32))
    complainant: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(2000))
    claim_amount: Mapped[Decimal | None] = mapped_column(Money)
    filed_on: Mapped[date | None] = mapped_column(Date)
    notice_received_on: Mapped[date | None] = mapped_column(Date)
    reply_due_on: Mapped[date | None] = mapped_column(Date)
    reply_filed_on: Mapped[date | None] = mapped_column(Date)
    next_hearing_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="notice")
    lawyer: Mapped[str | None] = mapped_column(String(200))
    settlement_offered: Mapped[Decimal | None] = mapped_column(Money)
    settlement_agreed: Mapped[Decimal | None] = mapped_column(Money)
    appealed_on: Mapped[date | None] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    updated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    hearings: Mapped[list["DisputeHearing"]] = relationship(order_by="DisputeHearing.held_on")
    orders: Mapped[list["DisputeOrder"]] = relationship(order_by="DisputeOrder.ordered_on")
    payments: Mapped[list["DisputePayment"]] = relationship(order_by="DisputePayment.paid_on")


class DisputeHearing(Base):
    __tablename__ = "dispute_hearings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("dispute_cases.id"), index=True)
    held_on: Mapped[date] = mapped_column(Date)
    purpose: Mapped[str] = mapped_column(String(200))
    outcome: Mapped[str | None] = mapped_column(String(1000))
    recorded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class DisputeOrder(Base):
    __tablename__ = "dispute_orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("dispute_cases.id"), index=True)
    ordered_on: Mapped[date] = mapped_column(Date)
    received_on: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal | None] = mapped_column(Money)
    """A fixed sum. Empty for refund and delay-interest orders, which Lekhara works out."""
    comply_by: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(String(2000))
    recorded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class DisputePayment(Base):
    """Money the developer paid under an order or a settlement."""

    __tablename__ = "dispute_payments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("dispute_cases.id"), index=True)
    paid_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    reference: Mapped[str | None] = mapped_column(String(200))
    recorded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


# Document vault


class Document(Base):
    """One version of a document. Versions of the same document share a family id."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(200))
    document_date: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(200))
    """The number on the document: an approval, policy or registration number."""
    notes: Mapped[str | None] = mapped_column(String(2000))
    requirement: Mapped[str | None] = mapped_column(String(64))
    """The checklist item this document answers, if any."""
    link_type: Mapped[str | None] = mapped_column(String(16))
    link_id: Mapped[str | None] = mapped_column(String(64), index=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    text_status: Mapped[str] = mapped_column(String(16), default="no_text")
    """text, no_text or unreadable."""
    archived_on: Mapped[date | None] = mapped_column(Date)
    filed_by: Mapped[str | None] = mapped_column(String(100))
    """The filing rule that chose its kind, when no person did."""
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DocumentPage(Base):
    """The text of one page, for search with page citations."""

    __tablename__ = "document_pages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class ChecklistWaiver(Base):
    """A checklist item the project does not need, and why."""

    __tablename__ = "checklist_waivers"
    __table_args__ = (UniqueConstraint("project_id", "requirement"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    requirement: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500))
    waived_on: Mapped[date] = mapped_column(Date)
    waived_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class DataRoom(Base):
    """Documents shared outside the company through a link that expires. Only a hash of the
    link's token is stored."""

    __tablename__ = "data_rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    audience: Mapped[str | None] = mapped_column(String(200))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    revoked_on: Mapped[date | None] = mapped_column(Date)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    ask_visitor: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    """Ask everyone who opens the link for their name and email first."""

    entries: Mapped[list["DataRoomDocument"]] = relationship(cascade="all, delete-orphan")
    visits: Mapped[list["DataRoomVisit"]] = relationship(order_by="DataRoomVisit.at.desc()")


class DataRoomDocument(Base):
    __tablename__ = "data_room_documents"
    __table_args__ = (UniqueConstraint("room_id", "family_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("data_rooms.id"), index=True)
    family_id: Mapped[str] = mapped_column(String(64))
    """The room shows the latest version of the document."""


class DataRoomVisit(Base):
    __tablename__ = "data_room_visits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("data_rooms.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    action: Mapped[str] = mapped_column(String(16))
    """open or download."""
    document_id: Mapped[str | None] = mapped_column(String(64))
    visitor_id: Mapped[str | None] = mapped_column(ForeignKey("data_room_visitors.id"))


class DataRoomVisitor(Base):
    """Someone who gave their name and email to open a data room, and confirmed the email with
    a code sent to it. Only a hash of the token their browser keeps is stored."""

    __tablename__ = "data_room_visitors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("data_rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64))
    code_hash: Mapped[str | None] = mapped_column(String(64))
    """The code emailed to them, hashed; the room opens once it is entered."""
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    code_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)


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
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    two_step_on: Mapped[datetime | None] = mapped_column(DateTime)
    """When two-step sign-in with an authenticator app was turned on; None while it is off."""
    totp_secret: Mapped[str | None] = mapped_column(String(300))
    """The authenticator app's shared secret, sealed with the server's key."""
    totp_pending: Mapped[str | None] = mapped_column(String(300))
    totp_last_step: Mapped[int | None] = mapped_column(Integer)
    """The time step of the last code accepted, so a code cannot be used twice."""
    recovery_codes: Mapped[str | None] = mapped_column(Text)
    """Hashes of the unused recovery codes, as JSON."""
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    """Works for Lekhara and may open the admin console (set with `python -m lekhara.staff`)."""

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
    support_org_id: Mapped[str | None] = mapped_column(String(64))
    """Set on a support session: Lekhara staff seeing this firm, read-only, with its consent."""
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    """When the person last proved it was them (signing in counts): sensitive steps need it
    to be recent."""
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class OneTimeToken(Base):
    """A link sent by email to confirm an address or reset a password. Only its hash is kept."""

    __tablename__ = "one_time_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    """verify_email or reset_password."""
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class Invitation(Base):
    """An invitation to join a firm's team, or to certify some of its projects."""

    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    org_role: Mapped[str | None] = mapped_column(String(16))
    certifier_role: Mapped[str | None] = mapped_column(String(16))
    project_ids: Mapped[str | None] = mapped_column(String(2000))
    """Comma-separated, for certifiers."""
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)


class OutboundEmail(Base):
    """Every email Lekhara sends, kept as a record of what was sent and whether it went."""

    __tablename__ = "outbound_emails"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    to_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(String(500))


class ImportBatch(Base):
    """One file brought in through the Import centre: previewed, then applied, then perhaps
    undone."""

    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(300))
    origin: Mapped[str] = mapped_column(String(16), default="file", server_default="file")
    recognised: Mapped[str | None] = mapped_column(String(100))
    """The system the file came from, when Lekhara recognises its layout (such as Sell.Do)."""
    """file, for a spreadsheet brought in, or table, for rows edited as a table in Lekhara."""
    status: Mapped[str] = mapped_column(String(16), default="preview")
    """preview, applied or undone."""
    headers: Mapped[str] = mapped_column(Text)
    header_row: Mapped[int] = mapped_column(Integer)
    rows: Mapped[str] = mapped_column(Text)
    mapping: Mapped[str] = mapped_column(Text)
    """Column index to field key, as JSON."""
    result: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime)


class ImportMapping(Base):
    """How a firm's file with these headers maps to Lekhara's fields, remembered for next
    time."""

    __tablename__ = "import_mappings"
    __table_args__ = (UniqueConstraint("organization_id", "kind", "signature"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    signature: Mapped[str] = mapped_column(String(64))
    mapping: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChangeEntry(Base):
    """One change to one record: who, when, from where, and each field before and after."""

    __tablename__ = "change_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    record_type: Mapped[str] = mapped_column(String(32))
    record_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(16))
    """created, updated or deleted."""
    changes: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))
    """typed, import or undo."""
    import_batch_id: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TallyImport(Base):
    """A file exported from Tally: reviewed, then applied, then perhaps undone."""

    __tablename__ = "tally_imports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    file_kind: Mapped[str] = mapped_column(String(16))
    """xml, json, xlsx or text."""
    source: Mapped[str] = mapped_column(String(32))
    """xml, json, or the kind of report."""
    storage_key: Mapped[str] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="review")
    """review, applied or undone."""
    options: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime)


class TallyLink(Base):
    """What a Tally ledger stands for in a project, chosen by the builder and remembered: a
    buyer's unit, a cost line, the RERA designated account, a landowner, or nothing."""

    __tablename__ = "tally_links"
    __table_args__ = (UniqueConstraint("project_id", "ledger"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    ledger: Mapped[str] = mapped_column(String(200))
    """The ledger's name, lowercased with single spaces."""
    ledger_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(16), default="unit", server_default="unit")
    """unit, cost_line, rera_account, landowner or ignore."""
    target_id: Mapped[str | None] = mapped_column(String(64))
    """The unit, cost line or landowner the ledger stands for."""
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BankAccount(Base):
    """A bank account whose statements come into a project, and what it is: the RERA
    designated account, or the account buyers pay into. Chosen once, then recognised."""

    __tablename__ = "bank_accounts"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    number: Mapped[str] = mapped_column(String(32))
    """The account number as the statement prints it, digits and any masking."""
    bank: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16))
    """rera (the designated account) or collections (where buyers pay)."""
    buyers_pay_here: Mapped[bool] = mapped_column(Boolean, default=False)
    """For the RERA account: buyers pay straight into it, so its credits are their payments."""
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BankStatement(Base):
    """A statement exported from net banking: reviewed, then applied, then perhaps undone."""

    __tablename__ = "bank_statements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(String(200))
    bank: Mapped[str | None] = mapped_column(String(100))
    account_number: Mapped[str | None] = mapped_column(String(32))
    period_from: Mapped[date | None] = mapped_column(Date)
    period_to: Mapped[date | None] = mapped_column(Date)
    lines: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="review")
    """review, applied or undone."""
    options: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime)


class BankPayer(Base):
    """Who a payer on a bank statement is, chosen by the builder once and remembered: a
    buyer's unit, or not a buyer at all."""

    __tablename__ = "bank_payers"
    __table_args__ = (UniqueConstraint("project_id", "payer"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    payer: Mapped[str] = mapped_column(String(200))
    """The payer's name, lowercased with single spaces."""
    payer_name: Mapped[str] = mapped_column(String(200), default="")
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"))
    """None when the payer is not a buyer."""
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Commitment(Base):
    """A work order, purchase order or contract committing the project to spend on a cost line.
    Its amount is mirrored in the append-only ledger as a commitment."""

    __tablename__ = "commitments"
    __table_args__ = (UniqueConstraint("project_id", "reference"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    cost_line_id: Mapped[str] = mapped_column(ForeignKey("cost_lines.id"))
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"))
    reference: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300))
    amount: Mapped[Decimal] = mapped_column(Money)
    committed_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TrustedSender(Base):
    """An address whose emails to a firm's projects are brought in without asking, besides the
    firm's own team: a bank's statement service, the accountant, a contractor."""

    __tablename__ = "trusted_senders"
    __table_args__ = (UniqueConstraint("organization_id", "address"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    address: Mapped[str] = mapped_column(String(320))
    """Lower case; a whole domain is written as @bank.example."""
    added_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StatementPassword(Base):
    """A password a bank puts on the statements it emails, given once so Lekhara can open them.
    Kept sealed with the server's secret key; never shown again."""

    __tablename__ = "statement_passwords"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    """Which account or bank it is for, in the firm's words."""
    sealed: Mapped[str] = mapped_column(Text)
    added_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InboundMessage(Base):
    """An email that reached a project's forwarding address."""

    __tablename__ = "inbound_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    from_address: Mapped[str] = mapped_column(String(320))
    from_name: Mapped[str | None] = mapped_column(String(200))
    subject: Mapped[str | None] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(200))
    """The whole email as received."""
    trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    """queued, held (waiting for a team member to allow it), done, rejected or failed."""
    note: Mapped[str | None] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class InboundItem(Base):
    """One file in an inbound email, and what became of it."""

    __tablename__ = "inbound_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    message_id: Mapped[str] = mapped_column(ForeignKey("inbound_messages.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str | None] = mapped_column(String(32))
    """tally, bank_statement, sheet, document or unknown, once looked at."""
    status: Mapped[str] = mapped_column(String(16), default="queued")
    """queued, done (brought in), review (waiting for a choice), ignored or failed."""
    note: Mapped[str | None] = mapped_column(String(500))
    result_type: Mapped[str | None] = mapped_column(String(32))
    """tally_import, bank_statement, import_batch or document."""
    result_id: Mapped[str | None] = mapped_column(String(64))


class Connector(Base):
    """A program on the builder's own computer that feeds a project by itself: today, the
    Lekhara Connector for Tally. Linked once with a short code; it then signs in with its own
    key, which only ever lets it send data to this project."""

    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="tally")
    name: Mapped[str | None] = mapped_column(String(200))
    """The computer's name, as the connector reports it."""
    status: Mapped[str] = mapped_column(String(16), default="pending")
    """pending (waiting for its code), active or unlinked."""
    code_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    key_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    company: Mapped[str | None] = mapped_column(String(200))
    """The Tally company it reads."""
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_state: Mapped[str | None] = mapped_column(String(300))
    """What the connector said last: Tally not running, a company not open, an error."""
    last_import_id: Mapped[str | None] = mapped_column(String(64))
    last_hash: Mapped[str | None] = mapped_column(String(64))
    masters_key: Mapped[str | None] = mapped_column(String(200))
    """The latest masters it sent, kept to read later vouchers against."""
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GstImport(Base):
    """A GSTR-2B (or GSTR-2A) downloaded from the GST portal: the suppliers' invoices the GST
    system holds for the firm, checked against the project's bills."""

    __tablename__ = "gst_imports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(String(200))
    form: Mapped[str] = mapped_column(String(16), default="GSTR-2B")
    gstin: Mapped[str | None] = mapped_column(String(15))
    """Whose return it is: the firm's GSTIN, as the file says."""
    period: Mapped[str | None] = mapped_column(String(16))
    """The return period, as MMYYYY."""
    invoices: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="review")
    """review, applied or undone."""
    options: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime)


class Acceptance(Base):
    """A person accepting a version of Lekhara's terms, privacy notice or data processing
    terms. Kept as evidence, so it survives the person's account being deleted."""

    __tablename__ = "acceptances"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    organization_id: Mapped[str | None] = mapped_column(String(64))
    document: Mapped[str] = mapped_column(String(32))
    """terms, privacy or data_processing."""
    version: Mapped[str] = mapped_column(String(32))
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64))


class AccessEvent(Base):
    """A sign-in, an export, a download, a change to who may do what: kept at least 180 days
    (CERT-In), and on its own, so it outlives the people and firms it names."""

    __tablename__ = "access_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64))
    who: Mapped[str | None] = mapped_column(String(320))
    """The person's email at the time, for reading the log later."""
    action: Mapped[str] = mapped_column(String(48))
    detail: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    seq: Mapped[int | None] = mapped_column(Integer, index=True)
    """Its place in the chain: each event carries a hash of itself and of the one before, so
    an event changed or taken out later breaks the chain (see legal.verify_log)."""
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str | None] = mapped_column(String(64))


class Job(Base):
    """Work done in the background: an email to read, a mailbox to check."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    """queued, running, done or failed."""
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class AppendOnlyViolation(RuntimeError):
    pass


def _forbid(_mapper, _connection, target) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} rows are append-only; add a reversing entry instead"
    )


for _model in (LedgerEntry, EscrowTxn, DisputePayment, DataRoomVisit, ChangeEntry):
    event.listen(_model, "before_update", _forbid)
    event.listen(_model, "before_delete", _forbid)


class SupportGrant(Base):
    """A firm's consent for Lekhara support to see its workspace, read-only, until a time."""

    __tablename__ = "support_grants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    granted_by: Mapped[str] = mapped_column(String(64))
    granted_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime)
    withdrawn_by: Mapped[str | None] = mapped_column(String(64))


class SubscriptionPayment(Base):
    """A payment for a firm's subscription, recorded by us for now (a bank transfer, a cheque).
    Kept when a firm's data is deleted, as the record of what was paid, so it names the firm
    rather than pointing at it."""

    __tablename__ = "subscription_payments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(String(64), index=True)
    firm_name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Money)
    """Rupees received, GST included."""
    paid_on: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(24))
    reference: Mapped[str] = mapped_column(String(120))
    covers_from: Mapped[date] = mapped_column(Date)
    covers_to: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[str] = mapped_column(String(320))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Passkey(Base):
    """A passkey: a key pair held by the person's phone or computer, unlocked by its own lock.
    Only the public half is kept."""

    __tablename__ = "passkeys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    credential_id: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)


class PasskeyChallenge(Base):
    """A one-time challenge for adding a passkey or signing in with one, kept a few minutes."""

    __tablename__ = "passkey_challenges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    challenge: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AccessLogHead(Base):
    """The end of the access log's chain: the last event's place and hash."""

    __tablename__ = "access_log_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    hash: Mapped[str] = mapped_column(String(64), default="")


class RateLimitEvent(Base):
    """One counted attempt, for limits shared by every API server. The key (an email or an
    address) is kept only as a hash."""

    __tablename__ = "rate_limit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    bucket: Mapped[str] = mapped_column(String(32))
    key_hash: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    __table_args__ = (Index("ix_rate_limit_events_bucket_key", "bucket", "key_hash"),)


class IntegrityCheck(Base):
    """One run of the nightly check that every stored file is there and unchanged."""

    __tablename__ = "integrity_checks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    checked: Mapped[int] = mapped_column(Integer)
    missing: Mapped[int] = mapped_column(Integer)
    altered: Mapped[int] = mapped_column(Integer)
    problems: Mapped[str] = mapped_column(Text)
    """The files found missing or altered, as JSON (the first 200)."""


class FilingRule(Base):
    """A firm's rule for filing documents: words to look for, how, and what kind of document
    (and which checklist item) a document containing them is."""

    __tablename__ = "filing_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    words: Mapped[str] = mapped_column(String(200))
    how: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(32))
    requirement: Mapped[str | None] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Original(Base):
    """A paper original (a title deed, the sanctioned plan, a sale deed) and where it is now.
    Its number goes on a barcode label on its folder."""

    __tablename__ = "originals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    number: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(32))
    document_family_id: Mapped[str | None] = mapped_column(String(64))
    """Its scan in the vault, if there is one."""
    held_at: Mapped[str] = mapped_column(String(16))
    held_by: Mapped[str | None] = mapped_column(String(200))
    since: Mapped[date] = mapped_column(Date)
    against: Mapped[str | None] = mapped_column(String(200))
    """What it is held against, such as a loan."""
    note: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("organization_id", "number"),)


class OriginalMove(Base):
    """Where an original went, when, and who recorded it."""

    __tablename__ = "original_moves"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    original_id: Mapped[str] = mapped_column(ForeignKey("originals.id"), index=True)
    held_at: Mapped[str] = mapped_column(String(16))
    held_by: Mapped[str | None] = mapped_column(String(200))
    since: Mapped[date] = mapped_column(Date)
    against: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[str | None] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
