"""store_visibility_override: per-store frequent/low_freq/hidden override.

Revision ID: 018_store_visibility_override
Revises: 017_store_is_payment_artifact
Create Date: 2026-04-30

Adds a single nullable String column to ``stores`` so the picker can be
bucketed via auto-classification (last purchase recency) plus an explicit
user override. NULL means "follow the auto rule"; otherwise the value
pins the store to one of {"frequent", "low_freq", "hidden"}.

Idempotent ADD COLUMN with PRAGMA-driven existence check, matching the
pattern used by 008_receipt_attribution and 017_store_is_payment_artifact.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "018_store_visibility_override"
down_revision: Union[str, None] = "017_store_is_payment_artifact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_stores"))
    if not _column_exists(conn, "stores", "visibility_override"):
        op.add_column(
            "stores",
            sa.Column("visibility_override", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    pass
