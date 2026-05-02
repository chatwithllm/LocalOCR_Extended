"""
Tests for ORM columns added in Task 2 (inventory true-state feature).
"""


def test_inventory_has_new_columns():
    from src.backend.initialize_database_schema import Inventory
    cols = {c.name for c in Inventory.__table__.columns}
    assert {"expires_at", "expires_at_system", "expires_source", "last_purchased_at"}.issubset(cols)


def test_category_shelf_life_default_model_exists():
    from src.backend.initialize_database_schema import CategoryShelfLifeDefault
    cols = {c.name for c in CategoryShelfLifeDefault.__table__.columns}
    assert cols == {"category", "location_default", "shelf_life_days"}


def test_backfill_floors_to_today_plus_7(tmp_path):
    from datetime import date, datetime, timedelta, timezone
    from src.backend.initialize_database_schema import (
        Base, CategoryShelfLifeDefault, Inventory, Product, Purchase, ReceiptItem,
        Store, create_db_engine, create_session_factory,
    )
    from src.backend.active_inventory import backfill_inventory_truth

    db = tmp_path / "bf.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()
    s.add(CategoryShelfLifeDefault(category="produce", location_default="Fridge", shelf_life_days=7))
    s.add(CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0))
    store = Store(name="T"); s.add(store); s.flush()
    prod = Product(name="Banana", category="produce"); s.add(prod); s.flush()
    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    pur = Purchase(store_id=store.id, total_amount=1.0, date=long_ago, transaction_type="purchase")
    s.add(pur); s.flush()
    s.add(ReceiptItem(purchase_id=pur.id, product_id=prod.id, quantity=1, unit_price=1.0))
    s.add(Inventory(product_id=prod.id, quantity=1))
    s.commit()

    backfill_inventory_truth(s)
    inv = s.query(Inventory).filter_by(product_id=prod.id).one()
    assert inv.expires_at_system >= date.today() + timedelta(days=7)
    assert inv.expires_source == "system"


def test_backfill_skips_already_migrated(tmp_path):
    from datetime import date
    from src.backend.initialize_database_schema import (
        Base, CategoryShelfLifeDefault, Inventory, Product,
        create_db_engine, create_session_factory,
    )
    from src.backend.active_inventory import backfill_inventory_truth

    db = tmp_path / "bf2.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()
    s.add(CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0))
    prod = Product(name="X", category="other"); s.add(prod); s.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Bathroom",
                    expires_at=date(2030, 1, 1), expires_at_system=date(2030, 1, 1),
                    expires_source="user")
    s.add(inv); s.commit()
    backfill_inventory_truth(s)
    refreshed = s.query(Inventory).filter_by(product_id=prod.id).one()
    assert refreshed.location == "Bathroom"
    assert refreshed.expires_source == "user"
    assert refreshed.expires_at == date(2030, 1, 1)
