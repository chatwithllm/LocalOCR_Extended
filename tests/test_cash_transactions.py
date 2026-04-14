import os
from unittest.mock import patch

import pytest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["INITIAL_ADMIN_TOKEN"] = "test-admin-token"


@pytest.fixture
def app():
    with patch("src.backend.setup_mqtt_connection.setup_mqtt_connection"), \
         patch("src.backend.setup_mqtt_connection.publish_message"), \
         patch("src.backend.schedule_daily_recommendations.start_recommendation_scheduler"):
        from src.backend.create_flask_application import create_app
        from src.backend.create_flask_application import _get_db
        from src.backend.initialize_database_schema import (
            BillProvider,
            BillServiceLine,
            CashTransaction,
            Purchase,
            Store,
        )

        app = create_app()
        app.config["TESTING"] = True

        _, SessionFactory = _get_db()

        def _reset_state():
            session = SessionFactory()
            session.query(CashTransaction).delete()
            session.query(BillServiceLine).delete()
            session.query(BillProvider).delete()
            session.query(Purchase).delete()
            session.query(Store).delete()
            session.commit()
            session.close()

        _reset_state()
        yield app
        _reset_state()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_header():
    return {"Authorization": "Bearer test-admin-token"}


def test_cash_transaction_creates_purchase_and_appears_in_bills_and_budget(
    client, auth_header
):
    payload = {
        "amount": 80,
        "transaction_date": "2026-04-10",
        "payment_method": "cash",
        "provider": {
            "provider_name": "Math Tutor",
            "provider_category": "personal_service",
            "preferred_contact_method": "app",
            "payment_handle": "@mathtutor",
        },
        "service_line": {
            "service_type": "tutoring",
            "account_label": "Kid A",
            "expected_payment_day": 1,
            "planning_month_rule": "paid_date_month",
            "preferred_payment_method": "cash",
        },
    }

    response = client.post("/cash-transactions", json=payload, headers=auth_header)
    assert response.status_code == 201, response.get_data(as_text=True)
    data = response.get_json()
    assert data["transaction"]["planning_month"] == "2026-04"
    assert data["transaction"]["purchase_id"]
    assert data["provider"]["provider_category"] == "personal_service"

    providers_response = client.get("/receipts/bill-providers", headers=auth_header)
    assert providers_response.status_code == 200
    providers = providers_response.get_json()["providers"]
    tutor_provider = next(
        provider for provider in providers if provider["canonical_name"] == "Math Tutor"
    )
    assert tutor_provider["payment_handle"] == "@mathtutor"

    recurring_response = client.get(
        "/analytics/recurring-obligations?month=2026-04", headers=auth_header
    )
    assert recurring_response.status_code == 200
    obligations = recurring_response.get_json()["obligations"]
    tutor_obligation = next(
        item for item in obligations if item["provider_name"] == "Math Tutor"
    )
    assert tutor_obligation["provider_category"] == "personal_service"
    assert tutor_obligation["status"] == "entered"
    assert tutor_obligation["actual_amount"] == 80.0

    budget_response = client.get(
        "/budget/status?month=2026-04&domain=household_obligations",
        headers=auth_header,
    )
    assert budget_response.status_code == 200
    assert budget_response.get_json()["spent"] == 80.0


def test_personal_service_projection_marks_missing_or_overdue_when_unpaid(
    app, client, auth_header
):
    create_response = client.post(
        "/cash-transactions",
        json={
            "amount": 120,
            "transaction_date": "2026-03-05",
            "payment_method": "app_transfer",
            "provider": {
                "provider_name": "Dance Studio",
                "provider_category": "personal_service",
            },
            "service_line": {
                "service_type": "lessons_dance",
                "account_label": "Kid B",
                "expected_payment_day": 1,
                "planning_month_rule": "due_date_month",
                "preferred_payment_method": "app_transfer",
            },
        },
        headers=auth_header,
    )
    assert create_response.status_code == 201, create_response.get_data(as_text=True)

    with app.app_context():
        from src.backend.create_flask_application import _get_db
        from src.backend.generate_bill_projections import generate_monthly_obligation_slots

        _, SessionFactory = _get_db()
        session = SessionFactory()
        slots = generate_monthly_obligation_slots(session, "2026-04")
        session.close()

    dance_slot = next(slot for slot in slots if slot["provider_name"] == "Dance Studio")
    assert dance_slot["slot_type"] == "projected"
    assert dance_slot["source_type"] == "cash_transaction"
    assert dance_slot["payment_status"] in {"upcoming", "overdue", "missing"}
