# Telegram Inventory Walk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `/inventory` Telegram flow that walks the user through stale items by category using quantized stock-level buttons (Empty/¼/½/¾/Full), then optionally adds empty items to the shopping list. Plus a daily proactive nudge for stale inventory.

**Architecture:** New `TelegramInventorySession` table (one row per chat_id) holds walk state. New `handle_inventory_walk.py` module owns the state machine, rendering, and per-callback handlers. Existing `handle_telegram_messages.py` is extended only with routing for `/inventory` command and `inv:*` / `nudge:*` callback prefixes. Inventory writes reuse existing `Inventory.consumed_pct_override` / `manual_low` / `is_active_window` fields. Shopping-list inserts reuse `manage_shopping_list._ensure_current_session`. Daily nudge runs via APScheduler alongside `check_inventory_thresholds`.

**Tech Stack:** Python 3.11+, Flask, SQLAlchemy 2.x, Alembic, APScheduler, pytest, SQLite (test) / Postgres (prod).

**Spec:** [docs/superpowers/specs/2026-05-13-telegram-inventory-walk-design.md](../specs/2026-05-13-telegram-inventory-walk-design.md)

---

## File map

**Create:**
- `alembic/versions/031_telegram_inventory_session.py` — migration (additive, idempotent, no-op downgrade)
- `src/backend/handle_inventory_walk.py` — state machine, dispatch, rendering, inventory mutations
- `src/backend/inventory_nudge_job.py` — daily eligibility + send job
- `tests/test_migration_031.py` — migration unit tests
- `tests/test_telegram_inventory_walk.py` — module unit tests
- `tests/test_inventory_nudge_job.py` — nudge job unit tests
- `tests/test_telegram_inventory_e2e.py` — end-to-end webhook flow test

**Modify:**
- `src/backend/initialize_database_schema.py` — add `TelegramInventorySession` SQLAlchemy model
- `src/backend/handle_telegram_messages.py` — route `/inventory` command + `inv:*` / `nudge:*` callbacks
- `src/backend/check_inventory_thresholds.py` — register daily nudge APScheduler job

---

## Conventions

- All `pytest` commands run from repo root.
- Each task ends with one commit. Commit messages use Conventional Commits (`feat(...)`, `test(...)`, `chore(...)`).
- Tests use the existing in-memory SQLite fixture pattern from `tests/test_full_receipt_flow.py` (`os.environ["DATABASE_URL"] = "sqlite://"` set before imports).
- All Telegram HTTP calls in tests are stubbed via `unittest.mock.patch("src.backend.handle_inventory_walk.send_telegram_message")` (or equivalent).
- Time is mocked via `freezegun` if available; otherwise via `unittest.mock.patch("src.backend.handle_inventory_walk.utcnow")`. Check `tests/test_active_inventory.py` for the pattern used in this repo before deciding.

---

## Task 1: Migration 031 — `telegram_inventory_session` table

**Files:**
- Create: `alembic/versions/031_telegram_inventory_session.py`
- Test: `tests/test_migration_031.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migration_031.py
"""Tests for Alembic migration 031_telegram_inventory_session."""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "031_telegram_inventory_session.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_031", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.db"
    c = sqlite3.connect(db)
    yield c
    c.close()


def test_031_module_loads():
    mig = _load_migration()
    assert mig.revision == "031_telegram_inventory_session"
    assert mig.down_revision == "030_account_display_name_and_owner"


def test_031_downgrade_drops_table(conn):
    mig = _load_migration()
    # Pre-create the table so downgrade has something to drop.
    conn.executescript(
        "CREATE TABLE telegram_inventory_session ("
        " chat_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'active');"
    )
    conn.commit()
    engine = sa.create_engine(f"sqlite:///{conn.execute('PRAGMA database_list').fetchone()[2]}")
    with patch("alembic.op.get_bind", return_value=engine.connect()):
        mig.downgrade()
    # Table is dropped (best-effort: re-open and check).
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='telegram_inventory_session'"
    )
    assert cur.fetchone() is None


def test_031_upgrade_creates_table_and_is_idempotent(tmp_path):
    """upgrade() creates table with expected columns; re-running is a no-op."""
    mig = _load_migration()
    db_path = tmp_path / "u.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")

    with engine.begin() as bind:
        with patch("alembic.op.get_bind", return_value=bind):
            mig.upgrade()
            # Idempotent — second run must not raise.
            mig.upgrade()

    # Inspect schema.
    insp = sa.inspect(engine)
    assert "telegram_inventory_session" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("telegram_inventory_session")}
    expected = {
        "chat_id", "user_id", "status", "current_category", "item_queue",
        "cursor", "page", "pending_prompt", "last_item_id", "stats",
        "nudge_muted_until", "last_nudge_sent_at", "started_at", "last_action_at",
    }
    assert expected <= cols, f"missing: {expected - cols}"

    idx_names = {i["name"] for i in insp.get_indexes("telegram_inventory_session")}
    assert "ix_tg_inv_status" in idx_names
    assert "ix_tg_inv_last_action" in idx_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migration_031.py -v`
Expected: FAIL — migration file doesn't exist.

- [ ] **Step 3: Write the migration**

```python
# alembic/versions/031_telegram_inventory_session.py
"""telegram_inventory_session: per-chat walk state for /inventory Telegram flow.

Revision ID: 031_telegram_inventory_session
Revises: 030_account_display_name_and_owner
Create Date: 2026-05-13

Additive: creates one new table. Idempotent: re-running upgrade is a no-op.
Downgrade drops the table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "031_telegram_inventory_session"
down_revision: Union[str, None] = "030_account_display_name_and_owner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    row = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "telegram_inventory_session"):
        return

    op.create_table(
        "telegram_inventory_session",
        sa.Column("chat_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("current_category", sa.String(40), nullable=True),
        sa.Column("item_queue", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("cursor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("page", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pending_prompt", sa.String(30), nullable=True),
        sa.Column("last_item_id", sa.Integer, nullable=True),
        sa.Column("stats", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("nudge_muted_until", sa.DateTime, nullable=True),
        sa.Column("last_nudge_sent_at", sa.DateTime, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("last_action_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index(
        "ix_tg_inv_status", "telegram_inventory_session", ["status"]
    )
    op.create_index(
        "ix_tg_inv_last_action", "telegram_inventory_session", ["last_action_at"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "telegram_inventory_session"):
        return
    op.drop_index("ix_tg_inv_last_action", table_name="telegram_inventory_session")
    op.drop_index("ix_tg_inv_status", table_name="telegram_inventory_session")
    op.drop_table("telegram_inventory_session")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_migration_031.py -v`
Expected: PASS — all four tests.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/031_telegram_inventory_session.py tests/test_migration_031.py
git commit -m "feat(db): migration 031 — telegram_inventory_session table"
```

---

## Task 2: SQLAlchemy `TelegramInventorySession` model

**Files:**
- Modify: `src/backend/initialize_database_schema.py` — add new class near `TelegramReceipt` (around line 646)
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telegram_inventory_walk.py
"""Unit tests for handle_inventory_walk + TelegramInventorySession model."""
from __future__ import annotations

import os
import pytest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ.setdefault("TELEGRAM_INVENTORY_WALK_ENABLED", "1")

from src.backend.initialize_database_schema import (
    Base, TelegramInventorySession, get_engine, get_session_factory,
)


@pytest.fixture
def session():
    eng = get_engine()
    Base.metadata.create_all(eng)
    SessionFactory = get_session_factory()
    s = SessionFactory()
    yield s
    s.close()
    Base.metadata.drop_all(eng)


def test_telegram_inventory_session_round_trip(session):
    row = TelegramInventorySession(
        chat_id="12345",
        status="active",
        current_category="pantry",
        item_queue=[1, 2, 3],
        cursor=0,
        page=1,
        pending_prompt="level",
        stats={"updated": 0},
    )
    session.add(row)
    session.commit()

    fetched = session.query(TelegramInventorySession).filter_by(chat_id="12345").one()
    assert fetched.status == "active"
    assert fetched.current_category == "pantry"
    assert fetched.item_queue == [1, 2, 3]
    assert fetched.cursor == 0
    assert fetched.pending_prompt == "level"
    assert fetched.stats == {"updated": 0}
    assert fetched.started_at is not None
    assert fetched.last_action_at is not None
```

Note: `get_engine` and `get_session_factory` are existing helpers; if their actual names differ in `initialize_database_schema.py`, substitute the existing helper names used by `tests/test_active_inventory.py` or `tests/test_full_receipt_flow.py`. Check those tests for the right import.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_inventory_walk.py::test_telegram_inventory_session_round_trip -v`
Expected: FAIL — `ImportError: cannot import name 'TelegramInventorySession'`.

- [ ] **Step 3: Add the model**

In `src/backend/initialize_database_schema.py`, add the class near the existing `TelegramReceipt` class (after `class TelegramReceipt(Base):`):

```python
class TelegramInventorySession(Base):
    __tablename__ = "telegram_inventory_session"

    chat_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    current_category = Column(String(40), nullable=True)
    item_queue = Column(JSON, nullable=False, default=list)
    cursor = Column(Integer, nullable=False, default=0)
    page = Column(Integer, nullable=False, default=1)
    pending_prompt = Column(String(30), nullable=True)
    last_item_id = Column(Integer, nullable=True)
    stats = Column(JSON, nullable=False, default=dict)
    nudge_muted_until = Column(DateTime, nullable=True)
    last_nudge_sent_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, default=utcnow)
    last_action_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_tg_inv_status", "status"),
        Index("ix_tg_inv_last_action", "last_action_at"),
    )
```

Verify `JSON` and `utcnow` are already imported in this file (they are — used by `TelegramReceipt`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_telegram_inventory_walk.py::test_telegram_inventory_session_round_trip -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/initialize_database_schema.py tests/test_telegram_inventory_walk.py
git commit -m "feat(db): TelegramInventorySession SQLAlchemy model"
```

---

## Task 3: Module skeleton — constants, env, `_is_walk_enabled`

**Files:**
- Create: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_telegram_inventory_walk.py`:

```python
def test_constants_have_safe_defaults(monkeypatch):
    monkeypatch.delenv("INVENTORY_STALE_DAYS", raising=False)
    monkeypatch.delenv("TELEGRAM_INVENTORY_WALK_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_INVENTORY_WALK_PILOT_CHATS", raising=False)
    import importlib
    import src.backend.handle_inventory_walk as m
    importlib.reload(m)
    assert m.INVENTORY_STALE_DAYS == 14
    assert m.PAGE_SIZE == 10
    assert m.IDLE_TIMEOUT_MIN == 30
    assert m.WALK_ENABLED is False
    assert m.PILOT_CHATS == set()


def test_is_walk_enabled_respects_flags(monkeypatch):
    import importlib
    import src.backend.handle_inventory_walk as m
    monkeypatch.setenv("TELEGRAM_INVENTORY_WALK_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_INVENTORY_WALK_PILOT_CHATS", "")
    importlib.reload(m)
    assert m.is_walk_enabled("999") is True

    monkeypatch.setenv("TELEGRAM_INVENTORY_WALK_PILOT_CHATS", "111,222")
    importlib.reload(m)
    assert m.is_walk_enabled("111") is True
    assert m.is_walk_enabled("999") is False

    monkeypatch.setenv("TELEGRAM_INVENTORY_WALK_ENABLED", "0")
    importlib.reload(m)
    assert m.is_walk_enabled("111") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_inventory_walk.py::test_constants_have_safe_defaults -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write the module skeleton**

```python
# src/backend/handle_inventory_walk.py
"""Telegram /inventory walk — state machine, dispatch, rendering.

See docs/superpowers/specs/2026-05-13-telegram-inventory-walk-design.md
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _csv_env(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {chunk.strip() for chunk in raw.split(",") if chunk.strip()}


INVENTORY_STALE_DAYS = _int_env("INVENTORY_STALE_DAYS", 14)
PAGE_SIZE = _int_env("INVENTORY_WALK_PAGE_SIZE", 10)
IDLE_TIMEOUT_MIN = _int_env("INVENTORY_WALK_IDLE_TIMEOUT_MIN", 30)
WALK_ENABLED = _bool_env("TELEGRAM_INVENTORY_WALK_ENABLED", False)
PILOT_CHATS: set[str] = _csv_env("TELEGRAM_INVENTORY_WALK_PILOT_CHATS")


def is_walk_enabled(chat_id: str) -> bool:
    if not WALK_ENABLED:
        return False
    if PILOT_CHATS and chat_id not in PILOT_CHATS:
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "constants or is_walk_enabled"`
Expected: PASS — both new tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): handle_inventory_walk module skeleton + feature flags"
```

---

## Task 4: Stale-item queries

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing test**

```python
def _seed_inventory(session, *, days_old_pairs):
    """days_old_pairs: list[(product_name, category, days_old)]."""
    from src.backend.initialize_database_schema import Product, Inventory, utcnow
    from datetime import timedelta
    for name, category, days in days_old_pairs:
        p = Product(name=name, category=category)
        session.add(p)
        session.flush()
        inv = Inventory(
            product_id=p.id,
            quantity=1.0,
            location="Pantry",
            is_active_window=True,
        )
        inv.last_updated = utcnow() - timedelta(days=days)
        session.add(inv)
    session.commit()


def test_categories_with_stale_counts_filters_threshold(session):
    from src.backend.handle_inventory_walk import categories_with_stale_counts
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil",  "pantry",  20),  # stale
        ("Black pepper", "pantry", 30), # stale
        ("Milk", "fridge", 15),         # stale
        ("Fresh bread", "pantry", 2),   # not stale
    ])
    counts = categories_with_stale_counts(session)
    assert counts == [("pantry", 2), ("fridge", 1)]


def test_categories_with_stale_counts_ignores_inactive_rows(session):
    from src.backend.handle_inventory_walk import categories_with_stale_counts
    from src.backend.initialize_database_schema import Product, Inventory, utcnow
    p = Product(name="Ghost", category="pantry")
    session.add(p)
    session.flush()
    inv = Inventory(product_id=p.id, quantity=0, is_active_window=False)
    inv.last_updated = utcnow() - timedelta(days=99)
    session.add(inv)
    session.commit()
    assert categories_with_stale_counts(session) == []


def test_stale_items_in_category_returns_ordered_page(session):
    from src.backend.handle_inventory_walk import stale_items_in_category
    _seed_inventory(session, days_old_pairs=[
        (f"Item {i}", "pantry", 14 + i) for i in range(12)
    ])
    page1 = stale_items_in_category(session, "pantry", page=1)
    page2 = stale_items_in_category(session, "pantry", page=2)
    assert len(page1) == 10
    assert len(page2) == 2
    # oldest first
    assert page1[0].product.name == "Item 11"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "categories_with_stale or stale_items"`
Expected: FAIL — `cannot import name 'categories_with_stale_counts'`.

- [ ] **Step 3: Implement the queries**

Append to `src/backend/handle_inventory_walk.py`:

```python
from sqlalchemy import func, and_

def _stale_cutoff() -> datetime:
    return datetime.utcnow() - timedelta(days=INVENTORY_STALE_DAYS)


def categories_with_stale_counts(session) -> list[tuple[str, int]]:
    """Return [(category, n_stale_items), ...] sorted by count desc."""
    from src.backend.initialize_database_schema import Inventory, Product

    cutoff = _stale_cutoff()
    rows = (
        session.query(Product.category, func.count(Inventory.id))
        .join(Inventory, Inventory.product_id == Product.id)
        .filter(Inventory.is_active_window.is_(True))
        .filter(Inventory.last_updated < cutoff)
        .group_by(Product.category)
        .order_by(func.count(Inventory.id).desc())
        .all()
    )
    return [(cat or "other", n) for cat, n in rows]


def stale_items_in_category(session, category: str, page: int = 1):
    """Return Inventory rows for one page (oldest-first) in the given category."""
    from src.backend.initialize_database_schema import Inventory, Product

    cutoff = _stale_cutoff()
    offset = (page - 1) * PAGE_SIZE
    return (
        session.query(Inventory)
        .join(Product, Product.id == Inventory.product_id)
        .filter(Inventory.is_active_window.is_(True))
        .filter(Inventory.last_updated < cutoff)
        .filter(func.lower(func.coalesce(Product.category, "other")) == category.lower())
        .order_by(Inventory.last_updated.asc())
        .offset(offset)
        .limit(PAGE_SIZE)
        .all()
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "categories_with_stale or stale_items"`
Expected: PASS — three tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): stale-item queries for inventory walk"
```

---

## Task 5: Session row helpers — fetch / create / reset / idle-check

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_get_or_create_session_creates_row(session):
    from src.backend.handle_inventory_walk import get_or_create_session
    row = get_or_create_session(session, "abc")
    assert row.chat_id == "abc"
    assert row.status == "active"
    assert row.item_queue == []
    assert row.cursor == 0


def test_get_or_create_session_returns_existing(session):
    from src.backend.handle_inventory_walk import get_or_create_session
    from src.backend.initialize_database_schema import TelegramInventorySession
    session.add(TelegramInventorySession(
        chat_id="abc", status="active", current_category="pantry", cursor=3,
    ))
    session.commit()
    row = get_or_create_session(session, "abc")
    assert row.current_category == "pantry"
    assert row.cursor == 3


def test_reset_for_start_over_preserves_nudge_prefs(session):
    from src.backend.handle_inventory_walk import reset_for_start_over
    from src.backend.initialize_database_schema import TelegramInventorySession
    from datetime import datetime, timedelta
    nudge_until = datetime.utcnow() + timedelta(days=7)
    row = TelegramInventorySession(
        chat_id="abc",
        status="done",
        current_category="pantry",
        item_queue=[1, 2, 3],
        cursor=2,
        stats={"updated": 5},
        nudge_muted_until=nudge_until,
    )
    session.add(row)
    session.commit()

    reset_for_start_over(row)
    session.commit()

    assert row.status == "active"
    assert row.current_category is None
    assert row.item_queue == []
    assert row.cursor == 0
    assert row.page == 1
    assert row.pending_prompt == "category"
    assert row.stats == {}
    assert row.nudge_muted_until == nudge_until  # preserved


def test_abandon_if_idle_marks_status(session):
    from src.backend.handle_inventory_walk import abandon_if_idle
    from src.backend.initialize_database_schema import TelegramInventorySession, utcnow
    row = TelegramInventorySession(chat_id="abc", status="active")
    session.add(row)
    session.commit()
    row.last_action_at = utcnow() - timedelta(minutes=45)
    session.commit()

    assert abandon_if_idle(row) is True
    assert row.status == "abandoned"


def test_abandon_if_idle_leaves_fresh_session_alone(session):
    from src.backend.handle_inventory_walk import abandon_if_idle
    from src.backend.initialize_database_schema import TelegramInventorySession
    row = TelegramInventorySession(chat_id="abc", status="active")
    session.add(row)
    session.commit()
    assert abandon_if_idle(row) is False
    assert row.status == "active"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "get_or_create or reset_for_start_over or abandon_if_idle"`
Expected: FAIL — names not importable.

- [ ] **Step 3: Implement helpers**

Append to `src/backend/handle_inventory_walk.py`:

```python
def get_or_create_session(session, chat_id: str):
    from src.backend.initialize_database_schema import TelegramInventorySession
    row = (
        session.query(TelegramInventorySession)
        .filter_by(chat_id=chat_id)
        .one_or_none()
    )
    if row is None:
        row = TelegramInventorySession(chat_id=chat_id, status="active")
        session.add(row)
        session.flush()
    return row


def reset_for_start_over(row) -> None:
    row.status = "active"
    row.current_category = None
    row.item_queue = []
    row.cursor = 0
    row.page = 1
    row.pending_prompt = "category"
    row.last_item_id = None
    row.stats = {}


def abandon_if_idle(row) -> bool:
    """Return True if session was just marked abandoned due to idle timeout."""
    if row.status != "active":
        return False
    if row.last_action_at is None:
        return False
    cutoff = datetime.utcnow() - timedelta(minutes=IDLE_TIMEOUT_MIN)
    if row.last_action_at < cutoff:
        row.status = "abandoned"
        return True
    return False
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "get_or_create or reset_for_start_over or abandon_if_idle"`
Expected: PASS — five tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): session helpers — create, reset, idle-abandon"
```

---

## Task 6: Inventory mutation helpers — level + no-longer-have

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
LEVEL_PCT_MAP = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25, 4: 0.0}  # used only by tests


@pytest.mark.parametrize("level_idx,expected_pct,expected_low", [
    (0, 1.0, True),
    (1, 0.75, False),
    (2, 0.50, False),
    (3, 0.25, False),
    (4, 0.0,  False),
])
def test_apply_level_writes_pct_and_low_flag(session, level_idx, expected_pct, expected_low):
    from src.backend.handle_inventory_walk import apply_level
    from src.backend.initialize_database_schema import Product, Inventory, InventoryAdjustment
    p = Product(name="Olive oil", category="pantry")
    session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=1.0, manual_low=False, is_active_window=True)
    session.add(inv); session.commit()

    apply_level(session, inv.id, level_idx, user_id=None)
    session.commit()

    session.refresh(inv)
    assert inv.consumed_pct_override == expected_pct
    assert inv.manual_low is expected_low

    adj = session.query(InventoryAdjustment).filter_by(product_id=p.id).all()
    assert len(adj) == 1
    assert adj[0].reason == "telegram_walk"


def test_mark_no_longer_have_deactivates(session):
    from src.backend.handle_inventory_walk import mark_no_longer_have
    from src.backend.initialize_database_schema import Product, Inventory, InventoryAdjustment
    p = Product(name="Old soap", category="bathroom")
    session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=0.2, is_active_window=True)
    session.add(inv); session.commit()

    mark_no_longer_have(session, inv.id, user_id=None)
    session.commit()
    session.refresh(inv)
    assert inv.is_active_window is False
    adj = session.query(InventoryAdjustment).filter_by(product_id=p.id).one()
    assert adj.reason == "telegram_walk_remove"
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "apply_level or mark_no_longer_have"`
Expected: FAIL — imports missing.

- [ ] **Step 3: Implement mutations**

Append to `src/backend/handle_inventory_walk.py`:

```python
_LEVEL_TO_PCT = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25, 4: 0.0}


def apply_level(session, inventory_id: int, level_idx: int, user_id: int | None):
    """Write consumed_pct_override + manual_low for a level button.

    level_idx 0..4 maps to Empty / ¼ / ½ / ¾ / Full.
    """
    from src.backend.initialize_database_schema import Inventory, InventoryAdjustment

    if level_idx not in _LEVEL_TO_PCT:
        raise ValueError(f"invalid level_idx {level_idx}")

    inv = session.query(Inventory).filter_by(id=inventory_id).one_or_none()
    if inv is None:
        logger.warning("apply_level: inventory %s vanished", inventory_id)
        return None

    pct = _LEVEL_TO_PCT[level_idx]
    inv.consumed_pct_override = pct
    inv.manual_low = (level_idx == 0)
    inv.last_updated = datetime.utcnow()

    session.add(InventoryAdjustment(
        product_id=inv.product_id,
        quantity_delta=0.0,
        reason="telegram_walk",
        user_id=user_id,
    ))
    return inv


def mark_no_longer_have(session, inventory_id: int, user_id: int | None):
    from src.backend.initialize_database_schema import Inventory, InventoryAdjustment

    inv = session.query(Inventory).filter_by(id=inventory_id).one_or_none()
    if inv is None:
        return None
    inv.is_active_window = False
    inv.last_updated = datetime.utcnow()
    session.add(InventoryAdjustment(
        product_id=inv.product_id,
        quantity_delta=0.0,
        reason="telegram_walk_remove",
        user_id=user_id,
    ))
    return inv
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "apply_level or mark_no_longer_have"`
Expected: PASS — six tests (five parametrized + one).

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): inventory mutation helpers — level + no-longer-have"
```

---

## Task 7: Shopping-list insert helper

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing test**

```python
def test_add_empty_to_shopping_list_inserts_item(session):
    from src.backend.handle_inventory_walk import add_empty_to_shopping_list
    from src.backend.initialize_database_schema import (
        Product, Inventory, ShoppingListItem,
    )
    p = Product(name="Olive oil", category="pantry")
    session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=0, manual_low=True)
    session.add(inv); session.commit()

    item = add_empty_to_shopping_list(session, inv.id)
    session.commit()

    assert item is not None
    fetched = session.query(ShoppingListItem).filter_by(product_id=p.id).all()
    assert len(fetched) == 1
    assert fetched[0].name == "Olive oil"
    assert fetched[0].category == "pantry"
    assert fetched[0].source == "telegram_walk"


def test_add_empty_to_shopping_list_dedups_existing_item(session):
    from src.backend.handle_inventory_walk import add_empty_to_shopping_list
    from src.backend.initialize_database_schema import (
        Product, Inventory, ShoppingListItem,
    )
    p = Product(name="Olive oil", category="pantry")
    session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=0, manual_low=True)
    session.add(inv); session.commit()

    add_empty_to_shopping_list(session, inv.id); session.commit()
    add_empty_to_shopping_list(session, inv.id); session.commit()

    items = session.query(ShoppingListItem).filter_by(product_id=p.id, status="pending").all()
    assert len(items) == 1, "should not double-insert the same pending item"
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "add_empty_to_shopping_list"`
Expected: FAIL — import error.

- [ ] **Step 3: Implement insert helper**

Append to `src/backend/handle_inventory_walk.py`:

```python
def add_empty_to_shopping_list(session, inventory_id: int):
    """Insert the product backing this inventory row into the active shopping session.

    Reuses manage_shopping_list._ensure_current_session. De-duplicates: if a
    pending ShoppingListItem already exists for this product in the active
    session, returns it without inserting again.
    """
    from src.backend.initialize_database_schema import (
        Inventory, ShoppingListItem,
    )
    from src.backend.manage_shopping_list import _ensure_current_session

    inv = session.query(Inventory).filter_by(id=inventory_id).one_or_none()
    if inv is None or inv.product is None:
        return None

    shop_session = _ensure_current_session(session)

    existing = (
        session.query(ShoppingListItem)
        .filter_by(
            session_id=shop_session.id,
            product_id=inv.product_id,
        )
        .filter(ShoppingListItem.status == "pending")
        .one_or_none()
    )
    if existing is not None:
        return existing

    item = ShoppingListItem(
        session_id=shop_session.id,
        product_id=inv.product_id,
        name=inv.product.name,
        category=inv.product.category,
        quantity=1,
        source="telegram_walk",
        status="pending",
    )
    session.add(item)
    session.flush()
    return item
```

If `ShoppingListItem.status` field name differs (check `initialize_database_schema.py`), adapt accordingly. Same for `source`. Verify against `_serialize_item` in `manage_shopping_list.py` which lists all fields.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "add_empty_to_shopping_list"`
Expected: PASS — two tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): shopping-list insert helper for empty items"
```

---

## Task 8: Rendering helpers — text + keyboards

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_render_category_screen_shows_counts():
    from src.backend.handle_inventory_walk import render_category_screen
    text, kb = render_category_screen([("pantry", 8), ("fridge", 4)])
    assert "Update inventory" in text
    assert "2 categories" in text or "pantry" in text.lower()
    # buttons
    btns = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert any("Pantry" in b and "8" in b for b in btns)
    assert any("Fridge" in b and "4" in b for b in btns)
    assert any("Cancel" in b for b in btns)


def test_render_level_prompt_includes_progress_and_buttons():
    from src.backend.handle_inventory_walk import render_level_prompt
    text, kb = render_level_prompt(
        product_name="Olive oil",
        category="pantry",
        idx=2,
        total=8,
        days_old=23,
    )
    assert "2/8" in text
    assert "Olive oil" in text
    assert "23 days ago" in text
    labels = [b["text"] for row in kb["inline_keyboard"] for b in row]
    for expected in ("Empty", "¼", "½", "¾", "Full", "Skip", "No longer have", "Done"):
        assert any(expected in lbl for lbl in labels), f"missing button: {expected}"


def test_render_cart_prompt_has_three_buttons():
    from src.backend.handle_inventory_walk import render_cart_prompt
    text, kb = render_cart_prompt("Olive oil")
    assert "Olive oil" in text
    assert "Add to shopping list" in text
    labels = [b["text"] for row in kb["inline_keyboard"] for b in row]
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "inv:cart:y" in callbacks
    assert "inv:cart:n" in callbacks
    assert "inv:cart:a" in callbacks


def test_render_summary_shows_stats():
    from src.backend.handle_inventory_walk import render_summary
    text, kb = render_summary(
        category="pantry",
        stats={"updated": 6, "skipped": 1, "removed": 1, "cart_added": 2},
    )
    assert "Walk complete" in text
    assert "Updated" in text and "6" in text
    assert "Skipped" in text and "1" in text
    assert "Removed" in text
    assert "shopping list" in text.lower()


def test_render_resume_shows_progress():
    from src.backend.handle_inventory_walk import render_resume
    text, kb = render_resume(category="pantry", cursor=3, total=8)
    assert "progress" in text.lower() or "in progress" in text.lower()
    assert "3/8" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "inv:resume" in callbacks
    assert "inv:restart" in callbacks
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "render_"`
Expected: FAIL — import errors.

- [ ] **Step 3: Implement rendering helpers**

Append to `src/backend/handle_inventory_walk.py`:

```python
_CATEGORY_EMOJI = {
    "pantry": "🥫", "fridge": "🥶", "freezer": "🧊", "bathroom": "🧴",
    "household": "🧹", "personal_care": "🧴", "produce": "🥦",
    "dairy": "🥛", "meat": "🥩", "snacks": "🍿", "beverages": "🥤",
    "frozen": "🧊", "bakery": "🍞", "canned": "🥫", "condiments": "🧂",
}


def _cat_emoji(category: str | None) -> str:
    return _CATEGORY_EMOJI.get((category or "").lower(), "📦")


def _days_ago_phrase(days: int) -> str:
    if days >= 60:
        return "2+ months ago"
    return f"{days} days ago"


def render_category_screen(counts: list[tuple[str, int]]) -> tuple[str, dict]:
    n = len(counts)
    lines = [
        "📦 Update inventory",
        "",
        f"{n} categories have stale items (>{INVENTORY_STALE_DAYS} days):",
    ]
    rows: list[list[dict]] = []
    pair: list[dict] = []
    for category, count in counts:
        label = f"{_cat_emoji(category)} {category.title()} · {count}"
        pair.append({"text": label, "callback_data": f"inv:cat:{category}"})
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([{"text": "Cancel", "callback_data": "inv:cancel"}])
    return "\n".join(lines), {"inline_keyboard": rows}


def render_level_prompt(
    *, product_name: str, category: str, idx: int, total: int, days_old: int
) -> tuple[str, dict]:
    text = (
        f"{_cat_emoji(category)} {category.title()} · {idx}/{total}\n\n"
        f"{product_name}\n"
        f"Last updated {_days_ago_phrase(days_old)}\n\n"
        "How much left?"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "Empty", "callback_data": "inv:lvl:0"},
            {"text": "¼",     "callback_data": "inv:lvl:1"},
            {"text": "½",     "callback_data": "inv:lvl:2"},
            {"text": "¾",     "callback_data": "inv:lvl:3"},
            {"text": "Full",  "callback_data": "inv:lvl:4"},
        ],
        [
            {"text": "Skip",            "callback_data": "inv:skip"},
            {"text": "No longer have",  "callback_data": "inv:nohave"},
        ],
        [{"text": "✓ Done for now", "callback_data": "inv:done"}],
    ]}
    return text, kb


def render_cart_prompt(product_name: str) -> tuple[str, dict]:
    text = (
        f"{product_name} → empty.\n\n"
        "Add to shopping list?"
    )
    kb = {"inline_keyboard": [[
        {"text": "✓ Yes",            "callback_data": "inv:cart:y"},
        {"text": "✗ No",             "callback_data": "inv:cart:n"},
        {"text": "Already have it",  "callback_data": "inv:cart:a"},
    ]]}
    return text, kb


def render_continue(category: str, done: int, remaining: int) -> tuple[str, dict]:
    text = (
        f"{_cat_emoji(category)} {category.title()} · {done} done\n\n"
        f"{remaining} more stale items left. Continue?"
    )
    kb = {"inline_keyboard": [[
        {"text": "▶ Continue",    "callback_data": "inv:cont"},
        {"text": "✓ Done for now", "callback_data": "inv:done"},
    ]]}
    return text, kb


def render_summary(category: str, stats: dict[str, int]) -> tuple[str, dict]:
    updated = stats.get("updated", 0)
    skipped = stats.get("skipped", 0)
    removed = stats.get("removed", 0)
    cart_added = stats.get("cart_added", 0)
    text = (
        f"✅ Walk complete · {category.title()}\n\n"
        f"Updated: {updated}\n"
        f"Skipped: {skipped}\n"
        f"Removed: {removed}\n"
        f"Added to shopping list: {cart_added}"
    )
    kb = {"inline_keyboard": [[
        {"text": "📦 Another category", "callback_data": "inv:restart"},
    ]]}
    public_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if public_url:
        kb["inline_keyboard"][0].append({
            "text": "📋 View shopping list",
            "url": f"{public_url}/shopping/list",
        })
    return text, kb


def render_resume(category: str, cursor: int, total: int) -> tuple[str, dict]:
    text = (
        "You have a walk in progress.\n\n"
        f"{category.title()} · {cursor}/{total} done"
    )
    kb = {"inline_keyboard": [[
        {"text": "▶ Resume",     "callback_data": "inv:resume"},
        {"text": "↻ Start over", "callback_data": "inv:restart"},
    ]]}
    return text, kb


def render_nudge(stale_count: int) -> tuple[str, dict]:
    text = (
        f"📦 {stale_count} items haven't been counted in 2+ weeks. Update now?"
    )
    kb = {"inline_keyboard": [
        [{"text": "▶ Yes, walk me through", "callback_data": "nudge:yes"}],
        [{"text": "⏰ Later",                "callback_data": "nudge:later"}],
        [{"text": "🔕 Mute 7d",              "callback_data": "nudge:mute"}],
    ]}
    return text, kb
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "render_"`
Expected: PASS — five tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): rendering helpers — category/level/cart/continue/summary/resume/nudge"
```

---

## Task 9: `start_walk` entry point

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_start_walk_with_no_stale_items_sends_caught_up(session, monkeypatch):
    from src.backend.handle_inventory_walk import start_walk
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)),
    )
    start_walk(session, "abc")
    session.commit()
    assert len(sent) == 1
    assert "caught up" in sent[0][1].lower() or "nothing stale" in sent[0][1].lower()


def test_start_walk_with_stale_items_renders_category_screen(session, monkeypatch):
    from src.backend.handle_inventory_walk import start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil",  "pantry",  20),
        ("Milk",        "fridge",  20),
    ])
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)),
    )
    start_walk(session, "abc")
    session.commit()
    assert sent and "Update inventory" in sent[0][1]

    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "category"
    assert row.status == "active"


def test_start_walk_offers_resume_when_active_session_mid_walk(session, monkeypatch):
    from src.backend.handle_inventory_walk import start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    row = TelegramInventorySession(
        chat_id="abc",
        status="active",
        current_category="pantry",
        item_queue=[1, 2, 3, 4, 5, 6, 7, 8],
        cursor=3,
        pending_prompt="level",
    )
    session.add(row); session.commit()
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)),
    )
    start_walk(session, "abc")
    session.commit()
    assert sent and "progress" in sent[0][1].lower()
    callbacks = [b["callback_data"] for r in sent[0][2]["inline_keyboard"] for b in r]
    assert "inv:resume" in callbacks
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "start_walk"`
Expected: FAIL — import error or no behavior.

- [ ] **Step 3: Implement `start_walk` + thin send wrapper**

Append to `src/backend/handle_inventory_walk.py`:

```python
# Send helper — wraps existing handle_telegram_messages.send_telegram_message
# so tests can monkeypatch one symbol in this module.
def send_telegram_message(chat_id: str, text: str, reply_markup: dict | None = None):
    from src.backend.handle_telegram_messages import send_telegram_message as _send
    return _send(chat_id, text, reply_markup=reply_markup)


def _edit_telegram_message(chat_id: str, message_id: int | None, text: str,
                           reply_markup: dict | None = None):
    from src.backend.handle_telegram_messages import _edit_telegram_message as _edit
    return _edit(chat_id, message_id, text)  # NOTE: extend _edit signature in Task 16


def start_walk(session, chat_id: str) -> None:
    row = get_or_create_session(session, chat_id)
    abandoned = abandon_if_idle(row)
    if abandoned and row.status == "abandoned":
        # treat as fresh start
        reset_for_start_over(row)

    # Resume offer if active mid-walk.
    if (row.status == "active"
            and row.current_category
            and row.item_queue
            and row.cursor < len(row.item_queue)):
        total = len(row.item_queue)
        text, kb = render_resume(row.current_category, row.cursor, total)
        row.pending_prompt = "resume"
        send_telegram_message(chat_id, text, reply_markup=kb)
        return

    counts = categories_with_stale_counts(session)
    if not counts:
        send_telegram_message(chat_id, "🎉 All caught up — nothing stale.")
        # leave row dormant; status stays whatever it was
        return

    reset_for_start_over(row)
    text, kb = render_category_screen(counts)
    send_telegram_message(chat_id, text, reply_markup=kb)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "start_walk"`
Expected: PASS — three tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): start_walk entry point with resume offer"
```

---

## Task 10: `handle_category` — pick category, render first item

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing test**

```python
def test_handle_category_loads_queue_and_renders_level(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil",   "pantry", 20),
        ("Black pepper", "pantry", 30),
        ("Milk",         "fridge", 20),
    ])
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda chat_id, message_id, text, reply_markup=None:
            edits.append((chat_id, message_id, text, reply_markup)),
    )
    # Set state to "category" first.
    start_walk(session, "abc"); session.commit()

    handle_category(session, "abc", category="pantry", message_id=100)
    session.commit()

    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.current_category == "pantry"
    assert row.pending_prompt == "level"
    assert row.cursor == 0
    assert len(row.item_queue) == 2  # two pantry items
    assert edits, "should edit category message to level prompt"
    assert "1/2" in edits[-1][2]
    assert "Black pepper" in edits[-1][2]  # oldest first (30 days > 20 days)
```

- [ ] **Step 2: Run test — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_category"`
Expected: FAIL.

- [ ] **Step 3: Implement `handle_category` + a small `_render_current_item` helper**

Append to `src/backend/handle_inventory_walk.py`:

```python
def _render_current_item(session, row, message_id: int | None) -> None:
    """Re-render the LEVEL prompt for the item at row.cursor."""
    from src.backend.initialize_database_schema import Inventory

    if row.cursor >= len(row.item_queue):
        return  # caller handles end-of-page
    inv_id = row.item_queue[row.cursor]
    inv = session.query(Inventory).filter_by(id=inv_id).one_or_none()
    if inv is None:
        # vanished mid-walk — silently advance
        row.cursor += 1
        logger.warning("inventory %s vanished mid-walk for chat %s", inv_id, row.chat_id)
        if row.cursor < len(row.item_queue):
            return _render_current_item(session, row, message_id)
        return

    days_old = (datetime.utcnow() - inv.last_updated).days if inv.last_updated else INVENTORY_STALE_DAYS
    text, kb = render_level_prompt(
        product_name=inv.product.name,
        category=row.current_category or "other",
        idx=row.cursor + 1,
        total=len(row.item_queue),
        days_old=days_old,
    )
    row.pending_prompt = "level"
    row.last_item_id = inv_id
    _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)


def handle_category(session, chat_id: str, category: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    items = stale_items_in_category(session, category, page=1)
    row.current_category = category
    row.item_queue = [i.id for i in items]
    row.cursor = 0
    row.page = 1
    row.stats = {"updated": 0, "skipped": 0, "removed": 0, "cart_added": 0}
    if not row.item_queue:
        send_telegram_message(chat_id, f"No stale items in {category}.")
        row.pending_prompt = "category"
        return
    _render_current_item(session, row, message_id)
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_category"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): handle_category — load queue + render first item"
```

---

## Task 11: `handle_level` — Empty → cart, else advance

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_handle_level_full_advances_to_next_item(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_level, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession, Inventory
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",     "pantry", 30),
    ])
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_level(session, "abc", level_idx=4, message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["updated"] == 1
    # next item rendered
    assert any("2/2" in e[2] for e in edits)


def test_handle_level_empty_transitions_to_cart_prompt(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_level, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[("Olive oil", "pantry", 20)])
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_level(session, "abc", level_idx=0, message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "cart"
    assert row.stats["updated"] == 1
    callbacks = [b["callback_data"] for r in edits[-1][3]["inline_keyboard"] for b in r]
    assert "inv:cart:y" in callbacks
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_level"`
Expected: FAIL — `handle_level` not defined.

- [ ] **Step 3: Implement `handle_level`**

Append to `src/backend/handle_inventory_walk.py`:

```python
def _advance_or_end(session, row, message_id: int | None) -> None:
    """After a non-Empty action: bump cursor and either render next, prompt continue, or end."""
    row.cursor += 1
    if row.cursor < len(row.item_queue):
        _render_current_item(session, row, message_id)
        return

    # End of page. Are there more pages?
    cutoff = _stale_cutoff()
    from src.backend.initialize_database_schema import Inventory, Product
    remaining = (
        session.query(func.count(Inventory.id))
        .join(Product, Product.id == Inventory.product_id)
        .filter(Inventory.is_active_window.is_(True))
        .filter(Inventory.last_updated < cutoff)
        .filter(func.lower(func.coalesce(Product.category, "other")) == (row.current_category or "").lower())
        .scalar()
    ) or 0
    done_on_page = row.cursor  # cursor == len(item_queue) here
    remaining_after = max(0, remaining - (row.page - 1) * PAGE_SIZE - done_on_page)
    if remaining_after > 0:
        text, kb = render_continue(row.current_category or "other", done=done_on_page, remaining=remaining_after)
        row.pending_prompt = "continue"
        _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)
        return

    _end_walk(session, row, message_id)


def _end_walk(session, row, message_id: int | None) -> None:
    text, kb = render_summary(row.current_category or "other", row.stats or {})
    _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)
    row.status = "done"
    row.pending_prompt = None


def handle_level(session, chat_id: str, level_idx: int, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    if row.cursor >= len(row.item_queue):
        # Defensive: nothing to act on.
        return
    inv_id = row.item_queue[row.cursor]
    apply_level(session, inv_id, level_idx, user_id=row.user_id)
    row.stats = {**(row.stats or {}), "updated": (row.stats or {}).get("updated", 0) + 1}

    if level_idx == 0:
        # Show cart prompt before advancing.
        from src.backend.initialize_database_schema import Inventory
        inv = session.query(Inventory).filter_by(id=inv_id).one_or_none()
        product_name = inv.product.name if (inv and inv.product) else "Item"
        text, kb = render_cart_prompt(product_name)
        row.pending_prompt = "cart"
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
        return

    _advance_or_end(session, row, message_id)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_level"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): handle_level + advance/end + continue prompt"
```

---

## Task 12: `handle_cart` — Yes/No/Already

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_handle_cart_yes_inserts_shopping_list_item(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_cart, handle_level, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession, ShoppingListItem
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",    "pantry", 30),
    ])
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", 100); session.commit()
    handle_level(session, "abc", 0, 100); session.commit()  # Empty, advances to cart prompt

    handle_cart(session, "abc", "y", 100); session.commit()
    items = session.query(ShoppingListItem).all()
    assert len(items) == 1
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.stats["cart_added"] == 1
    assert row.pending_prompt == "level"
    assert row.cursor == 1


def test_handle_cart_no_does_not_insert(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_cart, handle_level, handle_category, start_walk
    from src.backend.initialize_database_schema import ShoppingListItem
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",    "pantry", 30),
    ])
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", 100); session.commit()
    handle_level(session, "abc", 0, 100); session.commit()

    handle_cart(session, "abc", "n", 100); session.commit()
    assert session.query(ShoppingListItem).count() == 0


def test_handle_cart_already_does_not_insert(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_cart, handle_level, handle_category, start_walk
    from src.backend.initialize_database_schema import ShoppingListItem
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",    "pantry", 30),
    ])
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", 100); session.commit()
    handle_level(session, "abc", 0, 100); session.commit()

    handle_cart(session, "abc", "a", 100); session.commit()
    assert session.query(ShoppingListItem).count() == 0
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_cart"`
Expected: FAIL.

- [ ] **Step 3: Implement `handle_cart`**

Append to `src/backend/handle_inventory_walk.py`:

```python
def handle_cart(session, chat_id: str, choice: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    if choice == "y" and row.last_item_id is not None:
        added = add_empty_to_shopping_list(session, row.last_item_id)
        if added is not None:
            stats = dict(row.stats or {})
            stats["cart_added"] = stats.get("cart_added", 0) + 1
            row.stats = stats
    # No/Already → no insert.
    _advance_or_end(session, row, message_id)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_cart"`
Expected: PASS — three tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): handle_cart — yes/no/already paths"
```

---

## Task 13: `handle_skip`, `handle_nohave`, `handle_done`

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_handle_skip_advances_without_write(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_skip, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession, Inventory
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",    "pantry", 30),
    ])
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", 100); session.commit()
    inv_id = session.query(TelegramInventorySession).filter_by(chat_id="abc").one().item_queue[0]

    handle_skip(session, "abc", 100); session.commit()

    inv = session.query(Inventory).filter_by(id=inv_id).one()
    assert inv.consumed_pct_override is None  # no write
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["skipped"] == 1


def test_handle_nohave_deactivates_and_advances(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_nohave, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession, Inventory
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",    "pantry", 30),
    ])
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", 100); session.commit()
    inv_id = session.query(TelegramInventorySession).filter_by(chat_id="abc").one().item_queue[0]

    handle_nohave(session, "abc", 100); session.commit()
    inv = session.query(Inventory).filter_by(id=inv_id).one()
    assert inv.is_active_window is False
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["removed"] == 1


def test_handle_done_ends_walk_with_summary(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_done, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",    "pantry", 30),
    ])
    edits = []
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda c, m, t, reply_markup=None: edits.append(t))
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", 100); session.commit()

    handle_done(session, "abc", 100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.status == "done"
    assert any("Walk complete" in t for t in edits)
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_skip or handle_nohave or handle_done"`
Expected: FAIL.

- [ ] **Step 3: Implement the three handlers**

Append to `src/backend/handle_inventory_walk.py`:

```python
def handle_skip(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    stats = dict(row.stats or {})
    stats["skipped"] = stats.get("skipped", 0) + 1
    row.stats = stats
    _advance_or_end(session, row, message_id)


def handle_nohave(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    if row.cursor < len(row.item_queue):
        inv_id = row.item_queue[row.cursor]
        mark_no_longer_have(session, inv_id, user_id=row.user_id)
    stats = dict(row.stats or {})
    stats["removed"] = stats.get("removed", 0) + 1
    row.stats = stats
    _advance_or_end(session, row, message_id)


def handle_done(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    _end_walk(session, row, message_id)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_skip or handle_nohave or handle_done"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): handle_skip/nohave/done"
```

---

## Task 14: `handle_continue`, `handle_cancel`, `handle_resume`, `handle_restart`

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_handle_continue_loads_next_page(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_continue, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[
        (f"Item {i}", "pantry", 14 + i) for i in range(12)
    ])
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", 100); session.commit()
    # simulate finishing page 1
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    row.cursor = 10
    row.pending_prompt = "continue"
    session.commit()

    handle_continue(session, "abc", 100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.page == 2
    assert row.cursor == 0
    assert len(row.item_queue) == 2
    assert row.pending_prompt == "level"


def test_handle_cancel_marks_abandoned(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_cancel, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    edits = []
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda c, m, t, reply_markup=None: edits.append(t))
    start_walk(session, "abc"); session.commit()

    handle_cancel(session, "abc", 100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.status == "abandoned"
    assert any("ancel" in t for t in edits)


def test_handle_resume_re_renders_current_prompt(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_resume
    from src.backend.initialize_database_schema import TelegramInventorySession, Product, Inventory, utcnow
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
    inv.last_updated = utcnow() - timedelta(days=30)
    session.add(inv); session.commit()

    row = TelegramInventorySession(
        chat_id="abc", status="active", current_category="pantry",
        item_queue=[inv.id], cursor=0, pending_prompt="resume",
    )
    session.add(row); session.commit()
    edits = []
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda c, m, t, reply_markup=None: edits.append(t))

    handle_resume(session, "abc", 100); session.commit()
    assert any("Olive oil" in t for t in edits)
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "level"


def test_handle_restart_resets_and_shows_categories(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_restart
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[("Olive oil", "pantry", 30)])
    edits = []
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda c, m, t, reply_markup=None: edits.append(t))
    row = TelegramInventorySession(
        chat_id="abc", status="active", current_category="pantry",
        item_queue=[1, 2], cursor=1, pending_prompt="level",
    )
    session.add(row); session.commit()

    handle_restart(session, "abc", 100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.cursor == 0
    assert row.current_category is None
    assert row.pending_prompt == "category"
    assert any("Update inventory" in t for t in edits)
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_continue or handle_cancel or handle_resume or handle_restart"`
Expected: FAIL.

- [ ] **Step 3: Implement the four handlers**

Append to `src/backend/handle_inventory_walk.py`:

```python
def handle_continue(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    row.page += 1
    row.cursor = 0
    items = stale_items_in_category(session, row.current_category or "", page=row.page)
    row.item_queue = [i.id for i in items]
    if not row.item_queue:
        _end_walk(session, row, message_id)
        return
    _render_current_item(session, row, message_id)


def handle_cancel(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    row.status = "abandoned"
    row.pending_prompt = None
    _edit_telegram_message(chat_id, message_id, "Cancelled.")


def handle_resume(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    if not row.item_queue or row.cursor >= len(row.item_queue):
        # nothing to resume; fall back to fresh start
        start_walk(session, chat_id)
        return
    _render_current_item(session, row, message_id)


def handle_restart(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    reset_for_start_over(row)
    counts = categories_with_stale_counts(session)
    if not counts:
        _edit_telegram_message(chat_id, message_id, "🎉 All caught up — nothing stale.")
        return
    text, kb = render_category_screen(counts)
    _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "handle_continue or handle_cancel or handle_resume or handle_restart"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): handle continue/cancel/resume/restart"
```

---

## Task 15: Top-level dispatch — verb match, idle check, error reply

**Files:**
- Modify: `src/backend/handle_inventory_walk.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_dispatch_rejects_stale_verb_and_rerenders(session, monkeypatch):
    from src.backend.handle_inventory_walk import dispatch_inv_callback, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[("Olive oil", "pantry", 30)])
    edits = []
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda c, m, t, reply_markup=None: edits.append(t))
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", 100); session.commit()
    # pending_prompt is 'level' now; sending a cart verb should be rejected.

    dispatch_inv_callback(session, "abc", "inv:cart:y", message_id=100); session.commit()
    # Stale-callback message + re-render of level prompt should both appear.
    assert any("stale" in t.lower() for t in edits) or any("Olive oil" in t for t in edits)


def test_dispatch_idle_session_auto_abandons(session, monkeypatch):
    from src.backend.handle_inventory_walk import dispatch_inv_callback
    from src.backend.initialize_database_schema import TelegramInventorySession, utcnow
    row = TelegramInventorySession(
        chat_id="abc", status="active",
        current_category="pantry", item_queue=[1], cursor=0,
        pending_prompt="level",
    )
    session.add(row); session.commit()
    row.last_action_at = utcnow() - timedelta(minutes=60)
    session.commit()
    sent = []
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda c, t, reply_markup=None: sent.append(t))
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)

    dispatch_inv_callback(session, "abc", "inv:lvl:4", message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.status == "abandoned"
    assert any("timed out" in t.lower() for t in sent)
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "dispatch_rejects or dispatch_idle"`
Expected: FAIL.

- [ ] **Step 3: Implement top-level dispatch**

Append to `src/backend/handle_inventory_walk.py`:

```python
_VERB_TO_EXPECTED_PROMPT = {
    "cat":     "category",
    "lvl":     "level",
    "skip":    "level",
    "nohave":  "level",
    "done":    {"level", "continue"},
    "cont":    "continue",
    "cart":    "cart",
    "resume":  "resume",
    "restart": {"resume", "category", "continue", "level"},
    "cancel":  {"category", "resume", "continue"},
}


def _matches_expected(prompt: str | None, expected) -> bool:
    if isinstance(expected, set):
        return prompt in expected
    return prompt == expected


def dispatch_inv_callback(session, chat_id: str, data: str, message_id: int | None) -> None:
    """Route an `inv:*` callback. `data` is the raw callback_data."""
    row = get_or_create_session(session, chat_id)

    if abandon_if_idle(row):
        send_telegram_message(chat_id, "Session timed out. /inventory to restart.")
        return

    parts = data.split(":", 2)
    if len(parts) < 2 or parts[0] != "inv":
        return
    verb = parts[1]
    arg = parts[2] if len(parts) == 3 else ""

    expected = _VERB_TO_EXPECTED_PROMPT.get(verb)
    if expected is not None and not _matches_expected(row.pending_prompt, expected):
        # Stale callback — reject and re-render current step.
        _edit_telegram_message(chat_id, message_id, "That button is stale. Showing current step:")
        _rerender_current_prompt(session, row, message_id=None)
        return

    if verb == "cat":
        handle_category(session, chat_id, arg, message_id)
    elif verb == "lvl":
        try:
            level = int(arg)
        except ValueError:
            return
        handle_level(session, chat_id, level, message_id)
    elif verb == "skip":
        handle_skip(session, chat_id, message_id)
    elif verb == "nohave":
        handle_nohave(session, chat_id, message_id)
    elif verb == "done":
        handle_done(session, chat_id, message_id)
    elif verb == "cont":
        handle_continue(session, chat_id, message_id)
    elif verb == "cart":
        handle_cart(session, chat_id, arg, message_id)
    elif verb == "resume":
        handle_resume(session, chat_id, message_id)
    elif verb == "restart":
        handle_restart(session, chat_id, message_id)
    elif verb == "cancel":
        handle_cancel(session, chat_id, message_id)


def _rerender_current_prompt(session, row, message_id: int | None) -> None:
    """Send (not edit) a fresh prompt matching row.pending_prompt."""
    prompt = row.pending_prompt
    if prompt == "category":
        counts = categories_with_stale_counts(session)
        text, kb = render_category_screen(counts)
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif prompt == "level":
        if row.cursor < len(row.item_queue):
            from src.backend.initialize_database_schema import Inventory
            inv = session.query(Inventory).filter_by(id=row.item_queue[row.cursor]).one_or_none()
            if inv is not None:
                days_old = (datetime.utcnow() - inv.last_updated).days if inv.last_updated else 0
                text, kb = render_level_prompt(
                    product_name=inv.product.name,
                    category=row.current_category or "other",
                    idx=row.cursor + 1,
                    total=len(row.item_queue),
                    days_old=days_old,
                )
                send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif prompt == "cart":
        if row.last_item_id is not None:
            from src.backend.initialize_database_schema import Inventory
            inv = session.query(Inventory).filter_by(id=row.last_item_id).one_or_none()
            if inv is not None and inv.product is not None:
                text, kb = render_cart_prompt(inv.product.name)
                send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif prompt == "continue":
        # Recompute remaining and re-render.
        cutoff = _stale_cutoff()
        from src.backend.initialize_database_schema import Inventory, Product
        total_left = session.query(func.count(Inventory.id)).join(
            Product, Product.id == Inventory.product_id
        ).filter(
            Inventory.is_active_window.is_(True),
            Inventory.last_updated < cutoff,
            func.lower(func.coalesce(Product.category, "other")) == (row.current_category or "").lower(),
        ).scalar() or 0
        remaining = max(0, total_left - (row.page - 1) * PAGE_SIZE - row.cursor)
        text, kb = render_continue(row.current_category or "other", done=row.cursor, remaining=remaining)
        send_telegram_message(row.chat_id, text, reply_markup=kb)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "dispatch_rejects or dispatch_idle"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_inventory_walk.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): dispatcher with idle timeout + stale-verb guard"
```

---

## Task 16: Wire `/inventory` command + callback routing into webhook

**Files:**
- Modify: `src/backend/handle_telegram_messages.py`
- Test: `tests/test_telegram_inventory_walk.py`

- [ ] **Step 1: Inspect current `_edit_telegram_message` signature**

Open `src/backend/handle_telegram_messages.py` around line 296. Today it accepts `(chat_id, message_id, text)`. We need it to optionally accept `reply_markup`. Add `reply_markup: dict | None = None` to the signature and pass it through to the Telegram HTTP body the same way `send_telegram_message` does (line 124–146).

- [ ] **Step 2: Write the failing test**

```python
def test_webhook_inventory_command_starts_walk(session, monkeypatch):
    """Posting /inventory text to the webhook handler dispatches start_walk."""
    from src.backend.handle_telegram_messages import _handle_command
    called = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.start_walk",
        lambda s, chat_id: called.append(chat_id),
    )
    # _handle_command currently returns a string; we extend it to side-effect for /inventory.
    monkeypatch.setattr("src.backend.handle_telegram_messages.g", type("g", (), {"db_session": session})())
    monkeypatch.setenv("TELEGRAM_INVENTORY_WALK_ENABLED", "1")
    out = _handle_command("/inventory", chat_id="abc")
    assert called == ["abc"]
    # The command handler may return empty string when it sends side-channel messages.


def test_webhook_routes_inv_callback_to_dispatch(session, monkeypatch):
    from src.backend.handle_telegram_messages import _handle_callback_query
    called = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.dispatch_inv_callback",
        lambda s, chat_id, data, message_id: called.append((chat_id, data, message_id)),
    )
    monkeypatch.setattr("src.backend.handle_telegram_messages.g",
                        type("g", (), {"db_session": session})())
    monkeypatch.setenv("TELEGRAM_INVENTORY_WALK_ENABLED", "1")
    cb = {
        "id": "cb1",
        "data": "inv:cat:pantry",
        "from": {"id": 42},
        "message": {"chat": {"id": "abc"}, "message_id": 100},
    }
    _handle_callback_query(cb)
    assert called == [("abc", "inv:cat:pantry", 100)]
```

- [ ] **Step 3: Run test — fail**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "webhook_inventory_command or webhook_routes_inv_callback"`
Expected: FAIL.

- [ ] **Step 4: Modify `handle_telegram_messages.py`**

Two changes:

**Change A**: extend `_handle_command(command)` to accept `chat_id` and side-effect for `/inventory`:

```python
# In src/backend/handle_telegram_messages.py
def _handle_command(command: str, chat_id: str = "") -> str:
    cmd = command.split()[0].lower()
    if cmd == "/inventory":
        from src.backend.handle_inventory_walk import is_walk_enabled, start_walk
        if not is_walk_enabled(chat_id):
            return "Inventory walk is not enabled for this chat."
        start_walk(g.db_session, chat_id)
        return ""  # nothing to send — start_walk already sent message
    commands = {
        "/start": "👋 Welcome to Grocery Manager! Send me a receipt photo or PDF to get started.",
        "/help": (
            "📸 Send a receipt photo or PDF → I'll extract items and update your inventory.\n"
            "📦 /inventory → Walk through stale items and update what's left\n"
            "📊 /status → Check system status\n"
            "❓ /help → Show this message"
        ),
        "/status": "✅ System is running. Send a receipt photo or PDF to test!",
    }
    return commands.get(cmd, "❓ Unknown command. Type /help for available commands.")
```

Update the caller in `telegram_webhook` (around line 64) to pass `chat_id`:

```python
if text.startswith("/"):
    response_text = _handle_command(text, chat_id=chat_id)
    if response_text:
        send_telegram_message(chat_id, response_text)
    return jsonify({"status": "ok"}), 200
```

**Change B**: extend `_handle_callback_query` to route `inv:*` and `nudge:*`:

Inside `_handle_callback_query`, near the top after extracting `data`, `chat_id`, `message_id`:

```python
if data.startswith("inv:"):
    from src.backend.handle_inventory_walk import dispatch_inv_callback, is_walk_enabled
    if is_walk_enabled(chat_id):
        dispatch_inv_callback(g.db_session, chat_id, data, message_id)
        g.db_session.commit()
    _answer_callback_query(callback_query.get("id"))
    return jsonify({"status": "ok"}), 200

if data.startswith("nudge:"):
    from src.backend.handle_inventory_walk import dispatch_nudge_callback
    if is_walk_enabled(chat_id):
        dispatch_nudge_callback(g.db_session, chat_id, data, message_id)
        g.db_session.commit()
    _answer_callback_query(callback_query.get("id"))
    return jsonify({"status": "ok"}), 200
```

(`dispatch_nudge_callback` is implemented in Task 17.)

**Change C**: extend `_edit_telegram_message` signature:

```python
def _edit_telegram_message(chat_id: str, message_id: int | None,
                           text: str, reply_markup: dict | None = None):
    if message_id is None:
        return
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        http_requests.post(f"{TELEGRAM_API_BASE}/editMessageText", json=payload, timeout=8)
    except Exception as e:
        logger.warning("editMessageText failed: %s", e)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_telegram_inventory_walk.py -v -k "webhook_inventory_command or webhook_routes_inv_callback"`
Expected: PASS.

Also run the full inventory test file to verify nothing regressed:

Run: `pytest tests/test_telegram_inventory_walk.py -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/handle_telegram_messages.py tests/test_telegram_inventory_walk.py
git commit -m "feat(telegram): wire /inventory command + inv/nudge callback routing"
```

---

## Task 17: Nudge job — eligibility + send + callback handlers

**Files:**
- Create: `src/backend/inventory_nudge_job.py`
- Modify: `src/backend/handle_inventory_walk.py` (add `dispatch_nudge_callback`)
- Test: `tests/test_inventory_nudge_job.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_inventory_nudge_job.py
import os
import pytest
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")

from src.backend.initialize_database_schema import (
    Base, Product, Inventory, TelegramInventorySession, TelegramReceipt,
    get_engine, get_session_factory, utcnow,
)


@pytest.fixture
def session():
    eng = get_engine()
    Base.metadata.create_all(eng)
    s = get_session_factory()()
    yield s
    s.close()
    Base.metadata.drop_all(eng)


def _seed_stale(session, chat_id, n_stale):
    """Create a TelegramReceipt for chat_id (allowlist) and N stale items."""
    session.add(TelegramReceipt(
        chat_id=chat_id, message_id="m1", image_path="/tmp/x", status="processed",
    ))
    for i in range(n_stale):
        p = Product(name=f"Item {chat_id}-{i}", category="pantry")
        session.add(p); session.flush()
        inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
        inv.last_updated = utcnow() - timedelta(days=30)
        session.add(inv)
    session.commit()


def test_eligibility_skips_under_threshold(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    _seed_stale(session, "abc", n_stale=2)  # under 3
    assert "abc" not in eligible_chat_ids(session)


def test_eligibility_includes_chat_with_3plus_stale(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    _seed_stale(session, "abc", n_stale=3)
    assert "abc" in eligible_chat_ids(session)


def test_eligibility_skips_muted_chat(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    _seed_stale(session, "abc", n_stale=5)
    session.add(TelegramInventorySession(
        chat_id="abc", status="done",
        nudge_muted_until=utcnow() + timedelta(days=2),
    ))
    session.commit()
    assert "abc" not in eligible_chat_ids(session)


def test_eligibility_skips_recently_nudged(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    _seed_stale(session, "abc", n_stale=5)
    session.add(TelegramInventorySession(
        chat_id="abc", status="done",
        last_nudge_sent_at=utcnow() - timedelta(days=2),
    ))
    session.commit()
    assert "abc" not in eligible_chat_ids(session)


def test_eligibility_skips_chat_with_active_session(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    _seed_stale(session, "abc", n_stale=5)
    session.add(TelegramInventorySession(
        chat_id="abc", status="active",
        current_category="pantry", item_queue=[1, 2], cursor=0, pending_prompt="level",
    ))
    session.commit()
    assert "abc" not in eligible_chat_ids(session)


def test_run_daily_nudge_sends_and_records(session, monkeypatch):
    from src.backend.inventory_nudge_job import run_daily_nudge
    _seed_stale(session, "abc", n_stale=5)
    sent = []
    monkeypatch.setattr(
        "src.backend.inventory_nudge_job.send_telegram_message",
        lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)),
    )
    monkeypatch.setenv("INVENTORY_NUDGES_ENABLED", "1")
    import importlib, src.backend.inventory_nudge_job as m
    importlib.reload(m)

    m.run_daily_nudge(session); session.commit()
    assert len(sent) == 1
    assert sent[0][0] == "abc"
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.last_nudge_sent_at is not None


def test_run_daily_nudge_respects_disable_flag(session, monkeypatch):
    from src.backend.inventory_nudge_job import run_daily_nudge
    _seed_stale(session, "abc", n_stale=5)
    sent = []
    monkeypatch.setattr(
        "src.backend.inventory_nudge_job.send_telegram_message",
        lambda chat_id, text, reply_markup=None: sent.append(chat_id),
    )
    monkeypatch.setenv("INVENTORY_NUDGES_ENABLED", "0")
    import importlib, src.backend.inventory_nudge_job as m
    importlib.reload(m)

    m.run_daily_nudge(session); session.commit()
    assert sent == []


def test_nudge_mute_callback_sets_7_day_mute(session, monkeypatch):
    from src.backend.handle_inventory_walk import dispatch_nudge_callback
    from src.backend.initialize_database_schema import TelegramInventorySession
    session.add(TelegramInventorySession(chat_id="abc", status="done")); session.commit()
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)

    dispatch_nudge_callback(session, "abc", "nudge:mute", message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.nudge_muted_until is not None
    assert row.nudge_muted_until > utcnow() + timedelta(days=6)
    assert row.nudge_muted_until < utcnow() + timedelta(days=8)
```

- [ ] **Step 2: Run tests — fail**

Run: `pytest tests/test_inventory_nudge_job.py -v`
Expected: FAIL — modules don't exist.

- [ ] **Step 3: Implement `inventory_nudge_job.py`**

```python
# src/backend/inventory_nudge_job.py
"""Daily proactive nudge for stale Telegram inventory.

See docs/superpowers/specs/2026-05-13-telegram-inventory-walk-design.md §8.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import func

from src.backend.handle_inventory_walk import (
    INVENTORY_STALE_DAYS,
    _bool_env,
    _csv_env,
    render_nudge,
)
from src.backend.handle_inventory_walk import send_telegram_message  # re-exported

logger = logging.getLogger(__name__)

NUDGE_MIN_STALE = 3
NUDGE_GAP_DAYS = 5


def _allowlist() -> set[str] | None:
    cs = _csv_env("TELEGRAM_AUTHORIZED_CHAT_IDS")
    return cs or None  # None means "fall back to TelegramReceipt distinct chats"


def _candidate_chat_ids(session) -> set[str]:
    from src.backend.initialize_database_schema import TelegramReceipt
    allow = _allowlist()
    if allow:
        return allow
    rows = session.query(TelegramReceipt.chat_id).distinct().all()
    return {r[0] for r in rows if r[0]}


def eligible_chat_ids(session) -> list[str]:
    from src.backend.initialize_database_schema import (
        Inventory, Product, TelegramInventorySession,
    )
    cutoff = datetime.utcnow() - timedelta(days=INVENTORY_STALE_DAYS)
    now = datetime.utcnow()
    out: list[str] = []
    for chat_id in _candidate_chat_ids(session):
        # Active session? skip.
        sess_row = (
            session.query(TelegramInventorySession)
            .filter_by(chat_id=chat_id)
            .one_or_none()
        )
        if sess_row and sess_row.status == "active" and sess_row.item_queue:
            continue
        if sess_row and sess_row.nudge_muted_until and sess_row.nudge_muted_until > now:
            continue
        if (sess_row and sess_row.last_nudge_sent_at and
                sess_row.last_nudge_sent_at > now - timedelta(days=NUDGE_GAP_DAYS)):
            continue
        stale_count = (
            session.query(func.count(Inventory.id))
            .join(Product, Product.id == Inventory.product_id)
            .filter(Inventory.is_active_window.is_(True))
            .filter(Inventory.last_updated < cutoff)
            .scalar()
        ) or 0
        if stale_count < NUDGE_MIN_STALE:
            continue
        out.append(chat_id)
    return out


def _stale_count_for(session, _chat_id: str) -> int:
    """Total stale items visible to this chat (single-household assumption)."""
    from src.backend.initialize_database_schema import Inventory, Product
    cutoff = datetime.utcnow() - timedelta(days=INVENTORY_STALE_DAYS)
    return (
        session.query(func.count(Inventory.id))
        .join(Product, Product.id == Inventory.product_id)
        .filter(Inventory.is_active_window.is_(True))
        .filter(Inventory.last_updated < cutoff)
        .scalar()
    ) or 0


def run_daily_nudge(session) -> None:
    if not _bool_env("INVENTORY_NUDGES_ENABLED", False):
        logger.info("inventory nudges disabled via env")
        return

    from src.backend.initialize_database_schema import TelegramInventorySession

    for chat_id in eligible_chat_ids(session):
        stale_count = _stale_count_for(session, chat_id)
        if stale_count < NUDGE_MIN_STALE:
            continue
        text, kb = render_nudge(stale_count)
        try:
            send_telegram_message(chat_id, text, reply_markup=kb)
        except Exception as e:
            logger.warning("nudge send failed for %s: %s", chat_id, e)
            continue
        row = (
            session.query(TelegramInventorySession)
            .filter_by(chat_id=chat_id)
            .one_or_none()
        )
        if row is None:
            row = TelegramInventorySession(chat_id=chat_id, status="done")
            session.add(row)
            session.flush()
        row.last_nudge_sent_at = datetime.utcnow()
```

Append `dispatch_nudge_callback` to `src/backend/handle_inventory_walk.py`:

```python
def dispatch_nudge_callback(session, chat_id: str, data: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    if data == "nudge:yes":
        _edit_telegram_message(chat_id, message_id, "Starting walk…")
        start_walk(session, chat_id)
    elif data == "nudge:later":
        row.nudge_muted_until = datetime.utcnow() + timedelta(days=3)
        _edit_telegram_message(chat_id, message_id, "OK, I'll ask again in a few days.")
    elif data == "nudge:mute":
        row.nudge_muted_until = datetime.utcnow() + timedelta(days=7)
        _edit_telegram_message(chat_id, message_id, "Muted for a week.")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_inventory_nudge_job.py -v`
Expected: PASS — eight tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/inventory_nudge_job.py src/backend/handle_inventory_walk.py tests/test_inventory_nudge_job.py
git commit -m "feat(telegram): inventory_nudge_job — eligibility, send, nudge handlers"
```

---

## Task 18: APScheduler — register daily nudge job

**Files:**
- Modify: `src/backend/check_inventory_thresholds.py`
- Test: `tests/test_inventory_nudge_job.py`

- [ ] **Step 1: Inspect current scheduler shape**

Open `src/backend/check_inventory_thresholds.py`. There's a `start_threshold_checker()` (line 24) that registers an APScheduler job. We follow the same pattern.

- [ ] **Step 2: Write the failing test**

```python
def test_nudge_job_registers_when_enabled(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler()
    monkeypatch.setenv("INVENTORY_NUDGES_ENABLED", "1")
    from src.backend.inventory_nudge_job import register_daily_nudge_job
    register_daily_nudge_job(sched)
    jobs = sched.get_jobs()
    assert any(j.id == "inventory_daily_nudge" for j in jobs)


def test_nudge_job_skips_registration_when_disabled(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler()
    monkeypatch.setenv("INVENTORY_NUDGES_ENABLED", "0")
    from src.backend.inventory_nudge_job import register_daily_nudge_job
    register_daily_nudge_job(sched)
    jobs = sched.get_jobs()
    assert not any(j.id == "inventory_daily_nudge" for j in jobs)
```

- [ ] **Step 3: Run — fail**

Run: `pytest tests/test_inventory_nudge_job.py -v -k "nudge_job_registers or nudge_job_skips"`
Expected: FAIL — `register_daily_nudge_job` not defined.

- [ ] **Step 4: Add the registration helper**

Append to `src/backend/inventory_nudge_job.py`:

```python
def register_daily_nudge_job(scheduler) -> None:
    """Register the daily nudge job at 09:00 server-local time. No-op if disabled."""
    if not _bool_env("INVENTORY_NUDGES_ENABLED", False):
        return
    from apscheduler.triggers.cron import CronTrigger

    def _job_wrapper():
        from src.backend.initialize_database_schema import get_session_factory
        sess = get_session_factory()()
        try:
            run_daily_nudge(sess)
            sess.commit()
        except Exception:
            sess.rollback()
            logger.exception("daily nudge job failed")
        finally:
            sess.close()

    scheduler.add_job(
        _job_wrapper,
        trigger=CronTrigger(hour=9, minute=0),
        id="inventory_daily_nudge",
        replace_existing=True,
    )
```

Then in `src/backend/check_inventory_thresholds.py`, modify `start_threshold_checker` to also call `register_daily_nudge_job(scheduler)`:

```python
# At the end of start_threshold_checker(), after the threshold-check job is added:
try:
    from src.backend.inventory_nudge_job import register_daily_nudge_job
    register_daily_nudge_job(scheduler)
except Exception:
    logger.exception("failed to register inventory nudge job")
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_inventory_nudge_job.py -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/inventory_nudge_job.py src/backend/check_inventory_thresholds.py tests/test_inventory_nudge_job.py
git commit -m "feat(telegram): register daily nudge APScheduler job at 09:00"
```

---

## Task 19: End-to-end webhook flow test

**Files:**
- Create: `tests/test_telegram_inventory_e2e.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_telegram_inventory_e2e.py
"""Full webhook → state → DB flow tests."""
import os
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ.setdefault("TELEGRAM_INVENTORY_WALK_ENABLED", "1")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "")

from src.backend.initialize_database_schema import (
    Base, Product, Inventory, ShoppingListItem, TelegramInventorySession,
    get_engine, get_session_factory, utcnow,
)
from src.backend.create_flask_application import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    eng = get_engine()
    Base.metadata.create_all(eng)
    with app.test_client() as c:
        with app.app_context():
            yield c
    Base.metadata.drop_all(eng)


@pytest.fixture
def db():
    return get_session_factory()()


def _post_update(client, payload):
    return client.post("/telegram/webhook", json=payload)


def _post_command(client, chat_id, text):
    return _post_update(client, {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id},
            "text": text,
        },
    })


def _post_callback(client, chat_id, data, message_id=100):
    return _post_update(client, {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "data": data,
            "from": {"id": 42},
            "message": {"chat": {"id": chat_id}, "message_id": message_id},
        },
    })


@patch("src.backend.handle_telegram_messages.http_requests")
def test_full_walk_one_item_empty_to_cart(http_mock, client, db):
    http_mock.post = MagicMock(return_value=MagicMock(status_code=200))
    p = Product(name="Olive oil", category="pantry"); db.add(p); db.flush()
    inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
    inv.last_updated = utcnow() - timedelta(days=30)
    db.add(inv); db.commit()

    chat = "12345"
    assert _post_command(client, chat, "/inventory").status_code == 200
    assert _post_callback(client, chat, "inv:cat:pantry").status_code == 200
    assert _post_callback(client, chat, "inv:lvl:0").status_code == 200   # Empty
    assert _post_callback(client, chat, "inv:cart:y").status_code == 200  # Yes add

    db.expire_all()
    inv2 = db.query(Inventory).filter_by(id=inv.id).one()
    assert inv2.consumed_pct_override == 1.0
    assert inv2.manual_low is True
    items = db.query(ShoppingListItem).filter_by(product_id=p.id).all()
    assert len(items) == 1
    sess = db.query(TelegramInventorySession).filter_by(chat_id=chat).one()
    assert sess.stats.get("updated") == 1
    assert sess.stats.get("cart_added") == 1
    assert sess.status == "done"


@patch("src.backend.handle_telegram_messages.http_requests")
def test_two_chats_dont_interfere(http_mock, client, db):
    http_mock.post = MagicMock(return_value=MagicMock(status_code=200))
    for i in range(2):
        p = Product(name=f"Item {i}", category="pantry"); db.add(p); db.flush()
        inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
        inv.last_updated = utcnow() - timedelta(days=30)
        db.add(inv)
    db.commit()

    _post_command(client, "alpha", "/inventory")
    _post_callback(client, "alpha", "inv:cat:pantry", message_id=200)
    _post_command(client, "bravo", "/inventory")
    _post_callback(client, "bravo", "inv:cat:pantry", message_id=300)

    db.expire_all()
    a = db.query(TelegramInventorySession).filter_by(chat_id="alpha").one()
    b = db.query(TelegramInventorySession).filter_by(chat_id="bravo").one()
    assert a.current_category == "pantry"
    assert b.current_category == "pantry"
    assert a.cursor == 0 and b.cursor == 0
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_telegram_inventory_e2e.py -v`
Expected: PASS — both tests. If `create_app` import path differs (verify against `tests/test_full_receipt_flow.py`), adjust accordingly.

- [ ] **Step 3: Commit**

```bash
git add tests/test_telegram_inventory_e2e.py
git commit -m "test(telegram): end-to-end webhook walk flow + multi-chat isolation"
```

---

## Task 20: Run full suite + post-merge smoke checklist

- [ ] **Step 1: Run full test suite**

Run: `pytest -x -q`
Expected: All tests pass (existing + new). Investigate and fix any unexpected regressions.

- [ ] **Step 2: Run lint / type checks consistent with repo conventions**

Run: `python -m compileall src/backend/handle_inventory_walk.py src/backend/inventory_nudge_job.py`
Expected: no syntax errors.

Run (if mypy / ruff are configured): `ruff check src/backend/handle_inventory_walk.py src/backend/inventory_nudge_job.py` and fix anything that surfaces. Skip silently if these tools aren't part of the repo conventions.

- [ ] **Step 3: Manual smoke-test guide for the human**

Add the following to the PR description (do not commit it as a file — it's per-release). Per the user's memory `feedback_smoke_tests`, include this checklist after every phase completion:

- [ ] On dev with `TELEGRAM_INVENTORY_WALK_ENABLED=1` and chat-id whitelisted, send `/inventory`. Category screen appears.
- [ ] Tap a category. First item shown with correct staleness phrase.
- [ ] Tap each level button on different items. Open `/inventory` web page, confirm green-fill % matches the button pressed.
- [ ] Mark one item Empty → Yes. Open `/shopping/list` web page, confirm item appears with source `telegram_walk`.
- [ ] Mark another item No-longer-have. Reload web inventory; item is gone from active view.
- [ ] Tap Done mid-walk. Summary message shows correct Updated/Skipped/Removed/Cart Added counts.
- [ ] Within 1h, send `/inventory` again. "Resume in progress" prompt appears with cursor position.
- [ ] Run `flask shell` (or equivalent) and call `inventory_nudge_job.run_daily_nudge(db.session)`. Verify nudge arrives once.
- [ ] Tap Mute 7d on the nudge. Re-run nudge job; chat is skipped.
- [ ] Run the dev container restart (e.g. `docker compose restart backend`) mid-walk. Re-tap the last button. Bot replies "That button is stale" and re-renders current step.
- [ ] Per user's memory `feedback_backup_restore_safety`: backup-then-restore the dev DB. Verify `telegram_inventory_session` rows survive and no FK orphans appear.
- [ ] Per user's memory `feedback_dev_lan_cookie`: this flow doesn't touch session cookies, but if running over LAN, confirm webhook endpoint still receives Telegram POSTs end-to-end (no `SESSION_COOKIE_SECURE` issues — Telegram talks HTTP/HTTPS to the webhook, not browser cookies).

- [ ] **Step 4: Final commit (if anything was tweaked in step 2)**

```bash
git status
# if there are tracked changes: git add ...
# git commit -m "chore(telegram): final lint/cleanup before merge"
```

---

## Spec-coverage check (self-review)

Mapping each spec section to tasks:

| Spec section | Tasks |
|--------------|-------|
| §1–4 User flow + scope | Tasks 8, 9, 10, 11, 12, 13, 14 (renders + handlers cover every screen) |
| §5 Data model — table | Task 1 (migration) + Task 2 (model) |
| §5 Inventory mutations | Task 6 |
| §5 Shopping list insert | Task 7 |
| §5 Stale-item SQL | Task 4 |
| §6 State machine | Tasks 9–15 (each handler is one transition) |
| §6 Callback_data format | Tasks 8 (renders use exact verbs), 15 (dispatch parses) |
| §7 Telegram UI copy | Task 8 |
| §7 Error copy | Task 15 (stale verb), Task 10 (vanished row), Task 15 (idle) |
| §8 Proactive nudge | Tasks 17, 18 |
| §9 Module layout | All tasks together |
| §10 Feature flags | Task 3 (flags) + Task 16 (gating in webhook) + Task 17 (`INVENTORY_NUDGES_ENABLED`) |
| §11 Testing strategy | Tasks 1–19 each include tests |
| §12 Risks & open questions | Acknowledged inline; deferred items match spec |
| §13 Non-goals | Implicitly respected — no Inventory/ShoppingList schema changes |
