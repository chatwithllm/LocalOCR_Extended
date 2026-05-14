"""telegram_inventory_session: per-chat walk state for /inventory Telegram flow.

Revision ID: 031_telegram_inventory_session
Revises: 030_acct_identity
Create Date: 2026-05-13

Additive: creates one new table. Idempotent: re-running upgrade is a no-op.
Downgrade drops the table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "031_telegram_inventory_session"
down_revision: Union[str, None] = "030_acct_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    row = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "telegram_inventory_session"):
        return

    op.create_table(
        "telegram_inventory_session",
        sa.Column("chat_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("current_category", sa.String(40), nullable=True),
        sa.Column("item_queue", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("cursor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("page", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pending_prompt", sa.String(30), nullable=True),
        sa.Column("last_item_id", sa.Integer, nullable=True),
        sa.Column("stats", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("nudge_muted_until", sa.DateTime, nullable=True),
        sa.Column("last_nudge_sent_at", sa.DateTime, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("last_action_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_tg_inv_status", "telegram_inventory_session", ["status"])
    op.create_index("ix_tg_inv_last_action", "telegram_inventory_session", ["last_action_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "telegram_inventory_session"):
        return
    op.drop_index("ix_tg_inv_last_action", table_name="telegram_inventory_session")
    op.drop_index("ix_tg_inv_status", table_name="telegram_inventory_session")
    op.drop_table("telegram_inventory_session")
