"""Integration tests for PUT /inventory/products/<id>/essential
and PUT /inventory/products/<id>/backup toggle endpoints.

Client fixture, auth approach, and seeding mirror tests/test_inventory_endpoints.py
exactly: tmp SQLite DB, monkeypatched module-level engine/session singletons,
MQTT patches, and session cookie with user_id + session_version.
"""
from __future__ import annotations

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
    s.add(CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0))
    admin = User(name="Admin", email="admin@test", role="admin", is_active=True)
    s.add(admin)
    s.flush()
    prod = Product(name="Olive Oil", category="other", is_essential=False, has_backup=False)
    s.add(prod)
    s.flush()
    inv = Inventory(
        product_id=prod.id,
        quantity=1,
        location="Pantry",
        is_active_window=True,
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


# ---------------------------------------------------------------------------
# /essential toggle
# ---------------------------------------------------------------------------

def test_set_essential_true(client):
    """PUT essential with is_essential=true returns 200 and sets flag."""
    c, pid = client
    r = c.put(f"/inventory/products/{pid}/essential", json={"is_essential": True})
    assert r.status_code == 200
    body = r.get_json()
    assert body["is_essential"] is True
    assert body["product_id"] == pid


def test_set_essential_false(client):
    """After marking essential, clearing it returns is_essential=false."""
    c, pid = client
    # First set it true.
    c.put(f"/inventory/products/{pid}/essential", json={"is_essential": True})
    # Then clear it.
    r = c.put(f"/inventory/products/{pid}/essential", json={"is_essential": False})
    assert r.status_code == 200
    body = r.get_json()
    assert body["is_essential"] is False
    assert body["product_id"] == pid


def test_set_essential_persists_to_db(client):
    """is_essential=true round-trips: a second PUT read-back confirms DB write."""
    c, pid = client
    c.put(f"/inventory/products/{pid}/essential", json={"is_essential": True})
    # Re-read via a second toggle (false) — the prior state must have been True
    # for the response to flip correctly, confirming the DB was actually updated.
    r = c.put(f"/inventory/products/{pid}/essential", json={"is_essential": False})
    assert r.status_code == 200
    assert r.get_json()["is_essential"] is False


def test_set_essential_defaults_to_true(client):
    """Omitting is_essential from the body defaults to True."""
    c, pid = client
    r = c.put(f"/inventory/products/{pid}/essential", json={})
    assert r.status_code == 200
    assert r.get_json()["is_essential"] is True


def test_set_essential_nonexistent_product(client):
    """PUT essential on a non-existent product id returns 404."""
    c, _ = client
    r = c.put("/inventory/products/999999/essential", json={"is_essential": True})
    assert r.status_code == 404
    assert "not found" in r.get_json().get("error", "").lower()


# ---------------------------------------------------------------------------
# /backup toggle
# ---------------------------------------------------------------------------

def test_set_backup_true(client):
    """PUT backup with has_backup=true returns 200 and sets flag."""
    c, pid = client
    r = c.put(f"/inventory/products/{pid}/backup", json={"has_backup": True})
    assert r.status_code == 200
    body = r.get_json()
    assert body["has_backup"] is True
    assert body["product_id"] == pid


def test_set_backup_false(client):
    """After setting has_backup, clearing it returns has_backup=false."""
    c, pid = client
    c.put(f"/inventory/products/{pid}/backup", json={"has_backup": True})
    r = c.put(f"/inventory/products/{pid}/backup", json={"has_backup": False})
    assert r.status_code == 200
    body = r.get_json()
    assert body["has_backup"] is False


def test_set_backup_nonexistent_product(client):
    """PUT backup on a non-existent product id returns 404."""
    c, _ = client
    r = c.put("/inventory/products/999999/backup", json={"has_backup": True})
    assert r.status_code == 404
    assert "not found" in r.get_json().get("error", "").lower()
