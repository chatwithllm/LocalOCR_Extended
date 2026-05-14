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
