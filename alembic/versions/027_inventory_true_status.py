"""inventory true-status columns

Revision ID: 027_true_status
Revises: 026_loan_original_amount
Create Date: 2026-05-06

Adds Product.expected_shelf_days (Integer) and
Inventory.consumed_pct_override (Float). Both nullable. Power the
auto-decaying %-remaining + fresh/low/out status that replaces the
meaningless x1/x2 tile counts.

PRAGMA-guarded idempotent pattern. Downgrade is no-op (additive only).
"""
from alembic import op
import sqlalchemy as sa


revision = "027_true_status"
down_revision = "026_loan_original_amount"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(sa.text(f"PRAGMA table_info({table})")))


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "products", "expected_shelf_days"):
        op.add_column(
            "products",
            sa.Column("expected_shelf_days", sa.Integer(), nullable=True),
        )
    if not _column_exists(conn, "inventory", "consumed_pct_override"):
        op.add_column(
            "inventory",
            sa.Column("consumed_pct_override", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    # Additive-only migration; keep columns to avoid data loss on revert.
    pass
