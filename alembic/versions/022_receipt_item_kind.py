"""receipt_item_kind: tag non-product lines (fees, discounts, savings, membership)
so they're persisted for analytics instead of silently dropped at OCR time.

Revision ID: 022_receipt_item_kind
Revises: 021_inventory_true_state
Create Date: 2026-05-02

Additive ADD COLUMN x2:
  - receipt_items.kind        TEXT DEFAULT 'product'
  - products.is_non_product   INTEGER DEFAULT 0

Mirrors the PRAGMA-guarded idempotent pattern of prior migrations.
Downgrade is no-op (additive only).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "022_receipt_item_kind"
down_revision: Union[str, None] = "021_inventory_true_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_receipt_items"))
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_products"))

    if not _column_exists(conn, "receipt_items", "kind"):
        op.add_column(
            "receipt_items",
            sa.Column("kind", sa.String(length=24), nullable=True, server_default="product"),
        )

    if not _column_exists(conn, "products", "is_non_product"):
        op.add_column(
            "products",
            sa.Column("is_non_product", sa.Boolean(), nullable=True, server_default=sa.text("0")),
        )


def downgrade() -> None:
    # Additive-only migration; keep columns to avoid data loss on revert.
    pass
