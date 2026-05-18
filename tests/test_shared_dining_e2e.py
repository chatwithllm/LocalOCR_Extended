# tests/test_shared_dining_e2e.py
from __future__ import annotations
import os
import json
import pytest

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
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    from src.backend.create_flask_application import create_app

    db_path = tmp_path / "e2e.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url

    # Patch the module-level DATABASE_URL so initialize_database() uses the
    # per-test file path rather than the value frozen at import time.
    schema_module.DATABASE_URL = db_url

    # Reset module-level engine cache so create_app() creates a fresh engine.
    cfa._engine = None
    cfa._SessionFactory = None

    application = create_app()
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {os.environ['INITIAL_ADMIN_TOKEN']}"}


@pytest.fixture
def purchase_id(app):
    import src.backend.create_flask_application as cfa
    from src.backend.initialize_database_schema import (
        create_session_factory, Purchase
    )
    from datetime import datetime, timezone

    # Use the same engine the Flask app's before_request hook will use.
    SessionFactory = create_session_factory(cfa._engine)
    s = SessionFactory()
    p = Purchase(total_amount=100.0, date=datetime.now(timezone.utc), domain="restaurant")
    s.add(p)
    s.commit()
    pid = p.id
    s.close()
    return pid


def test_create_shared_expense_via_api(client, auth_headers, purchase_id):
    payload = {
        "payment_scenario": "PAID_ALL",
        "participants": [
            {"is_self": True,  "share_amount": 50.0, "ad_hoc_name": None, "contact_id": None},
            {"is_self": False, "share_amount": 50.0, "ad_hoc_name": "Bob", "contact_id": None},
        ],
    }
    resp = client.post(
        f"/shared-dining/purchases/{purchase_id}",
        data=json.dumps(payload),
        content_type="application/json",
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["my_amount"] == 50.0


def test_create_contact_and_list(client, auth_headers):
    resp = client.post(
        "/shared-dining/contacts",
        data=json.dumps({"name": "Alice", "phone": "555-9999"}),
        content_type="application/json",
        headers=auth_headers,
    )
    assert resp.status_code == 201

    resp2 = client.get("/shared-dining/contacts", headers=auth_headers)
    assert resp2.status_code == 200
    contacts = resp2.get_json()
    assert any(c["name"] == "Alice" for c in contacts)


def test_get_balances_empty(client, auth_headers):
    resp = client.get("/shared-dining/balances", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_settle_debt_via_api(client, auth_headers, purchase_id):
    payload = {
        "payment_scenario": "PAID_ALL",
        "participants": [
            {"is_self": True,  "share_amount": 50.0, "ad_hoc_name": None, "contact_id": None},
            {"is_self": False, "share_amount": 50.0, "ad_hoc_name": "Bob", "contact_id": None},
        ],
    }
    create_resp = client.post(
        f"/shared-dining/purchases/{purchase_id}",
        data=json.dumps(payload),
        content_type="application/json",
        headers=auth_headers,
    )
    assert create_resp.status_code == 201

    import src.backend.create_flask_application as cfa
    from src.backend.initialize_database_schema import (
        create_session_factory, SharedDebt
    )
    sess = create_session_factory(cfa._engine)()
    debt = sess.query(SharedDebt).first()
    debt_id = debt.id
    sess.close()

    settle_resp = client.post(
        f"/shared-dining/debts/{debt_id}/settle",
        data=json.dumps({"note": "paid cash"}),
        content_type="application/json",
        headers=auth_headers,
    )
    assert settle_resp.status_code == 200
