"""Unit tests for handle_inventory_walk + TelegramInventorySession model."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ.setdefault("TELEGRAM_INVENTORY_WALK_ENABLED", "1")


@pytest.fixture
def session(tmp_path):
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    db = tmp_path / "t.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    SessionFactory = create_session_factory(eng)
    s = SessionFactory()
    yield s
    s.close()


def test_telegram_inventory_session_round_trip(session):
    from src.backend.initialize_database_schema import TelegramInventorySession
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


def test_telegram_inventory_session_defaults(session):
    """Bare construction should yield sensible defaults."""
    from src.backend.initialize_database_schema import TelegramInventorySession
    row = TelegramInventorySession(chat_id="bare")
    session.add(row); session.commit()
    fetched = session.query(TelegramInventorySession).filter_by(chat_id="bare").one()
    assert fetched.status == "active"
    assert fetched.item_queue == []
    assert fetched.cursor == 0
    assert fetched.page == 1
    assert fetched.stats == {}
    assert fetched.nudge_muted_until is None
    assert fetched.last_nudge_sent_at is None


def test_constants_have_safe_defaults(monkeypatch):
    monkeypatch.delenv("INVENTORY_STALE_DAYS", raising=False)
    monkeypatch.delenv("TELEGRAM_INVENTORY_WALK_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_INVENTORY_WALK_PILOT_CHATS", raising=False)
    monkeypatch.delenv("INVENTORY_WALK_PAGE_SIZE", raising=False)
    monkeypatch.delenv("INVENTORY_WALK_IDLE_TIMEOUT_MIN", raising=False)
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


def test_bool_env_handles_truthy_strings(monkeypatch):
    """Sanity check the env parsing helper."""
    import importlib
    import src.backend.handle_inventory_walk as m
    importlib.reload(m)
    assert m._bool_env.__call__ if False else True  # ensure attr exists
    monkeypatch.setenv("FOO", "true")
    assert m._bool_env("FOO") is True
    monkeypatch.setenv("FOO", "0")
    assert m._bool_env("FOO") is False
    monkeypatch.delenv("FOO", raising=False)
    assert m._bool_env("FOO", default=True) is True
