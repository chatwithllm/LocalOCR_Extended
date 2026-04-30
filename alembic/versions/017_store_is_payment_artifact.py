"""store_is_payment_artifact: flag bank/CC artifact rows in the stores table.

Revision ID: 017_store_is_payment_artifact
Revises: 016_chat_message_flagged
Create Date: 2026-04-30

Plaid promotion + manual receipt flow can create Store rows for things like
"CHASE CREDIT CRD AUTO-PMT", "Capital One Auto Pay", "Interest Charged"
which clutter the Stores dropdown without being real merchants.

This migration adds a single nullable-but-defaulted boolean column so the
backfill + dropdown filter can hide them without losing the underlying
purchase rows (which still need a Store FK target).

Idempotent ADD COLUMN with PRAGMA-driven existence check, matching the
pattern used by 008_receipt_attribution.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017_store_is_payment_artifact"
down_revision: Union[str, None] = "016_chat_message_flagged"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_stores"))

    if not _column_exists(conn, "stores", "is_payment_artifact"):
        op.add_column(
            "stores",
            sa.Column(
                "is_payment_artifact",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    pass
