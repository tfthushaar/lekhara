"""operations: contractors' running bills and payment approval, site reports and materials,
issues after handover, and construction loans

Revision ID: e7a3c9d52f18
Revises: d5f2b8c41e67
Create Date: 2026-11-06 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import lekhara.db

revision: str = "e7a3c9d52f18"
down_revision: str | None = "d5f2b8c41e67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(length=64)
MONEY = lekhara.db.Money()
QTY = lekhara.db.Quantity()


def _id() -> sa.Column:
    return sa.Column("id", ID, nullable=False)


def _project() -> sa.Column:
    return sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False)


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(), nullable=False)


def _index(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    with op.batch_alter_table("bills") as t:
        t.add_column(sa.Column("approval", sa.String(length=16), nullable=True))
        t.add_column(sa.Column("approval_by", ID, nullable=True))
        t.add_column(sa.Column("approval_at", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("approval_note", sa.String(length=300), nullable=True))
        t.add_column(sa.Column("pay_reference", sa.String(length=200), nullable=True))
        t.create_foreign_key("fk_bills_approval_by_users", "users", ["approval_by"], ["id"])
    with op.batch_alter_table("commitments") as t:
        t.add_column(
            sa.Column("retention_pct", lekhara.db.Percent(), nullable=False, server_default="0")
        )
        t.add_column(sa.Column("advance", MONEY, nullable=False, server_default="0"))
        t.add_column(
            sa.Column("deduct_cess", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        t.add_column(sa.Column("retention_released_on", sa.Date(), nullable=True))

    op.create_table(
        "ra_bills",
        _id(),
        _project(),
        sa.Column("commitment_id", ID, sa.ForeignKey("commitments.id"), nullable=False),
        sa.Column("bill_id", ID, sa.ForeignKey("bills.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("work_value", MONEY, nullable=False),
        sa.Column("gst", MONEY, nullable=False),
        sa.Column("retention", MONEY, nullable=False),
        sa.Column("advance_recovery", MONEY, nullable=False),
        sa.Column("tds", MONEY, nullable=False),
        sa.Column("cess", MONEY, nullable=False),
        sa.Column("net_payable", MONEY, nullable=False),
        sa.Column("created_by", ID, sa.ForeignKey("users.id"), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_id"),
    )
    _index("ra_bills", "project_id", "commitment_id")

    op.create_table(
        "material_items",
        _id(),
        _project(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=False),
        sa.Column("min_level", QTY, nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
    )
    _index("material_items", "project_id")

    op.create_table(
        "daily_reports",
        _id(),
        _project(),
        sa.Column("on", sa.Date(), nullable=False),
        sa.Column("work_done", sa.Text(), nullable=False),
        sa.Column("workers", sa.Integer(), nullable=True),
        sa.Column("issues", sa.Text(), nullable=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id"), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "on"),
    )
    _index("daily_reports", "project_id")

    op.create_table(
        "daily_report_photos",
        _id(),
        _project(),
        sa.Column("report_id", ID, sa.ForeignKey("daily_reports.id"), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("daily_report_photos", "project_id", "report_id")

    op.create_table(
        "material_requests",
        _id(),
        _project(),
        sa.Column("item_id", ID, sa.ForeignKey("material_items.id"), nullable=False),
        sa.Column("quantity", QTY, nullable=False),
        sa.Column("needed_by", sa.Date(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("commitment_id", ID, sa.ForeignKey("commitments.id"), nullable=True),
        sa.Column("requested_by", ID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("ordered_at", sa.DateTime(), nullable=True),
        sa.Column("received_on", sa.Date(), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("material_requests", "project_id", "item_id")

    op.create_table(
        "material_quotes",
        _id(),
        _project(),
        sa.Column("request_id", ID, sa.ForeignKey("material_requests.id"), nullable=False),
        sa.Column("supplier", sa.String(length=200), nullable=False),
        sa.Column("rate", MONEY, nullable=False),
        sa.Column("chosen", sa.Boolean(), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("material_quotes", "project_id", "request_id")

    op.create_table(
        "material_moves",
        _id(),
        _project(),
        sa.Column("item_id", ID, sa.ForeignKey("material_items.id"), nullable=False),
        sa.Column("on", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("quantity", QTY, nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("report_id", ID, sa.ForeignKey("daily_reports.id"), nullable=True),
        sa.Column("request_id", ID, sa.ForeignKey("material_requests.id"), nullable=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id"), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("material_moves", "project_id", "item_id")

    op.create_table(
        "unit_issues",
        _id(),
        _project(),
        sa.Column("unit_id", ID, sa.ForeignKey("units.id"), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("reported_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.Column("reply", sa.Text(), nullable=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id"), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("unit_issues", "project_id", "unit_id")

    op.create_table(
        "loans",
        _id(),
        _project(),
        sa.Column("lender", sa.String(length=200), nullable=False),
        sa.Column("sanctioned", MONEY, nullable=False),
        sa.Column("rate_pct", lekhara.db.Percent(), nullable=True),
        sa.Column("sanctioned_on", sa.Date(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("loans", "project_id")

    op.create_table(
        "loan_moves",
        _id(),
        _project(),
        sa.Column("loan_id", ID, sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("on", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("loan_moves", "project_id", "loan_id")

    op.create_table(
        "loan_conditions",
        _id(),
        _project(),
        sa.Column("loan_id", ID, sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("met_on", sa.Date(), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("loan_conditions", "project_id", "loan_id")


def downgrade() -> None:
    for table in ("loan_conditions", "loan_moves", "loans", "unit_issues", "material_moves",
                  "material_quotes", "material_requests", "daily_report_photos", "daily_reports",
                  "material_items", "ra_bills"):  # fmt: skip
        op.drop_table(table)
    with op.batch_alter_table("commitments") as t:
        for column in ("retention_released_on", "deduct_cess", "advance", "retention_pct"):
            t.drop_column(column)
    with op.batch_alter_table("bills") as t:
        t.drop_constraint("fk_bills_approval_by_users", type_="foreignkey")
        for column in ("pay_reference", "approval_note", "approval_at", "approval_by", "approval"):
            t.drop_column(column)
