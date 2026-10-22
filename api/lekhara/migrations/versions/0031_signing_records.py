"""certificate signing records

Revision ID: b2d7f4a91c35
Revises: a6c3e8f14d92
Create Date: 2026-10-23 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d7f4a91c35"
down_revision: str | None = "a6c3e8f14d92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("withdrawal_certificates", schema=None) as batch_op:
        batch_op.add_column(sa.Column("signed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("check_code", sa.String(length=19), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_withdrawal_certificates_check_code"), ["check_code"], unique=True
        )

    op.create_table(
        "certificate_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("device", sa.String(length=100), nullable=True),
        sa.Column("two_step", sa.Boolean(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["withdrawal_requests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("certificate_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_certificate_events_request_id"), ["request_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("certificate_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_certificate_events_request_id"))
    op.drop_table("certificate_events")
    with op.batch_alter_table("withdrawal_certificates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_withdrawal_certificates_check_code"))
        batch_op.drop_column("check_code")
        batch_op.drop_column("fingerprint")
        batch_op.drop_column("signed_at")
