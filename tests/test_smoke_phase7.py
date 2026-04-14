import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date

os.environ["DATABASE_URL"] = "sqlite://"

@pytest.fixture
def app():
    from src.backend.create_flask_application import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app

def test_phase7_multi_service_allocation(app):
    from src.backend.extract_receipt_data import _save_bill_meta
    from src.backend.initialize_database_schema import BillMeta, Purchase, BillAllocation, BillServiceLine
    from src.backend.create_flask_application import _get_db
    from flask import g

    mock_ocr_data = {
        "bill_provider_name": "Citizens Energy",
        "bill_provider_type": "utility",
        "bill_account_label": "MAIN-ST",
        "bill_allocations": [
            {"service_type": "water", "amount": 40.0, "description": "Water portion"},
            {"service_type": "gas", "amount": 60.0, "description": "Gas portion"}
        ],
        "total": 100.0,
        "date": "2026-05-01"
    }

    with app.app_context():
        _, SessionFactory = _get_db()
        session = SessionFactory()
        
        # 1. Create a purchase
        p = Purchase(total_amount=100.0, date=date(2026, 5, 1))
        session.add(p)
        session.commit()
        
        # 2. Run meta save
        _save_bill_meta(session, p.id, mock_ocr_data, purchase_date=p.date)
        session.commit()
        
        # 3. Verify allocations
        allocations = session.query(BillAllocation).filter_by(purchase_id=p.id).all()
        assert len(allocations) == 2
        
        water_alloc = next(a for a in allocations if a.amount == 40.0)
        gas_alloc = next(a for a in allocations if a.amount == 60.0)
        
        assert water_alloc.description == "Water portion"
        
        # Verify service lines were created
        water_service = session.get(BillServiceLine, water_alloc.service_line_id)
        assert water_service.service_type == "water"
        
        session.close()
