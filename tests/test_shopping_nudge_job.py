"""Tests for the daily shopping nudge job."""
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


def _seed_chat_with_recs(session, chat_id, n_recs):
    from src.backend.initialize_database_schema import (
        Product, Inventory, TelegramReceipt,
    )
    session.add(TelegramReceipt(
        telegram_user_id=chat_id, message_id="m1", image_path="/tmp/x", status="processed",
    ))
    # Use distinct single-token product names so the recommendation engine's
    # family-grouping pass doesn't collapse them into a single bucket. Digits are
    # stripped by [a-z]+ when computing the family key, so each name needs its
    # own unique alphabetic stem.
    distinct_words = [
        "olives", "pepper", "milk", "bread", "rice", "pasta",
        "sugar", "salt", "butter", "cheese", "yogurt", "honey",
        "flour", "vinegar", "tea",
    ]
    assert n_recs <= len(distinct_words), "extend distinct_words for larger seeds"
    for i in range(n_recs):
        p = Product(name=distinct_words[i], category="pantry")
        session.add(p); session.flush()
        inv = Inventory(product_id=p.id, quantity=0.0, manual_low=True, is_active_window=True)
        session.add(inv)
    session.commit()


def test_eligibility_skips_under_threshold(session, monkeypatch):
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=5)
    assert "abc" not in m.eligible_chat_ids(session)


def test_eligibility_includes_chat_with_8plus_recs(session, monkeypatch):
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    assert "abc" in m.eligible_chat_ids(session)


def test_eligibility_skips_muted_chat(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    session.add(TelegramShoppingSession(
        chat_id="abc", status="done",
        nudge_muted_until=datetime.utcnow() + timedelta(days=2),
    ))
    session.commit()
    assert "abc" not in m.eligible_chat_ids(session)


def test_eligibility_skips_recently_nudged(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    monkeypatch.setenv("SHOPPING_NUDGE_GAP_DAYS", "3")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    session.add(TelegramShoppingSession(
        chat_id="abc", status="done",
        last_nudge_sent_at=datetime.utcnow() - timedelta(days=2),
    ))
    session.commit()
    assert "abc" not in m.eligible_chat_ids(session)


def test_eligibility_skips_chat_with_active_walk(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    session.add(TelegramShoppingSession(
        chat_id="abc", status="active",
        category_queue=["pantry"], current_category="pantry",
        item_queue=[{"product_id": 1}], cursor=0, pending_prompt="item",
    ))
    session.commit()
    assert "abc" not in m.eligible_chat_ids(session)


def test_run_daily_shopping_nudge_sends_and_records(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("SHOPPING_NUDGE_ENABLED", "1")
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    sent = []
    monkeypatch.setattr(
        "src.backend.shopping_nudge_job.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append((c, t)),
    )

    m.run_daily_shopping_nudge(session); session.commit()
    assert len(sent) == 1
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.last_nudge_sent_at is not None


def test_run_daily_shopping_nudge_respects_disable_flag(session, monkeypatch):
    monkeypatch.setenv("SHOPPING_NUDGE_ENABLED", "0")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    sent = []
    monkeypatch.setattr(
        "src.backend.shopping_nudge_job.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(c),
    )
    m.run_daily_shopping_nudge(session); session.commit()
    assert sent == []


def test_register_daily_shopping_nudge_job_when_enabled(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    monkeypatch.setenv("SHOPPING_NUDGE_ENABLED", "1")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    sched = BackgroundScheduler()
    m.register_daily_shopping_nudge_job(sched)
    jobs = sched.get_jobs()
    assert any(j.id == "shopping_daily_nudge" for j in jobs)


def test_register_skips_when_disabled(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    monkeypatch.setenv("SHOPPING_NUDGE_ENABLED", "0")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    sched = BackgroundScheduler()
    m.register_daily_shopping_nudge_job(sched)
    jobs = sched.get_jobs()
    assert not any(j.id == "shopping_daily_nudge" for j in jobs)


def test_eligibility_respects_walk_enabled_gate(session, monkeypatch):
    """If is_walk_enabled returns False for a chat, nudge job must skip it."""
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_PILOT_CHATS", "999")
    import importlib
    import src.backend.handle_shopping_walk as walk_mod
    importlib.reload(walk_mod)
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    assert "abc" not in m.eligible_chat_ids(session)
