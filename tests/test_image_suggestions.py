"""Integration tests for product image suggestion and link-to-product endpoints.

GET  /product-snapshots/suggest?name=X&category=Y
POST /product-snapshots/<id>/link-to-product/<product_id>

Native/cloud deps stubbed in tests/conftest.py.
"""
from __future__ import annotations

import pytest

from src.backend.initialize_database_schema import (
    Base,
    CategoryShelfLifeDefault,
    Product,
    ProductSnapshot,
    User,
    create_db_engine,
    create_session_factory,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "img_suggest.db"
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

    # Product with a snapshot (Avocado Oil — exact name match candidate)
    prod_with_image = Product(
        name="avocado oil",
        display_name="Avocado Oil",
        brand="Chosen Foods",
        category="oils",
    )
    s.add(prod_with_image)
    s.flush()

    snap = ProductSnapshot(
        product_id=prod_with_image.id,
        source_context="manual",
        status="unreviewed",
        image_path="/snapshots/2024/01/avocado_oil.jpg",
    )
    s.add(snap)

    # Product WITHOUT a snapshot (should be excluded from suggestions)
    prod_no_image = Product(
        name="coconut oil",
        display_name="Coconut Oil",
        brand="Nutiva",
        category="oils",
    )
    s.add(prod_no_image)

    # Second product for link-to-product tests (no snapshot yet)
    prod_target = Product(
        name="avocado oil organic",
        display_name="Avocado Oil Organic",
        brand=None,
        category="oils",
    )
    s.add(prod_target)

    s.commit()

    avocado_with_id = prod_with_image.id
    snap_id = snap.id
    target_id = prod_target.id
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
        yield c, snap_id, avocado_with_id, target_id


# ── suggest endpoint ──────────────────────────────────────────────────────────

def test_exact_match_returns_score_100(client):
    c, snap_id, product_id, target_id = client
    r = c.get("/product-snapshots/suggest?name=avocado+oil")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["suggestions"]) >= 1
    top = body["suggestions"][0]
    assert top["score"] == 100
    assert "avocado" in top["product_name"].lower()
    assert top["image_url"].startswith("/product-snapshots/")


def test_no_image_products_excluded(client):
    c, snap_id, product_id, target_id = client
    r = c.get("/product-snapshots/suggest?name=coconut+oil")
    assert r.status_code == 200
    body = r.get_json()
    # coconut oil product has no snapshot — must not appear
    names = [s["product_name"].lower() for s in body["suggestions"]]
    assert not any("coconut" in n for n in names)


def test_suggest_short_name_returns_400(client):
    c, *_ = client
    r = c.get("/product-snapshots/suggest?name=a")
    assert r.status_code == 400


def test_unauthenticated_suggest_returns_401(tmp_path, monkeypatch):
    db = tmp_path / "unauth.db"
    db_url = f"sqlite:///{db}"
    import src.backend.initialize_database_schema as _schema
    import src.backend.create_flask_application as _cfa
    monkeypatch.setattr(_schema, "DATABASE_URL", db_url)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    from src.backend.initialize_database_schema import create_db_engine, Base
    eng = create_db_engine(db_url)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(_cfa, "_engine", None)
    monkeypatch.setattr(_cfa, "_SessionFactory", None)
    from src.backend.create_flask_application import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/product-snapshots/suggest?name=avocado+oil")
        assert r.status_code == 401


# ── link-to-product endpoint ──────────────────────────────────────────────────

def test_link_snapshot_to_product_creates_new_snapshot(client):
    c, snap_id, product_id, target_id = client
    r = c.post(f"/product-snapshots/{snap_id}/link-to-product/{target_id}")
    assert r.status_code == 201
    body = r.get_json()
    assert body["copied_from"] == snap_id
    assert body["snapshot"]["product_id"] == target_id
    assert body["snapshot"]["image_url"].startswith("/product-snapshots/")


def test_link_to_product_409_if_target_already_has_snapshot(client):
    c, snap_id, product_id, target_id = client
    # First link succeeds
    c.post(f"/product-snapshots/{snap_id}/link-to-product/{target_id}")
    # Second link should return 409
    r = c.post(f"/product-snapshots/{snap_id}/link-to-product/{target_id}")
    assert r.status_code == 409
    assert "already has a snapshot" in r.get_json()["error"]


def test_link_to_nonexistent_snapshot_returns_404(client):
    c, snap_id, product_id, target_id = client
    r = c.post(f"/product-snapshots/99999/link-to-product/{target_id}")
    assert r.status_code == 404


def test_link_to_nonexistent_product_returns_404(client):
    c, snap_id, product_id, target_id = client
    r = c.post(f"/product-snapshots/{snap_id}/link-to-product/99999")
    assert r.status_code == 404
