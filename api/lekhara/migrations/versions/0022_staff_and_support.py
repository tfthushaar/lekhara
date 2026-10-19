"""staff, support access and subscription payments

Revision ID: 5c1e2f7a9b40
Revises: af6620e0308e
Create Date: 2026-10-19 23:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import lekhara.db

revision: str = "5c1e2f7a9b40"
down_revision: str | None = "af6620e0308e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscription_payments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("firm_name", sa.String(length=200), nullable=False),
        sa.Column("amount", lekhara.db.Money(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=24), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=False),
        sa.Column("covers_from", sa.Date(), nullable=False),
        sa.Column("covers_to", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("recorded_by", sa.String(length=320), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("subscription_payments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_subscription_payments_organization_id"),
            ["organization_id"],
            unique=False,
        )

    op.create_table(
        "support_grants",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("granted_by", sa.String(length=64), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
        sa.Column("withdrawn_by", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("support_grants", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_support_grants_organization_id"), ["organization_id"], unique=False
        )

    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("paid_until", sa.Date(), nullable=True))

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("support_org_id", sa.String(length=64), nullable=True))

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_staff", sa.Boolean(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_staff")

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_column("support_org_id")

    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("paid_until")

    with op.batch_alter_table("support_grants", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_support_grants_organization_id"))

    op.drop_table("support_grants")
    with op.batch_alter_table("subscription_payments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subscription_payments_organization_id"))

    op.drop_table("subscription_payments")
