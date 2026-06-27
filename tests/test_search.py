"""Integration tests for GET /api/search?q=<term>

Native/cloud deps are stubbed in tests/conftest.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.backend.initialize_database_schema import (
    Base,
    CategoryShelfLifeDefault,
    Inventory,
    Product,
    Purchase,
    ReceiptItem,
    Store,
    User,
    create_db_engine,
    create_session_factory,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "search.db"
    db_url = f"sqlite:///{db}"

    import src.backend.initialize_database_schema as _schema
    import src.backend.create_flask_application as _cfa

    monkeypatch.setattr(_schema, "DATABASE_URL", db_url)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")

    eng = create_db_engine(db_url)
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()

    s.add(CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0))
    admin = User(name="Admin", email="admin@test", role="admin", is_active=True)
    s.add(admin)
    s.flush()

    # Product + inventory hit
    prod = Product(name="avocado oil", display_name="Avocado Oil", brand="Chosen Foods", category="other")
    store = Store(name="Whole Foods")
    s.add(prod)
    s.add(store)
    s.flush()

    inv = Inventory(product_id=prod.id, quantity=2, location="Pantry", is_active_window=True)
    s.add(inv)

    # Receipt + line item hit
    pu = Purchase(
        store_id=store.id,
        total_amount=14.99,
        date=datetime(2026, 6, 1, tzinfo=timezone.utc),
        domain="grocery",
        transaction_type="purchase",
    )
    s.add(pu)
    s.flush()

    ri = ReceiptItem(purchase_id=pu.id, product_id=prod.id, quantity=1, unit_price=14.99)
    s.add(ri)
    s.commit()

    uid = admin.id
    s.close()
    eng.dispose()

    monkeypatch.setattr(_cfa, "_engine", None)
    monkeypatch.setattr(_cfa, "_SessionFactory", None)

    from src.backend.create_flask_application import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = uid
            sess["session_version"] = 0
        yield c


def test_empty_query_returns_400(client):
    r = client.get("/api/search?q=")
    assert r.status_code == 400


def test_short_query_returns_400(client):
    r = client.get("/api/search?q=a")
    assert r.status_code == 400


def test_avocado_oil_returns_all_sections(client):
    r = client.get("/api/search?q=avocado+oil")
    assert r.status_code == 200
    body = r.get_json()
    assert body["query"] == "avocado oil"
    results = body["results"]
    assert len(results["inventory"]) >= 1
    assert results["inventory"][0]["product_name"] == "Avocado Oil"
    assert len(results["products"]) >= 1
    assert len(results["receipts"]) >= 1
    # Receipt hit should carry matched_items
    receipt = results["receipts"][0]
    assert "purchase_id" in receipt
    assert "store" in receipt
    assert isinstance(receipt["matched_items"], list)


def test_unauthenticated_returns_401(client):
    from src.backend.create_flask_application import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as anon:
        r = anon.get("/api/search?q=avocado+oil")
        assert r.status_code == 401


def test_no_match_returns_empty_sections(client):
    r = client.get("/api/search?q=xyzzy+not+real")
    assert r.status_code == 200
    body = r.get_json()
    results = body["results"]
    assert results["inventory"] == []
    assert results["products"] == []
    assert results["receipts"] == []
