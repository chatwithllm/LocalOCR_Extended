"""chat_messages: per-user chat history for in-app assistant.

Revision ID: 015_chat_messages
Revises: 014_user_allowed_ips
Create Date: 2026-04-25

Adds chat_messages so the in-app assistant can persist a conversation
per user. Roles are 'user' or 'assistant'. Tool-call traces are
optional and stored as JSON. Admin-only at the API layer for v1, but
the schema is per-user so opening it up later is purely a permission
change.

Idempotent + CREATE TABLE only; self-heals _alembic_tmp_* leftovers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015_chat_messages"
down_revision: Union[str, None] = "014_user_allowed_ips"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table: str) -> bool:
    rows = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).fetchall()
    return bool(rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_chat_messages"))
    if not _table_exists(conn, "chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("tool_trace", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_chat_messages_user_created",
            "chat_messages",
            ["user_id", "created_at"],
        )


def downgrade() -> None:
    pass
