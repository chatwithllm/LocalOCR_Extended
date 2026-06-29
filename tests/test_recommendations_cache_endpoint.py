import os
os.environ["DATABASE_URL"] = "sqlite://"
import pytest

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    a = create_app(); a.config["TESTING"] = True
    yield a

def test_refresh_then_read_cache(app, monkeypatch):
    from flask import g
    import src.backend.generate_recommendations as gr
    from src.backend.create_flask_application import _get_db
    monkeypatch.setattr(gr, "generate_ai_recommendations",
        lambda: ([{"product_id": 1, "product_name": "Milk", "reason": "due",
                   "confidence": 0.9, "source": "ai"}], "ai"))
    _, SF = _get_db(); s = SF()
    with app.test_request_context():
        g.db_session = s
        gr.refresh_recommendation_cache()
        s.commit()
        row = gr.read_latest_cache(s, scope="household")
    assert row["source"] == "ai"
    assert row["payload"][0]["product_name"] == "Milk"
