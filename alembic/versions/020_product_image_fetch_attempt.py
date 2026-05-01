"""product_image_fetch_attempt: track last attempt at auto image backfill.

Revision ID: 020_product_image_fetch_attempt
Revises: 019_trusted_device_allowed_pages
Create Date: 2026-04-30

Adds a nullable DateTime column to ``products`` so the nightly image
backfill job can enforce a 7-day retry cooldown and not re-query
permanently-unmatched products every night.

Idempotent ADD COLUMN with PRAGMA-driven existence check, matching
the pattern used by 017/018/019.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "020_product_image_fetch_attempt"
down_revision: Union[str, None] = "019_trusted_device_allowed_pages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_products"))

    if not _column_exists(conn, "products", "last_image_fetch_attempt_at"):
        op.add_column(
            "products",
            sa.Column("last_image_fetch_attempt_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    # No-op: matches 017/018/019 — drop-column on SQLite is invasive and
    # the column is harmless when left in place.
    pass
