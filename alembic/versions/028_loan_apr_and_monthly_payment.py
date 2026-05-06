"""plaid_account loan APR + monthly payment columns

Revision ID: 028_loan_apr_payment
Revises: 027_true_status
Create Date: 2026-05-06

Adds nullable apr_bps (Integer; basis points so 7.25% = 725) and
monthly_payment_cents (Integer) to plaid_accounts. Loan-only fields,
populated via PUT /plaid/accounts/<id>/loan-meta.

Mirrors the PRAGMA-guarded idempotent pattern of prior migrations.
Downgrade is no-op (additive only).
"""
from alembic import op
import sqlalchemy as sa


revision = "028_loan_apr_payment"
down_revision = "027_true_status"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(sa.text(f"PRAGMA table_info({table})")))


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "plaid_accounts", "apr_bps"):
        op.add_column(
            "plaid_accounts",
            sa.Column("apr_bps", sa.Integer(), nullable=True),
        )
    if not _column_exists(conn, "plaid_accounts", "monthly_payment_cents"):
        op.add_column(
            "plaid_accounts",
            sa.Column("monthly_payment_cents", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    # Additive-only migration; keep columns to avoid data loss on revert.
    pass
