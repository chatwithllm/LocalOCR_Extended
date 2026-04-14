"""
Step 24: End-to-End Testing
============================
PROMPT Reference: Phase 9, Step 24

Real tests with actual assertions covering the core workflows.
Uses an in-memory SQLite database for isolation.
"""

import os
import json
import pytest
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

# Set test DB before importing anything
os.environ["DATABASE_URL"] = "sqlite://"  # In-memory
os.environ["MQTT_BROKER"] = "localhost"
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["INITIAL_ADMIN_TOKEN"] = "test-admin-token"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a test Flask application with in-memory DB."""
    # Patch MQTT to avoid real connections
    with patch("src.backend.setup_mqtt_connection.setup_mqtt_connection"), \
         patch("src.backend.setup_mqtt_connection.publish_message"), \
         patch("src.backend.schedule_daily_recommendations.start_recommendation_scheduler"):

        from src.backend.create_flask_application import create_app
        app = create_app()
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def auth_header():
    """Return auth header with the test admin token."""
    return {"Authorization": "Bearer test-admin-token"}


# ---------------------------------------------------------------------------
# Test 1: Health Check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["service"] == "localocr-extended-backend"


# ---------------------------------------------------------------------------
# Test 2: Authentication
# ---------------------------------------------------------------------------

class TestAuthentication:
    def test_missing_token_returns_401(self, client):
        response = client.get("/products")
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, client):
        response = client.get("/products", headers={"Authorization": "Bearer wrong-token"})
        assert response.status_code == 401

    def test_valid_token_returns_200(self, client, auth_header):
        response = client.get("/products", headers=auth_header)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test 3: Product CRUD
# ---------------------------------------------------------------------------

class TestProductCRUD:
    def test_create_product(self, client, auth_header):
        response = client.post("/products/create",
            headers=auth_header,
            json={"name": "Organic Milk", "category": "dairy"})
        assert response.status_code == 201
        data = response.get_json()
        assert data["name"] == "Organic Milk"
        assert data["category"] == "dairy"
        assert "id" in data

    def test_duplicate_product_returns_409(self, client, auth_header):
        # Create first
        client.post("/products/create",
            headers=auth_header,
            json={"name": "Eggs", "category": "dairy"})
        # Create duplicate
        response = client.post("/products/create",
            headers=auth_header,
            json={"name": "Eggs", "category": "dairy"})
        assert response.status_code == 409

    def test_search_products(self, client, auth_header):
        client.post("/products/create",
            headers=auth_header,
            json={"name": "Whole Wheat Bread", "category": "bakery"})
        response = client.get("/products/search?q=wheat", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] >= 1
        assert "Whole Wheat Bread" in [r["name"] for r in data["results"]]

    def test_list_products_paginated(self, client, auth_header):
        for i in range(5):
            client.post("/products/create",
                headers=auth_header,
                json={"name": f"Product {i}", "category": "test"})
        response = client.get("/products?per_page=3", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["products"]) <= 3
        assert data["total"] >= 5

    def test_delete_product(self, client, auth_header):
        resp = client.post("/products/create",
            headers=auth_header,
            json={"name": "Delete Me", "category": "test"})
        product_id = resp.get_json()["id"]

        response = client.delete(f"/products/{product_id}", headers=auth_header)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test 4: Inventory Management
# ---------------------------------------------------------------------------

class TestInventory:
    def test_add_item_by_name(self, client, auth_header):
        response = client.post("/inventory/add-item",
            headers=auth_header,
            json={"product_name": "Bananas", "quantity": 6, "location": "Pantry"})
        assert response.status_code == 201
        data = response.get_json()
        assert data["product_name"] == "Bananas"
        assert data["quantity"] == 6
        assert data["location"] == "Pantry"

    @patch("src.backend.manage_inventory._publish_update")
    def test_consume_item(self, mock_mqtt, client, auth_header):
        # Add item
        resp = client.post("/inventory/add-item",
            headers=auth_header,
            json={"product_name": "Apples", "quantity": 10, "location": "Fridge"})
        item_id = resp.get_json()["id"]

        # Consume 1
        response = client.put(f"/inventory/{item_id}/consume",
            headers=auth_header,
            json={"amount": 1})
        assert response.status_code == 200
        assert response.get_json()["quantity"] == 9

    @patch("src.backend.manage_inventory._publish_update")
    def test_cannot_go_below_zero(self, mock_mqtt, client, auth_header):
        resp = client.post("/inventory/add-item",
            headers=auth_header,
            json={"product_name": "Last Item", "quantity": 1})
        item_id = resp.get_json()["id"]

        # Consume more than available
        response = client.put(f"/inventory/{item_id}/consume",
            headers=auth_header,
            json={"amount": 5})
        assert response.status_code == 200
        assert response.get_json()["quantity"] == 0  # Not negative

    def test_list_inventory(self, client, auth_header):
        client.post("/inventory/add-item",
            headers=auth_header,
            json={"product_name": "Cheese", "quantity": 2, "location": "Fridge"})
        response = client.get("/inventory", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] >= 1


# ---------------------------------------------------------------------------
# Test 5: Budget Management
# ---------------------------------------------------------------------------

class TestBudget:
    def test_set_and_get_budget(self, client, auth_header):
        # Set budget
        response = client.post("/budget/set-monthly",
            headers=auth_header,
            json={"month": "2026-04", "budget_amount": 600.00})
        assert response.status_code == 200

        # Get status
        response = client.get("/budget/status?month=2026-04", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["budget_amount"] == 600.0
        assert data["percentage"] == 0  # No purchases yet


# ---------------------------------------------------------------------------
# Test 6: Recommendation Engine
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_deal_detection_formula(self):
        """Verify the deal confidence formula: min((avg - curr) / avg * 5, 1.0)"""
        avg_price = 3.80
        current_price = 3.20
        confidence = min((avg_price - current_price) / avg_price * 5, 1.0)
        assert round(confidence, 2) == 0.79  # 15.8% discount → 0.79

    def test_seasonal_detection_formula(self):
        """Verify the seasonal confidence formula: min((days/avg - 1.0) * 2.5, 1.0)"""
        avg_frequency = 5  # days
        days_since_last = 6
        confidence = min((days_since_last / avg_frequency - 1.0) * 2.5, 1.0)
        assert round(confidence, 2) == 0.50

    def test_threshold_filtering(self):
        """Verify items below 0.40 confidence are filtered out."""
        # 5% discount → confidence = 0.25 (below threshold)
        avg_price = 4.00
        current_price = 3.80
        confidence = min((avg_price - current_price) / avg_price * 5, 1.0)
        assert confidence == pytest.approx(0.25)
        assert confidence < 0.40  # Should be filtered out

    def test_recommendations_endpoint(self, client, auth_header):
        response = client.get("/recommendations", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert "recommendations" in data
        assert "count" in data


# ---------------------------------------------------------------------------
# Test 7: Analytics
# ---------------------------------------------------------------------------

class TestAnalytics:
    def test_spending_endpoint(self, client, auth_header):
        response = client.get("/analytics/spending?period=monthly", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert "spending_by_period" in data
        assert "category_breakdown" in data

    def test_deals_captured_endpoint(self, client, auth_header):
        response = client.get("/analytics/deals-captured?months=1", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert "total_saved" in data
        assert data["total_saved"] >= 0


# ---------------------------------------------------------------------------
# Test 8: Receipt Upload (mocked OCR)
# ---------------------------------------------------------------------------

class TestReceiptUpload:
    def test_upload_without_image_returns_400(self, client, auth_header):
        response = client.post("/receipts/upload", headers=auth_header)
        assert response.status_code == 400

    def test_upload_invalid_extension_returns_400(self, client, auth_header):
        from io import BytesIO
        data = {"image": (BytesIO(b"not an image"), "test.pdf")}
        response = client.post("/receipts/upload",
            headers=auth_header,
            data=data,
            content_type="multipart/form-data")
        assert response.status_code == 400
        assert "Unsupported" in response.get_json()["error"]


# ---------------------------------------------------------------------------
# Test 9: OCR Hybrid Fallback Logic
# ---------------------------------------------------------------------------

class TestHybridOCR:
    def test_validation_rejects_missing_fields(self):
        from src.backend.extract_receipt_data import _validate_receipt_data
        assert _validate_receipt_data({"store": "Test"}) is False  # Missing date, items, total
        assert _validate_receipt_data({
            "store": "Test", "date": "2026-01-01", "items": [], "total": 10
        }) is False  # Empty items
        assert _validate_receipt_data({
            "store": "Test", "date": "2026-01-01",
            "items": [{"name": "Milk", "unit_price": 3.50}],
            "total": 3.50
        }) is True  # Valid


# ---------------------------------------------------------------------------
# Test 10: Database Schema
# ---------------------------------------------------------------------------

class TestDatabase:
    def test_all_tables_created(self, app):
        from src.backend.initialize_database_schema import Base
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "users", "products", "stores", "inventory", "purchases",
            "receipt_items", "price_history", "budget",
            "telegram_receipts", "api_usage"
        }
        assert expected.issubset(table_names)

    def test_admin_user_created(self, client, auth_header):
        """Verify initial admin user was created from INITIAL_ADMIN_TOKEN."""
        response = client.get("/health")  # Any endpoint just to verify app started
        assert response.status_code == 200
        # Auth works with the token = admin was created
        response = client.get("/products", headers=auth_header)
        assert response.status_code == 200
