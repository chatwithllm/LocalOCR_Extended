# tests/test_manage_kitchen.py
import pytest
from src.backend.manage_kitchen import category_for_product, DEFAULT_CATEGORIES, CATEGORY_EMOJI


class _StubProduct:
    def __init__(self, category):
        self.category = category


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Produce", "Produce"),
        ("produce", "Produce"),
        ("PRODUCE", "Produce"),
        ("Vegetables", "Produce"),
        ("Fruit", "Produce"),
        ("Fruits", "Produce"),
        ("Meat", "Meat"),
        ("Poultry", "Meat"),
        ("Seafood", "Meat"),
        ("Fish", "Meat"),
        ("Dairy", "Dairy"),
        ("Cheese", "Dairy"),
        ("Yogurt", "Dairy"),
        ("Bakery", "Bakery"),
        ("Bread", "Bakery"),
        ("Pantry", "Pantry"),
        ("Snacks", "Pantry"),
        ("Beverages", "Pantry"),
        ("Spices", "Pantry"),
        ("Condiments", "Pantry"),
        (None, "Other"),
        ("", "Other"),
        ("   ", "Other"),
        ("weird random thing", "Other"),
    ],
)
def test_category_for_product_truth_table(raw, expected):
    assert category_for_product(_StubProduct(raw)) == expected


def test_default_categories_are_in_emoji_map():
    for cat in DEFAULT_CATEGORIES:
        assert cat in CATEGORY_EMOJI


def test_default_categories_order():
    assert DEFAULT_CATEGORIES == [
        "Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other",
    ]


from datetime import datetime, timedelta, timezone

from src.backend.initialize_database_schema import (
    Base, Product, ProductSnapshot, ShoppingListItem, ShoppingSession,
    Purchase, ReceiptItem, Store, create_db_engine, create_session_factory,
)
from src.backend.manage_kitchen import get_kitchen_catalog


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "kitchen.db"
    engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = create_session_factory(engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _fresh_product(session, name, category="Produce", **kw):
    p = Product(name=name, category=category, **kw)
    session.add(p)
    session.flush()
    return p


def _record_purchase(session, product, days_ago, store=None):
    """Insert one Purchase + one ReceiptItem `days_ago` days from now."""
    if store is None:
        store = Store(name="Costco")
        session.add(store)
        session.flush()
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    pur = Purchase(store_id=store.id, total_amount=1.0, date=when)
    session.add(pur)
    session.flush()
    ri = ReceiptItem(
        purchase_id=pur.id, product_id=product.id,
        quantity=1, unit_price=1.0,
    )
    session.add(ri)
    session.flush()


def test_empty_db_returns_empty_buckets(db_session):
    out = get_kitchen_catalog(db_session)
    assert out["frequent"] == []
    assert set(out["categories"].keys()) == {
        "Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other",
    }
    for tiles in out["categories"].values():
        assert tiles == []
    assert out["on_list_product_ids"] == []


def test_categorization_by_product_category(db_session):
    _fresh_product(db_session, "Spinach", category="Produce")
    _fresh_product(db_session, "Chicken", category="Poultry")
    _fresh_product(db_session, "Milk", category="Dairy")
    _fresh_product(db_session, "Mystery", category=None)
    db_session.commit()

    out = get_kitchen_catalog(db_session)
    names_in = lambda b: {t["name"] for t in out["categories"][b]}
    assert "Spinach" in names_in("Produce")
    assert "Chicken" in names_in("Meat")
    assert "Milk"    in names_in("Dairy")
    assert "Mystery" in names_in("Other")


def test_purchase_count_window(db_session):
    p = _fresh_product(db_session, "Tomatoes", category="Produce")
    _record_purchase(db_session, p, days_ago=10)
    _record_purchase(db_session, p, days_ago=80)
    _record_purchase(db_session, p, days_ago=120)  # outside 90 d window
    db_session.commit()

    out = get_kitchen_catalog(db_session)
    tile = next(t for t in out["categories"]["Produce"] if t["name"] == "Tomatoes")
    assert tile["purchase_count"] == 2


def test_sort_within_bucket_by_count_desc(db_session):
    a = _fresh_product(db_session, "Apple", category="Produce")
    b = _fresh_product(db_session, "Banana", category="Produce")
    c = _fresh_product(db_session, "Carrot", category="Produce")
    for _ in range(5): _record_purchase(db_session, a, days_ago=10)
    for _ in range(2): _record_purchase(db_session, b, days_ago=10)
    _record_purchase(db_session, c, days_ago=10)
    db_session.commit()

    names = [t["name"] for t in get_kitchen_catalog(db_session)["categories"]["Produce"]]
    assert names[:3] == ["Apple", "Banana", "Carrot"]


def test_frequent_bucket_top_n_across_categories(db_session):
    a = _fresh_product(db_session, "Apple", category="Produce")
    m = _fresh_product(db_session, "Milk",  category="Dairy")
    for _ in range(7): _record_purchase(db_session, a, days_ago=5)
    for _ in range(3): _record_purchase(db_session, m, days_ago=5)
    db_session.commit()

    freq = get_kitchen_catalog(db_session)["frequent"]
    assert [t["name"] for t in freq[:2]] == ["Apple", "Milk"]
    assert all(t["purchase_count"] >= 1 for t in freq)


def test_image_url_from_latest_snapshot(db_session):
    p = _fresh_product(db_session, "Eggs", category="Dairy")
    db_session.add_all([
        ProductSnapshot(product_id=p.id, status="resolved",
                        image_path="/tmp/old.jpg"),
        ProductSnapshot(product_id=p.id, status="resolved",
                        image_path="/tmp/new.jpg"),
    ])
    db_session.commit()

    tile = next(
        t for t in get_kitchen_catalog(db_session)["categories"]["Dairy"]
        if t["name"] == "Eggs"
    )
    assert tile["image_url"].endswith(f"/product-snapshots/{tile['_latest_snapshot_id']}/image")
    assert tile["fallback_emoji"] == "🥛"


def test_no_snapshot_returns_none_image_url(db_session):
    p = _fresh_product(db_session, "Lettuce", category="Produce")
    db_session.commit()

    tile = next(
        t for t in get_kitchen_catalog(db_session)["categories"]["Produce"]
        if t["name"] == "Lettuce"
    )
    assert tile["image_url"] is None
    assert tile["fallback_emoji"] == "🥬"


def test_on_list_product_ids_from_active_session(db_session):
    p = _fresh_product(db_session, "Bread", category="Bakery")
    sess = ShoppingSession(name="trip", status="active")
    db_session.add(sess)
    db_session.flush()
    db_session.add(ShoppingListItem(
        product_id=p.id, name="Bread", category="Bakery",
        quantity=1, status="open", shopping_session_id=sess.id,
    ))
    db_session.commit()

    out = get_kitchen_catalog(db_session)
    assert p.id in out["on_list_product_ids"]


def test_finalized_session_items_not_in_on_list(db_session):
    p = _fresh_product(db_session, "Croissant", category="Bakery")
    sess = ShoppingSession(name="old", status="finalized")
    db_session.add(sess)
    db_session.flush()
    db_session.add(ShoppingListItem(
        product_id=p.id, name="Croissant", category="Bakery",
        quantity=1, status="purchased", shopping_session_id=sess.id,
    ))
    db_session.commit()

    out = get_kitchen_catalog(db_session)
    assert p.id not in out["on_list_product_ids"]
