"""product_regular_use: flag for "frequently used" products (context-menu feature).

Revision ID: 007_product_regular_use
Revises: 006_dedup_dismissals
Create Date: 2026-04-18

Purely additive. Adds a single nullable boolean on `products` so users can
mark items as "regular use" (groceries/supplies they buy every cycle). The
flag is surfaced by a long-press context menu in the inventory and products
views and displayed as a small star badge.

Idempotent against partial previous state: gated on a pragma check so
re-running after a `create_all()` bootstrap is safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_product_regular_use"
down_revision: Union[str, None] = "006_dedup_dismissals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    # Clean up any leftover batch-mode temp table from a previous partial
    # attempt — a crash mid-batch_alter leaves it behind and blocks retries.
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_products"))

    if not _column_exists(conn, "products", "is_regular_use"):
        # SQLite supports plain ADD COLUMN for nullable columns with a
        # literal default — no full-table rebuild required, so foreign keys
        # pointing at `products` stay intact.
        op.add_column(
            "products",
            sa.Column(
                "is_regular_use",
                sa.Boolean(),
                nullable=True,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    # SQLite versions prior to 3.35 cannot drop columns without rebuilding
    # the table, and we don't need a real downgrade here — keep it a no-op.
    pass
