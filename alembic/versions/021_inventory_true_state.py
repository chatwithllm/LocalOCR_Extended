"""inventory_true_state: location/expires_at/expires_source/last_purchased_at + shelf-life defaults table.

Revision ID: 021_inventory_true_state
Revises: 020_product_image_fetch_attempt
Create Date: 2026-05-01

Additive ADD COLUMN x4 on `inventory` plus a new
`category_shelf_life_default` reference table seeded with sensible
per-category defaults. Mirrors the PRAGMA-guarded idempotent pattern
of migrations 017–020. Downgrade is no-op.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "021_inventory_true_state"
down_revision: Union[str, None] = "020_product_image_fetch_attempt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEED_DEFAULTS = [
    ("dairy",         "Fridge",   14),
    ("produce",       "Fridge",    7),
    ("meat",          "Fridge",    3),
    ("seafood",       "Fridge",    2),
    ("bakery",        "Pantry",    5),
    ("beverages",     "Pantry",  365),
    ("snacks",        "Pantry",   90),
    ("frozen",        "Freezer", 180),
    ("canned",        "Pantry",  730),
    ("condiments",    "Pantry",  365),
    ("household",     "Cabinet",   0),
    ("personal_care", "Bathroom",  0),
    ("restaurant",    "Fridge",    3),
    ("other",         "Pantry",    0),
]


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _table_exists(conn, table: str) -> bool:
    rows = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": table},
    ).fetchall()
    return bool(rows)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_inventory"))

    if not _column_exists(conn, "inventory", "expires_at"):
        op.add_column("inventory", sa.Column("expires_at", sa.Date(), nullable=True))
    if not _column_exists(conn, "inventory", "expires_at_system"):
        op.add_column("inventory", sa.Column("expires_at_system", sa.Date(), nullable=True))
    if not _column_exists(conn, "inventory", "expires_source"):
        op.add_column(
            "inventory",
            sa.Column("expires_source", sa.String(length=10), nullable=False, server_default="system"),
        )
    if not _column_exists(conn, "inventory", "last_purchased_at"):
        op.add_column("inventory", sa.Column("last_purchased_at", sa.DateTime(), nullable=True))

    if not _table_exists(conn, "category_shelf_life_default"):
        op.create_table(
            "category_shelf_life_default",
            sa.Column("category", sa.String(length=40), primary_key=True),
            sa.Column("location_default", sa.String(length=40), nullable=False),
            sa.Column("shelf_life_days", sa.Integer(), nullable=False, server_default="0"),
        )

    for cat, loc, days in _SEED_DEFAULTS:
        conn.execute(
            sa.text(
                "INSERT OR IGNORE INTO category_shelf_life_default "
                "(category, location_default, shelf_life_days) VALUES (:c, :l, :d)"
            ),
            {"c": cat, "l": loc, "d": days},
        )


def downgrade() -> None:
    # No-op: drop-column on SQLite is invasive and the columns are
    # harmless when left in place. Matches migrations 017–020.
    pass
