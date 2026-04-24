"""user_allowed_ips: per-user IP allowlist (JSON array).

Revision ID: 014_user_allowed_ips
Revises: 013_service_account_allow_write
Create Date: 2026-04-24

Adds users.allowed_ips as an optional per-user IP allowlist. Stored
as a JSON array of strings; each entry is a plain IPv4/IPv6 address
or a CIDR block (e.g. "10.0.0.0/8"). NULL or empty list = no
restriction (legacy behaviour). Currently consulted only for
service-role bearer-token auth, where a non-empty list causes the
request to be rejected if the client IP does not match any entry.

Idempotent + ADD COLUMN only; self-heals _alembic_tmp_* leftovers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_user_allowed_ips"
down_revision: Union[str, None] = "013_service_account_allow_write"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_users"))
    if not _column_exists(conn, "users", "allowed_ips"):
        op.add_column(
            "users",
            sa.Column("allowed_ips", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    pass
