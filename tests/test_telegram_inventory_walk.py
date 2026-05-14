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
    assert callable(m._bool_env)
    monkeypatch.setenv("FOO", "true")
    assert m._bool_env("FOO") is True
    monkeypatch.setenv("FOO", "0")
    assert m._bool_env("FOO") is False
    monkeypatch.delenv("FOO", raising=False)
    assert m._bool_env("FOO", default=True) is True


def _seed_inventory(session, *, days_old_pairs):
    """days_old_pairs: list[(product_name, category, days_old)].

    Creates a Product + Inventory row per tuple, with `last_updated`
    set to `now - days_old` days. Marks all rows is_active_window=True.
    """
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
        ("Olive oil",   "pantry", 20),  # stale
        ("Black pepper","pantry", 30),  # stale
        ("Milk",        "fridge", 15),  # stale
        ("Fresh bread", "pantry",  2),  # NOT stale (under 14-day threshold)
    ])
    counts = categories_with_stale_counts(session)
    assert counts == [("pantry", 2), ("fridge", 1)]


def test_categories_with_stale_counts_ignores_inactive_rows(session):
    from datetime import timedelta
    from src.backend.handle_inventory_walk import categories_with_stale_counts
    from src.backend.initialize_database_schema import Product, Inventory, utcnow
    p = Product(name="Ghost", category="pantry")
    session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=0, is_active_window=False)
    inv.last_updated = utcnow() - timedelta(days=99)
    session.add(inv); session.commit()
    assert categories_with_stale_counts(session) == []


def test_categories_with_stale_counts_normalizes_null_and_case(session):
    """NULL category and mixed-case duplicates both map to a single bucket."""
    from datetime import timedelta
    from src.backend.handle_inventory_walk import (
        categories_with_stale_counts, stale_items_in_category,
    )
    from src.backend.initialize_database_schema import Product, Inventory, utcnow

    # Three stale rows: NULL category, literal "other", literal "Other".
    # All three should collapse into one bucket keyed as "other".
    for name, category in [("A", None), ("B", "other"), ("C", "Other")]:
        p = Product(name=name, category=category)
        session.add(p); session.flush()
        inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
        inv.last_updated = utcnow() - timedelta(days=30)
        session.add(inv)
    session.commit()

    counts = categories_with_stale_counts(session)
    assert counts == [("other", 3)]
    # And stale_items_in_category finds all three via the same normalized key.
    items = stale_items_in_category(session, "other", page=1)
    assert len(items) == 3


def test_stale_items_in_category_empty_inputs(session):
    """category=None or unknown category returns empty list cleanly (no crash)."""
    from src.backend.handle_inventory_walk import stale_items_in_category
    assert stale_items_in_category(session, None) == []
    assert stale_items_in_category(session, "") == []
    assert stale_items_in_category(session, "nonexistent") == []


def test_stale_items_in_category_returns_ordered_page(session):
    from src.backend.handle_inventory_walk import stale_items_in_category
    _seed_inventory(session, days_old_pairs=[
        (f"Item {i}", "pantry", 14 + i) for i in range(12)
    ])
    page1 = stale_items_in_category(session, "pantry", page=1)
    page2 = stale_items_in_category(session, "pantry", page=2)
    assert len(page1) == 10
    assert len(page2) == 2
    # oldest first — Item 11 has the most days_old (14 + 11 = 25 days)
    assert page1[0].product.name == "Item 11"


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
    from datetime import timedelta
    from src.backend.handle_inventory_walk import reset_for_start_over
    from src.backend.initialize_database_schema import TelegramInventorySession
    nudge_until = datetime.utcnow() + timedelta(days=7)
    row = TelegramInventorySession(
        chat_id="abc",
        status="done",
        current_category="pantry",
        item_queue=[1, 2, 3],
        cursor=2,
        page=2,
        stats={"updated": 5},
        nudge_muted_until=nudge_until,
    )
    session.add(row); session.commit()

    reset_for_start_over(row)
    session.commit()

    assert row.status == "active"
    assert row.current_category is None
    assert row.item_queue == []
    assert row.cursor == 0
    assert row.page == 1
    assert row.pending_prompt == "category"
    assert row.stats == {}
    assert row.last_item_id is None
    assert row.nudge_muted_until == nudge_until  # preserved


def test_abandon_if_idle_marks_status(session):
    from datetime import timedelta
    from src.backend.handle_inventory_walk import abandon_if_idle
    from src.backend.initialize_database_schema import TelegramInventorySession
    row = TelegramInventorySession(chat_id="abc", status="active")
    session.add(row); session.commit()
    row.last_action_at = datetime.utcnow() - timedelta(minutes=45)
    session.commit()

    assert abandon_if_idle(row) is True
    assert row.status == "abandoned"


def test_abandon_if_idle_leaves_fresh_session_alone(session):
    from src.backend.handle_inventory_walk import abandon_if_idle
    from src.backend.initialize_database_schema import TelegramInventorySession
    row = TelegramInventorySession(chat_id="abc", status="active")
    session.add(row); session.commit()
    assert abandon_if_idle(row) is False
    assert row.status == "active"


@pytest.mark.parametrize("level_idx,expected_pct,expected_low", [
    (0, 1.0,  True),
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

    result = apply_level(session, inv.id, level_idx, user_id=None)
    session.commit()

    assert result is not None
    session.refresh(inv)
    assert inv.consumed_pct_override == expected_pct
    assert inv.manual_low is expected_low

    adj = session.query(InventoryAdjustment).filter_by(product_id=p.id).all()
    assert len(adj) == 1
    assert adj[0].reason == "telegram_walk"


def test_apply_level_invalid_idx_raises(session):
    from src.backend.handle_inventory_walk import apply_level
    from src.backend.initialize_database_schema import Product, Inventory
    p = Product(name="Olive oil", category="pantry")
    session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=1.0); session.add(inv); session.commit()
    with pytest.raises(ValueError):
        apply_level(session, inv.id, 9, user_id=None)


def test_apply_level_vanished_inventory_returns_none(session):
    from src.backend.handle_inventory_walk import apply_level
    assert apply_level(session, 99999, 0, user_id=None) is None


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


def test_mark_no_longer_have_vanished_inventory_returns_none(session):
    from src.backend.handle_inventory_walk import mark_no_longer_have
    assert mark_no_longer_have(session, 99999, user_id=None) is None


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
    assert fetched[0].status == "open"
    assert fetched[0].shopping_session_id is not None


def test_add_empty_to_shopping_list_dedups_existing_open_item(session):
    """Second call for the same inventory must not create a duplicate row."""
    from src.backend.handle_inventory_walk import add_empty_to_shopping_list
    from src.backend.initialize_database_schema import (
        Product, Inventory, ShoppingListItem,
    )
    p = Product(name="Olive oil", category="pantry")
    session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=0, manual_low=True)
    session.add(inv); session.commit()

    first = add_empty_to_shopping_list(session, inv.id); session.commit()
    second = add_empty_to_shopping_list(session, inv.id); session.commit()

    assert first is not None and second is not None
    assert first.id == second.id, "dedup should return the same row"
    items = session.query(ShoppingListItem).filter_by(
        product_id=p.id, status="open",
    ).all()
    assert len(items) == 1
