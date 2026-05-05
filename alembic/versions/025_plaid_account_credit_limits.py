"""plaid_account credit limit columns

Revision ID: 025_credit_limits
Revises: 024_medication_user_id
Create Date: 2026-05-05

Adds nullable credit_limit_cents and available_credit_cents to plaid_accounts.
Both are populated on the next /plaid/accounts/refresh-balances call; no
backfill is required because Plaid's Balance API already returns these fields
on every refresh — we previously discarded them.
"""
from alembic import op
import sqlalchemy as sa


revision = "025_credit_limits"
down_revision = "024_medication_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plaid_accounts",
        sa.Column("credit_limit_cents", sa.Integer(), nullable=True),
    )
    op.add_column(
        "plaid_accounts",
        sa.Column("available_credit_cents", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plaid_accounts", "available_credit_cents")
    op.drop_column("plaid_accounts", "credit_limit_cents")
