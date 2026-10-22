"""the register of originals

Revision ID: e1a4c7d92f58
Revises: d8f3a2b65c47
Create Date: 2026-10-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a4c7d92f58"
down_revision: str | None = "d8f3a2b65c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "originals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("document_family_id", sa.String(length=64), nullable=True),
        sa.Column("held_at", sa.String(length=16), nullable=False),
        sa.Column("held_by", sa.String(length=200), nullable=True),
        sa.Column("since", sa.Date(), nullable=False),
        sa.Column("against", sa.String(length=200), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "number"),
    )
    with op.batch_alter_table("originals", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_originals_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_originals_project_id"), ["project_id"], unique=False)
    op.create_table(
        "original_moves",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("original_id", sa.String(length=64), nullable=False),
        sa.Column("held_at", sa.String(length=16), nullable=False),
        sa.Column("held_by", sa.String(length=200), nullable=True),
        sa.Column("since", sa.Date(), nullable=False),
        sa.Column("against", sa.String(length=200), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("recorded_by", sa.String(length=64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["original_id"], ["originals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("original_moves", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_original_moves_original_id"), ["original_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("original_moves", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_original_moves_original_id"))
    op.drop_table("original_moves")
    with op.batch_alter_table("originals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_originals_project_id"))
        batch_op.drop_index(batch_op.f("ix_originals_organization_id"))
    op.drop_table("originals")
