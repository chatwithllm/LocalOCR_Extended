"""Tests for the daily inventory nudge job."""
import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")


@pytest.fixture
def session(tmp_path):
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    db = tmp_path / "n.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    SessionFactory = create_session_factory(eng)
    s = SessionFactory()
    yield s
    s.close()


def _seed_stale_for_chat(session, chat_id: str, n_stale: int):
    """Drop a TelegramReceipt row so the chat is in the allowlist, plus N stale items."""
    from src.backend.initialize_database_schema import (
        Product, Inventory, TelegramReceipt, utcnow,
    )
    session.add(TelegramReceipt(
        telegram_user_id=chat_id, message_id="m1", image_path="/tmp/x", status="processed",
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
    _seed_stale_for_chat(session, "abc", n_stale=2)  # < 3
    assert "abc" not in eligible_chat_ids(session)


def test_eligibility_includes_chat_with_3plus_stale(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    _seed_stale_for_chat(session, "abc", n_stale=3)
    assert "abc" in eligible_chat_ids(session)


def test_eligibility_skips_muted_chat(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_stale_for_chat(session, "abc", n_stale=5)
    session.add(TelegramInventorySession(
        chat_id="abc", status="done",
        nudge_muted_until=datetime.utcnow() + timedelta(days=2),
    ))
    session.commit()
    assert "abc" not in eligible_chat_ids(session)


def test_eligibility_skips_recently_nudged(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_stale_for_chat(session, "abc", n_stale=5)
    session.add(TelegramInventorySession(
        chat_id="abc", status="done",
        last_nudge_sent_at=datetime.utcnow() - timedelta(days=2),
    ))
    session.commit()
    assert "abc" not in eligible_chat_ids(session)


def test_eligibility_skips_chat_with_active_session(session):
    from src.backend.inventory_nudge_job import eligible_chat_ids
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_stale_for_chat(session, "abc", n_stale=5)
    session.add(TelegramInventorySession(
        chat_id="abc", status="active",
        current_category="pantry", item_queue=[1, 2], cursor=0, pending_prompt="level",
    ))
    session.commit()
    assert "abc" not in eligible_chat_ids(session)


def test_run_daily_nudge_sends_and_records(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_stale_for_chat(session, "abc", n_stale=5)
    sent = []
    monkeypatch.setenv("INVENTORY_NUDGES_ENABLED", "1")
    import importlib
    import src.backend.inventory_nudge_job as m
    importlib.reload(m)
    monkeypatch.setattr(
        "src.backend.inventory_nudge_job.send_telegram_message",
        lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)),
    )

    m.run_daily_nudge(session); session.commit()
    assert len(sent) == 1
    assert sent[0][0] == "abc"
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.last_nudge_sent_at is not None


def test_run_daily_nudge_respects_disable_flag(session, monkeypatch):
    _seed_stale_for_chat(session, "abc", n_stale=5)
    sent = []
    monkeypatch.setenv("INVENTORY_NUDGES_ENABLED", "0")
    import importlib
    import src.backend.inventory_nudge_job as m
    importlib.reload(m)
    monkeypatch.setattr(
        "src.backend.inventory_nudge_job.send_telegram_message",
        lambda chat_id, text, reply_markup=None: sent.append(chat_id),
    )

    m.run_daily_nudge(session); session.commit()
    assert sent == []


def test_run_daily_nudge_telegram_failure_does_not_record(session, monkeypatch):
    """If send raises, last_nudge_sent_at must not be set so next run retries."""
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_stale_for_chat(session, "abc", n_stale=5)
    monkeypatch.setenv("INVENTORY_NUDGES_ENABLED", "1")
    import importlib
    import src.backend.inventory_nudge_job as m
    importlib.reload(m)
    def _boom(*a, **kw):
        raise RuntimeError("telegram down")
    monkeypatch.setattr(
        "src.backend.inventory_nudge_job.send_telegram_message", _boom,
    )
    m.run_daily_nudge(session); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one_or_none()
    assert row is None or row.last_nudge_sent_at is None


def test_nudge_mute_callback_sets_7_day_mute(session, monkeypatch):
    from src.backend.handle_inventory_walk import dispatch_nudge_callback
    from src.backend.initialize_database_schema import TelegramInventorySession
    session.add(TelegramInventorySession(chat_id="abc", status="done"))
    session.commit()
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )

    dispatch_nudge_callback(session, "abc", "nudge:mute", message_id=100)
    session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.nudge_muted_until is not None
    now = datetime.utcnow()
    assert row.nudge_muted_until > now + timedelta(days=6)
    assert row.nudge_muted_until < now + timedelta(days=8)


def test_nudge_later_callback_sets_3_day_mute(session, monkeypatch):
    from src.backend.handle_inventory_walk import dispatch_nudge_callback
    from src.backend.initialize_database_schema import TelegramInventorySession
    session.add(TelegramInventorySession(chat_id="abc", status="done"))
    session.commit()
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )

    dispatch_nudge_callback(session, "abc", "nudge:later", message_id=100)
    session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.nudge_muted_until is not None
    now = datetime.utcnow()
    assert row.nudge_muted_until > now + timedelta(days=2)
    assert row.nudge_muted_until < now + timedelta(days=4)
