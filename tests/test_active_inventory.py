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
