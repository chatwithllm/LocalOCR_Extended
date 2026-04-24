"""service_account_allow_write: per-user write-allow flag.

Revision ID: 013_service_account_allow_write
Revises: 012_user_login_activity
Create Date: 2026-04-24

Adds users.allow_write as an optional per-user write gate. Only
consulted for service-role accounts right now; human users continue
to write freely. NULL/0 = read-only (default); 1 = full write access.
Purely additive, no data migration.

Idempotent + ADD COLUMN only; self-heals _alembic_tmp_* leftovers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013_service_account_allow_write"
down_revision: Union[str, None] = "012_user_login_activity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_users"))
    if not _column_exists(conn, "users", "allow_write"):
        op.add_column(
            "users",
            sa.Column("allow_write", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    pass
