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
    # Single-token names so the engine's family-grouping pass returns them as-is
    # (generate_all_recommendations rewrites product_name → family last token).
    _seed_low_inventory(session, pairs=[
        ("Oil",    "pantry", 1.0, 5.0, False),  # low_stock (qty < threshold)
        ("Pepper", "pantry", 0.0, None, True),  # manual_low
        ("Milk",   "fridge", 0.0, None, True),
    ])
    recs = fetch_recommendations(session)
    names = sorted(r["product_name"] for r in recs)
    cats = sorted(set(r["category"] for r in recs))
    assert "Oil" in names
    assert "Pepper" in names
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
    item = item_map["pantry"][0]
    assert "product_id" in item
    assert "name" in item
    assert "category" in item
    assert "reason_label" in item


def test_reason_label_for_each_kind():
    from src.backend.handle_shopping_walk import _reason_label
    assert "Low stock" in _reason_label({"reason": "low_stock", "current_quantity": 1.0, "threshold": 5.0})
    assert "Low stock" in _reason_label({"reason": "manual_low"})
    assert "Seasonal" in _reason_label({"reason": "seasonal"})
    assert "Price" in _reason_label({"reason": "deal", "avg_price": 8.99, "current_price": 6.49})
    assert "Suggested" in _reason_label({"reason": "unknown_kind"})


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
    # Tie on count (1 each) → alpha tie-break locks order to ["fridge", "pantry"].
    assert sorted(row.category_queue) == ["fridge", "pantry"]


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


def test_handle_category_loads_queue_and_renders_first_item(session, monkeypatch):
    from src.backend.handle_shopping_walk import handle_category, start_walk
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
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
    # pantry should have been popped from category_queue
    assert "pantry" not in row.category_queue
    assert "fridge" in row.category_queue
    last_text = edits[-1][2]
    assert "1/2" in last_text
    assert "Olive oil" in last_text
    assert row.stats == {"added": 0, "skipped": 0, "already_have": 0, "custom_added": 0}


def test_handle_add_inserts_qty_one_and_advances(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_add, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramShoppingSession, ShoppingListItem, Product,
    )
    p1 = Product(name="Olive oil", category="pantry"); session.add(p1); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()

    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p1.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock", "current_quantity": 1.0, "threshold": 5.0},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_add(session, "abc", message_id=100); session.commit()

    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["added"] == 1
    items = session.query(ShoppingListItem).all()
    assert len(items) == 1
    assert items[0].name == "Olive oil"
    assert items[0].quantity == 1
    assert items[0].preferred_store is None
    assert items[0].source == "telegram_shopping"


def test_handle_add_detailed_transitions_to_qty_prompt(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_add_detailed, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramShoppingSession, Product,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_add_detailed(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "qty"
    assert row.pending_action == "add_detailed"
    assert "how many" in edits[-1][2].lower()


def test_handle_qty_transitions_to_store_prompt(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_qty, handle_add_detailed, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramShoppingSession, Product, Store, Purchase,
    )
    from datetime import datetime
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    s_store = Store(name="Costco"); session.add(s_store); session.flush()
    session.add(Purchase(store_id=s_store.id, total_amount=1.0,
                         date=datetime.utcnow(), transaction_type="purchase"))
    session.commit()

    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()

    handle_qty(session, "abc", qty_arg="3", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "store"
    assert row.pending_qty == 3.0
    last = edits[-1][2]
    assert "× 3" in last or "x 3" in last.lower()
    callbacks = [b["callback_data"] for r in edits[-1][3]["inline_keyboard"] for b in r]
    assert "shop:store:costco" in callbacks


def test_handle_qty_custom_enters_typed_text_state(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_qty, handle_add_detailed, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramShoppingSession, Product,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()

    handle_qty(session, "abc", qty_arg="cu", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "qty"
    assert row.pending_action == "add_detailed_qty_typed"


def test_handle_store_inserts_with_qty_and_store_then_advances(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_store, handle_qty, handle_add_detailed,
        handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, Store, Purchase, ShoppingListItem, TelegramShoppingSession,
    )
    from datetime import datetime
    p1 = Product(name="Olive oil", category="pantry"); session.add(p1); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()
    s = Store(name="Costco"); session.add(s); session.flush()
    session.add(Purchase(store_id=s.id, total_amount=1.0,
                         date=datetime.utcnow(), transaction_type="purchase"))
    session.commit()

    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p1.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()
    handle_qty(session, "abc", qty_arg="3", message_id=100); session.commit()

    handle_store(session, "abc", store_arg="costco", message_id=100); session.commit()

    items = session.query(ShoppingListItem).all()
    assert len(items) == 1
    assert items[0].quantity == 3.0
    assert items[0].preferred_store == "Costco"
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["added"] == 1
    assert row.pending_prompt == "item"


def test_handle_store_skip_inserts_without_store(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_store, handle_qty, handle_add_detailed,
        handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, ShoppingListItem, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()
    handle_qty(session, "abc", qty_arg="2", message_id=100); session.commit()

    handle_store(session, "abc", store_arg="skip", message_id=100); session.commit()

    item = session.query(ShoppingListItem).one()
    assert item.preferred_store is None
    assert item.quantity == 2.0


def test_handle_store_other_enters_typed_text_state(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_store, handle_qty, handle_add_detailed,
        handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()
    handle_qty(session, "abc", qty_arg="1", message_id=100); session.commit()

    handle_store(session, "abc", store_arg="other", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "store"
    assert row.pending_action == "add_detailed_store_typed"


def test_handle_skip_advances_no_write(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_skip, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, ShoppingListItem, TelegramShoppingSession,
    )
    p1 = Product(name="Olive oil", category="pantry"); session.add(p1); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p1.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_skip(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["skipped"] == 1
    assert session.query(ShoppingListItem).count() == 0


def test_handle_have_advances_no_write(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_have, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, ShoppingListItem, TelegramShoppingSession,
    )
    p1 = Product(name="Olive oil", category="pantry"); session.add(p1); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p1.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_have(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["already_have"] == 1
    assert session.query(ShoppingListItem).count() == 0


def test_handle_done_ends_walk_with_summary(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_done, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_done(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.status == "done"
    assert row.pending_prompt is None
    assert any("Shopping plan complete" in t for t in edits)


def test_handle_cat_done_loads_next_category(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_cat_done, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    pa = Product(name="Olive oil", category="pantry"); session.add(pa); session.flush()
    pb = Product(name="Milk", category="fridge"); session.add(pb); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": pa.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": pb.id, "product_name": "Milk", "category": "fridge",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    # Simulate having reached category_end (pantry done).
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()

    handle_cat_done(session, "abc", message_id=100); session.commit()

    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.current_category == "fridge"
    assert row.pending_prompt == "item"
    assert row.cursor == 0
    assert len(row.item_queue) == 1


def test_handle_cat_done_ends_walk_when_no_more_categories(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_cat_done, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()

    handle_cat_done(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.status == "done"
    assert any("Shopping plan complete" in t for t in edits)


def test_handle_custom_transitions_to_custom_name(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_custom, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()

    handle_custom(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "custom_name"
    assert row.pending_action == "custom_add"


def test_consume_typed_name_transitions_to_custom_qty(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        consume_typed_name, handle_custom,
        handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((t, reply_markup)),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()
    handle_custom(session, "abc", message_id=100); session.commit()

    consume_typed_name(session, "abc", "Bay Leaves", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "custom_qty"
    assert row.pending_name == "Bay Leaves"
    assert "Bay Leaves" in edits[-1][0]


def test_consume_typed_name_rejects_empty(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        consume_typed_name, handle_custom, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()
    handle_custom(session, "abc", message_id=100); session.commit()

    consume_typed_name(session, "abc", "   ", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "custom_name"  # stays in name state
    assert any("can't be empty" in t for t in sent)
