import os
os.environ["DATABASE_URL"] = "sqlite://"
import pytest

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    a = create_app(); a.config["TESTING"] = True
    yield a

def _session():
    from src.backend.create_flask_application import _get_db
    _, SF = _get_db(); return SF()

def test_write_then_read_latest(app):
    from src.backend.recommendation_cache import write_cache, read_latest_cache
    s = _session()
    write_cache(s, scope="household", payload=[{"product_id": 1, "name": "Milk"}], source="ai")
    s.commit()
    row = read_latest_cache(s, scope="household")
    assert row is not None
    assert row["source"] == "ai"
    assert row["payload"][0]["name"] == "Milk"

def test_read_latest_returns_newest(app):
    from src.backend.recommendation_cache import write_cache, read_latest_cache
    s = _session()
    write_cache(s, scope="household", payload=[{"name": "old"}], source="heuristic")
    write_cache(s, scope="household", payload=[{"name": "new"}], source="ai")
    s.commit()
    row = read_latest_cache(s, scope="household")
    assert row["payload"][0]["name"] == "new"
    assert row["source"] == "ai"
