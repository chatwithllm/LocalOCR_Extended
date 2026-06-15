import os
os.environ["DATABASE_URL"] = "sqlite://"
from datetime import datetime, timedelta, timezone
import pytest

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    a = create_app(); a.config["TESTING"] = True
    yield a

def _session():
    from src.backend.create_flask_application import _get_db
    _, SF = _get_db(); return SF()

def _buy(s, product, days_ago_list):
    from src.backend.initialize_database_schema import Purchase, ReceiptItem
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for d in days_ago_list:
        p = Purchase(date=now - timedelta(days=d)); s.add(p); s.flush()
        s.add(ReceiptItem(purchase_id=p.id, product_id=product.id, quantity=1, unit_price=0.0))
    s.commit()

def test_recurring_item_has_intervals_and_not_oneoff(app):
    from src.backend.initialize_database_schema import Product
    from src.backend.recommendation_features import build_recommendation_candidates
    s = _session()
    milk = Product(name="Milk", category="Dairy"); s.add(milk); s.commit()
    _buy(s, milk, [28, 21, 14, 7])
    cands = build_recommendation_candidates(s, now=datetime(2026, 6, 1, tzinfo=timezone.utc), cap=30)
    milk_c = next(c for c in cands if c["name"] == "Milk")
    assert milk_c["purchase_count"] == 4
    assert milk_c["one_off"] is False
    assert 6 <= milk_c["mean_interval"] <= 8
    assert milk_c["days_since_last"] == 7

def test_single_purchase_is_oneoff(app):
    from src.backend.initialize_database_schema import Product
    from src.backend.recommendation_features import build_recommendation_candidates
    s = _session()
    charcoal = Product(name="Charcoal", category="Outdoor"); s.add(charcoal); s.commit()
    _buy(s, charcoal, [60])
    cands = build_recommendation_candidates(s, now=datetime(2026, 6, 1, tzinfo=timezone.utc), cap=30)
    c = next(c for c in cands if c["name"] == "Charcoal")
    assert c["one_off"] is True

def test_cobought_items_are_linked(app):
    from src.backend.initialize_database_schema import Product, Purchase, ReceiptItem
    from src.backend.recommendation_features import build_recommendation_candidates
    from datetime import datetime, timezone
    s = _session()
    shells = Product(name="Taco Shells", category="Pantry"); s.add(shells)
    salsa = Product(name="Salsa", category="Pantry"); s.add(salsa); s.commit()
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for _ in range(3):
        p = Purchase(date=now); s.add(p); s.flush()
        s.add(ReceiptItem(purchase_id=p.id, product_id=shells.id, unit_price=0.0))
        s.add(ReceiptItem(purchase_id=p.id, product_id=salsa.id, unit_price=0.0))
    s.commit()
    cands = build_recommendation_candidates(s, now=now, cap=30)
    shells_c = next(c for c in cands if c["name"] == "Taco Shells")
    assert "Salsa" in shells_c["cobought_with"]
