# Telegram Shopping Walk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `/shopping` Telegram flow that proactively proposes shopping-list items grouped by category (driven by the existing recommendation engine), with one-tap quick-add, qty+store detailed-add, and per-category custom typed-name add. Plus a daily smart-trigger nudge.

**Architecture:** New `TelegramShoppingSession` table (one row per chat_id). New `handle_shopping_walk.py` module owns state machine, rendering, dispatch, and per-button handlers. Existing `handle_telegram_messages.py` extended only with routing for `/shopping` command, `shop:*` callbacks, `nudge:shop:*` callbacks, and typed-text consumed during custom-add states. Reuses `generate_recommendations.generate_all_recommendations()` (read-only) and `manage_shopping_list._ensure_current_session(session)` for inserts. Daily nudge runs via APScheduler alongside the existing inventory nudge.

**Tech Stack:** Python 3.11+, Flask, SQLAlchemy 2.x, Alembic, APScheduler, pytest, SQLite (test) / SQLite (prod).

**Spec:** [docs/superpowers/specs/2026-05-14-telegram-shopping-walk-design.md](../specs/2026-05-14-telegram-shopping-walk-design.md)

---

## File map

**Create:**
- `alembic/versions/032_telegram_shopping_session.py` — migration (additive, idempotent, no-op downgrade when absent)
- `src/backend/handle_shopping_walk.py` — state machine, rendering, dispatch, handlers
- `src/backend/shopping_nudge_job.py` — daily eligibility + send job
- `tests/test_migration_032.py` — migration unit tests
- `tests/test_telegram_shopping_walk.py` — module unit tests
- `tests/test_shopping_nudge_job.py` — nudge job unit tests
- `tests/test_telegram_shopping_e2e.py` — end-to-end webhook flow test

**Modify:**
- `src/backend/initialize_database_schema.py` — add `TelegramShoppingSession` SQLAlchemy model
- `src/backend/handle_telegram_messages.py` — route `/shopping` command + `shop:*` / `nudge:shop:*` callbacks + custom-add typed-text states
- `src/backend/check_inventory_thresholds.py` — register daily shopping nudge APScheduler job

---

## Conventions

- All `pytest` commands run from repo root. Python is `./venv/bin/python`.
- Each task ends with one commit. Conventional Commits.
- Tests follow the established pattern in `tests/test_telegram_inventory_walk.py`: `tmp_path` + `create_db_engine` + `create_session_factory`, no Flask app required for unit tests of the handler module's pure functions.
- All Telegram HTTP calls in tests are stubbed via `monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message", ...)` and `..._edit_telegram_message`.
- `datetime.utcnow()` is used consistently with the rest of the module (matches existing codebase convention; DeprecationWarning expected and acceptable).
- The recommendation engine entry point used by this feature is `generate_all_recommendations()` (returns a `list[dict]`), NOT the Flask route `get_recommendations()` (returns `jsonify(...)`).

---

## Task 1: Migration 032 — `telegram_shopping_session` table

**Files:**
- Create: `alembic/versions/032_telegram_shopping_session.py`
- Test: `tests/test_migration_032.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_migration_032.py`:

```python
"""Tests for Alembic migration 032_telegram_shopping_session."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "032_telegram_shopping_session.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_032", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _compile_column(col):
    parts = [col.name, str(col.type)]
    if col.primary_key:
        parts.append("PRIMARY KEY")
    if not col.nullable and not col.primary_key:
        parts.append("NOT NULL")
    if col.server_default is not None and hasattr(col.server_default, "arg"):
        arg = col.server_default.arg
        parts.append(f"DEFAULT {arg}")
    return " ".join(parts)


def _install_op_patches(engine):
    """Patch alembic.op symbols the migration uses so it can run against
    a plain SQLAlchemy engine without a MigrationContext."""
    from contextlib import ExitStack
    stack = ExitStack()

    def fake_create_table(name, *cols, **_kw):
        col_sql = ", ".join(_compile_column(c) for c in cols)
        with engine.begin() as conn:
            conn.execute(sa.text(f"CREATE TABLE {name} ({col_sql})"))

    def fake_drop_table(name, **_kw):
        with engine.begin() as conn:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))

    def fake_create_index(name, table, cols, **_kw):
        cs = ", ".join(cols)
        with engine.begin() as conn:
            conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cs})"))

    def fake_drop_index(name, table_name=None, **_kw):
        with engine.begin() as conn:
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))

    bind = engine.connect()
    stack.enter_context(patch("alembic.op.get_bind", return_value=bind))
    stack.enter_context(patch("alembic.op.create_table", side_effect=fake_create_table))
    stack.enter_context(patch("alembic.op.drop_table", side_effect=fake_drop_table))
    stack.enter_context(patch("alembic.op.create_index", side_effect=fake_create_index))
    stack.enter_context(patch("alembic.op.drop_index", side_effect=fake_drop_index))
    return stack


def test_032_module_loads():
    mig = _load_migration()
    assert mig.revision == "032_telegram_shopping_session"
    assert mig.down_revision == "031_telegram_inventory_session"


def test_032_upgrade_creates_table_and_is_idempotent(tmp_path):
    mig = _load_migration()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'u.db'}")
    with _install_op_patches(engine):
        mig.upgrade()
        mig.upgrade()  # idempotent — second call must not raise

    insp = sa.inspect(engine)
    assert "telegram_shopping_session" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("telegram_shopping_session")}
    expected = {
        "chat_id", "user_id", "status",
        "category_queue", "current_category", "item_queue", "cursor",
        "pending_prompt", "pending_action",
        "last_item_id", "pending_name", "pending_qty",
        "stats", "nudge_muted_until", "last_nudge_sent_at",
        "started_at", "last_action_at",
    }
    assert expected <= cols, f"missing: {expected - cols}"

    idx_names = {i["name"] for i in insp.get_indexes("telegram_shopping_session")}
    assert "ix_tg_shop_status" in idx_names
    assert "ix_tg_shop_last_action" in idx_names


def test_032_downgrade_drops_table_when_present(tmp_path):
    mig = _load_migration()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    with _install_op_patches(engine):
        mig.upgrade()
        mig.downgrade()
    insp = sa.inspect(engine)
    assert "telegram_shopping_session" not in insp.get_table_names()


def test_032_downgrade_is_noop_when_table_absent(tmp_path):
    mig = _load_migration()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'd2.db'}")
    with _install_op_patches(engine):
        mig.downgrade()  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_migration_032.py -v`
Expected: FAIL — migration file doesn't exist.

- [ ] **Step 3: Write the migration**

Create `alembic/versions/032_telegram_shopping_session.py`:

```python
"""telegram_shopping_session: per-chat walk state for /shopping Telegram flow.

Revision ID: 032_telegram_shopping_session
Revises: 031_telegram_inventory_session
Create Date: 2026-05-14

Additive: creates one new table. Idempotent: re-running upgrade is a no-op.
Downgrade drops the table; no-op when already absent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "032_telegram_shopping_session"
down_revision: Union[str, None] = "031_telegram_inventory_session"
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
    if _table_exists(bind, "telegram_shopping_session"):
        return

    op.create_table(
        "telegram_shopping_session",
        sa.Column("chat_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("category_queue", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("current_category", sa.String(40), nullable=True),
        sa.Column("item_queue", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("cursor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pending_prompt", sa.String(30), nullable=True),
        sa.Column("pending_action", sa.String(20), nullable=True),
        sa.Column("last_item_id", sa.Integer, nullable=True),
        sa.Column("pending_name", sa.String(255), nullable=True),
        sa.Column("pending_qty", sa.Float, nullable=True),
        sa.Column("stats", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("nudge_muted_until", sa.DateTime, nullable=True),
        sa.Column("last_nudge_sent_at", sa.DateTime, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("last_action_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_tg_shop_status", "telegram_shopping_session", ["status"])
    op.create_index("ix_tg_shop_last_action", "telegram_shopping_session", ["last_action_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "telegram_shopping_session"):
        return
    op.drop_index("ix_tg_shop_last_action", table_name="telegram_shopping_session")
    op.drop_index("ix_tg_shop_status", table_name="telegram_shopping_session")
    op.drop_table("telegram_shopping_session")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_migration_032.py -v`
Expected: PASS — all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/032_telegram_shopping_session.py tests/test_migration_032.py
git commit -m "feat(db): migration 032 — telegram_shopping_session table"
```

---

## Task 2: SQLAlchemy `TelegramShoppingSession` model

**Files:**
- Modify: `src/backend/initialize_database_schema.py` — add class right after `TelegramInventorySession` (which lives between `TelegramReceipt` and `ApiUsage`)
- Test: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_telegram_shopping_walk.py`:

```python
"""Unit tests for handle_shopping_walk + TelegramShoppingSession model."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ.setdefault("TELEGRAM_SHOPPING_WALK_ENABLED", "1")


@pytest.fixture
def session(tmp_path):
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    db = tmp_path / "s.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    SessionFactory = create_session_factory(eng)
    s = SessionFactory()
    yield s
    s.close()


def test_telegram_shopping_session_round_trip(session):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = TelegramShoppingSession(
        chat_id="12345",
        status="active",
        category_queue=["pantry", "fridge"],
        current_category="pantry",
        item_queue=[{"product_id": 1, "name": "Olive oil", "category": "pantry",
                     "reason_label": "Low stock"}],
        cursor=0,
        pending_prompt="item",
        stats={"added": 0, "skipped": 0, "already_have": 0, "custom_added": 0},
    )
    session.add(row); session.commit()
    fetched = session.query(TelegramShoppingSession).filter_by(chat_id="12345").one()
    assert fetched.category_queue == ["pantry", "fridge"]
    assert fetched.item_queue[0]["product_id"] == 1
    assert fetched.cursor == 0
    assert fetched.pending_prompt == "item"
    assert fetched.stats == {"added": 0, "skipped": 0, "already_have": 0, "custom_added": 0}


def test_telegram_shopping_session_defaults(session):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = TelegramShoppingSession(chat_id="bare")
    session.add(row); session.commit()
    fetched = session.query(TelegramShoppingSession).filter_by(chat_id="bare").one()
    assert fetched.status == "active"
    assert fetched.category_queue == []
    assert fetched.item_queue == []
    assert fetched.cursor == 0
    assert fetched.stats == {}
    assert fetched.last_item_id is None
    assert fetched.pending_name is None
    assert fetched.pending_qty is None
    assert fetched.nudge_muted_until is None
    assert fetched.last_nudge_sent_at is None
    assert fetched.started_at is not None
    assert fetched.last_action_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v`
Expected: FAIL — `ImportError: cannot import name 'TelegramShoppingSession'`.

- [ ] **Step 3: Add the model**

In `src/backend/initialize_database_schema.py`, locate the existing `TelegramInventorySession` class (added by the previous PR). Add the new class immediately after it and before `ApiUsage`:

```python
class TelegramShoppingSession(Base):
    __tablename__ = "telegram_shopping_session"

    chat_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    category_queue = Column(JSON, nullable=False, default=list)
    current_category = Column(String(40), nullable=True)
    item_queue = Column(JSON, nullable=False, default=list)
    cursor = Column(Integer, nullable=False, default=0)
    pending_prompt = Column(String(30), nullable=True)
    pending_action = Column(String(20), nullable=True)
    last_item_id = Column(Integer, nullable=True)
    pending_name = Column(String(255), nullable=True)
    pending_qty = Column(Float, nullable=True)
    stats = Column(JSON, nullable=False, default=dict)
    nudge_muted_until = Column(DateTime, nullable=True)
    last_nudge_sent_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, default=utcnow)
    last_action_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_tg_shop_status", "status"),
        Index("ix_tg_shop_last_action", "last_action_at"),
    )
```

`Float` is already imported in this file. `JSON` was added by the inventory walk PR. No new imports needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/initialize_database_schema.py tests/test_telegram_shopping_walk.py
git commit -m "feat(db): TelegramShoppingSession SQLAlchemy model"
```

---

## Task 3: Module skeleton — env constants + `is_walk_enabled`

**Files:**
- Create: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py` (append 3 tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_constants_have_safe_defaults(monkeypatch):
    monkeypatch.delenv("TELEGRAM_SHOPPING_WALK_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_SHOPPING_WALK_PILOT_CHATS", raising=False)
    monkeypatch.delenv("SHOPPING_WALK_IDLE_TIMEOUT_MIN", raising=False)
    import importlib
    import src.backend.handle_shopping_walk as m
    importlib.reload(m)
    assert m.WALK_ENABLED is False
    assert m.PILOT_CHATS == set()
    assert m.IDLE_TIMEOUT_MIN == 30


def test_is_walk_enabled_respects_flags(monkeypatch):
    import importlib
    import src.backend.handle_shopping_walk as m
    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_PILOT_CHATS", "")
    importlib.reload(m)
    assert m.is_walk_enabled("999") is True

    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_PILOT_CHATS", "111,222")
    importlib.reload(m)
    assert m.is_walk_enabled("111") is True
    assert m.is_walk_enabled("999") is False

    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_ENABLED", "0")
    importlib.reload(m)
    assert m.is_walk_enabled("111") is False


def test_module_re_exports_env_helpers():
    import src.backend.handle_shopping_walk as m
    assert callable(m._bool_env)
    assert callable(m._csv_env)
    assert callable(m._int_env)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "constants or is_walk_enabled or re_exports"`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create the module skeleton**

Create `src/backend/handle_shopping_walk.py`:

```python
"""Telegram /shopping walk — state machine, dispatch, rendering.

See docs/superpowers/specs/2026-05-14-telegram-shopping-walk-design.md
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

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


WALK_ENABLED = _bool_env("TELEGRAM_SHOPPING_WALK_ENABLED", False)
PILOT_CHATS: set[str] = _csv_env("TELEGRAM_SHOPPING_WALK_PILOT_CHATS")
IDLE_TIMEOUT_MIN = _int_env("SHOPPING_WALK_IDLE_TIMEOUT_MIN", 30)


def is_walk_enabled(chat_id: str) -> bool:
    if not WALK_ENABLED:
        return False
    if PILOT_CHATS and chat_id not in PILOT_CHATS:
        return False
    return True
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v`
Expected: ALL PASS — 5 tests (2 model + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): handle_shopping_walk module skeleton + feature flags"
```

---

## Task 4: Session helpers + idle abandon

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_get_or_create_session_creates_row(session):
    from src.backend.handle_shopping_walk import get_or_create_session
    row = get_or_create_session(session, "abc")
    assert row.chat_id == "abc"
    assert row.status == "active"
    assert row.category_queue == []
    assert row.cursor == 0


def test_get_or_create_session_returns_existing(session):
    from src.backend.handle_shopping_walk import get_or_create_session
    from src.backend.initialize_database_schema import TelegramShoppingSession
    session.add(TelegramShoppingSession(
        chat_id="abc", status="active", current_category="pantry", cursor=2,
    ))
    session.commit()
    row = get_or_create_session(session, "abc")
    assert row.current_category == "pantry"
    assert row.cursor == 2


def test_reset_for_start_over_preserves_nudge_prefs(session):
    from src.backend.handle_shopping_walk import reset_for_start_over
    from src.backend.initialize_database_schema import TelegramShoppingSession
    nudge_until = datetime.utcnow() + timedelta(days=7)
    row = TelegramShoppingSession(
        chat_id="abc",
        status="done",
        category_queue=["pantry", "fridge"],
        current_category="pantry",
        item_queue=[{"product_id": 1}],
        cursor=1,
        pending_prompt="item",
        pending_action="add_detailed",
        last_item_id=5,
        pending_name="Bay leaves",
        pending_qty=2.0,
        stats={"added": 3},
        nudge_muted_until=nudge_until,
    )
    session.add(row); session.commit()
    reset_for_start_over(row)
    session.commit()
    assert row.status == "active"
    assert row.category_queue == []
    assert row.current_category is None
    assert row.item_queue == []
    assert row.cursor == 0
    assert row.pending_prompt == "category"
    assert row.pending_action is None
    assert row.last_item_id is None
    assert row.pending_name is None
    assert row.pending_qty is None
    assert row.stats == {}
    assert row.nudge_muted_until == nudge_until  # preserved


def test_abandon_if_idle_marks_status(session):
    from src.backend.handle_shopping_walk import abandon_if_idle
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = TelegramShoppingSession(chat_id="abc", status="active")
    session.add(row); session.commit()
    row.last_action_at = datetime.utcnow() - timedelta(minutes=45)
    session.commit()
    assert abandon_if_idle(row) is True
    assert row.status == "abandoned"


def test_abandon_if_idle_leaves_fresh_session_alone(session):
    from src.backend.handle_shopping_walk import abandon_if_idle
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = TelegramShoppingSession(chat_id="abc", status="active")
    session.add(row); session.commit()
    assert abandon_if_idle(row) is False
    assert row.status == "active"
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "get_or_create or reset_for_start_over or abandon_if_idle"`
Expected: FAIL.

- [ ] **Step 3: Implement helpers**

Append to `src/backend/handle_shopping_walk.py`:

```python
def get_or_create_session(session, chat_id: str):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = (
        session.query(TelegramShoppingSession)
        .filter_by(chat_id=chat_id)
        .one_or_none()
    )
    if row is None:
        row = TelegramShoppingSession(chat_id=chat_id, status="active")
        session.add(row)
        session.flush()
    return row


def reset_for_start_over(row) -> None:
    row.status = "active"
    row.category_queue = []
    row.current_category = None
    row.item_queue = []
    row.cursor = 0
    row.pending_prompt = "category"
    row.pending_action = None
    row.last_item_id = None
    row.pending_name = None
    row.pending_qty = None
    row.stats = {}


def abandon_if_idle(row) -> bool:
    if row.status != "active":
        return False
    if row.last_action_at is None:
        return False
    cutoff = datetime.utcnow() - timedelta(minutes=IDLE_TIMEOUT_MIN)
    last_action = row.last_action_at
    if last_action.tzinfo is not None:
        last_action = last_action.replace(tzinfo=None)
    if last_action < cutoff:
        row.status = "abandoned"
        return True
    return False
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v`
Expected: ALL PASS — 10 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): shopping walk session helpers — create, reset, idle"
```

---

## Task 5: Recommendation fetch + category bucketing

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def _seed_low_inventory(session, *, pairs):
    """pairs: list[(product_name, category, quantity, threshold, manual_low)]."""
    from src.backend.initialize_database_schema import Product, Inventory
    for name, category, qty, threshold, manual_low in pairs:
        p = Product(name=name, category=category); session.add(p); session.flush()
        inv = Inventory(
            product_id=p.id, quantity=qty, threshold=threshold,
            manual_low=manual_low, is_active_window=True,
        )
        session.add(inv)
    session.commit()


def test_fetch_recommendations_calls_engine_via_flask_shim(session):
    """Engine reads g.db_session, so the helper must push an app context with g.db_session=session."""
    from src.backend.handle_shopping_walk import fetch_recommendations
    _seed_low_inventory(session, pairs=[
        ("Olive oil",   "pantry", 1.0, 5.0, False),  # low_stock (qty < threshold)
        ("Black pepper","pantry", 0.0, None, True),  # manual_low
        ("Milk",        "fridge", 0.0, None, True),
    ])
    recs = fetch_recommendations(session)
    names = sorted(r["product_name"] for r in recs)
    cats = sorted(set(r["category"] for r in recs))
    assert "Olive oil" in names
    assert "Black pepper" in names
    assert "Milk" in names
    assert cats == ["fridge", "pantry"]


def test_bucketize_by_category_orders_by_count_desc():
    from src.backend.handle_shopping_walk import bucketize_by_category
    recs = [
        {"product_id": 1, "product_name": "A", "category": "pantry",  "reason": "low_stock"},
        {"product_id": 2, "product_name": "B", "category": "pantry",  "reason": "manual_low"},
        {"product_id": 3, "product_name": "C", "category": "fridge",  "reason": "low_stock"},
        {"product_id": 4, "product_name": "D", "category": None,       "reason": "low_stock"},
    ]
    cat_queue, item_map = bucketize_by_category(recs)
    assert cat_queue == ["pantry", "fridge", "other"]   # pantry first (2 items)
    assert len(item_map["pantry"]) == 2
    assert len(item_map["fridge"]) == 1
    assert len(item_map["other"]) == 1
    # item_map entries are the compact dicts stored in item_queue
    item = item_map["pantry"][0]
    assert "product_id" in item
    assert "name" in item
    assert "category" in item
    assert "reason_label" in item


def test_reason_label_for_each_kind():
    from src.backend.handle_shopping_walk import _reason_label
    assert "Low stock" in _reason_label({"reason": "low_stock", "current_quantity": 1.0, "threshold": 5.0})
    assert "Low stock" in _reason_label({"reason": "manual_low"})
    assert "Seasonal" in _reason_label({"reason": "seasonal_purchase"})
    assert "Price" in _reason_label({"reason": "price_deal", "regular_price": 8.99, "deal_price": 6.49})
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "fetch_recommendations or bucketize or reason_label"`
Expected: FAIL.

- [ ] **Step 3: Implement fetch + bucketize**

Append to `src/backend/handle_shopping_walk.py`:

```python
def _reason_label(rec: dict) -> str:
    """Short human label for the per-item reason."""
    kind = rec.get("reason", "")
    if kind == "manual_low":
        return "Low stock — marked manually"
    if kind == "low_stock":
        qty = rec.get("current_quantity")
        thr = rec.get("threshold")
        if qty is not None and thr is not None:
            return f"Low stock · {qty:g} left (threshold {thr:g})"
        return "Low stock"
    if kind == "seasonal_purchase" or kind == "seasonal":
        return "Seasonal pick"
    if kind == "price_deal":
        reg = rec.get("regular_price")
        deal = rec.get("deal_price")
        if reg and deal:
            return f"Price drop · was ${reg:.2f} now ${deal:.2f}"
        return "Price drop"
    if kind == "regular_use":
        days = rec.get("days_since_last_buy")
        if days is not None:
            return f"Regular item · {days} days since last buy"
        return "Regular item"
    return kind or "Suggested"


def _to_item_dict(rec: dict) -> dict:
    """Compact representation stored in item_queue JSON."""
    return {
        "product_id": rec.get("product_id"),
        "name": rec.get("product_name") or rec.get("name") or "Item",
        "category": (rec.get("category") or "other"),
        "reason_label": _reason_label(rec),
    }


def fetch_recommendations(session) -> list[dict]:
    """Call generate_all_recommendations under a Flask app context.

    Production path is always inside a Flask request context (Telegram webhook
    is a Flask route). The no-context fallback below pushes a throwaway context
    + binds `g.db_session=session` so unit tests can call this helper directly.
    """
    import flask
    from src.backend.generate_recommendations import generate_all_recommendations

    def _call():
        flask.g.db_session = session
        return generate_all_recommendations()

    if flask.has_app_context():
        # Honor existing g.db_session if set, else point at the provided session
        if not hasattr(flask.g, "db_session"):
            flask.g.db_session = session
        return generate_all_recommendations()

    _ctx_app = flask.Flask("shopping_walk_ctx")
    with _ctx_app.app_context():
        return _call()


def bucketize_by_category(recs: list[dict]) -> tuple[list[str], dict[str, list[dict]]]:
    """Split recs into per-category lists, return (ordered_categories, items_by_category).

    Categories sorted by item-count desc, ties broken by alpha. NULL/empty
    category → "other" bucket.
    """
    items_by: dict[str, list[dict]] = {}
    for rec in recs:
        item = _to_item_dict(rec)
        items_by.setdefault(item["category"], []).append(item)
    cat_queue = sorted(items_by.keys(), key=lambda c: (-len(items_by[c]), c))
    return cat_queue, items_by
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "fetch_recommendations or bucketize or reason_label"`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): recommendation fetch + category bucketing"
```

---

## Task 6: Shopping-list insert helper + dedup

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_insert_recommendation_inserts_with_qty_and_store(session):
    from src.backend.handle_shopping_walk import insert_recommendation
    from src.backend.initialize_database_schema import Product, ShoppingListItem
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    item = insert_recommendation(session, product_id=p.id, name="Olive oil",
                                 category="pantry", quantity=3.0,
                                 preferred_store="Costco")
    session.commit()
    assert item is not None
    fetched = session.query(ShoppingListItem).filter_by(product_id=p.id).all()
    assert len(fetched) == 1
    assert fetched[0].quantity == 3.0
    assert fetched[0].preferred_store == "Costco"
    assert fetched[0].source == "telegram_shopping"
    assert fetched[0].status == "open"


def test_insert_recommendation_dedups_open_item(session):
    from src.backend.handle_shopping_walk import insert_recommendation
    from src.backend.initialize_database_schema import Product, ShoppingListItem
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    first = insert_recommendation(session, product_id=p.id, name="Olive oil",
                                  category="pantry", quantity=1.0,
                                  preferred_store=None)
    session.commit()
    second = insert_recommendation(session, product_id=p.id, name="Olive oil",
                                   category="pantry", quantity=2.0,
                                   preferred_store="Sprouts")
    session.commit()
    assert first.id == second.id, "dedup must return existing OPEN row"
    items = session.query(ShoppingListItem).filter_by(
        product_id=p.id, status="open",
    ).all()
    assert len(items) == 1


def test_insert_custom_item_uses_null_product_id(session):
    from src.backend.handle_shopping_walk import insert_custom_item
    from src.backend.initialize_database_schema import ShoppingListItem
    item = insert_custom_item(session, name="Bay leaves", category="pantry",
                              quantity=1.0, preferred_store="Sprouts")
    session.commit()
    assert item is not None
    fetched = session.query(ShoppingListItem).filter_by(name="Bay leaves").one()
    assert fetched.product_id is None
    assert fetched.category == "pantry"
    assert fetched.quantity == 1.0
    assert fetched.preferred_store == "Sprouts"
    assert fetched.source == "telegram_shopping"
    assert fetched.status == "open"


def test_top_stores_returns_up_to_3_by_purchase_count(session):
    from src.backend.handle_shopping_walk import top_stores
    from src.backend.initialize_database_schema import Store, Purchase
    from datetime import datetime
    for nm, n in [("Costco", 5), ("Sprouts", 3), ("Trader Joe's", 4), ("Walgreens", 1)]:
        s = Store(name=nm); session.add(s); session.flush()
        for _ in range(n):
            session.add(Purchase(
                store_id=s.id, total_amount=1.0,
                date=datetime.utcnow(), transaction_type="purchase",
            ))
    session.commit()
    stores = top_stores(session)
    assert stores[:3] == ["Costco", "Trader Joe's", "Sprouts"]
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "insert_recommendation or insert_custom or top_stores"`
Expected: FAIL.

- [ ] **Step 3: Implement inserts + top-stores**

Append to `src/backend/handle_shopping_walk.py`:

```python
def _active_shopping_session(session):
    """Get or create the active shopping session, handling Flask context.

    Production path is inside a Flask request context. Tests call this
    helper without one, so we push a throwaway app context just like
    fetch_recommendations does.
    """
    import flask
    from src.backend.manage_shopping_list import _ensure_current_session
    if flask.has_app_context():
        return _ensure_current_session(session)
    _ctx_app = flask.Flask("shopping_walk_ctx")
    with _ctx_app.app_context():
        return _ensure_current_session(session)


def insert_recommendation(session, *, product_id: int, name: str,
                          category: str | None, quantity: float = 1.0,
                          preferred_store: str | None = None):
    """Insert a ShoppingListItem for an existing Product. Dedups against
    existing OPEN item in the same shopping session for this product_id.
    """
    from src.backend.initialize_database_schema import ShoppingListItem
    shop_session = _active_shopping_session(session)
    existing = (
        session.query(ShoppingListItem)
        .filter_by(
            shopping_session_id=shop_session.id,
            product_id=product_id,
            status="open",
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    item = ShoppingListItem(
        shopping_session_id=shop_session.id,
        product_id=product_id,
        name=name,
        category=category,
        quantity=quantity,
        preferred_store=preferred_store,
        source="telegram_shopping",
        status="open",
    )
    session.add(item)
    session.flush()
    return item


def insert_custom_item(session, *, name: str, category: str | None,
                       quantity: float = 1.0, preferred_store: str | None = None):
    """Insert a free-text ShoppingListItem (product_id=NULL)."""
    from src.backend.initialize_database_schema import ShoppingListItem
    shop_session = _active_shopping_session(session)
    item = ShoppingListItem(
        shopping_session_id=shop_session.id,
        product_id=None,
        name=name,
        category=category,
        quantity=quantity,
        preferred_store=preferred_store,
        source="telegram_shopping",
        status="open",
    )
    session.add(item)
    session.flush()
    return item


def top_stores(session, limit: int = 3) -> list[str]:
    """Return up to `limit` most-frequent store names from purchases."""
    from src.backend.initialize_database_schema import Store, Purchase
    rows = (
        session.query(Store.name, func.count(Purchase.id))
        .join(Purchase, Purchase.store_id == Store.id)
        .filter(func.coalesce(Store.is_payment_artifact, 0) == 0)
        .group_by(Store.id, Store.name)
        .order_by(func.count(Purchase.id).desc(), Store.name.asc())
        .limit(limit)
        .all()
    )
    return [name for name, _cnt in rows]
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "insert_recommendation or insert_custom or top_stores"`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): shopping-list insert helpers + top stores"
```

---

## Task 7: Rendering helpers (category screen + nudge + summary)

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_render_category_screen_lists_categories_with_counts():
    from src.backend.handle_shopping_walk import render_category_screen
    text, kb = render_category_screen([("pantry", 5), ("fridge", 4)])
    assert "Plan shopping" in text
    btns = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert any("Pantry" in b and "5" in b for b in btns)
    assert any("Fridge" in b and "4" in b for b in btns)
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "shop:cat:pantry" in callbacks
    assert "shop:cancel" in callbacks


def test_render_nudge_has_three_buttons():
    from src.backend.handle_shopping_walk import render_nudge
    text, kb = render_nudge(rec_count=12, category_count=4)
    assert "12" in text and "4" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "nudge:shop:yes" in callbacks
    assert "nudge:shop:later" in callbacks
    assert "nudge:shop:mute" in callbacks


def test_render_resume_shows_progress():
    from src.backend.handle_shopping_walk import render_resume
    text, kb = render_resume(category="pantry", cursor=3, total=5)
    assert "progress" in text.lower()
    assert "3/5" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "shop:resume" in callbacks
    assert "shop:restart" in callbacks


def test_render_summary_shows_all_four_counts():
    from src.backend.handle_shopping_walk import render_summary
    text, kb = render_summary({
        "added": 8, "skipped": 3, "already_have": 1, "custom_added": 2,
    })
    assert "Shopping plan complete" in text
    for n in ("8", "3", "1", "2"):
        assert n in text
    callbacks = [b.get("callback_data") for row in kb["inline_keyboard"] for b in row]
    assert "inv:restart" in callbacks  # bridge to inventory walk


def test_render_summary_includes_shopping_list_url_when_env_set(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    import importlib
    import src.backend.handle_shopping_walk as m
    importlib.reload(m)
    _, kb = m.render_summary({"added": 1, "skipped": 0, "already_have": 0, "custom_added": 0})
    urls = [b.get("url") for row in kb["inline_keyboard"] for b in row]
    assert any(u and "example.test" in u for u in urls)
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "render_category_screen or render_nudge or render_resume or render_summary"`
Expected: FAIL.

- [ ] **Step 3: Implement the renderers**

Append to `src/backend/handle_shopping_walk.py`:

```python
_CATEGORY_EMOJI = {
    "pantry": "🥫", "fridge": "🥶", "freezer": "🧊", "bathroom": "🧴",
    "household": "🧹", "personal_care": "🧴", "produce": "🥦",
    "dairy": "🥛", "meat": "🥩", "snacks": "🍿", "beverages": "🥤",
    "frozen": "🧊", "bakery": "🍞", "canned": "🥫", "condiments": "🧂",
}


def _cat_emoji(category: str | None) -> str:
    return _CATEGORY_EMOJI.get((category or "").lower(), "📦")


def render_category_screen(counts: list[tuple[str, int]]) -> tuple[str, dict]:
    total = sum(n for _, n in counts)
    n_cats = len(counts)
    lines = [
        "📋 Plan shopping",
        "",
        f"{total} items recommended across {n_cats} categor"
        f"{'y' if n_cats == 1 else 'ies'}:",
    ]
    rows: list[list[dict]] = []
    pair: list[dict] = []
    for category, count in counts:
        label = f"{_cat_emoji(category)} {category.title()} · {count}"
        pair.append({"text": label, "callback_data": f"shop:cat:{category}"})
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([{"text": "Cancel", "callback_data": "shop:cancel"}])
    return "\n".join(lines), {"inline_keyboard": rows}


def render_nudge(rec_count: int, category_count: int) -> tuple[str, dict]:
    text = (
        f"📋 {rec_count} items recommended across {category_count} categories.\n"
        "Plan this week's shop?"
    )
    kb = {"inline_keyboard": [
        [{"text": "▶ Yes",     "callback_data": "nudge:shop:yes"}],
        [{"text": "⏰ Later",   "callback_data": "nudge:shop:later"}],
        [{"text": "🔕 Mute 7d", "callback_data": "nudge:shop:mute"}],
    ]}
    return text, kb


def render_resume(category: str, cursor: int, total: int) -> tuple[str, dict]:
    text = (
        "You have a shopping plan in progress.\n\n"
        f"{category.title()} · {cursor}/{total} done"
    )
    kb = {"inline_keyboard": [[
        {"text": "▶ Resume",     "callback_data": "shop:resume"},
        {"text": "↻ Start over", "callback_data": "shop:restart"},
    ]]}
    return text, kb


def render_summary(stats: dict[str, int]) -> tuple[str, dict]:
    added = stats.get("added", 0)
    skipped = stats.get("skipped", 0)
    already = stats.get("already_have", 0)
    custom = stats.get("custom_added", 0)
    text = (
        "✅ Shopping plan complete\n\n"
        f"Added:        {added}\n"
        f"Skipped:      {skipped}\n"
        f"Already had:  {already}\n"
        f"Custom added: {custom}"
    )
    rows = []
    bottom = [{"text": "📦 Inventory walk", "callback_data": "inv:restart"}]
    public_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if public_url:
        rows.append([
            {"text": "📋 View shopping list", "url": f"{public_url}/shopping/list"},
        ])
    rows.append(bottom)
    return text, {"inline_keyboard": rows}
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "render_category_screen or render_nudge or render_resume or render_summary"`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): rendering helpers — category screen, nudge, resume, summary"
```

---

## Task 8: Per-item + qty + store + category-end rendering

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_render_item_prompt_includes_progress_and_reason():
    from src.backend.handle_shopping_walk import render_item_prompt
    text, kb = render_item_prompt(
        product_name="Olive Oil",
        category="pantry",
        idx=1,
        total=5,
        reason_label="Low stock · 1 left (threshold 5)",
        stats={"added": 0, "skipped": 0, "already_have": 0, "custom_added": 0},
    )
    assert "1/5" in text
    assert "Olive Oil" in text
    assert "Low stock" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    for v in ("shop:add", "shop:add+", "shop:skip", "shop:have", "shop:done"):
        assert v in callbacks


def test_render_qty_prompt_has_1_to_5_plus_custom():
    from src.backend.handle_shopping_walk import render_qty_prompt
    text, kb = render_qty_prompt(product_name="Olive Oil")
    assert "how many" in text.lower()
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    for n in range(1, 6):
        assert f"shop:qty:{n}" in callbacks
    assert "shop:qty:cu" in callbacks
    assert "shop:back" in callbacks


def test_render_store_prompt_shows_top_stores_skip_other():
    from src.backend.handle_shopping_walk import render_store_prompt
    text, kb = render_store_prompt(
        product_name="Olive Oil", qty=3, stores=["Costco", "Sprouts", "Trader Joe's"],
    )
    assert "Olive Oil" in text
    assert "3" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "shop:store:skip" in callbacks
    assert "shop:store:costco" in callbacks
    assert "shop:store:sprouts" in callbacks
    assert "shop:store:trader_joes" in callbacks  # slugified
    assert "shop:store:other" in callbacks
    assert "shop:back" in callbacks


def test_render_store_prompt_works_when_no_stores():
    from src.backend.handle_shopping_walk import render_store_prompt
    _, kb = render_store_prompt(product_name="X", qty=1, stores=[])
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "shop:store:skip" in callbacks
    assert "shop:store:other" in callbacks


def test_render_category_end_offers_custom_next_done():
    from src.backend.handle_shopping_walk import render_category_end
    text, kb = render_category_end(
        category="pantry", next_category="fridge",
        stats={"added": 3, "skipped": 1, "already_have": 1, "custom_added": 0},
    )
    assert "Pantry" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "shop:custom" in callbacks
    assert "shop:cat_done" in callbacks
    assert "shop:done" in callbacks
    labels = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert any("Fridge" in lbl for lbl in labels)


def test_render_category_end_last_category_says_finish():
    from src.backend.handle_shopping_walk import render_category_end
    _, kb = render_category_end(category="pantry", next_category=None,
                                stats={"added": 1, "skipped": 0,
                                       "already_have": 0, "custom_added": 0})
    labels = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert any("Finish" in lbl for lbl in labels)
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "render_item_prompt or render_qty_prompt or render_store_prompt or render_category_end"`
Expected: FAIL.

- [ ] **Step 3: Implement renderers + slug helper**

Append to `src/backend/handle_shopping_walk.py`:

```python
def _slug_store(name: str) -> str:
    """URL-safe lowercase slug for callback_data."""
    out = []
    for ch in (name or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "'"):
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "store"


_QTY_BTNS = (1, 2, 3, 4, 5)


def render_item_prompt(*, product_name: str, category: str, idx: int,
                       total: int, reason_label: str,
                       stats: dict[str, int]) -> tuple[str, dict]:
    added = stats.get("added", 0)
    banner = f" (added: {added})" if added else ""
    text = (
        f"{_cat_emoji(category)} {category.title()} · {idx}/{total}{banner}\n\n"
        f"{product_name}\n"
        f"{reason_label}"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "+ Add",            "callback_data": "shop:add"},
            {"text": "+ Add w/ qty+store","callback_data": "shop:add+"},
        ],
        [
            {"text": "⏭ Skip",            "callback_data": "shop:skip"},
            {"text": "✓ Already have",    "callback_data": "shop:have"},
        ],
        [{"text": "✓ Done for now", "callback_data": "shop:done"}],
    ]}
    return text, kb


def render_qty_prompt(product_name: str) -> tuple[str, dict]:
    text = f"{product_name} — how many?"
    row1 = [{"text": str(n), "callback_data": f"shop:qty:{n}"} for n in _QTY_BTNS]
    row2 = [
        {"text": "✏ Custom qty", "callback_data": "shop:qty:cu"},
        {"text": "← Back",       "callback_data": "shop:back"},
    ]
    return text, {"inline_keyboard": [row1, row2]}


def render_store_prompt(*, product_name: str, qty: float,
                        stores: list[str]) -> tuple[str, dict]:
    text = f"{product_name} × {qty:g} — where?"
    rows = [[{"text": "⏭ Skip store", "callback_data": "shop:store:skip"}]]
    store_btns = []
    for s in stores[:3]:
        store_btns.append({
            "text": f"🛒 {s}",
            "callback_data": f"shop:store:{_slug_store(s)}",
        })
    if store_btns:
        rows.append(store_btns)
    rows.append([
        {"text": "✏ Other store", "callback_data": "shop:store:other"},
        {"text": "← Back",        "callback_data": "shop:back"},
    ])
    return text, {"inline_keyboard": rows}


def render_category_end(*, category: str, next_category: str | None,
                        stats: dict[str, int]) -> tuple[str, dict]:
    added = stats.get("added", 0)
    skipped = stats.get("skipped", 0)
    have = stats.get("already_have", 0)
    text = (
        f"{_cat_emoji(category)} {category.title()} — done.\n"
        f"Added {added} · skipped {skipped} · already had {have}\n\n"
        "Anything else?"
    )
    next_btn = (
        {"text": f"→ Next: {next_category.title()}",
         "callback_data": "shop:cat_done"}
        if next_category
        else {"text": "✓ Finish shopping plan", "callback_data": "shop:cat_done"}
    )
    kb = {"inline_keyboard": [
        [{"text": "+ Add custom item", "callback_data": "shop:custom"}],
        [next_btn, {"text": "✓ Done for now", "callback_data": "shop:done"}],
    ]}
    return text, kb


def render_custom_name_prompt() -> tuple[str, dict]:
    text = "What's the item name?\n(type and send)"
    kb = {"inline_keyboard": [[{"text": "← Cancel", "callback_data": "shop:back"}]]}
    return text, kb


def render_custom_qty_prompt(product_name: str) -> tuple[str, dict]:
    text = f"{product_name} — how many?"
    row1 = [{"text": str(n), "callback_data": f"shop:qty:{n}"} for n in _QTY_BTNS]
    row2 = [
        {"text": "✏ Custom qty", "callback_data": "shop:qty:cu"},
        {"text": "← Back",       "callback_data": "shop:back"},
    ]
    return text, {"inline_keyboard": [row1, row2]}
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v`
Expected: ALL PASS — 24 tests (10 + 4 + 4 + 5 + 1 from prior tasks; verify count locally).

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): item/qty/store/category-end + custom prompts"
```

---

## Task 9: Send wrappers + `start_walk` entry point

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_start_walk_with_no_recommendations(session, monkeypatch):
    from src.backend.handle_shopping_walk import start_walk
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [],
    )
    start_walk(session, "abc"); session.commit()
    assert sent and "Nothing to suggest" in sent[0]


def test_start_walk_with_recommendations_renders_category_screen(session, monkeypatch):
    from src.backend.handle_shopping_walk import start_walk
    from src.backend.initialize_database_schema import TelegramShoppingSession
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append((c, t, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": 1, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": 2, "product_name": "Milk", "category": "fridge",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    assert sent and "Plan shopping" in sent[0][1]
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "category"
    assert row.status == "active"
    assert row.category_queue == ["pantry", "fridge"]


def test_start_walk_offers_resume_when_active_mid_walk(session, monkeypatch):
    from src.backend.handle_shopping_walk import start_walk
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = TelegramShoppingSession(
        chat_id="abc", status="active",
        category_queue=["pantry"], current_category="pantry",
        item_queue=[{"product_id": 1, "name": "A", "category": "pantry",
                     "reason_label": "Low stock"}],
        cursor=0, pending_prompt="item",
    )
    session.add(row); session.commit()
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append((c, t, reply_markup)),
    )
    start_walk(session, "abc"); session.commit()
    assert sent and "progress" in sent[0][1].lower()
    callbacks = [b["callback_data"] for r in sent[0][2]["inline_keyboard"] for b in r]
    assert "shop:resume" in callbacks
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "start_walk"`
Expected: FAIL.

- [ ] **Step 3: Implement send wrappers + `start_walk`**

Append to `src/backend/handle_shopping_walk.py`:

```python
def send_telegram_message(chat_id: str, text: str, reply_markup: dict | None = None):
    """Thin wrapper so tests can monkeypatch this symbol in this module."""
    from src.backend.handle_telegram_messages import (
        send_telegram_message as _send,
    )
    return _send(chat_id, text, reply_markup=reply_markup)


def _edit_telegram_message(chat_id: str, message_id: int | None, text: str,
                           reply_markup: dict | None = None):
    """Thin wrapper for editMessageText so tests can monkeypatch."""
    from src.backend.handle_telegram_messages import (
        _edit_telegram_message as _edit,
    )
    return _edit(chat_id, message_id, text, reply_markup=reply_markup)


def start_walk(session, chat_id: str) -> None:
    """Entry point for /shopping. Sends category screen, resume offer, or 'nothing to suggest'."""
    row = get_or_create_session(session, chat_id)
    if abandon_if_idle(row):
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

    recs = fetch_recommendations(session)
    if not recs:
        row.status = "done"
        row.pending_prompt = None
        send_telegram_message(
            chat_id,
            "🎉 Nothing to suggest right now — shopping list looks good.",
        )
        return

    cat_queue, items_by = bucketize_by_category(recs)
    reset_for_start_over(row)
    row.category_queue = cat_queue
    # Stash items_by inside item_queue indirection: store the full structure
    # so handle_category can pop the right bucket without re-querying.
    row._items_by = items_by  # transient, not persisted
    # Persist the per-category counts in a separate way: encode as JSON in
    # item_queue is wrong (it's flat). Instead, persist a list of {category, count}
    # and let handle_category re-fetch on demand. Simpler: persist nothing here;
    # call fetch+bucketize again on category tap. Keep it simple.
    counts = [(c, len(items_by[c])) for c in cat_queue]
    text, kb = render_category_screen(counts)
    send_telegram_message(chat_id, text, reply_markup=kb)
```

NOTE: the `row._items_by` line above is a deliberate placeholder we tear down here. Replace the body of `start_walk` after `if not recs` with the simpler version below (no transient stash; we just re-fetch + re-bucketize on each category tap):

```python
    cat_queue, items_by = bucketize_by_category(recs)
    reset_for_start_over(row)
    row.category_queue = cat_queue
    counts = [(c, len(items_by[c])) for c in cat_queue]
    text, kb = render_category_screen(counts)
    send_telegram_message(chat_id, text, reply_markup=kb)
```

Use the simpler body. Do not include the `_items_by` line. (Listed above only to flag the alternative we considered and rejected — keep the implementation clean.)

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "start_walk"`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): start_walk entry point + send wrappers"
```

---

## Task 10: `handle_category` — load page, render first item

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_handle_category_loads_queue_and_renders_first_item(session, monkeypatch):
    from src.backend.handle_shopping_walk import handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.send_telegram_message",
        lambda *a, **kw: None,
    )
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": 1, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock", "current_quantity": 1.0, "threshold": 5.0},
            {"product_id": 2, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
            {"product_id": 3, "product_name": "Milk", "category": "fridge",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()

    handle_category(session, "abc", category="pantry", message_id=100)
    session.commit()

    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.current_category == "pantry"
    assert row.pending_prompt == "item"
    assert row.cursor == 0
    assert len(row.item_queue) == 2  # two pantry items
    # remaining category_queue should NOT include pantry anymore
    assert "pantry" not in row.category_queue
    assert "fridge" in row.category_queue
    last_text = edits[-1][2]
    assert "1/2" in last_text
    assert "Olive oil" in last_text
    assert row.stats == {"added": 0, "skipped": 0, "already_have": 0, "custom_added": 0}
```

- [ ] **Step 2: Run test — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_category"`
Expected: FAIL.

- [ ] **Step 3: Implement `_render_current_item` + `handle_category`**

Append to `src/backend/handle_shopping_walk.py`:

```python
def _render_current_item(row, message_id: int | None) -> None:
    if row.cursor >= len(row.item_queue):
        return  # caller handles end-of-page
    item = row.item_queue[row.cursor]
    text, kb = render_item_prompt(
        product_name=item.get("name", "Item"),
        category=row.current_category or "other",
        idx=row.cursor + 1,
        total=len(row.item_queue),
        reason_label=item.get("reason_label") or "Suggested",
        stats=row.stats or {},
    )
    row.pending_prompt = "item"
    row.last_item_id = item.get("product_id")
    _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)


def handle_category(session, chat_id: str, category: str,
                    message_id: int | None) -> None:
    """User picked a category — load that bucket, render first item."""
    row = get_or_create_session(session, chat_id)
    if not category:
        row.pending_prompt = "category"
        return

    recs = fetch_recommendations(session)
    _, items_by = bucketize_by_category(recs)
    bucket = items_by.get(category, [])

    row.current_category = category
    row.item_queue = bucket
    row.cursor = 0
    row.stats = {"added": 0, "skipped": 0, "already_have": 0, "custom_added": 0}
    # Remove this category from the queue (it's now in-flight).
    row.category_queue = [c for c in (row.category_queue or []) if c != category]

    if not row.item_queue:
        send_telegram_message(chat_id, f"No recommendations in {category}.")
        row.pending_prompt = "category"
        return

    _render_current_item(row, message_id)
```

- [ ] **Step 4: Run test**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_category"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): handle_category — load bucket + render first item"
```

---

## Plan continuation in Part 2

This is the end of Part 1 (Tasks 1–10). Continue in:

**`docs/superpowers/plans/2026-05-14-telegram-shopping-walk-part2.md`** for Tasks 11–20:

- Task 11: `handle_add` (quick add, qty=1)
- Task 12: `handle_add_detailed` + `handle_qty` (qty sub-prompt)
- Task 13: `handle_store` + advance/end (store sub-prompt, insert with qty+store)
- Task 14: `handle_skip` / `handle_have` / `handle_done`
- Task 15: `handle_cat_done` + category-end transitions
- Task 16: `handle_custom` (custom-name + custom-qty + custom-store sub-flow)
- Task 17: `handle_back` / `handle_cancel` / `handle_resume` / `handle_restart`
- Task 18: Top-level `dispatch_shop_callback` + idle + stale-verb guard + typed-text consumer
- Task 19: Webhook routing extension (`/shopping` command + `shop:*` + `nudge:shop:*` + typed-text states)
- Task 20: Nudge job (`shopping_nudge_job.py`) + APScheduler registration + E2E test + full suite

The next plan file should include the full code for each handler — DO NOT abbreviate. Use the spec sections 6 (state machine), 7 (UI copy), 8 (nudge) as the authoritative source for transitions and copy.

---

## Self-Review notes (Part 1)

**Spec coverage so far:**
- §5 schema → Tasks 1, 2 ✅
- §3 env flags → Task 3 ✅
- §5 invariants (idle, reset preserves nudge prefs) → Task 4 ✅
- §5 recommendation source + category ordering → Task 5 ✅
- §5 inventory writes (insert + dedup) → Task 6 ✅
- §7 UI copy (category, nudge, resume, summary) → Task 7 ✅
- §7 UI copy (item, qty, store, category-end, custom) → Task 8 ✅
- §4 entry point + resume → Task 9 ✅
- §6 state machine CATEGORY → ITEM transition → Task 10 ✅

**Remaining (Part 2):** all per-button handlers, dispatch + stale guard, webhook routing, nudge job, APScheduler, E2E.

**Placeholder scan:** None found in Part 1 — every step has concrete code or commands.

**Type consistency:**
- `pending_prompt` values used: `category`, `item`, `qty`, `store`, `custom_name`, `custom_qty`, `custom_store`, `category_end`, `resume`, `None`. Matches spec section 5 + 6.
- Stats dict keys: `added`, `skipped`, `already_have`, `custom_added`. Matches spec.
- Function names: `start_walk`, `handle_category`, `fetch_recommendations`, `bucketize_by_category`, `insert_recommendation`, `insert_custom_item`, `top_stores`, `render_*`, `get_or_create_session`, `reset_for_start_over`, `abandon_if_idle`. Consistent across all task references.
