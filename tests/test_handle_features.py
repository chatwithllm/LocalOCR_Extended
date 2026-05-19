import os
import pytest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")


@pytest.fixture
def client():
    with patch("src.backend.setup_mqtt_connection.setup_mqtt_connection"), \
         patch("src.backend.setup_mqtt_connection.publish_message"), \
         patch("src.backend.schedule_daily_recommendations.start_recommendation_scheduler"):
        from src.backend.create_flask_application import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def test_features_page_serves_html_without_auth(client):
    """GET /features returns 200 without session."""
    resp = client.get("/features")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")


def test_features_data_requires_auth(client):
    """GET /features/data without session returns 401."""
    resp = client.get("/features/data")
    assert resp.status_code == 401


def test_features_data_with_auth(client):
    """GET /features/data with valid session returns JS content-type."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["household_id"] = 1
        sess["session_version"] = 0  # must match user.session_version default
    resp = client.get("/features/data")
    assert resp.status_code == 200
    assert "javascript" in resp.content_type
