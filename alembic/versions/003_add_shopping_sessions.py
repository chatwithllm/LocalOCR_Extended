"""add shopping sessions for ready-to-bill lifecycle

Revision ID: 003_add_shopping_sessions
Revises: 002_add_failed_receipt_fields
Create Date: 2026-04-17
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_add_shopping_sessions"
down_revision: Union[str, None] = "002_add_failed_receipt_fields"
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


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


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
    """Introduce the ShoppingSession entity and attach existing items to a default session.

    This migration is written idempotently so it can recover from a prior
    partially-applied run (e.g. table created, alembic version rollback).
    """

    conn = op.get_bind()

    if not _table_exists(conn, "shopping_sessions"):
        op.create_table(
            "shopping_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=200), nullable=True),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="active",
            ),
            sa.Column("store_hint", sa.String(length=120), nullable=True),
            sa.Column("estimated_total_snapshot", sa.Float(), nullable=True),
            sa.Column("actual_total_snapshot", sa.Float(), nullable=True),
            sa.Column(
                "created_by_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
        )

    if not _index_exists(conn, "ix_shopping_sessions_status"):
        op.create_index(
            "ix_shopping_sessions_status",
            "shopping_sessions",
            ["status"],
        )

    # Add columns on shopping_list_items. SQLite supports ALTER TABLE ADD COLUMN
    # with an inline REFERENCES clause; we rely on that here.
    if not _column_exists(conn, "shopping_list_items", "shopping_session_id"):
        op.add_column(
            "shopping_list_items",
            sa.Column(
                "shopping_session_id",
                sa.Integer(),
                sa.ForeignKey("shopping_sessions.id"),
                nullable=True,
            ),
        )
    if not _column_exists(conn, "shopping_list_items", "actual_price"):
        op.add_column(
            "shopping_list_items",
            sa.Column("actual_price", sa.Float(), nullable=True),
        )

    if not _index_exists(conn, "ix_shopping_list_items_shopping_session_id"):
        op.create_index(
            "ix_shopping_list_items_shopping_session_id",
            "shopping_list_items",
            ["shopping_session_id"],
        )

    # Data migration: if any existing items are present and are not yet
    # attached to a session, drop them into a single "Current list" session
    # so the shopping page keeps working without manual intervention.
    orphan_count = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM shopping_list_items "
            "WHERE shopping_session_id IS NULL"
        )
    ).scalar() or 0
    if orphan_count > 0:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        existing_session_id = conn.execute(
            sa.text(
                "SELECT id FROM shopping_sessions "
                "WHERE status='active' ORDER BY id DESC LIMIT 1"
            )
        ).scalar()
        if existing_session_id is None:
            result = conn.execute(
                sa.text(
                    "INSERT INTO shopping_sessions (name, status, created_at, updated_at) "
                    "VALUES (:name, 'active', :now, :now)"
                ),
                {"name": "Current list", "now": now},
            )
            session_id = result.lastrowid
            if session_id is None:
                session_id = conn.execute(
                    sa.text("SELECT last_insert_rowid()")
                ).scalar()
        else:
            session_id = existing_session_id
        conn.execute(
            sa.text(
                "UPDATE shopping_list_items "
                "SET shopping_session_id = :sid "
                "WHERE shopping_session_id IS NULL"
            ),
            {"sid": session_id},
        )


def downgrade() -> None:
    """Reverse the shopping session additions."""
    conn = op.get_bind()
    if _index_exists(conn, "ix_shopping_list_items_shopping_session_id"):
        op.drop_index(
            "ix_shopping_list_items_shopping_session_id",
            table_name="shopping_list_items",
        )
    if _column_exists(conn, "shopping_list_items", "actual_price"):
        op.drop_column("shopping_list_items", "actual_price")
    if _column_exists(conn, "shopping_list_items", "shopping_session_id"):
        op.drop_column("shopping_list_items", "shopping_session_id")
    if _index_exists(conn, "ix_shopping_sessions_status"):
        op.drop_index(
            "ix_shopping_sessions_status",
            table_name="shopping_sessions",
        )
    if _table_exists(conn, "shopping_sessions"):
        op.drop_table("shopping_sessions")
