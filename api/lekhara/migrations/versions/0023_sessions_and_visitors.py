"""confirmed sessions, the firm's two-step rule and verified data room visitors

Revision ID: 7d2a9c4e1f63
Revises: 5c1e2f7a9b40
Create Date: 2026-10-22 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d2a9c4e1f63"
down_revision: str | None = "5c1e2f7a9b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("confirmed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("ip", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(length=300), nullable=True))

    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("require_two_step", sa.Boolean(), server_default="0", nullable=False)
        )

    with op.batch_alter_table("data_room_visitors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("code_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("code_expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("code_attempts", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("data_room_visitors", schema=None) as batch_op:
        batch_op.drop_column("verified_at")
        batch_op.drop_column("code_attempts")
        batch_op.drop_column("code_expires_at")
        batch_op.drop_column("code_hash")

    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("require_two_step")

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_column("user_agent")
        batch_op.drop_column("ip")
        batch_op.drop_column("last_seen_at")
        batch_op.drop_column("confirmed_at")
