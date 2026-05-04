"""medicine_cabinet: add household_members and medications tables.

Revision ID: 023_medicine_cabinet
Revises: 022_receipt_item_kind
Create Date: 2026-05-03

Additive CREATE TABLE x2:
  - household_members
  - medications

PRAGMA-guarded idempotent pattern (CREATE TABLE IF NOT EXISTS).
Downgrade is no-op (additive only).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "023_medicine_cabinet"
down_revision: Union[str, None] = "022_receipt_item_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table: str) -> bool:
    rows = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).fetchall()
    return len(rows) > 0


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------ #
    # household_members                                                    #
    # ------------------------------------------------------------------ #
    if not _table_exists(conn, "household_members"):
        op.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS household_members (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL,
                age_group       TEXT    NOT NULL DEFAULT 'adult',
                avatar_emoji    TEXT,
                created_by_id   INTEGER REFERENCES users(id),
                created_at      DATETIME,
                updated_at      DATETIME
            )
        """))

    # ------------------------------------------------------------------ #
    # medications                                                          #
    # ------------------------------------------------------------------ #
    if not _table_exists(conn, "medications"):
        op.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS medications (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                name                TEXT    NOT NULL,
                brand               TEXT,
                strength            TEXT,
                dosage_form         TEXT,
                active_ingredient   TEXT,
                age_group           TEXT    NOT NULL DEFAULT 'both',
                belongs_to          TEXT    NOT NULL DEFAULT 'household',
                member_id           INTEGER REFERENCES household_members(id) ON DELETE SET NULL,
                barcode             TEXT,
                product_id          INTEGER REFERENCES products(id) ON DELETE SET NULL,
                manufacture_date    DATE,
                expiry_date         DATE,
                quantity            REAL    DEFAULT 1,
                unit                TEXT    DEFAULT 'count',
                low_threshold       REAL,
                rx_number           TEXT,
                prescribing_doctor  TEXT,
                ai_warnings         TEXT,
                ai_enriched_at      DATETIME,
                image_path          TEXT,
                status              TEXT    NOT NULL DEFAULT 'active',
                notes               TEXT,
                created_by_id       INTEGER REFERENCES users(id),
                created_at          DATETIME,
                updated_at          DATETIME
            )
        """))
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_medications_status     ON medications(status)"
        ))
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_medications_member_id  ON medications(member_id)"
        ))
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_medications_barcode    ON medications(barcode)"
        ))
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_medications_product_id ON medications(product_id)"
        ))


def downgrade() -> None:
    # Additive-only migration; keep tables to avoid data loss on revert.
    pass
