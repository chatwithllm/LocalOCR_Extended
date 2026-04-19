"""receipt_attribution: per-purchase and per-item "for which person/household" tags.

Revision ID: 008_receipt_attribution
Revises: 007_product_regular_use
Create Date: 2026-04-18

Purely additive. Adds two nullable columns to both `purchases` and
`receipt_items` so each receipt (and individual line item) can be tagged
as belonging to a specific household user, to the "household" pseudo-tag
for shared spend, or left untagged.

Schema:
  attribution_user_id INTEGER NULL  — FK to users.id for personal spend
  attribution_kind    TEXT    NULL  — one of: 'household', 'personal', NULL

States:
  user_id NULL + kind NULL         → untagged (needs review)
  user_id NULL + kind 'household'  → shared household spend
  user_id 42   + kind 'personal'   → personal spend for user 42

Idempotent + uses plain ADD COLUMN (no batch_alter rebuild) so existing
foreign keys referring to purchases / receipt_items stay intact.
Self-heals any leftover _alembic_tmp_* tables from earlier crash states.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_receipt_attribution"
down_revision: Union[str, None] = "007_product_regular_use"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    # Defensive cleanup — batch_alter from a prior crash can leave these behind.
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_purchases"))
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_receipt_items"))

    if not _column_exists(conn, "purchases", "attribution_user_id"):
        op.add_column(
            "purchases",
            sa.Column("attribution_user_id", sa.Integer(), nullable=True),
        )
    if not _column_exists(conn, "purchases", "attribution_kind"):
        op.add_column(
            "purchases",
            sa.Column("attribution_kind", sa.String(length=16), nullable=True),
        )

    if not _column_exists(conn, "receipt_items", "attribution_user_id"):
        op.add_column(
            "receipt_items",
            sa.Column("attribution_user_id", sa.Integer(), nullable=True),
        )
    if not _column_exists(conn, "receipt_items", "attribution_kind"):
        op.add_column(
            "receipt_items",
            sa.Column("attribution_kind", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    # SQLite < 3.35 can't drop columns without rebuilding the table, and
    # we don't need a real downgrade here — keep it a no-op.
    pass
