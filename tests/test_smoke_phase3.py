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

def test_phase3_smoke_test_bill_lifecycle(app, client, auth_header):
    """Smoke test to verify Phase 3: Bill Lifecycle And Paid-State Model."""
    
    # 1. Create a dummy receipt/purchase manually
    ocr_payload = {
        "receipt_type": "utility_bill",
        "data": {
            "store": "Test Utility Phase 3",
            "total": 95.00,
            "date": "2026-06-02",
            "bill_provider_name": "Test Utility Phase 3",
            "bill_provider_type": "internet",
            "bill_due_date": "2026-06-25",
            "items": []
        }
    }

    # Enter the manual receipt
    response = client.post("/receipts/manual", json=ocr_payload, headers=auth_header)
    assert response.status_code == 201
    purchase_id = response.get_json()["purchase_id"]
    
    # 2. Check the database to confirm default status is 'upcoming'
    from src.backend.initialize_database_schema import BillMeta
    from src.backend.create_flask_application import _get_db
    
    with app.app_context():
        _, SessionFactory = _get_db()
        session = SessionFactory()
        
        bill_meta = session.query(BillMeta).filter_by(purchase_id=purchase_id).first()
        assert bill_meta is not None, "BillMeta was not saved"
        assert bill_meta.payment_status == "upcoming", f"Default status should be upcoming, got {bill_meta.payment_status}"
        assert bill_meta.payment_confirmed_at is None, "Payment confirmed should default to null"
        
        session.close()
    
    # 3. Mark the bill as PAID
    payment_update_payload = {"payment_status": "paid"}
    update_response = client.put(
        f"/receipts/{purchase_id}/bill-status",  
        json=payment_update_payload,
        headers=auth_header
    )
    assert update_response.status_code == 200, f"Status update failed: {update_response.get_data(as_text=True)}"
    
    with app.app_context():
        session = SessionFactory()
        bill_meta = session.query(BillMeta).filter_by(purchase_id=purchase_id).first()
        assert bill_meta.payment_status == "paid", "Status did not formally update to paid"
        assert bill_meta.payment_confirmed_at is not None, "payment_confirmed_at should be fully marked!"
        session.close()
        
    # 4. Rollback to OVERDUE to test the unset behaviour
    rollback_payload = {"payment_status": "overdue"}
    rollback_response = client.put(
        f"/receipts/{purchase_id}/bill-status",
        json=rollback_payload,
        headers=auth_header
    )
    assert rollback_response.status_code == 200
    
    with app.app_context():
        session = SessionFactory()
        bill_meta = session.query(BillMeta).filter_by(purchase_id=purchase_id).first()
        assert bill_meta.payment_status == "overdue", "Status did not rollback to overdue"
        assert bill_meta.payment_confirmed_at is None, "payment_confirmed_at should be unlinked/nullified when rolling back from paid!"
        session.close()
