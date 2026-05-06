"""plaid_account display_name + owner_label

Revision ID: 030_acct_identity
Revises: 029_payment_due_day
Create Date: 2026-05-06

Adds two nullable string columns to plaid_accounts:
  - display_name (String 128) — user-set override of Plaid's account_name.
    Lets users rename loans ("Citi Mortgage" → "House") and cards
    ("CHASE FREEDOM 2292" → "Chase Freedom — Groceries").
  - owner_label  (String 64)  — free-form person tag ("Me", "Spouse",
    "Kid1") used to group cards by household member in the UI.

Both populated via PUT /plaid/accounts/<id>/identity.
Mirrors the PRAGMA-guarded idempotent pattern of prior migrations.
Downgrade is no-op (additive only; preserves user data).
"""
from alembic import op
import sqlalchemy as sa


revision = "030_acct_identity"
down_revision = "029_payment_due_day"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(sa.text(f"PRAGMA table_info({table})")))


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "plaid_accounts", "display_name"):
        op.add_column(
            "plaid_accounts",
            sa.Column("display_name", sa.String(length=128), nullable=True),
        )
    if not _column_exists(conn, "plaid_accounts", "owner_label"):
        op.add_column(
            "plaid_accounts",
            sa.Column("owner_label", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    # Additive-only; preserve user-entered names + owner tags on revert.
    pass
