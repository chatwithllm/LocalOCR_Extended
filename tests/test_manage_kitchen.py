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
    Purchase, ReceiptItem, Store, Inventory, PriceHistory,
    create_db_engine, create_session_factory,
)
from src.backend.manage_kitchen import get_kitchen_essentials


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


def _add_inventory(session, product, quantity, location="Pantry"):
    inv = Inventory(product_id=product.id, quantity=quantity, location=location)
    session.add(inv)
    session.flush()
    return inv


def test_product_essential_backup_default_false(db_session):
    p = _fresh_product(db_session, "Olive Oil", category="Pantry")
    db_session.commit()
    db_session.refresh(p)
    assert p.is_essential is False
    assert p.has_backup is False


def test_product_essential_backup_settable(db_session):
    p = _fresh_product(db_session, "Olive Oil", category="Pantry")
    p.is_essential = True
    p.has_backup = True
    db_session.commit()
    db_session.refresh(p)
    assert p.is_essential is True
    assert p.has_backup is True


def test_essentials_only_returns_tagged_products(db_session):
    a = _fresh_product(db_session, "Olive Oil", category="Pantry", is_essential=True)
    _fresh_product(db_session, "Sprinkles", category="Pantry", is_essential=False)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    names = [t["name"] for t in out["essentials"]]
    assert names == ["Olive Oil"]
    assert out["essentials"][0]["product_id"] == a.id


def test_essentials_excludes_non_product(db_session):
    _fresh_product(db_session, "Bag Fee", category="Other",
                   is_essential=True, is_non_product=True)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"] == []


def test_essentials_sorted_alphabetically(db_session):
    _fresh_product(db_session, "Zucchini", category="Produce", is_essential=True)
    _fresh_product(db_session, "Apples", category="Produce", is_essential=True)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert [t["name"] for t in out["essentials"]] == ["Apples", "Zucchini"]


def test_essentials_quantity_summed_across_locations(db_session):
    p = _fresh_product(db_session, "Milk", category="Dairy", is_essential=True)
    _add_inventory(db_session, p, 1, location="Fridge")
    _add_inventory(db_session, p, 2, location="Pantry")
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["quantity"] == 3.0


def test_essentials_quantity_zero_when_no_inventory(db_session):
    _fresh_product(db_session, "Salt", category="Pantry", is_essential=True)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["quantity"] == 0.0


def test_essentials_has_backup_reported(db_session):
    _fresh_product(db_session, "Paper Towels", category="Other",
                   is_essential=True, has_backup=True)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["has_backup"] is True


def test_essentials_on_list_reflects_active_session(db_session):
    p = _fresh_product(db_session, "Eggs", category="Dairy", is_essential=True)
    sess = ShoppingSession(status="active")
    db_session.add(sess)
    db_session.flush()
    db_session.add(ShoppingListItem(
        shopping_session_id=sess.id, product_id=p.id, status="open",
        name=p.name,
    ))
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["on_list"] is True


def test_suggested_only_when_no_essentials(db_session):
    p = _fresh_product(db_session, "Bananas", category="Produce")
    _record_purchase(db_session, p, days_ago=3)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"] == []
    assert [t["name"] for t in out["suggested"]] == ["Bananas"]


def test_suggested_empty_once_an_essential_exists(db_session):
    _fresh_product(db_session, "Coffee", category="Pantry", is_essential=True)
    p = _fresh_product(db_session, "Bananas", category="Produce")
    _record_purchase(db_session, p, days_ago=3)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert [t["name"] for t in out["essentials"]] == ["Coffee"]
    assert out["suggested"] == []


def test_suggested_includes_frequent_non_essential(db_session):
    e = _fresh_product(db_session, "Coffee", category="Pantry")
    _record_purchase(db_session, e, days_ago=2)
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert [t["name"] for t in out["suggested"]] == ["Coffee"]


def test_essentials_on_list_with_ready_to_bill_session(db_session):
    p = _fresh_product(db_session, "Butter", category="Dairy", is_essential=True)
    sess = ShoppingSession(status="ready_to_bill")
    db_session.add(sess)
    db_session.flush()
    db_session.add(ShoppingListItem(
        shopping_session_id=sess.id, product_id=p.id, status="open", name=p.name,
    ))
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["on_list"] is True


def test_essentials_latest_unit_price(db_session):
    p = _fresh_product(db_session, "Rice", category="Pantry", is_essential=True)
    db_session.add(PriceHistory(product_id=p.id, price=2.50,
                                date=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    db_session.flush()
    db_session.add(PriceHistory(product_id=p.id, price=3.75,
                                date=datetime(2026, 1, 2, tzinfo=timezone.utc)))
    db_session.commit()
    out = get_kitchen_essentials(db_session)
    assert out["essentials"][0]["latest_unit_price"] == 3.75
