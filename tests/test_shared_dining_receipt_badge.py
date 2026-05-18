"""Receipts list endpoint includes my_amount when purchase is split."""
from __future__ import annotations

import os
import pytest
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ.setdefault("SESSION_SECRET", "test-secret")


@pytest.fixture
def app(tmp_path):
    import src.backend.create_flask_application as cfa
    import src.backend.initialize_database_schema as schema_module
    from src.backend.initialize_database_schema import create_db_engine, create_session_factory
    from src.backend.create_flask_application import create_app

    db_path = tmp_path / "badge_test.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url

    schema_module.DATABASE_URL = db_url
    cfa._engine = None
    cfa._SessionFactory = None

    application = create_app()
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _seed(session, total=100.0):
    from src.backend.initialize_database_schema import Purchase, Store, TelegramReceipt

    store = Store(name="Test Dining")
    session.add(store)
    session.flush()
    purchase = Purchase(
        store_id=store.id,
        total_amount=total,
        date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        domain="restaurant",
    )
    session.add(purchase)
    session.flush()
    tr = TelegramReceipt(
        telegram_user_id="tg_123",
        message_id="99",
        image_path="/tmp/badge_test.jpg",
        status="processed",
        purchase_id=purchase.id,
    )
    session.add(tr)
    session.flush()
    return tr, purchase


def test_receipt_without_split_has_no_my_amount(client):
    """Unsplit receipt: my_amount absent (None) in list response."""
    import src.backend.create_flask_application as cfa
    from src.backend.initialize_database_schema import create_session_factory

    with client.application.app_context():
        SessionFactory = create_session_factory(cfa._engine)
        session = SessionFactory()
        _seed(session, total=120.0)
        session.commit()
        session.close()

    res = client.get("/receipts", headers={"Authorization": "Bearer test-admin-token"})
    assert res.status_code == 200
    receipts = res.get_json().get("receipts", [])
    # At least one receipt should be present
    assert len(receipts) > 0
    # All receipts in this isolated DB have no SharedExpense — all must have my_amount == None
    assert all(r.get("my_amount") is None for r in receipts)


def test_receipt_with_split_has_my_amount(client):
    """Split receipt: my_amount present and correct in list response."""
    import src.backend.create_flask_application as cfa
    from src.backend.initialize_database_schema import create_session_factory, SharedExpense

    with client.application.app_context():
        SessionFactory = create_session_factory(cfa._engine)
        session = SessionFactory()
        tr, purchase = _seed(session, total=200.0)
        expense = SharedExpense(
            purchase_id=purchase.id,
            total_amount=200.0,
            my_amount=100.0,
            payment_scenario="PAID_ALL",
        )
        session.add(expense)
        session.commit()
        session.close()

    res = client.get("/receipts", headers={"Authorization": "Bearer test-admin-token"})
    assert res.status_code == 200
    receipts = res.get_json().get("receipts", [])
    split = next((r for r in receipts if r.get("my_amount") is not None), None)
    assert split is not None
    assert split["my_amount"] == pytest.approx(100.0)
    assert split["shared_expense_id"] is not None
