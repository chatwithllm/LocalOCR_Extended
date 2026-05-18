"""FloorObligation model and CRUD API tests."""
from __future__ import annotations
import os
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
    from src.backend.create_flask_application import create_app

    db_url = f"sqlite:///{tmp_path / 'floor_test.db'}"
    os.environ["DATABASE_URL"] = db_url
    schema_module.DATABASE_URL = db_url
    cfa._engine = None
    cfa._SessionFactory = None

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _auth(client):
    return {"Authorization": "Bearer test-admin-token"}


def test_floor_obligation_table_exists(app):
    from src.backend.initialize_database_schema import FloorObligation
    from src.backend.create_flask_application import _engine
    from sqlalchemy import inspect
    insp = inspect(_engine)
    assert "floor_obligations" in insp.get_table_names()


def test_list_floor_obligations_empty(client):
    res = client.get("/floor-obligations/", headers=_auth(client))
    assert res.status_code == 200
    assert res.get_json()["obligations"] == []


def test_create_manual_obligation(client):
    res = client.post(
        "/floor-obligations/",
        json={"label": "Rent", "expected_monthly_amount": 1500.0},
        headers=_auth(client),
    )
    assert res.status_code == 201
    ob = res.get_json()["obligation"]
    assert ob["label"] == "Rent"
    assert ob["expected_monthly_amount"] == 1500.0
    assert ob["is_active"] is True
    assert ob["source"] == "manual"


def test_patch_obligation_toggle(client):
    create_res = client.post(
        "/floor-obligations/",
        json={"label": "Car Loan", "expected_monthly_amount": 450.0},
        headers=_auth(client),
    )
    oid = create_res.get_json()["obligation"]["id"]
    patch_res = client.patch(
        f"/floor-obligations/{oid}",
        json={"is_active": False},
        headers=_auth(client),
    )
    assert patch_res.status_code == 200
    assert patch_res.get_json()["obligation"]["is_active"] is False


def test_delete_manual_obligation(client):
    create_res = client.post(
        "/floor-obligations/",
        json={"label": "Allowance", "expected_monthly_amount": 200.0},
        headers=_auth(client),
    )
    oid = create_res.get_json()["obligation"]["id"]
    del_res = client.delete(f"/floor-obligations/{oid}", headers=_auth(client))
    assert del_res.status_code == 200
    ids = [o["id"] for o in client.get("/floor-obligations/", headers=_auth(client)).get_json()["obligations"]]
    assert oid not in ids


def test_summary_manual_obligation_shows_expected(client):
    client.post(
        "/floor-obligations/",
        json={"label": "Internet", "expected_monthly_amount": 80.0},
        headers=_auth(client),
    )
    res = client.get("/floor-obligations/summary?month=2026-05", headers=_auth(client))
    assert res.status_code == 200
    data = res.get_json()
    assert data["floor_total"] == 80.0
    assert len(data["obligations"]) == 1
    ob = data["obligations"][0]
    assert ob["label"] == "Internet"
    assert ob["this_month_actual"] is None
    assert ob["last_month_actual"] is None
    assert ob["status"] == "manual"


def test_summary_inactive_excluded(client):
    create_res = client.post(
        "/floor-obligations/",
        json={"label": "Gym", "expected_monthly_amount": 50.0},
        headers=_auth(client),
    )
    oid = create_res.get_json()["obligation"]["id"]
    client.patch(f"/floor-obligations/{oid}", json={"is_active": False}, headers=_auth(client))
    res = client.get("/floor-obligations/summary?month=2026-05", headers=_auth(client))
    assert res.status_code == 200
    labels = [o["label"] for o in res.get_json()["obligations"]]
    assert "Gym" not in labels


def test_summary_invalid_month_returns_400(client):
    res = client.get("/floor-obligations/summary?month=2026-13", headers=_auth(client))
    assert res.status_code == 400
    assert "month" in res.get_json().get("error", "").lower()


# --- helpers for v2 tests ---

def _create_provider_and_purchase(app, provider_name, amount, months_ago):
    """Create BillProvider + Purchase + BillMeta dated `months_ago` calendar months before now."""
    from datetime import datetime, timezone
    from dateutil.relativedelta import relativedelta
    from src.backend.initialize_database_schema import BillProvider, BillMeta, Purchase
    now = datetime.now(timezone.utc).replace(day=15, hour=0, minute=0, second=0, microsecond=0)
    target = now - relativedelta(months=months_ago)
    purchase_date = target.replace(tzinfo=None)  # naïve, matches DB convention
    with app.app_context():
        from src.backend.create_flask_application import _get_db
        _, SessionFactory = _get_db()
        session = SessionFactory()
        try:
            provider = BillProvider(
                canonical_name=provider_name,
                normalized_key=provider_name.lower(),
            )
            session.add(provider)
            session.flush()
            purchase = Purchase(
                date=purchase_date,
                total_amount=amount,
            )
            session.add(purchase)
            session.flush()
            meta = BillMeta(purchase_id=purchase.id, provider_id=provider.id)
            session.add(meta)
            session.commit()
            return provider.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def test_list_includes_avg_and_latest_for_manual(client, app):
    """Manual obligations have null avg_6mo and latest_actual."""
    r = client.post("/floor-obligations/", json={"label": "Rent", "expected_monthly_amount": 1200}, headers=_auth(client))
    assert r.status_code == 201
    r2 = client.get("/floor-obligations/", headers=_auth(client))
    assert r2.status_code == 200
    obs = r2.get_json()["obligations"]
    rent = next(o for o in obs if o["label"] == "Rent")
    assert rent["avg_6mo"] is None
    assert rent["latest_actual"] is None


def test_list_includes_avg_and_latest_for_bill_provider(client, app):
    """Bill-linked obligations surface correct avg_6mo and latest_actual from purchase history."""
    # Two purchases in different months: 1 month ago = 100, 2 months ago = 80
    # avg = (100 + 80) / 2 = 90.0; latest = 100.0 (most recent month)
    provider_id = _create_provider_and_purchase(app, "TestElectric", 100.0, 1)
    # Add a second purchase for same provider in an older month
    with app.app_context():
        from datetime import datetime, timezone
        from dateutil.relativedelta import relativedelta
        from src.backend.initialize_database_schema import BillMeta, Purchase
        from src.backend.create_flask_application import _get_db
        _, SessionFactory = _get_db()
        session = SessionFactory()
        try:
            now = datetime.now(timezone.utc).replace(day=15, hour=0, minute=0, second=0, microsecond=0)
            target = (now - relativedelta(months=2)).replace(tzinfo=None)
            p2 = Purchase(date=target, total_amount=80.0)
            session.add(p2)
            session.flush()
            session.add(BillMeta(purchase_id=p2.id, provider_id=provider_id))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    with app.app_context():
        from src.backend.initialize_database_schema import FloorObligation
        from src.backend.create_flask_application import _get_db
        _, SessionFactory = _get_db()
        session = SessionFactory()
        try:
            ob = FloorObligation(label="TestElectric", expected_monthly_amount=95, is_active=True, bill_provider_id=provider_id)
            session.add(ob)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    r = client.get("/floor-obligations/", headers=_auth(client))
    assert r.status_code == 200
    obs = r.get_json()["obligations"]
    te = next(o for o in obs if o["label"] == "TestElectric")
    assert te["avg_6mo"] == 90.0
    assert te["latest_actual"] == 100.0


def test_list_bill_linked_no_history_returns_null(client, app):
    """Bill-linked obligation with no purchases in window → avg_6mo and latest_actual are null."""
    with app.app_context():
        from src.backend.initialize_database_schema import BillProvider, FloorObligation
        from src.backend.create_flask_application import _get_db
        _, SessionFactory = _get_db()
        session = SessionFactory()
        try:
            provider = BillProvider(canonical_name="NoHistProv", normalized_key="nohistprov", is_active=True)
            session.add(provider)
            session.flush()
            ob = FloorObligation(label="NoHistProv", expected_monthly_amount=50, is_active=True, bill_provider_id=provider.id)
            session.add(ob)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    r = client.get("/floor-obligations/", headers=_auth(client))
    assert r.status_code == 200
    obs = r.get_json()["obligations"]
    entry = next((o for o in obs if o["label"] == "NoHistProv"), None)
    assert entry is not None
    assert entry["avg_6mo"] is None
    assert entry["latest_actual"] is None
