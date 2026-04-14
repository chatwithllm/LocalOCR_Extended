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
        from src.backend.initialize_database_schema import Base, BillMeta, Purchase
        
        app = create_app()
        app.config["TESTING"] = True
        
        # Clean the db completely for phase 4 logic isolation
        from src.backend.create_flask_application import _get_db
        _, SessionFactory = _get_db()
        session = SessionFactory()
        session.query(BillMeta).delete()
        session.query(Purchase).filter(Purchase.domain == "utility_bill").delete()
        session.commit()
        session.close()

        yield app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_header():
    return {"Authorization": "Bearer test-admin-token"}

def test_phase4_smoke_test_obligation_slots(app, client, auth_header):
    """Smoke test to verify Phase 4: Monthly projection correctly mixes fulfilled vs missing bills."""
    
    # 1. Create a manually entered recurring bill for May 2026.
    ocr_payload_may = {
        "receipt_type": "utility_bill",
        "data": {
            "store": "Water Company Phase 4",
            "total": 55.20,
            "date": "2026-05-10", 
            "bill_provider_name": "Water Company Phase 4",
            "bill_provider_type": "water",
            "bill_due_date": "2026-05-25", 
            "items": []
        }
    }
    
    # Upload it. (The planning_month will be 2026-05 based on due date)
    resp_may = client.post("/receipts/manual", json=ocr_payload_may, headers=auth_header)
    assert resp_may.status_code == 201

    # 2. Add ANOTHER bill for totally unrelated Internet company in May 2026.
    ocr_payload_internet = {
        "receipt_type": "utility_bill",
        "data": {
            "store": "Internet Phase 4",
            "total": 105.00,
            "date": "2026-05-15", 
            "bill_provider_name": "Internet Phase 4",
            "bill_provider_type": "internet",
            "bill_due_date": "2026-05-30", 
            "items": []
        }
    }
    resp_int = client.post("/receipts/manual", json=ocr_payload_internet, headers=auth_header)
    assert resp_int.status_code == 201
    
    # 3. Create a bill for Internet in June 2026 (so internet is fulfilled in June)
    ocr_payload_internet_june = {
        "receipt_type": "utility_bill",
        "data": {
            "store": "Internet Phase 4",
            "total": 110.00,  # Price hike
            "date": "2026-06-15", 
            "bill_provider_name": "Internet Phase 4",
            "bill_provider_type": "internet",
            "bill_due_date": "2026-06-30", 
            "items": []
        }
    }
    resp_int_june = client.post("/receipts/manual", json=ocr_payload_internet_june, headers=auth_header)
    assert resp_int_june.status_code == 201

    # 4. Now, fetch the projection for June 2026!
    # Expected: 
    # - "Internet Phase 4" should show as an ACTUAL slot (since we entered it for June)
    # - "Water Company Phase 4" should show as a PROJECTED/MISSING slot (since we entered it for May but not June)
    
    proj_resp = client.get("/receipts/bills/projection/2026-06", headers=auth_header)
    assert proj_resp.status_code == 200, f"Projection endpoint failed: {proj_resp.get_data(as_text=True)}"
    
    data = proj_resp.get_json()
    assert data["planning_month"] == "2026-06"
    slots = data["slots"]
    
    assert len(slots) == 2, f"Expected 2 slots, got {len(slots)}. Slots: {slots}"
    
    # Sort them by provider to be sure of order for asserting
    slots.sort(key=lambda s: s["provider_name"])
    
    # The First slot alphabetically is "Internet Phase 4"
    internet_slot = slots[0]
    assert internet_slot["provider_name"] == "Internet Phase 4"
    assert internet_slot["slot_type"] == "actual" # We actually entered it
    assert internet_slot["amount"] == 110.00 # June amount
    assert internet_slot["payment_status"] == "upcoming"
    
    # The Second is "Water Company Phase 4"
    water_slot = slots[1]
    assert water_slot["provider_name"] == "Water Company Phase 4"
    assert water_slot["slot_type"] == "projected" # We haven't entered June water bill yet
    assert water_slot["payment_status"] == "not_yet_entered"
    assert water_slot["amount"] == 55.20 # It should pull the estimation from May 2026!

    print("Phase 4 Smoke Test Passed! Projection generated correct blend of ACTUAL and PROJECTED obligations.")
