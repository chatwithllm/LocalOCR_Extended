"""Full webhook -> state -> DB E2E flow tests for the Telegram inventory walk.

These tests exercise the real Flask route (`POST /telegram/webhook`) plus the
real per-request DB session lifecycle wired by `create_flask_application`.
Outbound Telegram API calls are patched so nothing escapes the test process.
"""
from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ["TELEGRAM_INVENTORY_WALK_ENABLED"] = "1"
# Empty secret -> webhook route doesn't enforce the X-Telegram-Bot-Api-Secret-Token header.
os.environ["TELEGRAM_WEBHOOK_SECRET"] = ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    """Boot a fresh Flask app bound to a per-test SQLite file.

    The app factory caches `_engine` and `_SessionFactory` at module scope, so
    we null those out before each test to force re-init against the new URL.
    `handle_inventory_walk` reads module-level env flags at import time, so we
    reload it here too — the parent test_telegram_inventory_walk suite mutates
    those env vars when it runs, which can leave the module in a stale state.
    """
    import importlib

    db_path = tmp_path / "e2e.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["TELEGRAM_INVENTORY_WALK_ENABLED"] = "1"
    os.environ["TELEGRAM_INVENTORY_WALK_PILOT_CHATS"] = ""  # no allowlist gating
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = ""

    # Reset cached engine/session factory in the app factory module.
    import src.backend.create_flask_application as app_mod
    app_mod._engine = None
    app_mod._SessionFactory = None

    # Reload modules that read env at import time.
    import src.backend.handle_inventory_walk as walk_mod
    importlib.reload(walk_mod)

    # Patch MQTT + scheduler hooks so create_app() doesn't try to bind sockets.
    with patch("src.backend.setup_mqtt_connection.setup_mqtt_connection"), \
         patch("src.backend.setup_mqtt_connection.publish_message"), \
         patch("src.backend.schedule_daily_recommendations.start_recommendation_scheduler"):
        from src.backend.create_flask_application import create_app
        flask_app = create_app()
        flask_app.config["TESTING"] = True
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_session(app):
    """Factory: returns a fresh DB session bound to the SAME engine the app uses."""
    import src.backend.create_flask_application as app_mod

    engine, SessionFactory = app_mod._get_db()  # cached during create_app()
    # Make sure the schema is in place (initialize_database does this, but be defensive).
    from src.backend.initialize_database_schema import Base
    Base.metadata.create_all(engine)

    def _make():
        return SessionFactory()
    return _make


# ---------------------------------------------------------------------------
# Webhook helpers
# ---------------------------------------------------------------------------

def _post_update(client, payload):
    return client.post("/telegram/webhook", json=payload)


def _post_command(client, chat_id, text, update_id=1, message_id=1):
    return _post_update(client, {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "text": text,
        },
    })


def _post_callback(client, chat_id, data, update_id=2, message_id=100, cb_id="cb1"):
    return _post_update(client, {
        "update_id": update_id,
        "callback_query": {
            "id": cb_id,
            "data": data,
            "from": {"id": 42},
            "message": {"chat": {"id": chat_id}, "message_id": message_id},
        },
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("src.backend.handle_telegram_messages.http_requests")
def test_full_walk_one_item_empty_to_cart(http_mock, client, make_session):
    """E2E: /inventory -> pick category -> mark Empty -> Yes -> walk ends."""
    http_mock.post = MagicMock(return_value=MagicMock(status_code=200))

    from src.backend.initialize_database_schema import (
        Product, Inventory, ShoppingListItem, TelegramInventorySession,
        utcnow as schema_utcnow,
    )

    # Seed: one stale pantry item that will surface as a stale row.
    db = make_session()
    p = Product(name="Olive oil", category="pantry")
    db.add(p); db.flush()
    inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
    inv.last_updated = schema_utcnow() - timedelta(days=30)
    db.add(inv); db.commit()
    inv_id = inv.id
    product_id = p.id
    db.close()

    chat = "12345"
    assert _post_command(client, chat, "/inventory").status_code == 200
    assert _post_callback(client, chat, "inv:cat:pantry",
                          update_id=2, message_id=200).status_code == 200
    assert _post_callback(client, chat, "inv:lvl:0",
                          update_id=3, message_id=201, cb_id="cb2").status_code == 200
    assert _post_callback(client, chat, "inv:cart:y",
                          update_id=4, message_id=202, cb_id="cb3").status_code == 200

    # Validate via a fresh session against the same engine.
    db = make_session()
    inv2 = db.query(Inventory).filter_by(id=inv_id).one()
    assert inv2.consumed_pct_override == 1.0
    assert inv2.manual_low is True

    items = db.query(ShoppingListItem).filter_by(product_id=product_id).all()
    assert len(items) == 1
    assert items[0].source == "telegram_walk"
    assert items[0].status == "open"

    sess = db.query(TelegramInventorySession).filter_by(chat_id=chat).one()
    assert (sess.stats or {}).get("updated") == 1
    assert (sess.stats or {}).get("cart_added") == 1
    assert sess.status == "done"
    db.close()


@patch("src.backend.handle_telegram_messages.http_requests")
def test_two_chats_dont_interfere(http_mock, client, make_session):
    """Two chats walking simultaneously each get their own state row."""
    http_mock.post = MagicMock(return_value=MagicMock(status_code=200))

    from src.backend.initialize_database_schema import (
        Product, Inventory, TelegramInventorySession, utcnow as schema_utcnow,
    )

    db = make_session()
    for i in range(2):
        p = Product(name=f"Item {i}", category="pantry"); db.add(p); db.flush()
        inv = Inventory(product_id=p.id, quantity=1.0, is_active_window=True)
        inv.last_updated = schema_utcnow() - timedelta(days=30)
        db.add(inv)
    db.commit()
    db.close()

    # Interleave the two chats so their state mutations cross over.
    assert _post_command(client, "alpha", "/inventory", update_id=10, message_id=1).status_code == 200
    assert _post_callback(client, "alpha", "inv:cat:pantry",
                          update_id=11, message_id=200, cb_id="a1").status_code == 200
    assert _post_command(client, "bravo", "/inventory", update_id=20, message_id=2).status_code == 200
    assert _post_callback(client, "bravo", "inv:cat:pantry",
                          update_id=21, message_id=300, cb_id="b1").status_code == 200

    db = make_session()
    a = db.query(TelegramInventorySession).filter_by(chat_id="alpha").one()
    b = db.query(TelegramInventorySession).filter_by(chat_id="bravo").one()
    assert a.current_category == "pantry"
    assert b.current_category == "pantry"
    # Each walk has its own queue + cursor, even though they share the same source data.
    assert a.cursor == 0 and b.cursor == 0
    assert len(a.item_queue) == 2
    assert len(b.item_queue) == 2
    # The two queues are independent state — they refer to the same inventory rows
    # but live on separate session rows. Mutating one must not flip the other.
    assert a.chat_id != b.chat_id
    db.close()
