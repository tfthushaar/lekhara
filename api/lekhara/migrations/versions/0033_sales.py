"""sales: leads, site visits, holds, price lists, bookings, channel partners and commissions

Revision ID: d5f2b8c41e67
Revises: c8e1a5f27b04
Create Date: 2026-11-06 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import lekhara.db

revision: str = "d5f2b8c41e67"
down_revision: str | None = "c8e1a5f27b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(length=64)


def _index(table: str, *columns: str, unique: bool = False) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column], unique=unique)


def upgrade() -> None:
    op.create_table(
        "channel_partners",
        sa.Column("id", ID, nullable=False),
        sa.Column("organization_id", ID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("firm", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("krera_number", sa.String(length=100), nullable=True),
        sa.Column("krera_valid_until", sa.Date(), nullable=True),
        sa.Column("commission_pct", lekhara.db.Percent(), nullable=False),
        sa.Column("payable_after_pct", lekhara.db.Percent(), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("pan", sa.String(length=10), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("channel_partners", "organization_id")
    op.create_table(
        "leads",
        sa.Column("id", ID, nullable=False),
        sa.Column("organization_id", ID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("phone_key", sa.String(length=10), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("partner_id", ID, sa.ForeignKey("channel_partners.id"), nullable=True),
        sa.Column("interest", sa.String(length=200), nullable=True),
        sa.Column("budget", lekhara.db.Money(), nullable=True),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("owner_user_id", ID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("next_follow_up_on", sa.Date(), nullable=True),
        sa.Column("lost_reason", sa.String(length=300), nullable=True),
        sa.Column("unit_id", ID, sa.ForeignKey("units.id"), nullable=True),
        sa.Column("created_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("leads", "organization_id", "project_id", "phone_key")
    op.create_table(
        "lead_activities",
        sa.Column("id", ID, nullable=False),
        sa.Column("lead_id", ID, sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("user_id", ID, sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("lead_activities", "lead_id")
    op.create_table(
        "site_visits",
        sa.Column("id", ID, nullable=False),
        sa.Column("lead_id", ID, sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("on", sa.Date(), nullable=False),
        sa.Column("time", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("site_visits", "lead_id", "project_id")
    op.create_table(
        "unit_holds",
        sa.Column("id", ID, nullable=False),
        sa.Column("unit_id", ID, sa.ForeignKey("units.id"), nullable=False),
        sa.Column("lead_id", ID, sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("until", sa.DateTime(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("unit_holds", "unit_id", "lead_id")
    op.create_table(
        "price_lists",
        sa.Column("id", ID, nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("base_rate", lekhara.db.Money(), nullable=False),
        sa.Column("floor_rise", lekhara.db.Money(), nullable=False),
        sa.Column("floor_rise_from", sa.Integer(), nullable=False),
        sa.Column("plc", sa.Text(), nullable=False),
        sa.Column("car_park", lekhara.db.Money(), nullable=False),
        sa.Column("amenities", lekhara.db.Money(), nullable=False),
        sa.Column("other_charges", lekhara.db.Money(), nullable=False),
        sa.Column("corpus_per_sqft", lekhara.db.Money(), nullable=False),
        sa.Column("maintenance_per_sqft_month", lekhara.db.Money(), nullable=False),
        sa.Column("maintenance_months", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", ID, sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("price_lists", "project_id", unique=True)
    op.create_table(
        "bookings",
        sa.Column("id", ID, nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("unit_id", ID, sa.ForeignKey("units.id"), nullable=False),
        sa.Column("lead_id", ID, sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("partner_id", ID, sa.ForeignKey("channel_partners.id"), nullable=True),
        sa.Column("booked_on", sa.Date(), nullable=False),
        sa.Column("buyer_name", sa.String(length=200), nullable=False),
        sa.Column("buyer_pan", sa.String(length=10), nullable=True),
        sa.Column("aadhaar_last4", sa.String(length=4), nullable=True),
        sa.Column("buyer_address", sa.Text(), nullable=True),
        sa.Column("agreement_value", lekhara.db.Money(), nullable=False),
        sa.Column("cost_sheet", sa.Text(), nullable=False),
        sa.Column("booking_amount", lekhara.db.Money(), nullable=False),
        sa.Column("receipt_id", ID, sa.ForeignKey("receipts.id"), nullable=True),
        sa.Column("created_by", ID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("bookings", "project_id", "unit_id")
    op.create_table(
        "commissions",
        sa.Column("id", ID, nullable=False),
        sa.Column("organization_id", ID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("partner_id", ID, sa.ForeignKey("channel_partners.id"), nullable=False),
        sa.Column("booking_id", ID, sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("rate_pct", lekhara.db.Percent(), nullable=False),
        sa.Column("amount", lekhara.db.Money(), nullable=False),
        sa.Column("gst", lekhara.db.Money(), nullable=False),
        sa.Column("tds", lekhara.db.Money(), nullable=False),
        sa.Column("paid_by", ID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("reference", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    _index("commissions", "organization_id", "partner_id")


def downgrade() -> None:
    for table in ("commissions", "bookings", "price_lists", "unit_holds", "site_visits",
                  "lead_activities", "leads", "channel_partners"):  # fmt: skip
        op.drop_table(table)
