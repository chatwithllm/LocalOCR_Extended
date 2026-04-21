"""plaid_item_sharing: allow a PlaidItem (bank login) to be visible to
additional household users beyond the linker.

Revision ID: 011_plaid_item_sharing
Revises: 010_user_allowed_pages
Create Date: 2026-04-21

Adds `shared_with_user_ids TEXT` (JSON array) on `plaid_items`.

Semantics:
  NULL / '[]'   → only the linker (plaid_items.user_id) + admins see it.
  '[1,4]'       → linker + admins + users 1 and 4 see the item and all
                  of its accounts / transactions.

Admins always bypass this restriction — they see every item regardless.
Purely additive; existing rows keep NULL (no behaviour change until an
admin explicitly shares an item).

Idempotent + ADD COLUMN only; self-heals _alembic_tmp_* leftovers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011_plaid_item_sharing"
down_revision: Union[str, None] = "010_user_allowed_pages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_plaid_items"))

    if not _column_exists(conn, "plaid_items", "shared_with_user_ids"):
        op.add_column(
            "plaid_items",
            sa.Column("shared_with_user_ids", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    # SQLite < 3.35 can't drop columns cleanly; keep as a no-op.
    pass
