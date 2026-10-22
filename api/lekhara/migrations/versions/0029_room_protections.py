"""data room watermarks, terms and first-open emails

Revision ID: f4b8d1e36a20
Revises: e1a4c7d92f58
Create Date: 2026-10-23 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b8d1e36a20"
down_revision: str | None = "e1a4c7d92f58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("data_rooms", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("watermark", sa.Boolean(), server_default="1", nullable=False)
        )
        batch_op.add_column(sa.Column("terms", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("notify", sa.Boolean(), server_default="1", nullable=False))

    with op.batch_alter_table("data_room_visitors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("accepted_terms", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("accepted_terms_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("data_room_visitors", schema=None) as batch_op:
        batch_op.drop_column("accepted_terms_at")
        batch_op.drop_column("accepted_terms")

    with op.batch_alter_table("data_rooms", schema=None) as batch_op:
        batch_op.drop_column("notify")
        batch_op.drop_column("terms")
        batch_op.drop_column("watermark")
