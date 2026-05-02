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
