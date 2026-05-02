"""Tests for Alembic migration 021_inventory_true_state."""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest


MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "021_inventory_true_state.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_021", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.db"
    c = sqlite3.connect(db)
    c.executescript(
        "CREATE TABLE inventory ("
        "id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL,"
        "quantity FLOAT NOT NULL DEFAULT 0, location VARCHAR(50),"
        "last_updated DATETIME);"
    )
    c.commit()
    yield c
    c.close()


def test_021_module_loads():
    mig = _load_migration()
    assert mig.revision == "021_inventory_true_state"
    assert mig.down_revision == "020_product_image_fetch_attempt"


def test_021_seed_table_seed_list_has_14():
    mig = _load_migration()
    assert len(mig._SEED_DEFAULTS) == 14
    cats = {row[0] for row in mig._SEED_DEFAULTS}
    assert "dairy" in cats and "other" in cats and "personal_care" in cats


def test_021_downgrade_is_noop():
    mig = _load_migration()
    mig.downgrade()  # must not raise


def test_021_upgrade_runs_end_to_end_and_is_idempotent(conn, tmp_path):
    """upgrade() actually adds columns + seeds 14 rows; re-running is a no-op."""
    import sqlalchemy as sa
    from unittest.mock import patch, MagicMock

    mig = _load_migration()

    # Build a SQLAlchemy engine pointing at the same file the fixture created.
    db_path = str(tmp_path / "test.db")
    eng = sa.create_engine(f"sqlite:///{db_path}")

    def _run_upgrade():
        with eng.connect() as sa_conn:
            # op.get_bind() must return our SA connection
            # op.add_column() must actually execute ALTER TABLE via the same conn
            # op.create_table() must actually CREATE the table via the same conn

            def fake_add_column(table, column):
                col_type = column.type.compile(dialect=eng.dialect)
                nullable = "" if column.nullable else " NOT NULL"
                default = f" DEFAULT {column.server_default.arg!r}" if column.server_default else ""
                sa_conn.execute(sa.text(
                    f"ALTER TABLE {table} ADD COLUMN {column.name} {col_type}{nullable}{default}"
                ))

            def fake_create_table(table_name, *columns, **kw):
                col_defs = []
                for col in columns:
                    if not isinstance(col, sa.Column):
                        continue
                    col_type = col.type.compile(dialect=eng.dialect)
                    pk = " PRIMARY KEY" if col.primary_key else ""
                    nullable = "" if col.nullable and not col.primary_key else ""
                    notnull = " NOT NULL" if not col.nullable and not col.primary_key else ""
                    default = f" DEFAULT {col.server_default.arg!r}" if col.server_default else ""
                    col_defs.append(f"{col.name} {col_type}{pk}{notnull}{default}")
                ddl = f"CREATE TABLE {table_name} ({', '.join(col_defs)})"
                sa_conn.execute(sa.text(ddl))

            with patch("alembic.op.get_bind", return_value=sa_conn), \
                 patch("alembic.op.add_column", side_effect=fake_add_column), \
                 patch("alembic.op.create_table", side_effect=fake_create_table):
                mig.upgrade()
            sa_conn.commit()

    # First run
    _run_upgrade()

    cursor = conn.cursor()
    cols = {r[1] for r in cursor.execute("PRAGMA table_info(inventory)").fetchall()}
    assert {"expires_at", "expires_at_system", "expires_source", "last_purchased_at"}.issubset(cols), \
        f"Missing columns; found: {cols}"

    n = cursor.execute("SELECT COUNT(*) FROM category_shelf_life_default").fetchone()[0]
    assert n == 14, f"Expected 14 seed rows, got {n}"

    # Idempotency: re-run, expect same final state, no errors
    _run_upgrade()
    n2 = cursor.execute("SELECT COUNT(*) FROM category_shelf_life_default").fetchone()[0]
    assert n2 == 14, f"Expected 14 rows after idempotent re-run, got {n2}"
