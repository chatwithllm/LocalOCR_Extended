import os
import pytest
from datetime import datetime
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["INITIAL_ADMIN_TOKEN"] = "test-admin-token"

@pytest.fixture
def app():
    with patch("src.backend.setup_mqtt_connection.setup_mqtt_connection"), \
         patch("src.backend.setup_mqtt_connection.publish_message"), \
         patch("src.backend.schedule_daily_recommendations.start_recommendation_scheduler"):

        from src.backend.create_flask_application import create_app
        app = create_app()
        app.config["TESTING"] = True
        yield app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_header():
    return {"Authorization": "Bearer test-admin-token"}

def test_phase2_smoke_test_derives_planning_month(app, client, auth_header):
    """Smoke test to verify Phase 2: Manual receipt endpoint triggers planning month engine."""
    
    # Dummy OCR data representing a utility bill
    ocr_payload = {
        "receipt_type": "utility_bill",
        "data": {
            "store": "Water Company",
            "total": 55.20,
            "date": "2026-05-10", # Receipt generated on May 10th
            "bill_provider_name": "Water Company",
            "bill_provider_type": "water",
            "bill_due_date": "2026-06-03", # Due date month should drive planning month
            "items": []
        }
    }

    # 1. Enter the manual receipt
    response = client.post("/receipts/manual", json=ocr_payload, headers=auth_header)
    assert response.status_code == 201
    
    purchase_id = response.get_json()["purchase_id"]
    
    # 2. Fetch the receipt details from the DB and assert planning_month is set using the engine
    from src.backend.initialize_database_schema import BillMeta
    from src.backend.create_flask_application import _get_db
    
    with app.app_context():
        _, SessionFactory = _get_db()
        session = SessionFactory()
        bill_meta = session.query(BillMeta).filter_by(purchase_id=purchase_id).first()
        
        assert bill_meta is not None
        assert bill_meta.provider_name == "Water Company"
        assert bill_meta.planning_month == "2026-06", f"Engine incorrectly computed {bill_meta.planning_month}"
        session.close()
