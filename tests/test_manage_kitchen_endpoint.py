import os
import pytest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")


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


def test_get_catalog_requires_auth(client):
    resp = client.get("/api/kitchen/catalog")
    assert resp.status_code in (401, 403)
