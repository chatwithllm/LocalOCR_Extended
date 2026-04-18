"""dedup_dismissals: persistent 'not a duplicate' decisions for the receipts dedup-scan

Revision ID: 006_dedup_dismissals
Revises: 005_accounts_dashboard
Create Date: 2026-04-17

Purely additive. Stores pairs of Purchase ids the user has explicitly marked
as NOT duplicates so the dedup-scan endpoint can filter them out on future
scans (prevents the same false-positive — e.g. two legit same-day, same-amount
charges under a shared merchant alias — from resurfacing).

Idempotent against partial previous state (same pattern as migration 005):
every DDL is gated on a `sqlite_master` presence check so re-running this
migration after a `create_all()` auto-bootstrap is safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_dedup_dismissals"
down_revision: Union[str, None] = "005_accounts_dashboard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": name},
        ).first()
    )


def _index_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": name},
        ).first()
    )


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "dedup_dismissals"):
        op.create_table(
            "dedup_dismissals",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "purchase_id_low",
                sa.Integer(),
                sa.ForeignKey("purchases.id"),
                nullable=False,
            ),
            sa.Column(
                "purchase_id_high",
                sa.Integer(),
                sa.ForeignKey("purchases.id"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "user_id",
                "purchase_id_low",
                "purchase_id_high",
                name="uq_dedup_dismissal_pair",
            ),
        )

    if not _index_exists(conn, "ix_dedup_dismissal_user"):
        op.create_index(
            "ix_dedup_dismissal_user", "dedup_dismissals", ["user_id"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _index_exists(conn, "ix_dedup_dismissal_user"):
        op.drop_index("ix_dedup_dismissal_user", table_name="dedup_dismissals")
    if _table_exists(conn, "dedup_dismissals"):
        op.drop_table("dedup_dismissals")
