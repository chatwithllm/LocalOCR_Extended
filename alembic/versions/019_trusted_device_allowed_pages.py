"""trusted_device_allowed_pages: per-device sidebar-page allowlist.

Revision ID: 019_trusted_device_allowed_pages
Revises: 018_store_visibility_override
Create Date: 2026-04-30

Adds a nullable JSON-text column to ``trusted_devices`` and to
``device_pairing_sessions`` so admins can pin which sidebar pages a
specific paired device sees, mirroring the existing
``users.allowed_pages`` model.

NULL means "follow the legacy scope-based behaviour" (no per-device
restriction). A populated JSON array narrows visibility to the listed
page ids — unknown ids are silently ignored by the frontend, matching
the household-user picker.

Idempotent ADD COLUMN with PRAGMA-driven existence check, matching the
pattern used by 010_user_allowed_pages, 017_store_is_payment_artifact,
and 018_store_visibility_override.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019_trusted_device_allowed_pages"
down_revision: Union[str, None] = "018_store_visibility_override"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    # Defensive cleanup of any half-applied tmp tables from a prior abort.
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_trusted_devices"))
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_device_pairing_sessions"))

    if not _column_exists(conn, "trusted_devices", "allowed_pages"):
        op.add_column(
            "trusted_devices",
            sa.Column("allowed_pages", sa.Text(), nullable=True),
        )
    if not _column_exists(conn, "device_pairing_sessions", "allowed_pages"):
        op.add_column(
            "device_pairing_sessions",
            sa.Column("allowed_pages", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    # No-op: matches 017/018 — drop-column on SQLite is invasive and the
    # column is harmless when left in place.
    pass
