"""multi_person_attribution: allow tagging a purchase/item to 2+ users.

Revision ID: 009_multi_person_attribution
Revises: 008_receipt_attribution
Create Date: 2026-04-21

Extends the attribution model to support shared spend among a subset of
household members (e.g. a restaurant plate split between 2 of 4 people).

Schema change:
  purchases.attribution_user_ids     TEXT NULL  — JSON array of user ids
  receipt_items.attribution_user_ids TEXT NULL  — JSON array of user ids

The old single-user column (`attribution_user_id`) is kept for one release
as a read-fallback so a partial rollback stays safe. New writes populate
`attribution_user_ids` as the source of truth; reads prefer the JSON
column and fall back to `[attribution_user_id]` if it's null.

Backfill copies every existing `attribution_user_id` into the new JSON
column as a single-element array so the filter query works uniformly
across old and new rows.

Idempotent + ADD COLUMN only (no batch rebuild) so FKs stay intact.
Self-heals leftover _alembic_tmp_* tables from prior crash states.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_multi_person_attribution"
down_revision: Union[str, None] = "008_receipt_attribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_purchases"))
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_receipt_items"))

    if not _column_exists(conn, "purchases", "attribution_user_ids"):
        op.add_column(
            "purchases",
            sa.Column("attribution_user_ids", sa.Text(), nullable=True),
        )
    if not _column_exists(conn, "receipt_items", "attribution_user_ids"):
        op.add_column(
            "receipt_items",
            sa.Column("attribution_user_ids", sa.Text(), nullable=True),
        )

    # Backfill: copy single-user tags into the new JSON array column.
    conn.execute(sa.text("""
        UPDATE purchases
        SET attribution_user_ids = '[' || attribution_user_id || ']'
        WHERE attribution_user_id IS NOT NULL
          AND (attribution_user_ids IS NULL OR attribution_user_ids = '')
    """))
    conn.execute(sa.text("""
        UPDATE receipt_items
        SET attribution_user_ids = '[' || attribution_user_id || ']'
        WHERE attribution_user_id IS NOT NULL
          AND (attribution_user_ids IS NULL OR attribution_user_ids = '')
    """))


def downgrade() -> None:
    # No-op: SQLite < 3.35 can't drop columns without rebuild and we
    # don't want to risk the FK-bearing tables here.
    pass
