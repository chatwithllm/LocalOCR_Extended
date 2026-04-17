"""add Plaid items and staged-transactions tables

Revision ID: 004_add_plaid_tables
Revises: 003_add_shopping_sessions
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_add_plaid_tables"
down_revision: Union[str, None] = "003_add_shopping_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"
            ),
            {"n": name},
        ).first()
    )


def _index_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name=:n"
            ),
            {"n": name},
        ).first()
    )


def upgrade() -> None:
    """Create the two Plaid-integration tables.

    Idempotent: tables may already exist if a prior deploy created them via
    SQLAlchemy's Base.metadata.create_all() before this migration was wired up.
    We check-then-create so alembic can safely stamp the version forward.
    """
    conn = op.get_bind()

    # --- plaid_items ---
    if not _table_exists(conn, "plaid_items"):
        op.create_table(
            "plaid_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("plaid_item_id", sa.String(255), nullable=False, unique=True),
            sa.Column("institution_id", sa.String(60), nullable=True),
            sa.Column("institution_name", sa.String(255), nullable=True),
            sa.Column("access_token_encrypted", sa.Text(), nullable=False),
            sa.Column("accounts_json", sa.Text(), nullable=True),
            sa.Column("products", sa.String(255), nullable=True),
            sa.Column("transaction_cursor", sa.String(255), nullable=True),
            sa.Column("last_sync_at", sa.DateTime(), nullable=True),
            sa.Column("last_sync_status", sa.String(40), nullable=True),
            sa.Column("last_sync_error", sa.Text(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
    if not _index_exists(conn, "ix_plaid_items_user_id"):
        op.create_index("ix_plaid_items_user_id", "plaid_items", ["user_id"])
    if not _index_exists(conn, "ix_plaid_items_status"):
        op.create_index("ix_plaid_items_status", "plaid_items", ["status"])

    # --- plaid_staged_transactions ---
    if not _table_exists(conn, "plaid_staged_transactions"):
        op.create_table(
            "plaid_staged_transactions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "plaid_item_id",
                sa.Integer(),
                sa.ForeignKey("plaid_items.id"),
                nullable=False,
            ),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("plaid_transaction_id", sa.String(255), nullable=False, unique=True),
            sa.Column("plaid_account_id", sa.String(255), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("iso_currency_code", sa.String(10), nullable=True),
            sa.Column("transaction_date", sa.Date(), nullable=False),
            sa.Column("authorized_date", sa.Date(), nullable=True),
            sa.Column("name", sa.String(500), nullable=True),
            sa.Column("merchant_name", sa.String(500), nullable=True),
            sa.Column("plaid_category_primary", sa.String(120), nullable=True),
            sa.Column("plaid_category_detailed", sa.String(255), nullable=True),
            sa.Column("plaid_category_json", sa.Text(), nullable=True),
            sa.Column("pending", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("suggested_receipt_type", sa.String(30), nullable=True),
            sa.Column("suggested_spending_domain", sa.String(30), nullable=True),
            sa.Column("suggested_budget_category", sa.String(40), nullable=True),
            sa.Column(
                "status", sa.String(30), nullable=False, server_default="ready_to_import"
            ),
            sa.Column(
                "duplicate_purchase_id",
                sa.Integer(),
                sa.ForeignKey("purchases.id"),
                nullable=True,
            ),
            sa.Column(
                "confirmed_purchase_id",
                sa.Integer(),
                sa.ForeignKey("purchases.id"),
                nullable=True,
            ),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("dismissed_at", sa.DateTime(), nullable=True),
            sa.Column("raw_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
    if not _index_exists(conn, "ix_plaid_staged_user_id"):
        op.create_index(
            "ix_plaid_staged_user_id", "plaid_staged_transactions", ["user_id"]
        )
    if not _index_exists(conn, "ix_plaid_staged_status"):
        op.create_index(
            "ix_plaid_staged_status", "plaid_staged_transactions", ["status"]
        )
    if not _index_exists(conn, "ix_plaid_staged_item_id"):
        op.create_index(
            "ix_plaid_staged_item_id", "plaid_staged_transactions", ["plaid_item_id"]
        )
    if not _index_exists(conn, "ix_plaid_staged_account_id"):
        op.create_index(
            "ix_plaid_staged_account_id",
            "plaid_staged_transactions",
            ["plaid_account_id"],
        )
    if not _index_exists(conn, "ix_plaid_staged_date"):
        op.create_index(
            "ix_plaid_staged_date",
            "plaid_staged_transactions",
            ["transaction_date"],
        )


def downgrade() -> None:
    op.drop_index("ix_plaid_staged_date", table_name="plaid_staged_transactions")
    op.drop_index(
        "ix_plaid_staged_account_id", table_name="plaid_staged_transactions"
    )
    op.drop_index("ix_plaid_staged_item_id", table_name="plaid_staged_transactions")
    op.drop_index("ix_plaid_staged_status", table_name="plaid_staged_transactions")
    op.drop_index("ix_plaid_staged_user_id", table_name="plaid_staged_transactions")
    op.drop_table("plaid_staged_transactions")
    op.drop_index("ix_plaid_items_status", table_name="plaid_items")
    op.drop_index("ix_plaid_items_user_id", table_name="plaid_items")
    op.drop_table("plaid_items")
