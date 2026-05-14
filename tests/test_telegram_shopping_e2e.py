"""End-to-end webhook flow tests for the Telegram shopping walk."""
import os
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ["TELEGRAM_SHOPPING_WALK_ENABLED"] = "1"
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "")


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "se2e.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["TELEGRAM_SHOPPING_WALK_ENABLED"] = "1"
    os.environ["TELEGRAM_SHOPPING_WALK_PILOT_CHATS"] = ""
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = ""
    import importlib
    import src.backend.handle_shopping_walk as m
    importlib.reload(m)

    import src.backend.create_flask_application as cfa
    cfa._engine = None
    cfa._SessionFactory = None

    with patch("src.backend.setup_mqtt_connection.setup_mqtt_connection"), \
         patch("src.backend.setup_mqtt_connection.publish_message"), \
         patch("src.backend.schedule_daily_recommendations.start_recommendation_scheduler"):
        flask_app = cfa.create_app()
        flask_app.config["TESTING"] = True
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_session(app):
    import src.backend.create_flask_application as app_mod
    engine, SessionFactory = app_mod._get_db()
    from src.backend.initialize_database_schema import Base
    Base.metadata.create_all(engine)
    def _make():
        return SessionFactory()
    return _make


def _post(client, payload):
    return client.post("/telegram/webhook", json=payload)


def _post_command(client, chat_id, text, update_id=1, message_id=1):
    return _post(client, {
        "update_id": update_id,
        "message": {
            "message_id": message_id, "chat": {"id": chat_id}, "text": text,
        },
    })


def _post_callback(client, chat_id, data, update_id=2, message_id=100, cb_id="cb1"):
    return _post(client, {
        "update_id": update_id,
        "callback_query": {
            "id": cb_id, "data": data,
            "from": {"id": 42},
            "message": {"chat": {"id": chat_id}, "message_id": message_id},
        },
    })


def _post_text(client, chat_id, text, update_id=3, message_id=2):
    return _post(client, {
        "update_id": update_id,
        "message": {
            "message_id": message_id, "chat": {"id": chat_id}, "text": text,
        },
    })


@patch("src.backend.handle_telegram_messages.http_requests")
def test_full_shopping_walk_with_custom(http_mock, client, make_session):
    """End-to-end: /shopping -> cat -> +Add -> cat_done -> +custom -> name -> qty -> store -> done."""
    http_mock.post = MagicMock(return_value=MagicMock(status_code=200))

    from src.backend.initialize_database_schema import (
        Product, Inventory, ShoppingListItem, TelegramShoppingSession,
    )

    # Single-token name avoids the recommendation engine's family-grouping
    # rewrite (e.g. "Olive oil" -> "Oil"), so we can assert on the exact name
    # surfaced to the user and saved on the shopping list.
    db = make_session()
    p = Product(name="Pepper", category="pantry"); db.add(p); db.flush()
    inv = Inventory(product_id=p.id, quantity=0.0, manual_low=True, is_active_window=True)
    db.add(inv); db.commit()
    db.close()

    chat = "12345"
    assert _post_command(client, chat, "/shopping").status_code == 200
    assert _post_callback(client, chat, "shop:cat:pantry",
                          update_id=2, message_id=200, cb_id="cb1").status_code == 200
    assert _post_callback(client, chat, "shop:add",
                          update_id=3, message_id=201, cb_id="cb2").status_code == 200
    # Now in CATEGORY_END
    assert _post_callback(client, chat, "shop:custom",
                          update_id=4, message_id=202, cb_id="cb3").status_code == 200
    assert _post_text(client, chat, "Bay Leaves",
                      update_id=5, message_id=10).status_code == 200
    # Now in custom_qty
    assert _post_callback(client, chat, "shop:qty:1",
                          update_id=6, message_id=203, cb_id="cb4").status_code == 200
    # Now in custom_store
    assert _post_callback(client, chat, "shop:store:skip",
                          update_id=7, message_id=204, cb_id="cb5").status_code == 200
    # Back at CATEGORY_END
    assert _post_callback(client, chat, "shop:cat_done",
                          update_id=8, message_id=205, cb_id="cb6").status_code == 200
    # Walk should be done now (only one category, finished)

    db = make_session()
    items = db.query(ShoppingListItem).all()
    names = sorted(i.name for i in items)
    assert "Pepper" in names
    assert "Bay Leaves" in names

    sess = db.query(TelegramShoppingSession).filter_by(chat_id=chat).one()
    assert (sess.stats or {}).get("added") == 1
    assert (sess.stats or {}).get("custom_added") == 1
    assert sess.status == "done"
    db.close()


@patch("src.backend.handle_telegram_messages.http_requests")
def test_two_chats_isolated(http_mock, client, make_session):
    http_mock.post = MagicMock(return_value=MagicMock(status_code=200))
    from src.backend.initialize_database_schema import (
        Product, Inventory, TelegramShoppingSession,
    )
    # Distinct names from test_full_shopping_walk_with_custom so back-to-back
    # runs (which share the same SQLite path via the module-level DATABASE_URL
    # constant baked at import time) don't hit UNIQUE(name, category).
    db = make_session()
    p1 = Product(name="Sugar", category="pantry"); db.add(p1); db.flush()
    db.add(Inventory(product_id=p1.id, quantity=0.0, manual_low=True, is_active_window=True))
    p2 = Product(name="Yogurt", category="fridge"); db.add(p2); db.flush()
    db.add(Inventory(product_id=p2.id, quantity=0.0, manual_low=True, is_active_window=True))
    db.commit(); db.close()

    _post_command(client, "alpha", "/shopping", update_id=10, message_id=1)
    _post_callback(client, "alpha", "shop:cat:pantry",
                   update_id=11, message_id=200, cb_id="a1")
    _post_command(client, "bravo", "/shopping", update_id=20, message_id=2)
    _post_callback(client, "bravo", "shop:cat:fridge",
                   update_id=21, message_id=300, cb_id="b1")

    db = make_session()
    a = db.query(TelegramShoppingSession).filter_by(chat_id="alpha").one()
    b = db.query(TelegramShoppingSession).filter_by(chat_id="bravo").one()
    assert a.current_category == "pantry"
    assert b.current_category == "fridge"
    db.close()
