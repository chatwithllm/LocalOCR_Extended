"""plaid_account loan monthly payment due day

Revision ID: 029_payment_due_day
Revises: 028_loan_apr_payment
Create Date: 2026-05-06

Adds nullable monthly_payment_due_day (Integer 1-31) to plaid_accounts.
Loan-only field, populated via PUT /plaid/accounts/<id>/loan-meta.
Used to compute "next payment due" date in the Loan Progress tile.

Mirrors the PRAGMA-guarded idempotent pattern of prior migrations.
Downgrade is no-op (additive only).
"""
from alembic import op
import sqlalchemy as sa


revision = "029_payment_due_day"
down_revision = "028_loan_apr_payment"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(sa.text(f"PRAGMA table_info({table})")))


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "plaid_accounts", "monthly_payment_due_day"):
        op.add_column(
            "plaid_accounts",
            sa.Column("monthly_payment_due_day", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    # Additive-only migration; keep column to avoid data loss on revert.
    pass
