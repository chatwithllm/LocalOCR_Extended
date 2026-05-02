"""Integration tests for inventory PATCH and reset endpoints."""
from __future__ import annotations

import os
from datetime import date
from unittest.mock import patch

import pytest

from src.backend.initialize_database_schema import (
    Base, CategoryShelfLifeDefault, Inventory, Product, User,
    create_db_engine, create_session_factory,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "ep.db"
    db_url = f"sqlite:///{db}"

    # Patch the module-level DATABASE_URL constant BEFORE create_app() reads it.
    # (monkeypatch.setenv alone won't update the already-evaluated module-level var.)
    import src.backend.initialize_database_schema as _schema
    import src.backend.create_flask_application as _cfa
    monkeypatch.setattr(_schema, "DATABASE_URL", db_url)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")

    # Pre-seed the database using a standalone engine before create_app() runs.
    eng = create_db_engine(db_url)
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()
    s.add(CategoryShelfLifeDefault(category="dairy", location_default="Fridge", shelf_life_days=14))
    s.add(CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0))
    admin = User(name="Admin", email="admin@test", role="admin", is_active=True)
    s.add(admin)
    s.flush()
    prod = Product(name="Milk", category="dairy")
    s.add(prod)
    s.flush()
    inv = Inventory(
        product_id=prod.id,
        quantity=4,
        location="Fridge",
        expires_at=date(2026, 5, 3),
        expires_at_system=date(2026, 5, 3),
        expires_source="system",
    )
    s.add(inv)
    s.commit()
    pid, uid = prod.id, admin.id
    s.close()
    eng.dispose()

    # Reset the module-level engine singleton so create_app() re-initialises
    # against our tmp DB (the singleton caches the engine across test runs).
    monkeypatch.setattr(_cfa, "_engine", None)
    monkeypatch.setattr(_cfa, "_SessionFactory", None)

    with (
        patch("src.backend.setup_mqtt_connection.setup_mqtt_connection"),
        patch("src.backend.setup_mqtt_connection.publish_message"),
        patch("src.backend.schedule_daily_recommendations.start_recommendation_scheduler"),
    ):
        from src.backend.create_flask_application import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = uid
                # session_version must match user.session_version (default 0)
                sess["session_version"] = 0
            yield c, pid


def test_patch_quantity(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"quantity": 1})
    assert r.status_code == 200
    assert r.get_json()["quantity"] == 1


def test_patch_used_up(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"quantity": 0})
    assert r.status_code == 200
    assert r.get_json()["quantity"] == 0


def test_patch_defer_days_marks_defer(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"defer_days": 3})
    assert r.status_code == 200
    body = r.get_json()
    assert body["expires_source"] == "defer"
    assert body["expires_at"] == "2026-05-06"


def test_patch_explicit_expiry_marks_user(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"expires_at": "2026-06-01"})
    assert r.status_code == 200
    assert r.get_json()["expires_source"] == "user"


def test_reset_expiry_clears_override(client):
    c, pid = client
    c.patch(f"/inventory/products/{pid}", json={"expires_at": "2026-06-01"})
    r = c.delete(f"/inventory/products/{pid}/expiry-override")
    assert r.status_code == 200
    body = r.get_json()
    assert body["expires_source"] == "system"
    assert body["expires_at"] == "2026-05-03"


def test_patch_negative_clamps(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"quantity": -5})
    assert r.status_code == 200
    assert r.get_json()["quantity"] == 0


def test_patch_invalid_date_400(client):
    c, pid = client
    r = c.patch(f"/inventory/products/{pid}", json={"expires_at": "not-a-date"})
    assert r.status_code == 400
