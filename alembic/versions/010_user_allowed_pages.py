"""user_allowed_pages: per-user page-access restriction (JSON array).

Revision ID: 010_user_allowed_pages
Revises: 009_multi_person_attribution
Create Date: 2026-04-21

Adds `allowed_pages TEXT` on `users` as an opt-in restriction knob.

Semantics:
  NULL       → no restriction (existing behaviour — see every sidebar page).
  '[]'       → no pages visible (admin hasn't granted access yet).
  '[...]'    → JSON array of page ids the user can access.

Admins (role='admin') always bypass this check regardless of column
contents. This migration is purely additive — existing users keep NULL
and therefore see everything, matching pre-010 behaviour.

Idempotent + ADD COLUMN only (no batch rebuild) so FKs stay intact.
Self-heals leftover _alembic_tmp_* tables from prior crash states.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010_user_allowed_pages"
down_revision: Union[str, None] = "009_multi_person_attribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_users"))

    if not _column_exists(conn, "users", "allowed_pages"):
        op.add_column(
            "users",
            sa.Column("allowed_pages", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    # SQLite < 3.35 can't drop columns cleanly; keep as a no-op.
    pass
