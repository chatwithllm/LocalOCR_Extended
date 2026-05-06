"""plaid_account loan original amount column

Revision ID: 026_loan_original_amount
Revises: 025_credit_limits
Create Date: 2026-05-05

Adds nullable original_loan_amount_cents to plaid_accounts. User-entered
per loan via PUT /plaid/accounts/<id>/loan-meta. Phase 2 (Plaid Liabilities)
will auto-populate nulls without overwriting user values.

Mirrors the PRAGMA-guarded idempotent pattern of 025. Downgrade is no-op
(additive only).
"""
from alembic import op
import sqlalchemy as sa


revision = "026_loan_original_amount"
down_revision = "025_credit_limits"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(sa.text(f"PRAGMA table_info({table})")))


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "plaid_accounts", "original_loan_amount_cents"):
        op.add_column(
            "plaid_accounts",
            sa.Column("original_loan_amount_cents", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    # Additive-only migration; keep column to avoid data loss on revert.
    pass
