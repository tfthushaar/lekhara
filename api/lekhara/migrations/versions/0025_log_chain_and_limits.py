"""a tamper-evident access log, and rate limits shared by every server

Revision ID: b4c8e1a6d920
Revises: 9e3b5d7f2a18
Create Date: 2026-10-22 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c8e1a6d920"
down_revision: str | None = "9e3b5d7f2a18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("access_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("seq", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("prev_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("hash", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_access_events_seq"), ["seq"], unique=False)

    op.create_table(
        "access_log_head",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("bucket", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("rate_limit_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_rate_limit_events_at"), ["at"], unique=False)
        batch_op.create_index(
            "ix_rate_limit_events_bucket_key", ["bucket", "key_hash"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("rate_limit_events", schema=None) as batch_op:
        batch_op.drop_index("ix_rate_limit_events_bucket_key")
        batch_op.drop_index(batch_op.f("ix_rate_limit_events_at"))
    op.drop_table("rate_limit_events")
    op.drop_table("access_log_head")
    with op.batch_alter_table("access_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_access_events_seq"))
        batch_op.drop_column("hash")
        batch_op.drop_column("prev_hash")
        batch_op.drop_column("seq")
