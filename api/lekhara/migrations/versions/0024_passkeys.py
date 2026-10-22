"""passkeys

Revision ID: 9e3b5d7f2a18
Revises: 7d2a9c4e1f63
Create Date: 2026-10-22 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9e3b5d7f2a18"
down_revision: str | None = "7d2a9c4e1f63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "passkeys",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("credential_id", sa.String(length=1024), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("passkeys", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_passkeys_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_passkeys_credential_id"), ["credential_id"], unique=True
        )

    op.create_table(
        "passkey_challenges",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("challenge", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("passkey_challenges", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_passkey_challenges_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("passkey_challenges", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_passkey_challenges_user_id"))
    op.drop_table("passkey_challenges")
    with op.batch_alter_table("passkeys", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_passkeys_credential_id"))
        batch_op.drop_index(batch_op.f("ix_passkeys_user_id"))
    op.drop_table("passkeys")
