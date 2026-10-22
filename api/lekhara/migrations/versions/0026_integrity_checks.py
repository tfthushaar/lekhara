"""the nightly file check

Revision ID: c7e2f9a14b35
Revises: b4c8e1a6d920
Create Date: 2026-10-23 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e2f9a14b35"
down_revision: str | None = "b4c8e1a6d920"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integrity_checks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("checked", sa.Integer(), nullable=False),
        sa.Column("missing", sa.Integer(), nullable=False),
        sa.Column("altered", sa.Integer(), nullable=False),
        sa.Column("problems", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("integrity_checks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_integrity_checks_at"), ["at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("integrity_checks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_integrity_checks_at"))
    op.drop_table("integrity_checks")
