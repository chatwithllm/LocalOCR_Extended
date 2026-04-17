"""accounts dashboard: plaid_accounts table + plaid_items.nickname + purchases compound index

Revision ID: 005_accounts_dashboard
Revises: 004_add_plaid_tables
Create Date: 2026-04-17

Purely additive. Existing code paths are unaffected:
- New `plaid_items.nickname` column is nullable; old code ignores it.
- New `plaid_accounts` table is read/written only by new endpoints; its
  absence does not affect the existing sync/confirm/dismiss pipeline.
- New `ix_purchases_user_date_category` compound index only influences the
  SQLite query planner — never data correctness.

Idempotent against partial previous state (same pattern as migration 004):
every DDL is gated on a `sqlite_master` presence check so re-running this
migration after a crash or after a `create_all()` auto-bootstrap is safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_accounts_dashboard"
down_revision: Union[str, None] = "004_add_plaid_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": name},
        ).first()
    )


def _index_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": name},
        ).first()
    )


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()

    # --- plaid_items.nickname ---------------------------------------------
    if _table_exists(conn, "plaid_items") and not _column_exists(
        conn, "plaid_items", "nickname"
    ):
        op.add_column(
            "plaid_items",
            sa.Column("nickname", sa.String(64), nullable=True),
        )

    # --- plaid_accounts table --------------------------------------------
    if not _table_exists(conn, "plaid_accounts"):
        op.create_table(
            "plaid_accounts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "plaid_item_id",
                sa.Integer(),
                sa.ForeignKey("plaid_items.id"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("plaid_account_id", sa.String(64), nullable=False),
            sa.Column("account_name", sa.String(255), nullable=True),
            sa.Column("account_mask", sa.String(8), nullable=True),
            sa.Column("account_type", sa.String(32), nullable=True),
            sa.Column("account_subtype", sa.String(32), nullable=True),
            sa.Column("balance_cents", sa.Integer(), nullable=True),
            sa.Column(
                "balance_iso_currency_code",
                sa.String(3),
                nullable=False,
                server_default="USD",
            ),
            sa.Column("balance_updated_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.UniqueConstraint(
                "plaid_item_id",
                "plaid_account_id",
                name="uq_plaid_accounts_item_account",
            ),
        )
    if not _index_exists(conn, "ix_plaid_accounts_user_id"):
        op.create_index(
            "ix_plaid_accounts_user_id", "plaid_accounts", ["user_id"]
        )
    if not _index_exists(conn, "ix_plaid_accounts_item_id"):
        op.create_index(
            "ix_plaid_accounts_item_id", "plaid_accounts", ["plaid_item_id"]
        )

    # --- purchases compound index ----------------------------------------
    # Speeds up Accounts Dashboard Panel 2 (date-range + category filter per
    # user) and Panel 3 (monthly-by-category aggregation per user).
    # Column name is `default_budget_category` on the Purchase model —
    # there is no plain `category` column on purchases.
    if _table_exists(conn, "purchases") and not _index_exists(
        conn, "ix_purchases_user_date_category"
    ):
        op.create_index(
            "ix_purchases_user_date_category",
            "purchases",
            ["user_id", "date", "default_budget_category"],
        )

    # --- backfill plaid_accounts from plaid_items.accounts_json ----------
    # Best-effort: if the JSON blob is malformed we skip the item rather
    # than failing the migration. New syncs will populate plaid_accounts
    # directly, so any item skipped here recovers on the next sync.
    import json
    from datetime import datetime

    if _table_exists(conn, "plaid_accounts") and _table_exists(conn, "plaid_items"):
        rows = conn.execute(
            sa.text(
                "SELECT id, user_id, accounts_json FROM plaid_items "
                "WHERE accounts_json IS NOT NULL AND accounts_json != ''"
            )
        ).fetchall()
        now = datetime.utcnow().isoformat()
        for item_id, user_id, accounts_json in rows:
            try:
                accounts = json.loads(accounts_json) or []
            except (TypeError, ValueError):
                continue
            for acct in accounts:
                if not isinstance(acct, dict):
                    continue
                plaid_account_id = (
                    acct.get("account_id")
                    or acct.get("plaid_account_id")
                    or ""
                ).strip()
                if not plaid_account_id:
                    continue
                # Skip if already backfilled (idempotent re-run).
                existing = conn.execute(
                    sa.text(
                        "SELECT 1 FROM plaid_accounts "
                        "WHERE plaid_item_id = :i AND plaid_account_id = :a"
                    ),
                    {"i": item_id, "a": plaid_account_id},
                ).first()
                if existing:
                    continue
                conn.execute(
                    sa.text(
                        "INSERT INTO plaid_accounts ("
                        "plaid_item_id, user_id, plaid_account_id, "
                        "account_name, account_mask, account_type, "
                        "account_subtype, balance_cents, "
                        "balance_iso_currency_code, balance_updated_at, "
                        "created_at, updated_at"
                        ") VALUES ("
                        ":item_id, :user_id, :plaid_account_id, "
                        ":account_name, :account_mask, :account_type, "
                        ":account_subtype, NULL, 'USD', NULL, :now, :now"
                        ")"
                    ),
                    {
                        "item_id": item_id,
                        "user_id": user_id,
                        "plaid_account_id": plaid_account_id,
                        "account_name": (acct.get("name") or acct.get("official_name") or None),
                        "account_mask": acct.get("mask"),
                        "account_type": acct.get("type"),
                        "account_subtype": acct.get("subtype"),
                        "now": now,
                    },
                )


def downgrade() -> None:
    conn = op.get_bind()
    if _index_exists(conn, "ix_purchases_user_date_category"):
        op.drop_index("ix_purchases_user_date_category", table_name="purchases")
    if _index_exists(conn, "ix_plaid_accounts_item_id"):
        op.drop_index("ix_plaid_accounts_item_id", table_name="plaid_accounts")
    if _index_exists(conn, "ix_plaid_accounts_user_id"):
        op.drop_index("ix_plaid_accounts_user_id", table_name="plaid_accounts")
    if _table_exists(conn, "plaid_accounts"):
        op.drop_table("plaid_accounts")
    # SQLite can't DROP COLUMN before 3.35; we leave plaid_items.nickname in
    # place on downgrade — it's nullable and harmless for pre-feature code.
