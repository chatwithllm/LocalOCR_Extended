"""Unit tests for category shelf-life default lookup."""
import pytest
from src.backend.initialize_database_schema import (
    Base, CategoryShelfLifeDefault, create_db_engine, create_session_factory,
)


@pytest.fixture
def session(tmp_path):
    db = tmp_path / "csl.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    Session = create_session_factory(eng)
    s = Session()
    s.add_all([
        CategoryShelfLifeDefault(category="dairy", location_default="Fridge", shelf_life_days=14),
        CategoryShelfLifeDefault(category="other", location_default="Pantry", shelf_life_days=0),
    ])
    s.commit()
    yield s
    s.close()


def test_lookup_by_known_category(session):
    from src.backend.category_shelf_life import get_category_default
    d = get_category_default(session, "dairy")
    assert d.location_default == "Fridge"
    assert d.shelf_life_days == 14


def test_falls_back_to_other_when_unknown(session):
    from src.backend.category_shelf_life import get_category_default
    d = get_category_default(session, "made_up_category")
    assert d.category == "other"
    assert d.location_default == "Pantry"


def test_falls_back_to_sentinel_when_table_missing(tmp_path):
    from src.backend.category_shelf_life import get_category_default
    db = tmp_path / "empty.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    Session = create_session_factory(eng)
    s = Session()
    try:
        d = get_category_default(s, "anything")
        assert d.location_default == "Pantry"
        assert d.shelf_life_days == 0
    finally:
        s.close()


def test_none_category_falls_back_to_other(session):
    from src.backend.category_shelf_life import get_category_default
    d = get_category_default(session, None)
    assert d.category == "other"
