import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

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

def test_phase5_bill_extraction_logic(app):
    """Verify that household bills use the correct prompt and skip item validation."""
    from src.backend.extract_receipt_data import process_receipt
    from src.backend.initialize_database_schema import BillMeta, Purchase
    from src.backend.create_flask_application import _get_db

    # Mock extraction responses
    mock_bill_data = {
        "bill_provider_name": "Test Power Co",
        "bill_provider_type": "electricity",
        "bill_service_types": ["electricity"],
        "bill_account_label": "12345",
        "bill_service_period_start": "2026-04-01",
        "bill_service_period_end": "2026-04-30",
        "bill_due_date": "2026-05-15",
        "bill_billing_cycle_month": "2026-04",
        "bill_is_recurring": True,
        "date": "2026-05-01",
        "total": 120.50,
        "store": "Test Power Co",
        "items": [], # Empty items allowed for bills
        "confidence": 0.99
    }

    with patch("src.backend.extract_receipt_data._extract_best_receipt_candidate") as mock_ocr:
        mock_ocr.return_value = (mock_bill_data, "gemini")
        
        # Test processing with a bill hint
        from flask import g
        with app.app_context():
            _, SessionFactory = _get_db()
            g.db_session = SessionFactory()
            
            result = process_receipt(
                image_path="dummy.png", 
                receipt_type_hint="utility_bill",
                user_id=1
            )
            
            assert result["status"] == "processed"
            assert result["receipt_type"] == "utility_bill"
            assert "purchase_id" in result

            # Verify BillMeta was created correctly
            bill_meta = g.db_session.query(BillMeta).filter_by(purchase_id=result["purchase_id"]).first()
            
            assert bill_meta is not None
            assert bill_meta.provider_name == "Test Power Co"
            assert bill_meta.due_date.strftime("%Y-%m-%d") == "2026-05-15"
            assert bill_meta.is_recurring is True
            
            g.db_session.close()

def test_phase5_prompt_selection():
    """Verify that the correct prompt string is picked for bills."""
    from src.backend.call_gemini_vision_api import _build_prompt, RECEIPT_EXTRACTION_PROMPT, BILL_EXTRACTION_PROMPT
    
    # Test grocery
    p_grocery = _build_prompt(RECEIPT_EXTRACTION_PROMPT, None, mode_hint="grocery")
    assert "Analyze this receipt image" in p_grocery
    assert "Analyze this household bill" not in p_grocery

    # Test utility_bill
    p_bill = _build_prompt(RECEIPT_EXTRACTION_PROMPT, None, mode_hint="utility_bill")
    assert "Analyze this household bill" in p_bill
    assert "bill_provider_name" in p_bill

    # Test household_bill
    p_h_bill = _build_prompt(RECEIPT_EXTRACTION_PROMPT, None, mode_hint="household_bill")
    assert "Analyze this household bill" in p_h_bill
