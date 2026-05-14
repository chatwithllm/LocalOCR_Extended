"""telegram_shopping_session: per-chat walk state for /shopping Telegram flow.

Revision ID: 032_telegram_shopping_session
Revises: 031_telegram_inventory_session
Create Date: 2026-05-14

Additive: creates one new table. Idempotent: re-running upgrade is a no-op.
Downgrade drops the table; no-op when already absent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "032_telegram_shopping_session"
down_revision: Union[str, None] = "031_telegram_inventory_session"
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
    if _table_exists(bind, "telegram_shopping_session"):
        return

    op.create_table(
        "telegram_shopping_session",
        sa.Column("chat_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("category_queue", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("current_category", sa.String(40), nullable=True),
        sa.Column("item_queue", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("cursor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pending_prompt", sa.String(30), nullable=True),
        sa.Column("pending_action", sa.String(20), nullable=True),
        sa.Column("last_item_id", sa.Integer, nullable=True),
        sa.Column("pending_name", sa.String(255), nullable=True),
        sa.Column("pending_qty", sa.Float, nullable=True),
        sa.Column("stats", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("nudge_muted_until", sa.DateTime, nullable=True),
        sa.Column("last_nudge_sent_at", sa.DateTime, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("last_action_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_tg_shop_status", "telegram_shopping_session", ["status"])
    op.create_index("ix_tg_shop_last_action", "telegram_shopping_session", ["last_action_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "telegram_shopping_session"):
        return
    op.drop_index("ix_tg_shop_last_action", table_name="telegram_shopping_session")
    op.drop_index("ix_tg_shop_status", table_name="telegram_shopping_session")
    op.drop_table("telegram_shopping_session")
