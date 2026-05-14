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


def test_render_category_screen_shows_counts():
    from src.backend.handle_inventory_walk import render_category_screen
    text, kb = render_category_screen([("pantry", 8), ("fridge", 4)])
    assert "Update inventory" in text
    btns = [b["text"] for row in kb["inline_keyboard"] for b in row]
    assert any("Pantry" in b and "8" in b for b in btns)
    assert any("Fridge" in b and "4" in b for b in btns)
    assert any("Cancel" in b for b in btns)
    # Cancel callback present
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "inv:cancel" in callbacks
    assert "inv:cat:pantry" in callbacks


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
    # Level callbacks
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    for i in range(5):
        assert f"inv:lvl:{i}" in callbacks
    assert "inv:skip" in callbacks
    assert "inv:nohave" in callbacks
    assert "inv:done" in callbacks


def test_render_level_prompt_days_phrasing():
    from src.backend.handle_inventory_walk import render_level_prompt
    text_short, _ = render_level_prompt(
        product_name="X", category="pantry", idx=1, total=1, days_old=14,
    )
    text_long, _ = render_level_prompt(
        product_name="X", category="pantry", idx=1, total=1, days_old=75,
    )
    assert "14 days ago" in text_short
    assert "2+ months ago" in text_long


def test_render_cart_prompt_has_three_buttons():
    from src.backend.handle_inventory_walk import render_cart_prompt
    text, kb = render_cart_prompt("Olive oil")
    assert "Olive oil" in text
    assert "Add to shopping list" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "inv:cart:y" in callbacks
    assert "inv:cart:n" in callbacks
    assert "inv:cart:a" in callbacks


def test_render_continue_shows_remaining_and_buttons():
    from src.backend.handle_inventory_walk import render_continue
    text, kb = render_continue("pantry", done=10, remaining=13)
    assert "10" in text
    assert "13" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "inv:cont" in callbacks
    assert "inv:done" in callbacks


def test_render_summary_shows_stats(monkeypatch):
    # Hermetic: .env may have set PUBLIC_BASE_URL during the test session.
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    from src.backend.handle_inventory_walk import render_summary
    text, kb = render_summary(
        category="pantry",
        stats={"updated": 6, "skipped": 1, "removed": 1, "cart_added": 2},
    )
    assert "Walk complete" in text
    assert "6" in text
    assert "Skipped" in text and "1" in text
    assert "Removed" in text
    assert "shopping list" in text.lower()
    # Always-on Another Category button
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "inv:restart" in callbacks


def test_render_summary_includes_url_when_public_base_url_set(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    import importlib
    import src.backend.handle_inventory_walk as m
    importlib.reload(m)
    text, kb = m.render_summary("pantry", {"updated": 1, "skipped": 0, "removed": 0, "cart_added": 0})
    urls = [b.get("url") for row in kb["inline_keyboard"] for b in row]
    assert any(u and "example.test" in u for u in urls)


def test_render_resume_shows_progress():
    from src.backend.handle_inventory_walk import render_resume
    text, kb = render_resume(category="pantry", cursor=3, total=8)
    assert "progress" in text.lower()
    assert "3/8" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "inv:resume" in callbacks
    assert "inv:restart" in callbacks


def test_render_nudge_has_yes_later_mute():
    from src.backend.handle_inventory_walk import render_nudge
    text, kb = render_nudge(8)
    assert "8" in text
    assert "weeks" in text.lower() or "2+" in text
    callbacks = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert "nudge:yes" in callbacks
    assert "nudge:later" in callbacks
    assert "nudge:mute" in callbacks


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
        ("Milk",        "fridge", 20),
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


def test_handle_category_loads_queue_and_renders_level(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil",   "pantry", 20),
        ("Black pepper","pantry", 30),
        ("Milk",         "fridge", 20),
    ])
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda chat_id, message_id, text, reply_markup=None:
            edits.append((chat_id, message_id, text, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )
    # Set state to "category" first by running start_walk.
    start_walk(session, "abc"); session.commit()

    handle_category(session, "abc", category="pantry", message_id=100)
    session.commit()

    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.current_category == "pantry"
    assert row.pending_prompt == "level"
    assert row.cursor == 0
    assert row.page == 1
    assert len(row.item_queue) == 2  # two pantry items
    assert row.stats == {"updated": 0, "skipped": 0, "removed": 0, "cart_added": 0}
    assert edits, "should edit category message to level prompt"
    last_text = edits[-1][2]
    assert "1/2" in last_text
    assert "Black pepper" in last_text  # oldest first (30 days > 20 days)


def test_handle_category_empty_category_keeps_state_and_replies(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    # No seeds — the category has no stale items.
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda chat_id, text, reply_markup=None: sent.append(text),
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )

    handle_category(session, "abc", category="pantry", message_id=100)
    session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "category"  # stays so user can pick another
    assert any("No stale" in t or "no stale" in t.lower() for t in sent)


def test_handle_level_full_advances_to_next_item(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_level, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",     "pantry", 30),
    ])
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_level(session, "abc", level_idx=4, message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["updated"] == 1
    # next item rendered with 2/2
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
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_level(session, "abc", level_idx=0, message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "cart"
    assert row.stats["updated"] == 1
    last_kb = edits[-1][3]
    callbacks = [b["callback_data"] for r in last_kb["inline_keyboard"] for b in r]
    assert "inv:cart:y" in callbacks


def test_handle_level_last_item_in_last_page_ends_walk(session, monkeypatch):
    """When level button is pressed on the last item and no more pages remain → end walk."""
    from src.backend.handle_inventory_walk import handle_level, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[("Only one", "pantry", 25)])
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_level(session, "abc", level_idx=4, message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.status == "done"
    assert any("Walk complete" in e[2] for e in edits)


def test_handle_cart_yes_inserts_shopping_list_item(session, monkeypatch):
    from src.backend.handle_inventory_walk import (
        handle_cart, handle_level, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramInventorySession, ShoppingListItem,
    )
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",     "pantry", 30),
    ])
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_level(session, "abc", 0, message_id=100); session.commit()  # Empty → cart prompt

    handle_cart(session, "abc", "y", message_id=100); session.commit()

    items = session.query(ShoppingListItem).all()
    assert len(items) == 1
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.stats["cart_added"] == 1
    assert row.pending_prompt == "level"  # advanced to next item
    assert row.cursor == 1


def test_handle_cart_no_does_not_insert(session, monkeypatch):
    from src.backend.handle_inventory_walk import (
        handle_cart, handle_level, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import ShoppingListItem
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",     "pantry", 30),
    ])
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_level(session, "abc", 0, message_id=100); session.commit()

    handle_cart(session, "abc", "n", message_id=100); session.commit()
    assert session.query(ShoppingListItem).count() == 0


def test_handle_cart_already_does_not_insert(session, monkeypatch):
    from src.backend.handle_inventory_walk import (
        handle_cart, handle_level, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import ShoppingListItem
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",     "pantry", 30),
    ])
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda *a, **kw: None,
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_level(session, "abc", 0, message_id=100); session.commit()

    handle_cart(session, "abc", "a", message_id=100); session.commit()
    assert session.query(ShoppingListItem).count() == 0


def test_handle_skip_advances_without_write(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_skip, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession, Inventory
    _seed_inventory(session, days_old_pairs=[
        ("Olive oil", "pantry", 20),
        ("Pepper",     "pantry", 30),
    ])
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row_before = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    inv_id = row_before.item_queue[0]

    handle_skip(session, "abc", message_id=100); session.commit()

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
        ("Pepper",     "pantry", 30),
    ])
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row_before = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    inv_id = row_before.item_queue[0]

    handle_nohave(session, "abc", message_id=100); session.commit()

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
        ("Pepper",     "pantry", 30),
    ])
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_done(session, "abc", message_id=100); session.commit()

    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.status == "done"
    assert any("Walk complete" in t for t in edits)


def test_handle_continue_loads_next_page(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_continue, handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[
        (f"Item {i}", "pantry", 14 + i) for i in range(12)
    ])
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    # simulate finishing page 1
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    row.cursor = 10
    row.pending_prompt = "continue"
    session.commit()

    handle_continue(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.page == 2
    assert row.cursor == 0
    assert len(row.item_queue) == 2
    assert row.pending_prompt == "level"


def test_handle_cancel_marks_abandoned(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_cancel, start_walk
    from src.backend.initialize_database_schema import TelegramInventorySession
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()

    handle_cancel(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.status == "abandoned"
    assert any("ancel" in t for t in edits)


def test_handle_resume_re_renders_current_prompt(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_resume
    from src.backend.initialize_database_schema import (
        TelegramInventorySession, Product, Inventory,
    )
    from src.backend.initialize_database_schema import utcnow as schema_utcnow
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
    inv.last_updated = schema_utcnow() - timedelta(days=30)
    session.add(inv); session.commit()

    row = TelegramInventorySession(
        chat_id="abc", status="active", current_category="pantry",
        item_queue=[inv.id], cursor=0, pending_prompt="resume",
    )
    session.add(row); session.commit()
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda *a, **kw: None)

    handle_resume(session, "abc", message_id=100); session.commit()
    assert any("Olive oil" in t for t in edits)
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "level"


def test_handle_restart_resets_and_shows_categories(session, monkeypatch):
    from src.backend.handle_inventory_walk import handle_restart
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[("Olive oil", "pantry", 30)])
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda *a, **kw: None)
    row = TelegramInventorySession(
        chat_id="abc", status="active", current_category="pantry",
        item_queue=[1, 2], cursor=1, pending_prompt="level",
    )
    session.add(row); session.commit()

    handle_restart(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.cursor == 0
    assert row.current_category is None
    assert row.pending_prompt == "category"
    assert any("Update inventory" in t for t in edits)


def test_dispatch_rejects_stale_verb_and_rerenders(session, monkeypatch):
    from src.backend.handle_inventory_walk import (
        dispatch_inv_callback, handle_category, start_walk,
    )
    _seed_inventory(session, days_old_pairs=[("Olive oil", "pantry", 30)])
    sent = []
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    # pending_prompt is now 'level'. Sending a cart verb should be rejected.

    dispatch_inv_callback(session, "abc", "inv:cart:y", message_id=100); session.commit()
    # Stale-message + re-rendered level prompt should appear.
    combined = " ".join(edits) + " " + " ".join(sent)
    assert "stale" in combined.lower()
    assert "Olive oil" in combined


def test_dispatch_idle_session_auto_abandons(session, monkeypatch):
    from datetime import timedelta
    from src.backend.handle_inventory_walk import dispatch_inv_callback
    from src.backend.initialize_database_schema import TelegramInventorySession
    row = TelegramInventorySession(
        chat_id="abc", status="active",
        current_category="pantry", item_queue=[1], cursor=0,
        pending_prompt="level",
    )
    session.add(row); session.commit()
    row.last_action_at = datetime.utcnow() - timedelta(minutes=60)
    session.commit()
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )

    dispatch_inv_callback(session, "abc", "inv:lvl:4", message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.status == "abandoned"
    assert any("timed out" in t.lower() for t in sent)


def test_dispatch_correct_verb_routes_to_handler(session, monkeypatch):
    """Sanity: a well-formed callback fires the right handler."""
    from src.backend.handle_inventory_walk import (
        dispatch_inv_callback, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[("Olive oil", "pantry", 30)])
    monkeypatch.setattr("src.backend.handle_inventory_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_inventory_walk.send_telegram_message",
                        lambda *a, **kw: None)
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    # pending_prompt == 'level' now; route a valid skip verb.

    dispatch_inv_callback(session, "abc", "inv:skip", message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.stats["skipped"] == 1


def test_dispatch_restart_from_summary_works(session, monkeypatch):
    """Bug regression: tapping 'Another category' on the summary screen must
    route to handle_restart, not the stale-verb branch."""
    from src.backend.handle_inventory_walk import (
        dispatch_inv_callback, handle_done, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import TelegramInventorySession
    _seed_inventory(session, days_old_pairs=[("Olive oil", "pantry", 30)])
    sent = []
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    # Drive to end-of-walk state.
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_done(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.status == "done"
    assert row.pending_prompt is None

    # Tap "Another category" — should reset + show category screen, NOT show "stale".
    dispatch_inv_callback(session, "abc", "inv:restart", message_id=100); session.commit()

    combined = " ".join(edits + sent)
    # The stale-verb guard message would be "That button is stale."
    assert "That button is stale" not in combined
    assert "Update inventory" in combined
    row = session.query(TelegramInventorySession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "category"


def test_rerender_handles_resume_state(session, monkeypatch):
    """A stale verb while in pending_prompt='resume' should re-render the resume offer."""
    from src.backend.handle_inventory_walk import dispatch_inv_callback
    from src.backend.initialize_database_schema import (
        TelegramInventorySession, Product, Inventory,
    )
    from src.backend.initialize_database_schema import utcnow as schema_utcnow
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
    inv.last_updated = schema_utcnow() - timedelta(days=30)
    session.add(inv); session.commit()

    row = TelegramInventorySession(
        chat_id="abc", status="active", current_category="pantry",
        item_queue=[inv.id], cursor=0, pending_prompt="resume",
    )
    session.add(row); session.commit()

    sent = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk._edit_telegram_message",
        lambda *a, **kw: None,
    )

    # Send a stale verb (e.g., inv:lvl:0) while in resume state.
    dispatch_inv_callback(session, "abc", "inv:lvl:0", message_id=100); session.commit()
    assert any("progress" in t.lower() for t in sent), "should re-render the resume offer"


def test_webhook_inventory_command_starts_walk(session, monkeypatch):
    """Posting /inventory via the webhook command path dispatches start_walk."""
    import flask
    from src.backend.handle_telegram_messages import _handle_command
    monkeypatch.setenv("TELEGRAM_INVENTORY_WALK_ENABLED", "1")
    import importlib
    import src.backend.handle_inventory_walk as m
    importlib.reload(m)
    # Patch AFTER reload so the substitution survives.
    called = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.start_walk",
        lambda s, chat_id: called.append(chat_id),
    )

    app = flask.Flask("test")
    with app.app_context():
        flask.g.db_session = session
        out = _handle_command("/inventory", chat_id="abc")
    assert called == ["abc"]
    # _handle_command may return empty string when it side-channels via send_telegram_message.
    assert out == "" or "abc" in (out or "")


def test_webhook_routes_inv_callback_to_dispatch(session, monkeypatch):
    """A callback_query with data='inv:cat:pantry' routes to dispatch_inv_callback."""
    import flask
    from src.backend.handle_telegram_messages import _handle_callback_query
    monkeypatch.setenv("TELEGRAM_INVENTORY_WALK_ENABLED", "1")
    import importlib
    import src.backend.handle_inventory_walk as m
    importlib.reload(m)
    # Patch AFTER reload so the substitution survives.
    called = []
    monkeypatch.setattr(
        "src.backend.handle_inventory_walk.dispatch_inv_callback",
        lambda s, chat_id, data, message_id: called.append((chat_id, data, message_id)),
    )
    monkeypatch.setattr(
        "src.backend.handle_telegram_messages._answer_callback_query",
        lambda _: None,
    )

    cb = {
        "id": "cb1",
        "data": "inv:cat:pantry",
        "from": {"id": 42},
        "message": {"chat": {"id": "abc"}, "message_id": 100},
    }
    app = flask.Flask("test")
    with app.app_context():
        flask.g.db_session = session
        _handle_callback_query(cb)
    assert called == [("abc", "inv:cat:pantry", 100)]
