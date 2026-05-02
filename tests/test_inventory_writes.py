"""Unit tests for inventory_writes pure helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.backend.initialize_database_schema import (
    Base, CategoryShelfLifeDefault, Inventory, InventoryAdjustment,
    Product, Purchase, ReceiptItem,
    create_db_engine, create_session_factory,
)


@pytest.fixture
def session(tmp_path):
    db = tmp_path / "iw.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    S = create_session_factory(eng)
    s = S()
    s.add_all([
        CategoryShelfLifeDefault(category="dairy", location_default="Fridge", shelf_life_days=14),
        CategoryShelfLifeDefault(category="meat", location_default="Fridge", shelf_life_days=3),
        CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0),
    ])
    s.commit()
    yield s
    s.close()


def _purchase(s, when, txn="purchase"):
    p = Purchase(date=when, total_amount=1.0, transaction_type=txn)
    s.add(p); s.flush()
    return p


def test_upsert_creates_row(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Milk", category="dairy"); session.add(prod); session.flush()
    purchase = _purchase(session, datetime(2026, 5, 1, tzinfo=timezone.utc))
    item = ReceiptItem(purchase_id=purchase.id, product_id=prod.id, quantity=2, unit_price=3.0)
    session.add(item); session.flush()

    upsert_inventory_for_receipt_item(session, prod, item, purchase)
    inv = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert inv.quantity == 2
    assert inv.location == "Fridge"
    assert inv.expires_at_system == date(2026, 5, 15)
    assert inv.expires_at == date(2026, 5, 15)
    assert inv.expires_source == "system"


def test_upsert_extends_expiry_on_newer_purchase(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Steak", category="meat"); session.add(prod); session.flush()
    p1 = _purchase(session, datetime(2026, 5, 1, tzinfo=timezone.utc))
    i1 = ReceiptItem(purchase_id=p1.id, product_id=prod.id, quantity=1, unit_price=5.0)
    session.add(i1); session.flush()
    upsert_inventory_for_receipt_item(session, prod, i1, p1)
    p2 = _purchase(session, datetime(2026, 5, 4, tzinfo=timezone.utc))
    i2 = ReceiptItem(purchase_id=p2.id, product_id=prod.id, quantity=1, unit_price=5.0)
    session.add(i2); session.flush()
    upsert_inventory_for_receipt_item(session, prod, i2, p2)
    inv = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert inv.quantity == 2
    assert inv.expires_at_system == date(2026, 5, 7)
    assert inv.expires_at == date(2026, 5, 7)


def test_upsert_preserves_user_override(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Steak", category="meat"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2030, 1, 1), expires_at_system=date(2026, 5, 4),
                    expires_source="user")
    session.add(inv); session.flush()
    p = _purchase(session, datetime(2026, 5, 5, tzinfo=timezone.utc))
    item = ReceiptItem(purchase_id=p.id, product_id=prod.id, quantity=1, unit_price=5.0)
    session.add(item); session.flush()
    upsert_inventory_for_receipt_item(session, prod, item, p)
    refreshed = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert refreshed.expires_at == date(2030, 1, 1)
    assert refreshed.expires_at_system == date(2026, 5, 8)


def test_upsert_preserves_defer(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Steak", category="meat"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2026, 5, 10), expires_at_system=date(2026, 5, 4),
                    expires_source="defer")
    session.add(inv); session.flush()
    p = _purchase(session, datetime(2026, 5, 5, tzinfo=timezone.utc))
    item = ReceiptItem(purchase_id=p.id, product_id=prod.id, quantity=1, unit_price=5.0)
    session.add(item); session.flush()
    upsert_inventory_for_receipt_item(session, prod, item, p)
    refreshed = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert refreshed.expires_at == date(2026, 5, 10)
    assert refreshed.expires_at_system == date(2026, 5, 8)


def test_refund_decrements_and_clamps(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Milk", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge", expires_source="system")
    session.add(inv); session.flush()
    p = _purchase(session, datetime(2026, 5, 5, tzinfo=timezone.utc), txn="refund")
    item = ReceiptItem(purchase_id=p.id, product_id=prod.id, quantity=5, unit_price=3.0)
    session.add(item); session.flush()
    upsert_inventory_for_receipt_item(session, prod, item, p)
    refreshed = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert refreshed.quantity == 0


def test_unknown_category_uses_other(session):
    from src.backend.inventory_writes import upsert_inventory_for_receipt_item
    prod = Product(name="Toy", category="weird"); session.add(prod); session.flush()
    p = _purchase(session, datetime(2026, 5, 5, tzinfo=timezone.utc))
    item = ReceiptItem(purchase_id=p.id, product_id=prod.id, quantity=1, unit_price=10.0)
    session.add(item); session.flush()
    upsert_inventory_for_receipt_item(session, prod, item, p)
    inv = session.query(Inventory).filter_by(product_id=prod.id).one()
    assert inv.location == "Pantry"
    assert inv.expires_at_system is None


def test_apply_manual_patch_quantity(session):
    from src.backend.inventory_writes import apply_manual_patch
    prod = Product(name="Eggs", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=12, location="Fridge", expires_source="system")
    session.add(inv); session.flush()
    apply_manual_patch(session, inv, {"quantity": 6}, user_id=None)
    assert inv.quantity == 6
    adj = session.query(InventoryAdjustment).filter_by(product_id=prod.id).one()
    assert adj.quantity_delta == -6
    assert adj.reason == "manual_edit"


def test_apply_manual_patch_used_up(session):
    from src.backend.inventory_writes import apply_manual_patch
    prod = Product(name="Eggs", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=12, location="Fridge", expires_source="system")
    session.add(inv); session.flush()
    apply_manual_patch(session, inv, {"quantity": 0}, user_id=None)
    assert inv.quantity == 0
    adj = session.query(InventoryAdjustment).filter_by(product_id=prod.id).one()
    assert adj.reason == "consumed_all"


def test_apply_manual_patch_explicit_expiry_marks_user(session):
    from src.backend.inventory_writes import apply_manual_patch
    prod = Product(name="Cheese", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2026, 5, 3), expires_at_system=date(2026, 5, 3),
                    expires_source="system")
    session.add(inv); session.flush()
    apply_manual_patch(session, inv, {"expires_at": "2026-06-01"}, user_id=None)
    assert inv.expires_at == date(2026, 6, 1)
    assert inv.expires_at_system == date(2026, 5, 3)
    assert inv.expires_source == "user"


def test_apply_manual_patch_defer_days_accumulates(session):
    from src.backend.inventory_writes import apply_manual_patch
    prod = Product(name="Pasta", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2026, 5, 3), expires_at_system=date(2026, 5, 3),
                    expires_source="system")
    session.add(inv); session.flush()
    apply_manual_patch(session, inv, {"defer_days": 3}, user_id=None)
    assert inv.expires_at == date(2026, 5, 6)
    assert inv.expires_source == "defer"
    apply_manual_patch(session, inv, {"defer_days": 3}, user_id=None)
    assert inv.expires_at == date(2026, 5, 9)


def test_reset_expiry_to_system(session):
    from src.backend.inventory_writes import reset_expiry_to_system
    prod = Product(name="Pasta", category="dairy"); session.add(prod); session.flush()
    inv = Inventory(product_id=prod.id, quantity=1, location="Fridge",
                    expires_at=date(2026, 6, 1), expires_at_system=date(2026, 5, 3),
                    expires_source="user")
    session.add(inv); session.flush()
    reset_expiry_to_system(session, inv, user_id=None)
    assert inv.expires_at == date(2026, 5, 3)
    assert inv.expires_source == "system"
