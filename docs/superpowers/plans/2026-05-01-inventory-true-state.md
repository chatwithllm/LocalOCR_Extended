# Inventory True State — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Inventory` the authoritative source of truth: receipt finalize is the only automatic writer, manual edits + defers stick, expiry + location are first-class, UI shows tiles grouped by location with color-coded expiry.

**Architecture:** Additive schema migration (`021`) adds `expires_at`, `expires_at_system`, `expires_source`, `last_purchased_at` columns to `inventory` and creates `category_shelf_life_default`. Receipt finalize upserts `Inventory` rows (was: nightly `rebuild_active_inventory` cron). New PATCH endpoint covers manual edits, location moves, explicit expiry, and quick `+3d`/`+7d` defer presets. Frontend Inventory page rebuilt as DOM-constructed location-grouped tiles with stripe + pulse animation.

**Tech Stack:** Flask 3.1, SQLAlchemy 2.0, Alembic (PRAGMA-guarded ADD COLUMN), Pytest, vanilla JS in single `index.html` using `createElement` / `replaceChildren` (no string-template DOM injection).

---

## File Structure

| File | Role |
|---|---|
| `alembic/versions/021_inventory_true_state.py` *(new)* | Idempotent ADD COLUMN ×4 on `inventory`, CREATE TABLE `category_shelf_life_default`, INSERT 14 seed rows. No-op downgrade. |
| `src/backend/initialize_database_schema.py` *(modify)* | Add 4 columns to `Inventory`; add `CategoryShelfLifeDefault` model class. |
| `src/backend/category_shelf_life.py` *(new)* | `get_category_default(session, category)` with `"other"` fallback and hardcoded sentinel when table missing. |
| `src/backend/inventory_writes.py` *(new)* | Pure helpers: `upsert_inventory_for_receipt_item`, `apply_manual_patch`, `reset_expiry_to_system`. No HTTP, no transactions. |
| `src/backend/manage_inventory.py` *(modify)* | Add `PATCH /inventory/products/<product_id>` and `DELETE /inventory/products/<product_id>/expiry-override`. Extend `GET /inventory` with new fields. |
| `src/backend/handle_receipt_upload.py` *(modify)* | After `Purchase` + `ReceiptItem` rows are flushed, call `upsert_inventory_for_receipt_item` per item. |
| `src/backend/active_inventory.py` *(modify)* | Add `backfill_inventory_truth(session)` one-shot helper. Mark `rebuild_active_inventory` legacy. |
| `src/backend/initialize_database_schema.py` boot wiring *(modify)* | After `alembic upgrade head` finishes, call `backfill_inventory_truth(session)` once. |
| `src/backend/schedule_daily_recommendations.py` *(modify, defensive)* | Ensure `rebuild_active_inventory` is not registered as a recurring job. |
| `src/frontend/index.html` *(modify)* | Inventory page: header markup + safe DOM-built tile renderer + PATCH calls + undo toast. Uses `createElement`, `textContent`, `replaceChildren` — no string template injection. |
| `tests/test_active_inventory.py` *(extend)* | Schema + receipt upsert + backfill tests. |
| `tests/test_inventory_writes.py` *(new)* | Pure-helper tests. |
| `tests/test_inventory_endpoints.py` *(new)* | Integration tests for PATCH endpoint, defer, reset, group-by-location GET. |
| `tests/test_migration_021.py` *(new)* | Migration upgrade idempotency, seed count, downgrade no-op. |
| `tests/test_category_shelf_life.py` *(new)* | Lookup helper tests. |

---

## Task 1 — Schema migration 021

**Files:**
- Create: `alembic/versions/021_inventory_true_state.py`
- Test: `tests/test_migration_021.py`

- [ ] **Step 1: Write failing migration test** — `tests/test_migration_021.py`

```python
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
```

- [ ] **Step 2: Run test, expect failure**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_migration_021.py -v"`
Expected: `ModuleNotFoundError: No module named 'migration_021'` because the file does not exist yet.

- [ ] **Step 3: Create the migration file**

`alembic/versions/021_inventory_true_state.py`:

```python
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
```

- [ ] **Step 4: Run tests, expect pass**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_migration_021.py -v"`
Expected: `3 passed`.

- [ ] **Step 5: Apply migration in dev**

Run:
```
docker compose exec backend bash -c "cd /app && alembic upgrade head"
docker compose exec backend bash -c "sqlite3 /data/db/app.db '.schema inventory' | grep -E 'expires_at|expires_source|last_purchased_at'"
docker compose exec backend bash -c "sqlite3 /data/db/app.db 'SELECT count(*) FROM category_shelf_life_default'"
```
Expected: 4 column lines, count = 14.

- [ ] **Step 6: Commit**

```
git add alembic/versions/021_inventory_true_state.py tests/test_migration_021.py
git commit -m "feat(inventory): migration 021 — true-state columns + shelf-life defaults"
```

---

## Task 2 — ORM updates

**Files:**
- Modify: `src/backend/initialize_database_schema.py` (Inventory + new CategoryShelfLifeDefault)
- Test: `tests/test_active_inventory.py`

- [ ] **Step 1: Write failing test** — append to `tests/test_active_inventory.py`

```python
def test_inventory_has_new_columns():
    from src.backend.initialize_database_schema import Inventory
    cols = {c.name for c in Inventory.__table__.columns}
    assert {"expires_at", "expires_at_system", "expires_source", "last_purchased_at"}.issubset(cols)


def test_category_shelf_life_default_model_exists():
    from src.backend.initialize_database_schema import CategoryShelfLifeDefault
    cols = {c.name for c in CategoryShelfLifeDefault.__table__.columns}
    assert cols == {"category", "location_default", "shelf_life_days"}
```

- [ ] **Step 2: Run test, expect fail**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_active_inventory.py::test_inventory_has_new_columns tests/test_active_inventory.py::test_category_shelf_life_default_model_exists -v"`
Expected: `AttributeError` for `CategoryShelfLifeDefault`.

- [ ] **Step 3: Add columns + new model**

In `src/backend/initialize_database_schema.py`, ensure `Date` is imported alongside `DateTime`. Replace `class Inventory(Base):` body to add the four new columns:

```python
class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False, default=0)
    location = Column(String(50), nullable=True, default="Pantry")
    threshold = Column(Float, nullable=True)
    manual_low = Column(Boolean, nullable=False, default=False)
    is_active_window = Column(Boolean, nullable=False, default=True)
    last_updated = Column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    expires_at = Column(Date, nullable=True)
    expires_at_system = Column(Date, nullable=True)
    expires_source = Column(String(10), nullable=False, default="system")
    last_purchased_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_inventory_product_id", "product_id"),)
    product = relationship("Product", back_populates="inventory_items")
```

Add right after `class InventoryAdjustment`:

```python
class CategoryShelfLifeDefault(Base):
    __tablename__ = "category_shelf_life_default"

    category = Column(String(40), primary_key=True)
    location_default = Column(String(40), nullable=False)
    shelf_life_days = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 4: Run test, expect pass**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_active_inventory.py::test_inventory_has_new_columns tests/test_active_inventory.py::test_category_shelf_life_default_model_exists -v"`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```
git add src/backend/initialize_database_schema.py tests/test_active_inventory.py
git commit -m "feat(inventory): ORM — new columns + CategoryShelfLifeDefault model"
```

---

## Task 3 — Category defaults helper

**Files:**
- Create: `src/backend/category_shelf_life.py`
- Test: `tests/test_category_shelf_life.py`

- [ ] **Step 1: Write failing test** — `tests/test_category_shelf_life.py`

```python
"""Unit tests for category shelf-life default lookup."""
import pytest
from src.backend.initialize_database_schema import (
    Base, CategoryShelfLifeDefault, create_db_engine, create_session_factory,
)


@pytest.fixture
def session(tmp_path):
    db = tmp_path / "csl.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    Session = create_session_factory(eng)
    s = Session()
    s.add_all([
        CategoryShelfLifeDefault(category="dairy", location_default="Fridge", shelf_life_days=14),
        CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0),
    ])
    s.commit()
    yield s
    s.close()


def test_lookup_by_known_category(session):
    from src.backend.category_shelf_life import get_category_default
    d = get_category_default(session, "dairy")
    assert d.location_default == "Fridge"
    assert d.shelf_life_days == 14


def test_falls_back_to_other_when_unknown(session):
    from src.backend.category_shelf_life import get_category_default
    d = get_category_default(session, "made_up_category")
    assert d.category == "other"
    assert d.location_default == "Pantry"


def test_falls_back_to_sentinel_when_table_missing(tmp_path):
    from src.backend.category_shelf_life import get_category_default
    db = tmp_path / "empty.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    Session = create_session_factory(eng)
    s = Session()
    try:
        d = get_category_default(s, "anything")
        assert d.location_default == "Pantry"
        assert d.shelf_life_days == 0
    finally:
        s.close()


def test_none_category_falls_back_to_other(session):
    from src.backend.category_shelf_life import get_category_default
    d = get_category_default(session, None)
    assert d.category == "other"
```

- [ ] **Step 2: Run test, expect fail**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_category_shelf_life.py -v"`
Expected: `ModuleNotFoundError: No module named 'src.backend.category_shelf_life'`.

- [ ] **Step 3: Create the module** — `src/backend/category_shelf_life.py`

```python
"""Category shelf-life defaults — small lookup helper used by inventory writes.

Two safety nets:
  1. Unknown category falls back to the seeded "other" row.
  2. If the table is empty / corrupt, returns a hardcoded sentinel so the
     app stays up and the inventory page still loads.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging

from src.backend.initialize_database_schema import CategoryShelfLifeDefault


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Sentinel:
    category: str = "other"
    location_default: str = "Pantry"
    shelf_life_days: int = 0


_SENTINEL = _Sentinel()


def get_category_default(session, category: str | None):
    """Return the shelf-life default row for ``category``. Never raises."""
    cat = (category or "").strip().lower()
    try:
        if cat:
            row = session.query(CategoryShelfLifeDefault).filter_by(category=cat).first()
            if row:
                return row
        other = session.query(CategoryShelfLifeDefault).filter_by(category="other").first()
        if other:
            return other
        logger.warning("CategoryShelfLifeDefault table appears empty; using sentinel")
        return _SENTINEL
    except Exception as exc:  # noqa: BLE001
        logger.warning("CategoryShelfLifeDefault lookup failed (%s); using sentinel", exc)
        return _SENTINEL
```

- [ ] **Step 4: Run test, expect pass**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_category_shelf_life.py -v"`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```
git add src/backend/category_shelf_life.py tests/test_category_shelf_life.py
git commit -m "feat(inventory): category_shelf_life lookup with safe fallbacks"
```

---

## Task 4 — Pure write helpers

**Files:**
- Create: `src/backend/inventory_writes.py`
- Test: `tests/test_inventory_writes.py`

- [ ] **Step 1: Write failing test** — `tests/test_inventory_writes.py`

```python
"""Unit tests for inventory_writes pure helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.backend.initialize_database_schema import (
    Base, CategoryShelfLifeDefault, Inventory, InventoryAdjustment,
    Product, Purchase, ReceiptItem,
    create_db_engine, create_session_factory,
)


@pytest.fixture
def session(tmp_path):
    db = tmp_path / "iw.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()
    s.add_all([
        CategoryShelfLifeDefault(category="dairy", location_default="Fridge", shelf_life_days=14),
        CategoryShelfLifeDefault(category="meat", location_default="Fridge", shelf_life_days=3),
        CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0),
    ])
    s.commit()
    yield s
    s.close()


def _purchase(s, when, txn="purchase"):
    p = Purchase(date=when, total_amount=1.0, transaction_type=txn)
    s.add(p); s.flush()
    return p


def test_upsert_creates_row(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Milk", category="dairy"); session.add(prod); session.flush()
    purchase = _purchase(session, datetime(2026, 5, 1, tzinfo=timezone.utc))
    item = ReceiptItem(purchase_id=purchase.id, product_id=prod.id, quantity=2, unit_price=3.0)
    session.add(item); session.flush()

    upsert_inventory_for_receipt_item(session, prod, item, purchase)
    inv = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert inv.quantity == 2
    assert inv.location == "Fridge"
    assert inv.expires_at_system == date(2026, 5, 15)
    assert inv.expires_at == date(2026, 5, 15)
    assert inv.expires_source == "system"


def test_upsert_extends_expiry_on_newer_purchase(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Steak", category="meat"); session.add(prod); session.flush()
    p1 = _purchase(session, datetime(2026, 5, 1, tzinfo=timezone.utc))
    i1 = ReceiptItem(purchase_id=p1.id, product_id=prod.id, quantity=1, unit_price=5.0)
    session.add(i1); session.flush()
    upsert_inventory_for_receipt_item(session, prod, i1, p1)
    p2 = _purchase(session, datetime(2026, 5, 4, tzinfo=timezone.utc))
    i2 = ReceiptItem(purchase_id=p2.id, product_id=prod.id, quantity=1, unit_price=5.0)
    session.add(i2); session.flush()
    upsert_inventory_for_receipt_item(session, prod, i2, p2)
    inv = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert inv.quantity == 2
    assert inv.expires_at_system == date(2026, 5, 7)
    assert inv.expires_at == date(2026, 5, 7)


def test_upsert_preserves_user_override(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Steak", category="meat"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2030, 1, 1), expires_at_system=date(2026, 5, 4),
                    expires_source="user")
    session.add(inv); session.flush()
    p = _purchase(session, datetime(2026, 5, 5, tzinfo=timezone.utc))
    item = ReceiptItem(purchase_id=p.id, product_id=prod.id, quantity=1, unit_price=5.0)
    session.add(item); session.flush()
    upsert_inventory_for_receipt_item(session, prod, item, p)
    refreshed = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert refreshed.expires_at == date(2030, 1, 1)
    assert refreshed.expires_at_system == date(2026, 5, 8)


def test_upsert_preserves_defer(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Steak", category="meat"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2026, 5, 10), expires_at_system=date(2026, 5, 4),
                    expires_source="defer")
    session.add(inv); session.flush()
    p = _purchase(session, datetime(2026, 5, 5, tzinfo=timezone.utc))
    item = ReceiptItem(purchase_id=p.id, product_id=prod.id, quantity=1, unit_price=5.0)
    session.add(item); session.flush()
    upsert_inventory_for_receipt_item(session, prod, item, p)
    refreshed = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert refreshed.expires_at == date(2026, 5, 10)
    assert refreshed.expires_at_system == date(2026, 5, 8)


def test_refund_decrements_and_clamps(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Milk", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge", expires_source="system")
    session.add(inv); session.flush()
    p = _purchase(session, datetime(2026, 5, 5, tzinfo=timezone.utc), txn="refund")
    item = ReceiptItem(purchase_id=p.id, product_id=prod.id, quantity=5, unit_price=3.0)
    session.add(item); session.flush()
    upsert_inventory_for_receipt_item(session, prod, item, p)
    refreshed = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert refreshed.quantity == 0


def test_unknown_category_uses_other(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Toy", category="weird"); session.add(prod); session.flush()
    p = _purchase(session, datetime(2026, 5, 5, tzinfo=timezone.utc))
    item = ReceiptItem(purchase_id=p.id, product_id=prod.id, quantity=1, unit_price=10.0)
    session.add(item); session.flush()
    upsert_inventory_for_receipt_item(session, prod, item, p)
    inv = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert inv.location == "Pantry"
    assert inv.expires_at_system is None


def test_apply_manual_patch_quantity(session):
    from src.backend.inventory_writes import apply_manual_patch
    prod = Product(name="Eggs", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=12, location="Fridge", expires_source="system")
    session.add(inv); session.flush()
    apply_manual_patch(session, inv, {"quantity": 6}, user_id=None)
    assert inv.quantity == 6
    adj = session.query(InventoryAdjustment).filter_by(product_id=prod.id).one()
    assert adj.quantity_delta == -6
    assert adj.reason == "manual_edit"


def test_apply_manual_patch_used_up(session):
    from src.backend.inventory_writes import apply_manual_patch
    prod = Product(name="Eggs", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=12, location="Fridge", expires_source="system")
    session.add(inv); session.flush()
    apply_manual_patch(session, inv, {"quantity": 0}, user_id=None)
    assert inv.quantity == 0
    adj = session.query(InventoryAdjustment).filter_by(product_id=prod.id).one()
    assert adj.reason == "consumed_all"


def test_apply_manual_patch_explicit_expiry_marks_user(session):
    from src.backend.inventory_writes import apply_manual_patch
    prod = Product(name="Cheese", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2026, 5, 3), expires_at_system=date(2026, 5, 3),
                    expires_source="system")
    session.add(inv); session.flush()
    apply_manual_patch(session, inv, {"expires_at": "2026-06-01"}, user_id=None)
    assert inv.expires_at == date(2026, 6, 1)
    assert inv.expires_at_system == date(2026, 5, 3)
    assert inv.expires_source == "user"


def test_apply_manual_patch_defer_days_accumulates(session):
    from src.backend.inventory_writes import apply_manual_patch
    prod = Product(name="Pasta", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2026, 5, 3), expires_at_system=date(2026, 5, 3),
                    expires_source="system")
    session.add(inv); session.flush()
    apply_manual_patch(session, inv, {"defer_days": 3}, user_id=None)
    assert inv.expires_at == date(2026, 5, 6)
    assert inv.expires_source == "defer"
    apply_manual_patch(session, inv, {"defer_days": 3}, user_id=None)
    assert inv.expires_at == date(2026, 5, 9)


def test_reset_expiry_to_system(session):
    from src.backend.inventory_writes import reset_expiry_to_system
    prod = Product(name="Pasta", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2026, 6, 1), expires_at_system=date(2026, 5, 3),
                    expires_source="user")
    session.add(inv); session.flush()
    reset_expiry_to_system(session, inv, user_id=None)
    assert inv.expires_at == date(2026, 5, 3)
    assert inv.expires_source == "system"
```

- [ ] **Step 2: Run test, expect fail**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_inventory_writes.py -v"`
Expected: import error.

- [ ] **Step 3: Create the module** — `src/backend/inventory_writes.py`

```python
"""Pure inventory write helpers — no HTTP, no Flask, no transactions.

Three writers:
  upsert_inventory_for_receipt_item  — receipt-finalize side effect.
  apply_manual_patch                 — PATCH endpoint side effect.
  reset_expiry_to_system             — DELETE expiry-override side effect.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

from src.backend.category_shelf_life import get_category_default
from src.backend.initialize_database_schema import (
    Inventory, InventoryAdjustment, Product, Purchase, ReceiptItem,
)


logger = logging.getLogger(__name__)


def _purchase_sign(purchase: Purchase) -> int:
    txn = (getattr(purchase, "transaction_type", None) or "purchase").lower()
    return -1 if txn == "refund" else 1


def upsert_inventory_for_receipt_item(session, product: Product, item: ReceiptItem, purchase: Purchase) -> Inventory:
    """Mutates ``session``. Caller commits."""
    if product is None:
        return None  # type: ignore[return-value]
    defaults = get_category_default(session, product.category)
    inv = session.query(Inventory).filter_by(product_id=product.id).first()
    if inv is None:
        inv = Inventory(product_id=product.id, quantity=0,
                        location=defaults.location_default,
                        expires_source="system", is_active_window=True)
        session.add(inv); session.flush()

    sign = _purchase_sign(purchase)
    delta = float(item.quantity or 0) * sign
    inv.quantity = max(0.0, float(inv.quantity or 0) + delta)

    pdate = getattr(purchase, "date", None)
    if pdate is not None and (inv.last_purchased_at is None or pdate > inv.last_purchased_at):
        inv.last_purchased_at = pdate

    if defaults.shelf_life_days > 0 and pdate is not None and sign > 0:
        purchase_date = pdate.date() if isinstance(pdate, datetime) else pdate
        new_system = purchase_date + timedelta(days=defaults.shelf_life_days)
        prior_system = inv.expires_at_system or date.min
        inv.expires_at_system = max(new_system, prior_system)
        if inv.expires_source == "system":
            inv.expires_at = inv.expires_at_system

    inv.last_updated = datetime.now(timezone.utc)
    return inv


def _audit(session, product_id: int, delta: float, reason: str, user_id: int | None) -> None:
    session.add(InventoryAdjustment(product_id=product_id, quantity_delta=delta,
                                    reason=reason, user_id=user_id))


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"unsupported date value: {value!r}")


def apply_manual_patch(session, inv: Inventory, patch: dict, user_id: int | None) -> Inventory:
    if "quantity" in patch:
        new_qty = max(0.0, float(patch["quantity"]))
        delta = new_qty - float(inv.quantity or 0)
        if new_qty == 0 and (inv.quantity or 0) > 0:
            reason = "consumed_all"
        elif delta < 0:
            reason = "consumed"
        else:
            reason = "manual_edit"
        inv.quantity = new_qty
        _audit(session, inv.product_id, delta, reason, user_id)

    if "location" in patch and patch["location"]:
        new_loc = str(patch["location"]).strip()
        if new_loc and new_loc != (inv.location or ""):
            inv.location = new_loc
            _audit(session, inv.product_id, 0, "moved", user_id)

    if "expires_at" in patch:
        inv.expires_at = _coerce_date(patch["expires_at"])
        inv.expires_source = "user"
        _audit(session, inv.product_id, 0, "edit_expiry", user_id)

    if "defer_days" in patch and patch["defer_days"]:
        days = int(patch["defer_days"])
        base = inv.expires_at or inv.expires_at_system or date.today()
        inv.expires_at = base + timedelta(days=days)
        inv.expires_source = "defer"
        _audit(session, inv.product_id, 0, f"defer_expiry_+{days}d", user_id)

    inv.last_updated = datetime.now(timezone.utc)
    return inv


def reset_expiry_to_system(session, inv: Inventory, user_id: int | None) -> Inventory:
    inv.expires_at = inv.expires_at_system
    inv.expires_source = "system"
    _audit(session, inv.product_id, 0, "reset_expiry_to_system", user_id)
    inv.last_updated = datetime.now(timezone.utc)
    return inv
```

- [ ] **Step 4: Run test, expect pass**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_inventory_writes.py -v"`
Expected: `11 passed`.

- [ ] **Step 5: Commit**

```
git add src/backend/inventory_writes.py tests/test_inventory_writes.py
git commit -m "feat(inventory): pure write helpers — upsert, manual patch, reset"
```

---

## Task 5 — Wire receipt finalize → inventory upsert

**Files:**
- Modify: `src/backend/handle_receipt_upload.py`

- [ ] **Step 1: Locate the finalize loop**

Run: `grep -n "ReceiptItem(" src/backend/handle_receipt_upload.py`
Note the function name and the line where each `ReceiptItem` is added to the session.

- [ ] **Step 2: Add the upsert call**

Inside the per-item loop, immediately after the existing `session.add(receipt_item)` (and after the parent `Purchase` has its `id` available — call `session.flush()` if needed), insert:

```python
from src.backend.inventory_writes import upsert_inventory_for_receipt_item

# … inside the per-line-item loop, AFTER appending the ReceiptItem …
if product is not None:
    rt = (receipt_type or "").lower() if isinstance(receipt_type, str) else ""
    if rt in {"grocery", "retail_items", ""}:   # empty rt = older receipts treated as grocery
        try:
            upsert_inventory_for_receipt_item(session, product, receipt_item, purchase)
        except Exception as exc:  # noqa: BLE001
            logger.exception("inventory upsert failed for product %s: %s",
                             product.id, exc)
```

`receipt_type`, `product`, `receipt_item`, `purchase`, and `session` are existing locals in the function. Substitute the actual variable names if they differ.

- [ ] **Step 3: Run smoke test for receipt finalize**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_active_inventory.py tests/test_inventory_writes.py -v"`
Expected: green.

- [ ] **Step 4: Commit**

```
git add src/backend/handle_receipt_upload.py
git commit -m "feat(inventory): receipt finalize upserts Inventory rows"
```

---

## Task 6 — PATCH + reset endpoints

**Files:**
- Modify: `src/backend/manage_inventory.py`
- Test: `tests/test_inventory_endpoints.py`

- [ ] **Step 1: Write failing test** — `tests/test_inventory_endpoints.py`

```python
"""Integration tests for inventory PATCH and reset endpoints."""
from __future__ import annotations

from datetime import date

import pytest

from src.backend.create_flask_application import create_app
from src.backend.initialize_database_schema import (
    Base, CategoryShelfLifeDefault, Inventory, Product, User,
    create_db_engine, create_session_factory,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "ep.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()
    s.add(CategoryShelfLifeDefault(category="dairy", location_default="Fridge", shelf_life_days=14))
    s.add(CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0))
    admin = User(email="admin@test", role="admin"); s.add(admin); s.flush()
    prod = Product(name="Milk", category="dairy"); s.add(prod); s.flush()
    inv = Inventory(product_id=prod.id, quantity=4, location="Fridge",
                    expires_at=date(2026, 5, 3), expires_at_system=date(2026, 5, 3),
                    expires_source="system")
    s.add(inv); s.commit()
    pid, uid = prod.id, admin.id
    s.close()

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = uid
        yield c, pid


def test_patch_quantity(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"quantity": 1})
    assert r.status_code == 200
    assert r.get_json()["quantity"] == 1


def test_patch_used_up(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"quantity": 0})
    assert r.status_code == 200
    assert r.get_json()["quantity"] == 0


def test_patch_defer_days_marks_defer(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"defer_days": 3})
    assert r.status_code == 200
    body = r.get_json()
    assert body["expires_source"] == "defer"
    assert body["expires_at"] == "2026-05-06"


def test_patch_explicit_expiry_marks_user(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"expires_at": "2026-06-01"})
    assert r.status_code == 200
    assert r.get_json()["expires_source"] == "user"


def test_reset_expiry_clears_override(client):
    c, pid = client
    c.patch(f"/inventory/products/{pid}", json={"expires_at": "2026-06-01"})
    r = c.delete(f"/inventory/products/{pid}/expiry-override")
    assert r.status_code == 200
    body = r.get_json()
    assert body["expires_source"] == "system"
    assert body["expires_at"] == "2026-05-03"


def test_patch_negative_clamps(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"quantity": -5})
    assert r.status_code == 200
    assert r.get_json()["quantity"] == 0


def test_patch_invalid_date_400(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"expires_at": "not-a-date"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test, expect fail (404)**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_inventory_endpoints.py -v"`

- [ ] **Step 3: Add the routes** — append to `src/backend/manage_inventory.py`

```python
from src.backend.inventory_writes import apply_manual_patch, reset_expiry_to_system


def _serialize_inventory(inv):
    return {
        "product_id": inv.product_id,
        "quantity": inv.quantity,
        "location": inv.location,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "expires_at_system": inv.expires_at_system.isoformat() if inv.expires_at_system else None,
        "expires_source": inv.expires_source,
        "last_purchased_at": inv.last_purchased_at.isoformat() if inv.last_purchased_at else None,
    }


@inventory_bp.route("/products/<int:product_id>", methods=["PATCH"])
@require_auth
def patch_inventory_truth(product_id: int):
    body = request.get_json(silent=True) or {}
    inv = g.db_session.query(Inventory).filter_by(product_id=product_id).first()
    if not inv:
        return jsonify({"error": "inventory row not found"}), 404
    try:
        apply_manual_patch(g.db_session, inv, body, user_id=getattr(g.current_user, "id", None))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": f"invalid patch: {exc}"}), 400
    g.db_session.commit()
    return jsonify(_serialize_inventory(inv)), 200


@inventory_bp.route("/products/<int:product_id>/expiry-override", methods=["DELETE"])
@require_auth
def delete_expiry_override(product_id: int):
    inv = g.db_session.query(Inventory).filter_by(product_id=product_id).first()
    if not inv:
        return jsonify({"error": "inventory row not found"}), 404
    reset_expiry_to_system(g.db_session, inv, user_id=getattr(g.current_user, "id", None))
    g.db_session.commit()
    return jsonify(_serialize_inventory(inv)), 200
```

Then extend the existing `GET /inventory` serializer (search the file for `"quantity":` or `jsonify(`) so each row in the response includes the four new fields plus a derived `days_left = (expires_at - today).days if expires_at else None`.

- [ ] **Step 4: Run test, expect pass**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_inventory_endpoints.py -v"`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```
git add src/backend/manage_inventory.py tests/test_inventory_endpoints.py
git commit -m "feat(inventory): PATCH + reset endpoints with audit trail"
```

---

## Task 7 — Backfill helper + boot wiring

**Files:**
- Modify: `src/backend/active_inventory.py` (add `backfill_inventory_truth`)
- Modify: `src/backend/initialize_database_schema.py` (boot wiring)

- [ ] **Step 1: Write failing test** — append to `tests/test_active_inventory.py`

```python
def test_backfill_floors_to_today_plus_7(tmp_path):
    from datetime import date, datetime, timedelta, timezone
    from src.backend.initialize_database_schema import (
        Base, CategoryShelfLifeDefault, Inventory, Product, Purchase, ReceiptItem,
        Store, create_db_engine, create_session_factory,
    )
    from src.backend.active_inventory import backfill_inventory_truth

    db = tmp_path / "bf.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()
    s.add(CategoryShelfLifeDefault(category="produce", location_default="Fridge", shelf_life_days=7))
    s.add(CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0))
    store = Store(name="T"); s.add(store); s.flush()
    prod = Product(name="Banana", category="produce"); s.add(prod); s.flush()
    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    pur = Purchase(store_id=store.id, total_amount=1.0, date=long_ago, transaction_type="purchase")
    s.add(pur); s.flush()
    s.add(ReceiptItem(purchase_id=pur.id, product_id=prod.id, quantity=1, unit_price=1.0))
    s.add(Inventory(product_id=prod.id, quantity=1))
    s.commit()

    backfill_inventory_truth(s)
    inv = s.query(Inventory).filter_by(product_id=prod.id).one()
    assert inv.expires_at_system >= date.today() + timedelta(days=7)
    assert inv.expires_source == "system"


def test_backfill_skips_already_migrated(tmp_path):
    from datetime import date
    from src.backend.initialize_database_schema import (
        Base, CategoryShelfLifeDefault, Inventory, Product,
        create_db_engine, create_session_factory,
    )
    from src.backend.active_inventory import backfill_inventory_truth

    db = tmp_path / "bf2.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()
    s.add(CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0))
    prod = Product(name="X", category="other"); s.add(prod); s.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Bathroom",
                    expires_at=date(2030, 1, 1), expires_at_system=date(2030, 1, 1),
                    expires_source="user")
    s.add(inv); s.commit()
    backfill_inventory_truth(s)
    refreshed = s.query(Inventory).filter_by(product_id=prod.id).one()
    assert refreshed.location == "Bathroom"
    assert refreshed.expires_source == "user"
    assert refreshed.expires_at == date(2030, 1, 1)
```

- [ ] **Step 2: Run test, expect fail**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_active_inventory.py::test_backfill_floors_to_today_plus_7 tests/test_active_inventory.py::test_backfill_skips_already_migrated -v"`
Expected: `ImportError: cannot import name 'backfill_inventory_truth'`.

- [ ] **Step 3: Add the helper** — append to `src/backend/active_inventory.py`

```python
def backfill_inventory_truth(session) -> int:
    """Populate the new true-state columns for existing Inventory rows.

    Idempotent: rows where ``expires_at_system`` is already set are skipped.
    Returns the number of rows touched.
    """
    from datetime import date, timedelta
    from src.backend.category_shelf_life import get_category_default
    from src.backend.initialize_database_schema import (
        Inventory, Product, Purchase, ReceiptItem,
    )

    today = date.today()
    floor = today + timedelta(days=7)
    touched = 0
    rows = session.query(Inventory).filter(Inventory.expires_at_system.is_(None)).all()
    for inv in rows:
        product = session.query(Product).get(inv.product_id)
        if not product:
            continue
        defaults = get_category_default(session, product.category)
        last_ri = (
            session.query(ReceiptItem)
            .filter_by(product_id=product.id)
            .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
            .order_by(Purchase.date.desc())
            .first()
        )
        last_purchased = last_ri.purchase.date if last_ri else None
        inv.last_purchased_at = last_purchased
        if not inv.location:
            inv.location = defaults.location_default
        if defaults.shelf_life_days > 0 and last_purchased is not None:
            computed = last_purchased.date() + timedelta(days=defaults.shelf_life_days)
            inv.expires_at_system = max(computed, floor)
        else:
            inv.expires_at_system = None
        inv.expires_at = inv.expires_at_system
        inv.expires_source = "system"
        touched += 1
    session.commit()
    return touched
```

- [ ] **Step 4: Run tests, expect pass**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_active_inventory.py -v"`
Expected: green.

- [ ] **Step 5: Wire into boot**

In `src/backend/initialize_database_schema.py`, find `initialize_database()`. Right after the `command.upgrade(alembic_cfg, "head")` call, add:

```python
from src.backend.active_inventory import backfill_inventory_truth
SessionFactory = create_session_factory(engine)
session = SessionFactory()
try:
    n = backfill_inventory_truth(session)
    if n:
        logger.info("Inventory backfill: filled %d rows with true-state defaults", n)
except Exception as exc:  # noqa: BLE001
    logger.warning("Inventory backfill failed: %s", exc)
finally:
    session.close()
```

- [ ] **Step 6: Restart and confirm**

Run:
```
docker compose restart backend
docker compose logs backend --tail 30 | grep -i inventory
```

- [ ] **Step 7: Commit**

```
git add src/backend/active_inventory.py src/backend/initialize_database_schema.py tests/test_active_inventory.py
git commit -m "feat(inventory): one-shot backfill_inventory_truth + boot wiring"
```

---

## Task 8 — Drop nightly rebuild (defensive)

**Files:**
- Modify: `src/backend/schedule_daily_recommendations.py` (only if registration exists)
- Test: `tests/test_scheduler_inventory_off.py`

- [ ] **Step 1: Verify state**

Run: `grep -n "rebuild_active_inventory" src/backend/schedule_daily_recommendations.py`
If empty, the cron is already absent — proceed to Step 3 (still add the assertion test as a regression guard).

- [ ] **Step 2: Remove if present**

Delete any `_scheduler.add_job(rebuild_active_inventory, ...)` block and orphan imports.

- [ ] **Step 3: Add regression test** — `tests/test_scheduler_inventory_off.py`

```python
"""Regression guard: rebuild_active_inventory must not be a recurring job."""
import re

import src.backend.schedule_daily_recommendations as sched


def test_rebuild_active_inventory_is_not_scheduled():
    text = open(sched.__file__).read()
    matches = re.findall(r"add_job\(\s*rebuild_active_inventory", text)
    assert not matches, "rebuild_active_inventory must not be registered as a recurring job"
```

- [ ] **Step 4: Run tests**

Run: `docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_scheduler_inventory_off.py tests/test_smoke_phase*.py -v"`
Expected: green.

- [ ] **Step 5: Commit**

```
git add src/backend/schedule_daily_recommendations.py tests/test_scheduler_inventory_off.py
git commit -m "chore(inventory): regression guard against rebuild_active_inventory cron"
```

---

## Task 9 — Inventory page (DOM-built, no string injection)

**Files:**
- Modify: `src/frontend/index.html`

The renderer uses `document.createElement`, `textContent`, and `replaceChildren` exclusively — no string templates that interpolate user data into markup. CSS is added to the existing `<style>` block.

- [ ] **Step 1: Locate `#page-inventory`**

Run: `grep -n 'id="page-inventory"' src/frontend/index.html`
Note the line number. The page section ends before the next `<div class="page" id="page-...">`.

- [ ] **Step 2: Replace the page header + body markup**

Inside the `#page-inventory` block, replace the existing inventory rendering area with this scaffold:

```html
<div class="page-header">
  <h1 class="page-title">Inventory</h1>
  <div class="page-actions">
    <input id="inventory-search" class="page-search" placeholder="Search items...">
    <select id="inventory-location-filter" aria-label="Filter by location">
      <option value="">All locations</option>
      <option value="Fridge">Fridge</option>
      <option value="Freezer">Freezer</option>
      <option value="Pantry">Pantry</option>
      <option value="Cabinet">Cabinet</option>
      <option value="Bathroom">Bathroom</option>
    </select>
    <select id="inventory-sort">
      <option value="expiry">Sort: expiry asc</option>
      <option value="name">Sort: name</option>
      <option value="qty">Sort: quantity</option>
    </select>
    <label class="page-toggle">
      <input type="checkbox" id="inventory-show-empty"> Show empty
    </label>
  </div>
</div>
<div class="page-body">
  <div id="inventory-groups"></div>
</div>
```

- [ ] **Step 3: Append CSS to the existing `<style>` block**

```css
.inv-group { margin-bottom: 18px; }
.inv-group-header {
  font-size: 0.95rem; font-weight: 600; padding: 6px 0;
  border-bottom: 1px solid var(--border, #333); color: var(--accent, #aad);
  user-select: none;
}
.inv-tiles {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px; margin-top: 10px;
}
.inv-tile {
  background: var(--surface, #2a2a2a);
  border-left: 4px solid #4a4;
  border-radius: 6px; padding: 10px;
}
.inv-tile.exp-expired { border-left-color: #d33; }
.inv-tile.exp-soon    { border-left-color: #e87; }
.inv-tile.exp-watch   { border-left-color: #cc0; }
.inv-tile.empty       { opacity: 0.55; }
.inv-tile-head { display: flex; justify-content: space-between; font-size: 0.85rem; align-items: center; }
.inv-tile-name { font-weight: 600; margin: 4px 0; font-size: 1rem; }
.inv-tile-meta { font-size: 0.75rem; color: var(--muted, #999); line-height: 1.5; }
.inv-tile-meta .tag-user  { background: #3a4f6b; color: #cde; padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; }
.inv-tile-meta .tag-defer { background: #5a4a2a; color: #ffd; padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; }
.inv-tile-actions { display: flex; gap: 4px; margin-top: 10px; flex-wrap: wrap; }
.inv-tile-actions button { flex: 1; padding: 5px 8px; border: none; border-radius: 4px; font-size: 0.74rem; cursor: pointer; }
.inv-btn-edit  { background: #444;    color: #ddd; }
.inv-btn-defer { background: #5a4a2a; color: #ffd; }
.inv-btn-decr  { background: #444;    color: #ffb; }
.inv-btn-used  { background: #3a6b3a; color: #fff; }
@keyframes invExpiryPulse  { 0%,100% { color:#e87; text-shadow:0 0 0 transparent; } 50% { color:#fff; text-shadow:0 0 8px #e87; } }
@keyframes invExpiredPulse { 0%,100% { color:#d33; text-shadow:0 0 0 transparent; } 50% { color:#fff; text-shadow:0 0 10px #d33; } }
.flash-soon    { animation: invExpiryPulse 1.4s ease-in-out infinite; font-weight: 600; }
.flash-expired { animation: invExpiredPulse 1s ease-in-out infinite; font-weight: 700; }
@media (prefers-reduced-motion: reduce) {
  .flash-soon, .flash-expired { animation: none; }
}
```

- [ ] **Step 4: Add the JS renderer (DOM-only, no string injection)**

Find the existing JS that loads `/inventory` (search for `'/inventory'` in `src/frontend/index.html`). Replace the loader + renderer with the block below. Every text value goes through `textContent` and every element is a `createElement`; classes come from a static literal whitelist.

```javascript
const LOCATION_ORDER = ["Fridge", "Freezer", "Pantry", "Cabinet", "Bathroom"];
const LOCATION_EMOJI = {Fridge:"🧊", Freezer:"❄️", Pantry:"🥫", Cabinet:"🚪", Bathroom:"🛁"};

async function loadInventory() {
  const root = document.getElementById("inventory-groups");
  if (!root) return;
  root.replaceChildren(elText("div", "muted", "Loading..."));
  try {
    const res = await api("/inventory");
    if (!res.ok) {
      root.replaceChildren(elText("div", "error", "Failed: " + res.status));
      return;
    }
    const data = await res.json();
    window.__inventoryRaw = data.items || data || [];
    renderInventory();
  } catch (e) {
    root.replaceChildren(elText("div", "error", String(e.message || e)));
  }
}

function elText(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text != null) el.textContent = text;
  return el;
}

function classifyExpiry(daysLeft) {
  if (daysLeft === null || daysLeft === undefined) return "exp-fresh";
  if (daysLeft <= 0) return "exp-expired";
  if (daysLeft <= 3) return "exp-soon";
  if (daysLeft <= 7) return "exp-watch";
  return "exp-fresh";
}

function flashClassFor(expClass) {
  if (expClass === "exp-expired") return "flash-expired";
  if (expClass === "exp-soon") return "flash-soon";
  return "";
}

function enrich(items) {
  const today = new Date(); today.setHours(0,0,0,0);
  return items.map(i => {
    const exp = i.expires_at ? new Date(i.expires_at + "T00:00:00") : null;
    const days = exp ? Math.round((exp - today) / 86400000) : null;
    return Object.assign({}, i, { _days: days, _expCls: classifyExpiry(days) });
  });
}

function renderInventory() {
  const root = document.getElementById("inventory-groups");
  if (!root) return;
  const items = window.__inventoryRaw || [];
  const search = (document.getElementById("inventory-search").value || "").toLowerCase();
  const locFilter = document.getElementById("inventory-location-filter").value;
  const sort = document.getElementById("inventory-sort").value;
  const showEmpty = document.getElementById("inventory-show-empty").checked;

  let enriched = enrich(items)
    .filter(i => showEmpty || (i.quantity || 0) > 0)
    .filter(i => !search || (i.product_name || "").toLowerCase().includes(search))
    .filter(i => !locFilter || i.location === locFilter);

  if (sort === "name") enriched.sort((a, b) => (a.product_name || "").localeCompare(b.product_name || ""));
  else if (sort === "qty") enriched.sort((a, b) => (b.quantity || 0) - (a.quantity || 0));
  else enriched.sort((a, b) => ((a._days ?? 9999) - (b._days ?? 9999)));

  const groups = {};
  for (const i of enriched) {
    const loc = i.location || "Pantry";
    (groups[loc] = groups[loc] || []).push(i);
  }
  const order = LOCATION_ORDER.concat(Object.keys(groups).filter(k => !LOCATION_ORDER.includes(k)));
  const newChildren = [];
  for (const loc of order) {
    const list = groups[loc] || [];
    if (!list.length) continue;
    newChildren.push(buildGroup(loc, list));
  }
  root.replaceChildren.apply(root, newChildren);
}

function buildGroup(loc, items) {
  const wrap = elText("div", "inv-group");
  const head = elText("div", "inv-group-header");
  const expSoon = items.filter(i => i._expCls === "exp-soon" || i._expCls === "exp-expired").length;
  const emoji = LOCATION_EMOJI[loc] || "📦";
  head.appendChild(document.createTextNode(emoji + " " + loc + " · " + items.length + " items"));
  if (expSoon) {
    const s = elText("span", "muted-warn", " · " + expSoon + " expiring soon");
    s.style.color = "#e87";
    head.appendChild(s);
  }
  wrap.appendChild(head);
  const tiles = elText("div", "inv-tiles");
  for (const i of items) tiles.appendChild(buildTile(i));
  wrap.appendChild(tiles);
  return wrap;
}

function buildTile(i) {
  const tile = elText("div", "inv-tile " + i._expCls + ((i.quantity || 0) === 0 ? " empty" : ""));
  const head = elText("div", "inv-tile-head " + flashClassFor(i._expCls));
  const headLabel = i._days === null ? "no expiry"
                  : i._days <= 0 ? "EXPIRED " + Math.abs(i._days) + "d ago"
                  : i._days + "d left";
  head.appendChild(elText("span", null, headLabel));
  head.appendChild(elText("span", null, "×" + (i.quantity || 0)));
  tile.appendChild(head);

  tile.appendChild(elText("div", "inv-tile-name", i.product_name || ""));

  const meta = elText("div", "inv-tile-meta");
  if (i.last_purchased_at) {
    meta.appendChild(elText("div", null, "📅 Bought " + String(i.last_purchased_at).slice(0, 10)));
  }
  if (i.expires_at) {
    const line = document.createElement("div");
    line.appendChild(document.createTextNode("🍂 Expires "));
    const dateSpan = document.createElement("span");
    dateSpan.className = flashClassFor(i._expCls);
    dateSpan.textContent = i.expires_at;
    line.appendChild(dateSpan);
    if (i.expires_source === "user") {
      line.appendChild(document.createTextNode(" "));
      line.appendChild(elText("span", "tag-user", "user"));
    } else if (i.expires_source === "defer") {
      line.appendChild(document.createTextNode(" "));
      line.appendChild(elText("span", "tag-defer", "defer"));
    }
    meta.appendChild(line);
  }
  tile.appendChild(meta);

  const actions = elText("div", "inv-tile-actions");
  actions.appendChild(makeBtn("inv-btn-edit",  "✎", () => invEdit(i.product_id)));
  actions.appendChild(makeBtn("inv-btn-defer", "+3d", () => invDefer(i.product_id, 3)));
  actions.appendChild(makeBtn("inv-btn-defer", "+7d", () => invDefer(i.product_id, 7)));
  actions.appendChild(makeBtn("inv-btn-decr",  "−1",  () => invDecrement(i.product_id)));
  actions.appendChild(makeBtn("inv-btn-used",  "✓",   () => invUsedUp(i.product_id)));
  tile.appendChild(actions);
  return tile;
}

function makeBtn(cls, text, onClick) {
  const b = document.createElement("button");
  b.className = cls;
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}

async function invPatch(pid, body) {
  const res = await api("/inventory/products/" + pid, { method: "PATCH", body: JSON.stringify(body) });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    toast("Failed: " + (err.error || res.status), "error");
    return;
  }
  await loadInventory();
}

function invDefer(pid, days)   { invPatch(pid, { defer_days: days }); }
function invDecrement(pid) {
  const inv = (window.__inventoryRaw || []).find(x => x.product_id === pid);
  if (!inv) return;
  invPatch(pid, { quantity: Math.max(0, (inv.quantity || 0) - 1) });
}
function invUsedUp(pid)   {
  invPatch(pid, { quantity: 0 });
  toast("Marked used up · undo", "info");
}
function invEdit(pid) {
  const inv = (window.__inventoryRaw || []).find(x => x.product_id === pid);
  if (!inv) return;
  const nextQty = prompt("Quantity", inv.quantity);
  if (nextQty === null) return;
  const nextDate = prompt("Expires (YYYY-MM-DD or empty)", inv.expires_at || "");
  const body = {};
  if (nextQty !== "" && !isNaN(parseFloat(nextQty))) body.quantity = parseFloat(nextQty);
  if (nextDate !== null) body.expires_at = nextDate || null;
  invPatch(pid, body);
}

["inventory-search","inventory-location-filter","inventory-sort","inventory-show-empty"]
  .forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", renderInventory);
  });
```

Find the existing page-show handler (search for the function that switches to `#page-inventory`) and ensure it calls `loadInventory()` once on page show.

- [ ] **Step 5: Rebuild + reload**

Run: `docker compose up -d --build backend`
Then in the browser: hard-refresh (Cmd+Shift+R), navigate to Inventory.

- [ ] **Step 6: Manual smoke**

- Tiles group by location ✓
- Stripe color matches days_left ✓
- ≤2d expiry pulses; OS reduced-motion disables it ✓
- ✎ prompts qty + date, persists ✓
- +3d / +7d shifts, marks `defer` chip ✓
- −1 silently decrements ✓
- ✓ marks used up, toggling Show empty reveals greyed tile ✓

- [ ] **Step 7: Commit**

```
git add src/frontend/index.html
git commit -m "feat(inventory): location-grouped tiles with stripe + pulse + edit/defer/use actions"
```

---

## Task 10 — Final smoke + backup-restore safety check

- [ ] **Step 1: Run full test suite**

```
docker compose exec backend bash -c "cd /app && python3 -m pytest tests/test_active_inventory.py tests/test_inventory_writes.py tests/test_category_shelf_life.py tests/test_inventory_endpoints.py tests/test_migration_021.py tests/test_smoke_phase*.py -v"
```

- [ ] **Step 2: Backup → restore on dev**

Trigger a backup via the existing admin endpoint (or `manage_environment_ops._create_backup_archive()`), then restore it onto a copied DB and verify the Inventory page still loads with tiles.

- [ ] **Step 3: Push branch + open PR**

```
git push -u origin <branch-name>
gh pr create --title "Inventory true state — schema + UI overhaul" --body "$(cat <<'EOF'
## Summary
- Migration 021: location/expires_at/expires_source/last_purchased_at on inventory + new CategoryShelfLifeDefault table
- Receipt finalize is the only automatic writer
- New PATCH endpoint covers manual qty/location/expiry edits + defer presets
- Frontend: location-grouped tiles, color stripes, pulse animation, DOM-built (no innerHTML)
## Test plan
- [x] all unit + integration tests green
- [x] tile renders with stripe + pulse
- [x] backup → restore on dev → page still works

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

- **Spec coverage:** every spec section maps to ≥1 task. Schema → 1+2; helpers → 3, 4, 7; write paths → 5, 6, 8; UI → 9; migration safety → 1, 7, 10. ✓
- **Placeholder scan:** no TBDs, no "similar to Task N", every code block is complete. ✓
- **Type consistency:** `Inventory.expires_source` values `"system"` / `"user"` / `"defer"` consistent across Tasks 4, 6, 7, 9. `apply_manual_patch(session, inv, patch, user_id)` signature matches between definition (Task 4) and callers (Task 6). `get_category_default(session, category)` consistent across Tasks 3, 4, 7. `backfill_inventory_truth(session)` consistent in Tasks 7 + 10. ✓
- **Backup-restore safety:** Task 1 (PRAGMA-guarded ADD COLUMN), Task 7 (idempotent backfill on boot), Task 10 (manual restore drill). ✓
- **Frontend safety:** Task 9 uses `createElement` + `textContent` + `replaceChildren` exclusively — no string-template DOM injection that could XSS on user-controlled product names. ✓
