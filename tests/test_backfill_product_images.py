"""Integration tests for the nightly product-image backfill.

In-memory SQLite session (mirrors tests/test_manage_kitchen.py pattern).
``fetch_product_image`` is patched to return canned JPEG bytes so we
test the DB-layer logic in isolation from network providers.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from PIL import Image

from src.backend.initialize_database_schema import (
    Base, Product, ProductSnapshot, Purchase, ReceiptItem,
    ShoppingListItem, ShoppingSession, Store,
    create_db_engine, create_session_factory,
)


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (600, 600), color=(50, 100, 150))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "backfill.db"
    engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = create_session_factory(engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def snapshots_dir(tmp_path, monkeypatch):
    d = tmp_path / "snapshots"
    d.mkdir()
    monkeypatch.setenv("PRODUCT_SNAPSHOTS_DIR", str(d))
    return d


def _add_product(session, name, category="Produce"):
    p = Product(name=name, category=category)
    session.add(p)
    session.flush()
    return p


def _add_receipt_ref(session, product):
    store = Store(name="Test Store")
    session.add(store); session.flush()
    pur = Purchase(store_id=store.id, total_amount=1.0, date=datetime.now(timezone.utc))
    session.add(pur); session.flush()
    ri = ReceiptItem(purchase_id=pur.id, product_id=product.id, quantity=1, unit_price=1.0)
    session.add(ri); session.flush()


def _add_shopping_ref(session, product):
    sess = ShoppingSession(name="trip", status="active")
    session.add(sess); session.flush()
    item = ShoppingListItem(
        product_id=product.id, name=product.name, category=product.category,
        quantity=1, status="open", shopping_session_id=sess.id,
    )
    session.add(item); session.flush()


def test_excludes_products_with_existing_snapshot(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    p = _add_product(db_session, "Apples")
    _add_receipt_ref(db_session, p)
    db_session.add(ProductSnapshot(product_id=p.id, status="linked", image_path="/x.jpg"))
    db_session.commit()
    out = find_products_needing_images(db_session)
    assert p.id not in [r.id for r in out]


def test_excludes_orphan_products(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    p = _add_product(db_session, "Lonely Item")
    db_session.commit()
    out = find_products_needing_images(db_session)
    assert p.id not in [r.id for r in out]


def test_includes_product_referenced_only_by_shopping_list_item(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    p = _add_product(db_session, "Bread")
    _add_shopping_ref(db_session, p)
    db_session.commit()
    out = find_products_needing_images(db_session)
    assert p.id in [r.id for r in out]


def test_respects_retry_window(db_session):
    """RETRY_INTERVAL gates re-attempts so the cron doesn't hammer the same products."""
    from src.backend.backfill_product_images import find_products_needing_images
    p = _add_product(db_session, "Cheese")
    _add_receipt_ref(db_session, p)
    # Fresh attempt (1 hour ago) — excluded.
    p.last_image_fetch_attempt_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()
    assert p.id not in [r.id for r in find_products_needing_images(db_session)]
    # Older than retry window (2 days) — included.
    p.last_image_fetch_attempt_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.commit()
    assert p.id in [r.id for r in find_products_needing_images(db_session)]


def test_max_products_cap_honored(db_session):
    from src.backend.backfill_product_images import find_products_needing_images
    for i in range(30):
        p = _add_product(db_session, f"Item {i}")
        _add_receipt_ref(db_session, p)
    db_session.commit()
    out = find_products_needing_images(db_session, max_products=10)
    assert len(out) == 10


def test_backfill_creates_snapshot_and_marks_attempt(db_session, snapshots_dir):
    from src.backend.backfill_product_images import (
        find_products_needing_images, backfill_images_for_products,
    )
    p = _add_product(db_session, "Eggs")
    _add_receipt_ref(db_session, p)
    db_session.commit()

    products = find_products_needing_images(db_session)
    with patch("src.backend.backfill_product_images.fetch_product_image",
               return_value=(_jpeg_bytes(), "gemini")):
        stats = backfill_images_for_products(db_session, products)

    assert stats["fetched"] == 1
    assert stats["failed"] == 0
    assert stats["providers_used"] == {"gemini": 1}
    snaps = db_session.query(ProductSnapshot).filter_by(product_id=p.id).all()
    assert len(snaps) == 1
    assert snaps[0].source_context == "auto_fetch"
    assert snaps[0].status == "auto"
    from pathlib import Path
    assert Path(snaps[0].image_path).exists()
    assert str(snapshots_dir) in snaps[0].image_path
    db_session.refresh(p)
    assert p.last_image_fetch_attempt_at is not None


def test_backfill_marks_attempt_even_when_fetch_fails(db_session, snapshots_dir):
    from src.backend.backfill_product_images import (
        find_products_needing_images, backfill_images_for_products,
    )
    p = _add_product(db_session, "Mystery")
    _add_receipt_ref(db_session, p)
    db_session.commit()

    products = find_products_needing_images(db_session)
    with patch("src.backend.backfill_product_images.fetch_product_image",
               return_value=(None, None)):
        stats = backfill_images_for_products(db_session, products)

    assert stats["fetched"] == 0
    assert stats["failed"] == 1
    assert db_session.query(ProductSnapshot).filter_by(product_id=p.id).count() == 0
    db_session.refresh(p)
    assert p.last_image_fetch_attempt_at is not None


def test_per_product_commit_survives_partial_failure(db_session, snapshots_dir):
    from src.backend.backfill_product_images import (
        find_products_needing_images, backfill_images_for_products,
    )
    p1 = _add_product(db_session, "First")
    p2 = _add_product(db_session, "Second")
    for p in (p1, p2):
        _add_receipt_ref(db_session, p)
    db_session.commit()

    call_count = {"n": 0}
    def _fake(name, *a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (_jpeg_bytes(), "gemini")
        raise RuntimeError("simulated provider crash")

    products = find_products_needing_images(db_session)
    with patch("src.backend.backfill_product_images.fetch_product_image", side_effect=_fake):
        stats = backfill_images_for_products(db_session, products)

    assert stats["fetched"] == 1
    assert stats["failed"] == 1
    snaps = db_session.query(ProductSnapshot).all()
    assert len(snaps) == 1


def test_excludes_non_product_names(db_session):
    from src.backend.backfill_product_images import find_products_needing_images

    noise = ["Service Fee", "Sales Tax", "Subtotal", "Delivery", "Bag Charge"]
    for name in noise:
        p = _add_product(db_session, name)
        _add_receipt_ref(db_session, p)
    db_session.commit()

    out = find_products_needing_images(db_session)
    names = {r.name for r in out}
    assert names.isdisjoint(set(noise))


def test_meaningful_products_pass_filter(db_session):
    from src.backend.backfill_product_images import find_products_needing_images

    real = ["Bananas", "Chicken Wings", "Basmati Rice"]
    for name in real:
        p = _add_product(db_session, name)
        _add_receipt_ref(db_session, p)
    db_session.commit()

    out = find_products_needing_images(db_session)
    names = {r.name for r in out}
    assert set(real).issubset(names)
