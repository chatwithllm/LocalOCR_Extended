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
