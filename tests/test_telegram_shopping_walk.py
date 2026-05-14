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
