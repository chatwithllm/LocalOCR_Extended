"""chat_message_flagged: per-message moderation flags.

Revision ID: 016_chat_message_flagged
Revises: 015_chat_messages
Create Date: 2026-04-25

Adds chat_messages.flagged + chat_messages.flag_reason so the input
guardrail and output scrubber can mark messages that hit a blocklist.
Useful for audit ("show me every blocked attempt") without throwing
the rows away.

Idempotent + ADD COLUMN only; self-heals _alembic_tmp_* leftovers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016_chat_message_flagged"
down_revision: Union[str, None] = "015_chat_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_chat_messages"))
    if not _column_exists(conn, "chat_messages", "flagged"):
        op.add_column(
            "chat_messages",
            sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if not _column_exists(conn, "chat_messages", "flag_reason"):
        op.add_column(
            "chat_messages",
            sa.Column("flag_reason", sa.String(length=120), nullable=True),
        )


def downgrade() -> None:
    pass
