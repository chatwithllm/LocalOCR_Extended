"""Tests for cards-overview feature: schema migration, endpoint, math, scoping."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

# Force in-memory SQLite — must run before any backend imports that touch
# create_flask_application._get_db().
os.environ["DATABASE_URL"] = "sqlite://"

from src.backend.initialize_database_schema import Base


def test_plaid_account_has_credit_limit_columns():
    """Migration 025 must add credit_limit_cents and available_credit_cents."""
    cols = {c.name for c in Base.metadata.tables["plaid_accounts"].columns}
    assert "credit_limit_cents" in cols
    assert "available_credit_cents" in cols


# ---------------------------------------------------------------------------
# refresh_balances persists credit_limit + available_credit
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app

    application = create_app()
    application.config["TESTING"] = True
    yield application


@pytest.fixture
def credit_card_seed(app):
    """Seed a user + active PlaidItem (no PlaidAccount yet — exercises the
    lazy-create branch in refresh_balances)."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        PlaidAccount,
        PlaidItem,
        User,
    )

    with app.app_context():
        _, SF = _get_db()
        session = SF()
        try:
            user = User(
                name="Cardholder",
                email="cards@test.local",
                role="user",
                is_active=1,
                password_hash="x",
                session_version=0,
            )
            session.add(user)
            session.flush()

            item = PlaidItem(
                user_id=user.id,
                plaid_item_id="plaid_item_creditcard",
                institution_id="ins_cc",
                institution_name="Test Bank",
                access_token_encrypted="ENC",
                accounts_json="[]",
                status="active",
            )
            session.add(item)
            session.commit()

            # Clear any pre-existing balance_updated_at on this user's
            # accounts so the throttle doesn't fire (this user has none yet).
            session.query(PlaidAccount).filter_by(user_id=user.id).delete()
            session.commit()

            ids = {"user": user.id, "item": item.id}
        finally:
            session.close()
    return ids


def _invoke_refresh_balances(app, user_id):
    """Unwrap auth decorators and POST /plaid/accounts/refresh-balances."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        with app.test_request_context(
            "/plaid/accounts/refresh-balances", method="POST"
        ):
            g.current_user = user
            g.db_session = session
            endpoint, args = app.url_map.bind("").match(
                "/plaid/accounts/refresh-balances", method="POST"
            )
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            rv = fn(**args)
            if isinstance(rv, tuple):
                body = rv[0].get_json() if hasattr(rv[0], "get_json") else None
                return rv[1], body
            return 200, rv.get_json() if hasattr(rv, "get_json") else rv
    finally:
        session.close()


def test_refresh_balances_persists_limit_and_available(app, credit_card_seed):
    """When Plaid returns balances.limit and balances.available, both must be stored."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    fake_plaid_response = {
        "accounts": [{
            "account_id": "plaid_acct_creditcard_1",
            "name": "Sapphire",
            "mask": "4521",
            "type": "credit",
            "subtype": "credit card",
            "balances": {
                "current": 1243.00,
                "limit": 5000.00,
                "available": 3757.00,
                "iso_currency_code": "USD",
            },
        }],
    }
    fake_client = MagicMock()
    fake_client.accounts_balance_get.return_value = fake_plaid_response

    with patch(
        "src.backend.plaid_integration.is_plaid_configured", return_value=True
    ), patch(
        "src.backend.plaid_integration.get_client", return_value=fake_client
    ), patch(
        "src.backend.plaid_integration.decrypt_api_key",
        return_value="access_token_xxx",
    ):
        status, body = _invoke_refresh_balances(app, credit_card_seed["user"])
    assert status == 200, body

    _, SF = _get_db()
    session = SF()
    try:
        row = (
            session.query(PlaidAccount)
            .filter_by(plaid_account_id="plaid_acct_creditcard_1")
            .one()
        )
        assert row.balance_cents == 124300
        assert row.credit_limit_cents == 500000
        assert row.available_credit_cents == 375700
    finally:
        session.close()


# ---------------------------------------------------------------------------
# GET /plaid/cards-overview — empty case
# ---------------------------------------------------------------------------

def _make_user(app, *, email: str, name: str = "Empty"):
    """Create a fresh User with no Plaid items. Returns the user id."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    with app.app_context():
        _, SF = _get_db()
        session = SF()
        try:
            user = User(
                name=name,
                email=email,
                role="user",
                is_active=1,
                password_hash="x",
                session_version=0,
            )
            session.add(user)
            session.commit()
            return user.id
        finally:
            session.close()


def _invoke_cards_overview(app, user_id):
    """Unwrap auth decorators and GET /plaid/cards-overview."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        with app.test_request_context(
            "/plaid/cards-overview", method="GET"
        ):
            g.current_user = user
            g.db_session = session
            endpoint, args = app.url_map.bind("").match(
                "/plaid/cards-overview", method="GET"
            )
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            rv = fn(**args)
            if isinstance(rv, tuple):
                body = rv[0].get_json() if hasattr(rv[0], "get_json") else None
                return rv[1], body
            return 200, rv.get_json() if hasattr(rv, "get_json") else rv
    finally:
        session.close()


def test_cards_overview_empty(app):
    """User with no Plaid items returns 200 with empty groups + zeroed totals."""
    user_id = _make_user(app, email="cards_empty@test.local", name="EmptyCards")

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200, body
    assert isinstance(body.get("as_of"), str)
    assert isinstance(body.get("month_start"), str)
    assert body["groups"] == []
    assert body["totals"] == {
        "credit_balance_cents": 0,
        "credit_limit_cents": 0,
        "overall_utilization_pct": None,
        "credit_spend_mtd_cents": 0,
        "loan_balance_cents": 0,
    }


def test_serialize_plaid_account_includes_credit_fields():
    """Account serializer must surface credit limit and available credit."""
    from src.backend.initialize_database_schema import PlaidAccount
    from src.backend.plaid_integration import _serialize_plaid_account

    acct = PlaidAccount(
        id=1,
        plaid_item_id=1,
        user_id=1,
        plaid_account_id="x",
        account_name="Sapphire",
        account_mask="4521",
        account_type="credit",
        account_subtype="credit card",
        balance_cents=124300,
        credit_limit_cents=500000,
        available_credit_cents=375700,
        balance_iso_currency_code="USD",
        balance_updated_at=None,
    )
    out = _serialize_plaid_account(acct)
    assert out["credit_limit_cents"] == 500000
    assert out["available_credit_cents"] == 375700
