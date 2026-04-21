"""user_login_activity: surface last-login + current-session info.

Revision ID: 012_user_login_activity
Revises: 011_plaid_item_sharing
Create Date: 2026-04-21

Adds three columns on `users` so the Settings page can show each user
their own login history + current session:

  last_login_at               DATETIME  — previous successful login
  current_session_started_at  DATETIME  — when THIS browser session began
  last_login_user_agent       VARCHAR(500) — last UA string captured

Purely additive. Existing rows keep NULL; the Settings card falls back
to a graceful "no prior sessions recorded yet" state.

Idempotent + ADD COLUMN only; self-heals _alembic_tmp_* leftovers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012_user_login_activity"
down_revision: Union[str, None] = "011_plaid_item_sharing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_users"))

    if not _column_exists(conn, "users", "last_login_at"):
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    if not _column_exists(conn, "users", "current_session_started_at"):
        op.add_column(
            "users",
            sa.Column("current_session_started_at", sa.DateTime(), nullable=True),
        )
    if not _column_exists(conn, "users", "last_login_user_agent"):
        op.add_column(
            "users",
            sa.Column("last_login_user_agent", sa.String(length=500), nullable=True),
        )


def downgrade() -> None:
    pass
