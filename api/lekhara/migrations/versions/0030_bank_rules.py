"""bank rules

Revision ID: a6c3e8f14d92
Revises: f4b8d1e36a20
Create Date: 2026-10-23 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import lekhara.db

revision: str = "a6c3e8f14d92"
down_revision: str | None = "f4b8d1e36a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("words", sa.String(length=200), nullable=False),
        sa.Column("how", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("min_amount", lekhara.db.Money(), nullable=True),
        sa.Column("max_amount", lekhara.db.Money(), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("unit_id", sa.String(length=64), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bank_rules", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bank_rules_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_bank_rules_project_id"), ["project_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("bank_rules", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bank_rules_project_id"))
        batch_op.drop_index(batch_op.f("ix_bank_rules_organization_id"))
    op.drop_table("bank_rules")
