"""filing rules

Revision ID: d8f3a2b65c47
Revises: c7e2f9a14b35
Create Date: 2026-10-23 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8f3a2b65c47"
down_revision: str | None = "c7e2f9a14b35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "filing_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("words", sa.String(length=200), nullable=False),
        sa.Column("how", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("requirement", sa.String(length=64), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("filing_rules", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_filing_rules_organization_id"), ["organization_id"], unique=False
        )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("filed_by", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_column("filed_by")
    with op.batch_alter_table("filing_rules", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_filing_rules_organization_id"))
    op.drop_table("filing_rules")
