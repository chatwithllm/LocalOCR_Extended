"""Tests for cards-overview feature: schema migration, endpoint, math, scoping."""
from __future__ import annotations

import os
import uuid
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


def test_plaid_account_has_original_loan_amount_column():
    """Migration 026 must add original_loan_amount_cents."""
    cols = {c.name for c in Base.metadata.tables["plaid_accounts"].columns}
    assert "original_loan_amount_cents" in cols


def test_inventory_has_consumed_pct_override_column():
    """Migration 027 must add Inventory.consumed_pct_override."""
    cols = {c.name for c in Base.metadata.tables["inventory"].columns}
    assert "consumed_pct_override" in cols


def test_product_has_expected_shelf_days_column():
    """Migration 027 must add Product.expected_shelf_days."""
    cols = {c.name for c in Base.metadata.tables["products"].columns}
    assert "expected_shelf_days" in cols


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


def _invoke_put_loan_meta(app, user_id, account_id, body):
    """PUT /plaid/accounts/<id>/loan-meta — mirrors _invoke_cards_overview unwrap pattern."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User
    import json as _json

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/plaid/accounts/{account_id}/loan-meta"
        with app.test_request_context(path, method="PUT", json=body):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn(account_id=account_id)
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                obj = resp[0]
                status = resp[1]
                payload = obj.get_json() if hasattr(obj, "get_json") else (_json.loads(obj) if isinstance(obj, str) else obj)
                return status, payload
            return 200, resp
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


# ---------------------------------------------------------------------------
# GET /plaid/cards-overview — populated case (credit card with limit + MTD spend)
# ---------------------------------------------------------------------------

def _seed_plaid_item_simple(session, user_id, item_token="item_pop", inst_id="ins_pop"):
    """Seed a fresh Plaid item for a populated test."""
    from src.backend.initialize_database_schema import PlaidItem
    item = PlaidItem(
        user_id=user_id,
        plaid_item_id=item_token,
        institution_id=inst_id,
        institution_name="Test Bank",
        access_token_encrypted="ENC",
        accounts_json="[]",
        status="active",
    )
    session.add(item)
    session.commit()
    return item


def _seed_credit_account(session, user_id, item_id, plaid_account_id="cc_1",
                         balance_cents=124300, limit_cents=500000, avail_cents=375700):
    from datetime import datetime as _dt
    from src.backend.initialize_database_schema import PlaidAccount
    acct = PlaidAccount(
        plaid_item_id=item_id,
        user_id=user_id,
        plaid_account_id=plaid_account_id,
        account_name="Sapphire",
        account_mask="4521",
        account_type="credit",
        account_subtype="credit card",
        balance_cents=balance_cents,
        credit_limit_cents=limit_cents,
        available_credit_cents=avail_cents,
        balance_iso_currency_code="USD",
        balance_updated_at=_dt.utcnow(),
    )
    session.add(acct)
    session.commit()
    return acct


def _seed_staged(session, *, user_id, plaid_item_id, plaid_account_id, amount, date_str,
                 status="ready_to_import", txn_id=None):
    from datetime import date as date_cls
    from src.backend.initialize_database_schema import PlaidStagedTransaction
    txn = PlaidStagedTransaction(
        plaid_item_id=plaid_item_id,
        user_id=user_id,
        plaid_transaction_id=txn_id or f"txn_{plaid_account_id}_{amount}_{date_str}",
        plaid_account_id=plaid_account_id,
        amount=amount,
        transaction_date=date_cls.fromisoformat(date_str),
        status=status,
        raw_json="{}",
    )
    session.add(txn)
    session.commit()
    return txn


def test_cards_overview_credit_card_with_limit(app):
    """Credit card with limit: util%, MTD spend net of refunds, debit-only count."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db

    user_id = _make_user(app, email="cc_pop@test.local", name="CC Pop")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id)
        _seed_credit_account(session, user_id, item.id)

        today_iso = date_cls.today().isoformat()  # guaranteed in MTD
        _seed_staged(session, user_id=user_id, plaid_item_id=item.id,
                     plaid_account_id="cc_1", amount=200.00, date_str=today_iso, txn_id="t1")
        _seed_staged(session, user_id=user_id, plaid_item_id=item.id,
                     plaid_account_id="cc_1", amount=250.00, date_str=today_iso, txn_id="t2")
        _seed_staged(session, user_id=user_id, plaid_item_id=item.id,
                     plaid_account_id="cc_1", amount=-37.50, date_str=today_iso, txn_id="t3")  # refund
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200, body

    month_start = date_cls.today().replace(day=1).isoformat()
    assert body["month_start"] == month_start
    assert len(body["groups"]) == 1
    cc = body["groups"][0]["accounts"][0]
    assert cc["balance_cents"] == 124300
    assert cc["credit_limit_cents"] == 500000
    assert cc["utilization_pct"] == 24.86
    assert cc["spend_mtd_cents"] == 41250  # (200 + 250 - 37.50) × 100
    assert cc["txn_count_mtd"] == 2  # refund excluded

    assert body["totals"]["credit_balance_cents"] == 124300
    assert body["totals"]["credit_limit_cents"] == 500000
    assert body["totals"]["overall_utilization_pct"] == 24.86
    assert body["totals"]["credit_spend_mtd_cents"] == 41250


# ---------------------------------------------------------------------------
# Edge cases: null limit, loan, depository exclusion, scoping, MTD boundary
# ---------------------------------------------------------------------------

def test_cards_overview_credit_card_no_limit(app):
    """Credit card with null limit: utilization_pct null, available null, still rendered."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="cc_nolim@test.local", name="CC NoLim")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(
            session, user_id, item_token="item_nolim", inst_id="ins_nolim"
        )
        session.add(PlaidAccount(
            plaid_item_id=item.id,
            user_id=user_id,
            plaid_account_id="cc_nolim",
            account_name="No Limit Card",
            account_mask="0000",
            account_type="credit",
            account_subtype="credit card",
            balance_cents=10000,
            credit_limit_cents=None,
            available_credit_cents=None,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200, body
    assert len(body["groups"]) == 1
    assert body["groups"][0]["type"] == "credit_card"
    cc = body["groups"][0]["accounts"][0]
    assert cc["plaid_account_id"] == "cc_nolim"
    assert cc["utilization_pct"] is None
    assert cc["credit_limit_cents"] is None
    assert cc["available_credit_cents"] is None
    assert body["totals"]["overall_utilization_pct"] is None


def test_cards_overview_loan_excludes_util(app):
    """Loan accounts: no util%, balance only, grouped under 'loan'."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan@test.local", name="Loan User")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(
            session, user_id, item_token="item_loan", inst_id="ins_loan"
        )
        session.add(PlaidAccount(
            plaid_item_id=item.id,
            user_id=user_id,
            plaid_account_id="ln_1",
            account_name="Mortgage",
            account_mask="8821",
            account_type="loan",
            account_subtype="mortgage",
            balance_cents=18240000,
            credit_limit_cents=None,
            available_credit_cents=None,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200, body
    assert len(body["groups"]) == 1
    assert body["groups"][0]["type"] == "loan"
    loan = body["groups"][0]["accounts"][0]
    assert loan["plaid_account_id"] == "ln_1"
    assert loan["utilization_pct"] is None
    assert loan["balance_cents"] == 18240000
    assert body["totals"]["loan_balance_cents"] == 18240000
    assert body["totals"]["credit_balance_cents"] == 0
    assert body["totals"]["credit_limit_cents"] == 0
    assert body["totals"]["overall_utilization_pct"] is None


def test_cards_overview_excludes_depository(app):
    """Checking / savings accounts must not appear in the response."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="chk@test.local", name="Checking User")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(
            session, user_id, item_token="item_chk", inst_id="ins_chk"
        )
        session.add(PlaidAccount(
            plaid_item_id=item.id,
            user_id=user_id,
            plaid_account_id="chk_1",
            account_name="Checking",
            account_mask="1111",
            account_type="depository",
            account_subtype="checking",
            balance_cents=500000,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200, body
    assert body["groups"] == []
    assert body["totals"]["credit_balance_cents"] == 0
    assert body["totals"]["loan_balance_cents"] == 0


def test_cards_overview_visibility_filter(app):
    """User A's accounts must not appear in user B's view."""
    from src.backend.create_flask_application import _get_db

    user_a_id = _make_user(app, email="visa@test.local", name="User A")
    user_b_id = _make_user(app, email="visb@test.local", name="User B")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(
            session, user_a_id, item_token="item_a_only", inst_id="ins_a_only"
        )
        _seed_credit_account(session, user_a_id, item.id, plaid_account_id="cc_a_only")
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_b_id)
    assert status == 200, body
    assert body["groups"] == []
    assert body["totals"]["credit_balance_cents"] == 0
    assert body["totals"]["credit_limit_cents"] == 0
    assert body["totals"]["loan_balance_cents"] == 0


def test_cards_overview_mtd_boundary_and_dismissed(app):
    """Last day of prev month excluded; first day of current included; dismissed excluded."""
    from datetime import date as date_cls, timedelta
    from src.backend.create_flask_application import _get_db

    user_id = _make_user(app, email="mtd@test.local", name="MTD User")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(
            session, user_id, item_token="item_mtd", inst_id="ins_mtd"
        )
        _seed_credit_account(
            session, user_id, item.id, plaid_account_id="cc_mtd"
        )

        today = date_cls.today()
        first_of_month = today.replace(day=1)
        last_of_prev = first_of_month - timedelta(days=1)

        # $999 last day of previous month — must NOT count
        _seed_staged(
            session,
            user_id=user_id,
            plaid_item_id=item.id,
            plaid_account_id="cc_mtd",
            amount=999.00,
            date_str=last_of_prev.isoformat(),
            txn_id="prev_month",
        )
        # $10 first day of current month — counted
        _seed_staged(
            session,
            user_id=user_id,
            plaid_item_id=item.id,
            plaid_account_id="cc_mtd",
            amount=10.00,
            date_str=first_of_month.isoformat(),
            txn_id="first_of_month",
        )
        # $5000 first day of current month, dismissed — must NOT count
        _seed_staged(
            session,
            user_id=user_id,
            plaid_item_id=item.id,
            plaid_account_id="cc_mtd",
            amount=5000.00,
            date_str=first_of_month.isoformat(),
            status="dismissed",
            txn_id="dismissed",
        )
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200, body
    assert len(body["groups"]) == 1
    cc = body["groups"][0]["accounts"][0]
    assert cc["plaid_account_id"] == "cc_mtd"
    assert cc["spend_mtd_cents"] == 1000  # only the $10 first-of-month debit
    assert cc["txn_count_mtd"] == 1


def test_cards_overview_categories_basic(app):
    """Per-account categories_mtd: debits only, sorted by amount desc, refund excluded."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db

    user_id = _make_user(app, email="cat_basic@test.local", name="Cat Basic")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_cat_basic", inst_id="ins_cat_basic")
        _seed_credit_account(session, user_id, item.id)

        today_iso = date_cls.today().isoformat()
        from src.backend.initialize_database_schema import PlaidStagedTransaction
        for txn_id, amount, cat in [
            ("c1", 50.00, "FOOD_AND_DRINK"),
            ("c2", 30.00, "TRANSPORTATION"),
            ("c3", -10.00, "FOOD_AND_DRINK"),  # refund — excluded
        ]:
            session.add(PlaidStagedTransaction(
                plaid_item_id=item.id, user_id=user_id,
                plaid_transaction_id=txn_id,
                plaid_account_id="cc_1",
                amount=amount,
                transaction_date=date_cls.fromisoformat(today_iso),
                plaid_category_primary=cat,
                status="ready_to_import",
                raw_json="{}",
            ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200, body

    cc = body["groups"][0]["accounts"][0]
    assert cc["categories_mtd"] == [
        {"category": "FOOD_AND_DRINK", "amount_cents": 5000},
        {"category": "TRANSPORTATION", "amount_cents": 3000},
    ]


def test_cards_overview_categories_null_bucket(app):
    """Null plaid_category_primary buckets as UNCATEGORIZED."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    user_id = _make_user(app, email="cat_null@test.local", name="Cat Null")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_cat_null", inst_id="ins_cat_null")
        _seed_credit_account(session, user_id, item.id)
        session.add(PlaidStagedTransaction(
            plaid_item_id=item.id, user_id=user_id,
            plaid_transaction_id="cn1", plaid_account_id="cc_1",
            amount=42.00,
            transaction_date=date_cls.today(),
            plaid_category_primary=None,
            status="ready_to_import", raw_json="{}",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    cc = body["groups"][0]["accounts"][0]
    assert cc["categories_mtd"] == [{"category": "UNCATEGORIZED", "amount_cents": 4200}]


def test_cards_overview_categories_dismissed_excluded(app):
    """Dismissed txns must not contribute to categories_mtd."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    user_id = _make_user(app, email="cat_dis@test.local", name="Cat Dis")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_cat_dis", inst_id="ins_cat_dis")
        _seed_credit_account(session, user_id, item.id)
        session.add(PlaidStagedTransaction(
            plaid_item_id=item.id, user_id=user_id,
            plaid_transaction_id="cd_keep", plaid_account_id="cc_1",
            amount=20.00,
            transaction_date=date_cls.today(),
            plaid_category_primary="FOOD_AND_DRINK",
            status="ready_to_import", raw_json="{}",
        ))
        session.add(PlaidStagedTransaction(
            plaid_item_id=item.id, user_id=user_id,
            plaid_transaction_id="cd_drop", plaid_account_id="cc_1",
            amount=999.00,
            transaction_date=date_cls.today(),
            plaid_category_primary="FOOD_AND_DRINK",
            status="dismissed", raw_json="{}",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    cc = body["groups"][0]["accounts"][0]
    assert cc["categories_mtd"] == [{"category": "FOOD_AND_DRINK", "amount_cents": 2000}]


def test_cards_overview_loans_have_empty_categories(app):
    """Loan accounts always emit categories_mtd: []."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_cat@test.local", name="Loan Cat")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_cat", inst_id="ins_loan_cat")
        session.add(PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_cat",
            account_name="Mortgage", account_mask="8821",
            account_type="loan", account_subtype="mortgage",
            balance_cents=18240000, balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    loan = body["groups"][0]["accounts"][0]
    assert loan["categories_mtd"] == []


def test_cards_overview_categories_visibility_filter(app):
    """User A's category data must not leak to user B."""
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    user_a = _make_user(app, email="cat_a@test.local", name="Cat A")
    user_b = _make_user(app, email="cat_b@test.local", name="Cat B")

    _, SF = _get_db()
    session = SF()
    try:
        item_a = _seed_plaid_item_simple(session, user_a, item_token="item_cat_a", inst_id="ins_cat_a")
        _seed_credit_account(session, user_a, item_a.id, plaid_account_id="cc_a")
        session.add(PlaidStagedTransaction(
            plaid_item_id=item_a.id, user_id=user_a,
            plaid_transaction_id="cv1", plaid_account_id="cc_a",
            amount=99.00,
            transaction_date=date_cls.today(),
            plaid_category_primary="FOOD_AND_DRINK",
            status="ready_to_import", raw_json="{}",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_b)
    assert status == 200
    assert body["groups"] == []


# ---------------------------------------------------------------------------
# PUT /plaid/accounts/<id>/loan-meta
# ---------------------------------------------------------------------------

def test_put_loan_meta_happy_path(app):
    """PUT /plaid/accounts/<id>/loan-meta updates original_loan_amount_cents."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_put@test.local", name="Loan PUT")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_put", inst_id="ins_loan_put")
        loan = PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_put",
            account_name="Mortgage", account_mask="8821",
            account_type="loan", account_subtype="mortgage",
            balance_cents=12240000, balance_iso_currency_code="USD",
        )
        session.add(loan)
        session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, loan_id, {"original_loan_amount_cents": 18500000})
    assert status == 200, body
    assert body["account"]["original_loan_amount_cents"] == 18500000

    session = SF()
    try:
        row = session.get(PlaidAccount, loan_id)
        assert row.original_loan_amount_cents == 18500000
    finally:
        session.close()


def test_put_loan_meta_clear_with_null(app):
    """PUT with null clears the column."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_clear@test.local", name="Loan Clear")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_clear", inst_id="ins_loan_clear")
        loan = PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_clear",
            account_name="Mortgage", account_mask="8821",
            account_type="loan", account_subtype="mortgage",
            balance_cents=10000, balance_iso_currency_code="USD",
            original_loan_amount_cents=50000,
        )
        session.add(loan); session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, loan_id, {"original_loan_amount_cents": None})
    assert status == 200
    assert body["account"]["original_loan_amount_cents"] is None


def test_put_loan_meta_rejects_negative(app):
    """Negative values rejected with 400."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_neg@test.local", name="Loan Neg")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_neg", inst_id="ins_loan_neg")
        loan = PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_neg",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=10000, balance_iso_currency_code="USD",
        )
        session.add(loan); session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, loan_id, {"original_loan_amount_cents": -100})
    assert status == 400


def test_put_loan_meta_rejects_non_integer(app):
    """Non-integer values rejected with 400."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_str@test.local", name="Loan Str")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_str", inst_id="ins_loan_str")
        loan = PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_str",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=10000, balance_iso_currency_code="USD",
        )
        session.add(loan); session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, loan_id, {"original_loan_amount_cents": "abc"})
    assert status == 400


def test_put_loan_meta_rejects_credit_account(app):
    """Credit accounts return 404 (not loans)."""
    from src.backend.create_flask_application import _get_db

    user_id = _make_user(app, email="loan_cc@test.local", name="Loan CC")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_cc", inst_id="ins_loan_cc")
        cc = _seed_credit_account(session, user_id, item.id)
        cc_id = cc.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_id, cc_id, {"original_loan_amount_cents": 50000})
    assert status == 404


def test_put_loan_meta_visibility_filter(app):
    """User A cannot edit user B's loan."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_a = _make_user(app, email="loan_va@test.local", name="Loan VA")
    user_b = _make_user(app, email="loan_vb@test.local", name="Loan VB")

    _, SF = _get_db()
    session = SF()
    try:
        item_a = _seed_plaid_item_simple(session, user_a, item_token="item_loan_va", inst_id="ins_loan_va")
        loan = PlaidAccount(
            plaid_item_id=item_a.id, user_id=user_a, plaid_account_id="ln_v",
            account_name="A's Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=10000, balance_iso_currency_code="USD",
        )
        session.add(loan); session.commit()
        loan_id = loan.id
    finally:
        session.close()

    status, body = _invoke_put_loan_meta(app, user_b, loan_id, {"original_loan_amount_cents": 50000})
    assert status == 404


def test_cards_overview_loan_paid_off_computed(app):
    """Loan with original > balance: paid_off = original - balance."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_po@test.local", name="Loan PO")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_po", inst_id="ins_loan_po")
        session.add(PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_po",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=400000, original_loan_amount_cents=1000000,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    loan = body["groups"][0]["accounts"][0]
    assert loan["original_loan_amount_cents"] == 1000000
    assert loan["paid_off_cents"] == 600000


def test_cards_overview_loan_paid_off_overbalance(app):
    """balance > original → paid_off capped at original."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_ob@test.local", name="Loan OB")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_ob", inst_id="ins_loan_ob")
        session.add(PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_ob",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=1100000, original_loan_amount_cents=1000000,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    loan = body["groups"][0]["accounts"][0]
    assert loan["paid_off_cents"] == 1000000


def test_cards_overview_loan_no_original(app):
    """Loan with original=null → paid_off=null."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    user_id = _make_user(app, email="loan_no@test.local", name="Loan NO")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_no", inst_id="ins_loan_no")
        session.add(PlaidAccount(
            plaid_item_id=item.id, user_id=user_id, plaid_account_id="ln_no",
            account_name="Mortgage", account_mask="0000",
            account_type="loan", account_subtype="mortgage",
            balance_cents=400000, original_loan_amount_cents=None,
            balance_iso_currency_code="USD",
        ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    loan = body["groups"][0]["accounts"][0]
    assert loan["original_loan_amount_cents"] is None
    assert loan["paid_off_cents"] is None


def test_cards_overview_credit_row_no_loan_fields(app):
    """Credit accounts have original=null and paid_off=null."""
    from src.backend.create_flask_application import _get_db

    user_id = _make_user(app, email="loan_cc2@test.local", name="Loan CC2")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_loan_cc2", inst_id="ins_loan_cc2")
        _seed_credit_account(session, user_id, item.id)
    finally:
        session.close()

    status, body = _invoke_cards_overview(app, user_id)
    assert status == 200
    cc = body["groups"][0]["accounts"][0]
    assert cc["original_loan_amount_cents"] is None
    assert cc["paid_off_cents"] is None


# ---------------------------------------------------------------------------
# Plaid-sourced receipt: type-change + delete bug fixes
# ---------------------------------------------------------------------------

def _invoke_update_receipt(app, user_id, receipt_id, body):
    """PUT /receipts/<id>/update — mirrors _invoke_cards_overview unwrap pattern."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/receipts/{receipt_id}/update"
        with app.test_request_context(path, method="PUT", json=body):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn(receipt_id=receipt_id)
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                obj = resp[0]
                status = resp[1]
                payload = obj.get_json() if hasattr(obj, "get_json") else obj
                return status, payload
            return 200, resp
    finally:
        session.close()


def _invoke_delete_receipt(app, user_id, receipt_id):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/receipts/{receipt_id}"
        with app.test_request_context(path, method="DELETE"):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="DELETE")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn(receipt_id=receipt_id)
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                obj = resp[0]
                status = resp[1]
                payload = obj.get_json() if hasattr(obj, "get_json") else obj
                return status, payload
            return 200, resp
    finally:
        session.close()


def _seed_plaid_promoted_receipt(session, user_id, item_id, *, store_name="Indian Bazar",
                                  amount=36.81, plaid_account_id="cc_plaid_promo"):
    """Mirrors confirm_staged_transaction: creates Store, Purchase, TelegramReceipt
    (ocr_engine='plaid'), and a PlaidStagedTransaction with confirmed_purchase_id set."""
    from datetime import date as date_cls, datetime as _dt
    from src.backend.initialize_database_schema import (
        Store, Purchase, TelegramReceipt, PlaidStagedTransaction,
    )

    store = Store(name=store_name)
    session.add(store)
    session.flush()

    purchase = Purchase(
        store_id=store.id,
        total_amount=amount,
        date=_dt.utcnow(),
        domain="general_expense",
        transaction_type="purchase",
        default_spending_domain="general_expense",
        default_budget_category="other",
        user_id=user_id,
    )
    session.add(purchase)
    session.flush()

    receipt = TelegramReceipt(
        telegram_user_id=f"plaid:{plaid_account_id}",
        purchase_id=purchase.id,
        receipt_type="general_expense",
        ocr_engine="plaid",
        ocr_confidence=1.0,
        status="processed",
        raw_ocr_json='{"store":"' + store_name + '","items":[],"total":' + str(amount) + '}',
        image_path=None,
    )
    session.add(receipt)
    session.flush()

    staged = PlaidStagedTransaction(
        plaid_item_id=item_id,
        user_id=user_id,
        plaid_transaction_id=f"plaidtxn_{plaid_account_id}_{purchase.id}_{uuid.uuid4().hex[:8]}",
        plaid_account_id=plaid_account_id,
        amount=amount,
        transaction_date=date_cls.today(),
        name=store_name,
        merchant_name=store_name,
        plaid_category_primary="GENERAL_MERCHANDISE",
        status="confirmed",
        confirmed_purchase_id=purchase.id,
        confirmed_at=_dt.utcnow(),
        raw_json="{}",
    )
    session.add(staged)
    session.commit()
    return {
        "purchase_id": purchase.id,
        "receipt_id": receipt.id,
        "staged_id": staged.id,
        "store_id": store.id,
    }


def test_update_plaid_sourced_receipt_to_grocery_succeeds(app):
    """Bug fix: Plaid-sourced receipt with empty items must accept type=grocery."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import TelegramReceipt

    user_id = _make_user(app, email="plaid_grocery@test.local", name="Plaid Grocery")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_plaid_grocery", inst_id="ins_plaid_grocery")
        ids = _seed_plaid_promoted_receipt(session, user_id, item.id)
    finally:
        session.close()

    body = {
        "receipt_type": "grocery",
        "data": {
            "store": "Indian Bazar",
            "date": "2026-05-05",
            "total": 36.81,
            "subtotal": 36.81,
            "tax": 0,
            "tip": 0,
            "items": [],  # No items — Plaid never gives them
            "confidence": 1.0,
        },
    }
    status, resp = _invoke_update_receipt(app, user_id, ids["receipt_id"], body)
    assert status == 200, resp

    # Confirm receipt_type persisted
    session = SF()
    try:
        rec = session.get(TelegramReceipt, ids["receipt_id"])
        assert rec.receipt_type == "grocery"
    finally:
        session.close()


def test_delete_plaid_sourced_receipt_clears_staged_fk(app):
    """Bug fix: deleting a Plaid-promoted receipt must null staged FKs and reset
    status (otherwise FK constraint blocks the delete)."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        PlaidStagedTransaction, Purchase, TelegramReceipt,
    )

    user_id = _make_user(app, email="plaid_del@test.local", name="Plaid Del")
    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_plaid_del", inst_id="ins_plaid_del")
        ids = _seed_plaid_promoted_receipt(session, user_id, item.id)
    finally:
        session.close()

    status, resp = _invoke_delete_receipt(app, user_id, ids["receipt_id"])
    assert status == 200, resp

    session = SF()
    try:
        # Purchase + receipt rows are gone
        assert session.get(Purchase, ids["purchase_id"]) is None
        assert session.get(TelegramReceipt, ids["receipt_id"]) is None
        # Staged row still exists, but FK is cleared and status reset
        staged = session.get(PlaidStagedTransaction, ids["staged_id"])
        assert staged is not None
        assert staged.confirmed_purchase_id is None
        assert staged.status == "ready_to_import"
        assert staged.confirmed_at is None
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Auto-merge: OCR upload + existing Plaid-promoted Purchase
# ---------------------------------------------------------------------------

def test_auto_merge_links_ocr_upload_to_existing_plaid_purchase(app):
    """When an OCR-uploaded receipt matches an existing Plaid-promoted
    Purchase (same merchant, ±$0.02, ±3 days), they merge into one
    Purchase. The plaid_staged_transactions FK reparents to the kept
    Purchase, and the Plaid-placeholder TelegramReceipt is dropped in
    favor of the OCR one (which has the image)."""
    from datetime import date as date_cls, datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.handle_receipt_upload import _auto_merge_with_existing_match
    from src.backend.initialize_database_schema import (
        PlaidStagedTransaction, Purchase, ReceiptItem, Store, TelegramReceipt,
    )

    user_id = _make_user(app, email="auto_merge_a@test.local", name="Auto Merge A")

    _, SF = _get_db()
    session = SF()
    try:
        # Existing Plaid-promoted Purchase (placeholder, no items, no image)
        item = _seed_plaid_item_simple(session, user_id, item_token="item_amA", inst_id="ins_amA")
        plaid_ids = _seed_plaid_promoted_receipt(session, user_id, item.id,
                                                  store_name="India Bazar",
                                                  amount=36.81)

        # Now simulate a fresh OCR upload that creates a new Purchase for
        # the same merchant + same amount + same day. We seed it manually
        # the same way `_save_to_database` does (Store, Purchase,
        # ReceiptItem rows committed before auto-merge fires).
        ocr_store = Store(name="India Bazar Inc")  # alias-token match
        session.add(ocr_store)
        session.flush()

        ocr_purchase = Purchase(
            store_id=ocr_store.id,
            total_amount=36.81,
            date=_dt.utcnow(),
            domain="grocery",
            transaction_type="purchase",
            default_spending_domain="grocery",
            default_budget_category="grocery",
            user_id=user_id,
        )
        session.add(ocr_purchase)
        session.flush()

        # OCR sees 5 items; Plaid placeholder has none. Merge heuristic
        # should keep the OCR purchase.
        from src.backend.initialize_database_schema import Product
        for i in range(5):
            product = Product(name=f"AutoMergeTestItem{i}", display_name=f"Item {i}")
            session.add(product); session.flush()
            session.add(ReceiptItem(
                purchase_id=ocr_purchase.id,
                product_id=product.id,
                quantity=1,
                unit_price=7.36,
                unit="each",
                kind="product",
            ))
        session.commit()

        ocr_purchase_id = ocr_purchase.id
        plaid_purchase_id = plaid_ids["purchase_id"]

        # Trigger the auto-merge (this is what _save_to_database does)
        kept_id, was_merged = _auto_merge_with_existing_match(
            session, ocr_purchase, user_id, new_image_path="/tmp/fake_receipt.jpg"
        )
        session.commit()
    finally:
        session.close()

    assert was_merged is True
    assert kept_id == ocr_purchase_id  # OCR (more items) kept

    # Verify final state
    session = SF()
    try:
        # Plaid placeholder Purchase is gone
        assert session.get(Purchase, plaid_purchase_id) is None
        # OCR Purchase remains
        kept = session.get(Purchase, ocr_purchase_id)
        assert kept is not None

        # PlaidStagedTransaction FK reparented to kept (OCR) Purchase
        staged = session.get(PlaidStagedTransaction, plaid_ids["staged_id"])
        assert staged.confirmed_purchase_id == ocr_purchase_id

        # ReceiptItems still on kept
        items = session.query(ReceiptItem).filter_by(purchase_id=ocr_purchase_id).count()
        assert items == 5

        # Plaid placeholder TR (image-less) was dropped during cleanup
        trs = session.query(TelegramReceipt).filter_by(purchase_id=ocr_purchase_id).all()
        # At this point the OCR TR hasn't been created yet (caller does that
        # after _save_to_database returns). So zero TRs is correct here:
        # the placeholder was deleted, the OCR TR will be added next.
        assert len(trs) == 0
    finally:
        session.close()


def test_auto_merge_no_match_returns_unchanged(app):
    """If no matching Purchase exists, auto-merge returns (id, False)."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.handle_receipt_upload import _auto_merge_with_existing_match
    from src.backend.initialize_database_schema import Purchase, Store

    user_id = _make_user(app, email="auto_merge_b@test.local", name="Auto Merge B")

    _, SF = _get_db()
    session = SF()
    try:
        store = Store(name="Some Lonely Merchant")
        session.add(store); session.flush()
        new_purchase = Purchase(
            store_id=store.id,
            total_amount=12.34,
            date=_dt.utcnow(),
            domain="grocery",
            transaction_type="purchase",
            default_spending_domain="grocery",
            default_budget_category="grocery",
            user_id=user_id,
        )
        session.add(new_purchase); session.commit()

        kept_id, was_merged = _auto_merge_with_existing_match(session, new_purchase, user_id)
    finally:
        session.close()

    assert was_merged is False
    assert kept_id == new_purchase.id


def test_auto_merge_skips_when_amount_differs(app):
    """Different amount → no merge even if merchant + date match."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.handle_receipt_upload import _auto_merge_with_existing_match
    from src.backend.initialize_database_schema import Purchase, Store

    user_id = _make_user(app, email="auto_merge_c@test.local", name="Auto Merge C")

    _, SF = _get_db()
    session = SF()
    try:
        store = Store(name="Diff Amount Merchant")
        session.add(store); session.flush()
        old = Purchase(
            store_id=store.id, total_amount=20.00, date=_dt.utcnow(),
            domain="grocery", transaction_type="purchase",
            default_spending_domain="grocery", default_budget_category="grocery",
            user_id=user_id,
        )
        session.add(old); session.commit()

        new = Purchase(
            store_id=store.id, total_amount=99.99, date=_dt.utcnow(),
            domain="grocery", transaction_type="purchase",
            default_spending_domain="grocery", default_budget_category="grocery",
            user_id=user_id,
        )
        session.add(new); session.commit()

        kept_id, was_merged = _auto_merge_with_existing_match(session, new, user_id)
    finally:
        session.close()

    assert was_merged is False


# ---------------------------------------------------------------------------
# Auto-link backfill: existing Plaid+OCR pairs collapse into one
# ---------------------------------------------------------------------------

def _invoke_auto_link_plaid(app, user_id):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = "/receipts/auto-link-plaid"
        with app.test_request_context(path, method="POST"):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="POST")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn()
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                obj = resp[0]
                status = resp[1]
                payload = obj.get_json() if hasattr(obj, "get_json") else obj
                return status, payload
            return 200, resp
    finally:
        session.close()


def test_auto_link_plaid_merges_existing_plaid_ocr_pairs(app):
    """Backfill: pre-existing Plaid-promoted Purchase + OCR Upload Purchase
    for the same merchant/date/amount → merge into one. Idempotent."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        PlaidStagedTransaction, Product, Purchase, ReceiptItem, Store, TelegramReceipt,
    )

    user_id = _make_user(app, email="auto_link@test.local", name="Auto Link")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id, item_token="item_alink", inst_id="ins_alink")
        plaid_ids = _seed_plaid_promoted_receipt(
            session, user_id, item.id,
            store_name="India Bazar", amount=36.81,
            plaid_account_id="cc_alink",
        )

        # OCR-uploaded duplicate
        ocr_store = Store(name="India Bazar Inc")
        session.add(ocr_store); session.flush()
        ocr_purchase = Purchase(
            store_id=ocr_store.id, total_amount=36.81, date=_dt.utcnow(),
            domain="grocery", transaction_type="purchase",
            default_spending_domain="grocery", default_budget_category="grocery",
            user_id=user_id,
        )
        session.add(ocr_purchase); session.flush()
        product = Product(name=f"OCRItem-{uuid.uuid4().hex[:6]}", display_name="X")
        session.add(product); session.flush()
        session.add(ReceiptItem(
            purchase_id=ocr_purchase.id, product_id=product.id,
            quantity=1, unit_price=36.81, unit="each", kind="product",
        ))
        ocr_receipt = TelegramReceipt(
            telegram_user_id=f"upload:{user_id}",
            purchase_id=ocr_purchase.id,
            receipt_type="grocery",
            ocr_engine="gemini",
            ocr_confidence=0.98,
            status="processed",
            raw_ocr_json="{}",
            image_path="/tmp/india_bazar.jpg",
        )
        session.add(ocr_receipt); session.commit()

        plaid_purchase_id = plaid_ids["purchase_id"]
        ocr_purchase_id = ocr_purchase.id
    finally:
        session.close()

    # First pass — should merge
    status, body = _invoke_auto_link_plaid(app, user_id)
    assert status == 200
    assert body["merged"] == 1
    assert body["pairs"][0]["kept_purchase_id"] == ocr_purchase_id
    assert body["pairs"][0]["dropped_purchase_id"] == plaid_purchase_id

    # Verify final state
    session = SF()
    try:
        # Plaid placeholder Purchase removed
        assert session.get(Purchase, plaid_purchase_id) is None
        # OCR Purchase kept
        assert session.get(Purchase, ocr_purchase_id) is not None
        # Staged FK reparented
        staged = session.get(PlaidStagedTransaction, plaid_ids["staged_id"])
        assert staged.confirmed_purchase_id == ocr_purchase_id
        # Only the OCR (image-bearing) TR remains
        trs = session.query(TelegramReceipt).filter_by(purchase_id=ocr_purchase_id).all()
        assert len(trs) == 1
        assert trs[0].image_path == "/tmp/india_bazar.jpg"
    finally:
        session.close()

    # Second pass — idempotent
    status2, body2 = _invoke_auto_link_plaid(app, user_id)
    assert status2 == 200
    assert body2["merged"] == 0


def test_auto_link_plaid_skips_pure_ocr_pairs(app):
    """Two OCR upload Purchases for same merchant/amount/date are NOT
    auto-merged — those need user judgment via the dedup-scan UI."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        Product, Purchase, ReceiptItem, Store, TelegramReceipt,
    )

    user_id = _make_user(app, email="auto_link_ocr@test.local", name="Auto Link OCR")

    _, SF = _get_db()
    session = SF()
    try:
        store = Store(name="DoubleUpload Mart")
        session.add(store); session.flush()
        for tag in ("a", "b"):
            p = Purchase(
                store_id=store.id, total_amount=42.00, date=_dt.utcnow(),
                domain="grocery", transaction_type="purchase",
                default_spending_domain="grocery", default_budget_category="grocery",
                user_id=user_id,
            )
            session.add(p); session.flush()
            prod = Product(name=f"DupItem-{tag}-{uuid.uuid4().hex[:6]}", display_name=tag)
            session.add(prod); session.flush()
            session.add(ReceiptItem(
                purchase_id=p.id, product_id=prod.id,
                quantity=1, unit_price=42.00, unit="each", kind="product",
            ))
            session.add(TelegramReceipt(
                telegram_user_id=f"upload:{user_id}",
                purchase_id=p.id, receipt_type="grocery",
                ocr_engine="gemini", ocr_confidence=0.95,
                status="processed", raw_ocr_json="{}",
                image_path=f"/tmp/dup-{tag}.jpg",
            ))
        session.commit()
    finally:
        session.close()

    status, body = _invoke_auto_link_plaid(app, user_id)
    assert status == 200
    assert body["merged"] == 0  # OCR+OCR pairs are left alone


# ---------------------------------------------------------------------------
# Defensive list-grouping: two equivalent receipt rows collapse to one
# ---------------------------------------------------------------------------

def _invoke_list_receipts(app, user_id):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = "/receipts"
        with app.test_request_context(path, method="GET"):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="GET")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn()
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                obj = resp[0]
                status = resp[1]
                payload = obj.get_json() if hasattr(obj, "get_json") else obj
                return status, payload
            return 200, resp
    finally:
        session.close()


def test_list_receipts_groups_equivalent_plaid_and_upload(app):
    """Two Purchase rows for same merchant alias / date / amount —
    one Plaid placeholder + one OCR upload — collapse to ONE receipt
    in the list, with linked_to_plaid=True on the survivor (OCR row)."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        Product, Purchase, ReceiptItem, Store, TelegramReceipt,
    )

    # Unique store name + amount to avoid cross-test pollution in the
    # shared module-scoped DB.
    unique_tag = uuid.uuid4().hex[:8]
    store_name = f"GroupTest Store {unique_tag}"
    amount = 0.01 + (int(unique_tag, 16) % 10000) / 100  # unique per test

    user_id = _make_user(app, email=f"list_group_{unique_tag}@test.local", name="List Group")

    _, SF = _get_db()
    session = SF()
    try:
        item = _seed_plaid_item_simple(session, user_id,
                                        item_token=f"item_listg_{unique_tag}",
                                        inst_id=f"ins_listg_{unique_tag}")
        plaid_ids = _seed_plaid_promoted_receipt(
            session, user_id, item.id,
            store_name=store_name, amount=amount,
            plaid_account_id=f"cc_listg_{unique_tag}",
        )

        ocr_store = Store(name=store_name)
        session.add(ocr_store); session.flush()
        ocr_purchase = Purchase(
            store_id=ocr_store.id, total_amount=amount, date=_dt.utcnow(),
            domain="grocery", transaction_type="purchase",
            default_spending_domain="grocery", default_budget_category="grocery",
            user_id=user_id,
        )
        session.add(ocr_purchase); session.flush()
        prod = Product(name=f"GroupItem-{unique_tag}", display_name="X")
        session.add(prod); session.flush()
        session.add(ReceiptItem(
            purchase_id=ocr_purchase.id, product_id=prod.id,
            quantity=1, unit_price=amount, unit="each", kind="product",
        ))
        session.add(TelegramReceipt(
            telegram_user_id=f"upload:{user_id}",
            purchase_id=ocr_purchase.id,
            receipt_type="grocery",
            ocr_engine="gemini",
            ocr_confidence=0.98,
            status="processed",
            raw_ocr_json="{}",
            image_path=f"/tmp/group_{unique_tag}.jpg",
        ))
        session.commit()
        ocr_purchase_id = ocr_purchase.id
    finally:
        session.close()

    status, body = _invoke_list_receipts(app, user_id)
    assert status == 200
    receipts = body["receipts"]

    # Match on amount only (canonicalize_store_name may rewrite spaces/case).
    rows = [r for r in receipts if abs((r.get("total") or 0) - amount) < 0.005]
    assert len(rows) == 1, f"Expected 1 grouped row at amount={amount}, got {len(rows)}: {[(r.get('store'), r.get('total'), r.get('purchase_id')) for r in rows]}"
    survivor = rows[0]
    assert survivor["purchase_id"] == ocr_purchase_id
    assert survivor["linked_to_plaid"] is True
    assert "plaid" in survivor.get("sources", [])


# ---------------------------------------------------------------------------
# Product token-set dedup
# ---------------------------------------------------------------------------

def test_product_token_key_basic():
    """product_token_key normalizes word order, casing, plurals, stopwords."""
    from src.backend.normalize_product_names import product_token_key
    # Word-order swap → same key
    assert product_token_key("Red Onions") == product_token_key("Onions Red")
    assert product_token_key("Red Onions") == product_token_key("ONIONS RED")
    # Plural collapse
    assert product_token_key("Red Onions") == product_token_key("Red Onion")
    # Stopword drop ("of" gone)
    assert product_token_key("Onions of Red") == product_token_key("Red Onions")
    # Single-token returns None (skip auto-merge)
    assert product_token_key("Apple") is None
    # Punctuation
    assert product_token_key("Red, Onions") == product_token_key("Red Onions")


def test_find_matching_product_token_set_fallback(app):
    """find_matching_product matches by token-set when exact name miss."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Product
    from src.backend.normalize_product_names import find_matching_product

    user_id = _make_user(app, email="prod_tok@test.local", name="Prod Tok")
    _, SF = _get_db()
    session = SF()
    try:
        existing = Product(
            name="Red Onions", display_name="Red Onions",
            category="produce",
        )
        session.add(existing); session.commit()
        existing_id = existing.id

        # Lookup with permuted name + plural variant — should hit fallback
        match = find_matching_product(session, "Onions Red", "produce")
        assert match is not None
        assert match.id == existing_id

        match2 = find_matching_product(session, "Onion Red", "produce")
        assert match2 is not None and match2.id == existing_id

        # Different category → no match (safety guard)
        match_cat = find_matching_product(session, "Onions Red", "household")
        assert match_cat is None

        # Single-token name → no fallback (token_key returns None)
        single = Product(name="Apples", display_name="Apples", category="produce")
        session.add(single); session.commit()
        # Single-token search shouldn't accidentally match
        single_match = find_matching_product(session, "Apple", "produce")
        # exact matcher might still find Apples via plural — that's fine,
        # we just verify token-set didn't cross categories
        if single_match is not None:
            assert single_match.category == "produce"
    finally:
        session.close()


def _invoke_auto_dedup_products(app, user_id):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = "/products/auto-dedup-tokens"
        with app.test_request_context(path, method="POST"):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="POST")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn()
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                obj = resp[0]
                status = resp[1]
                payload = obj.get_json() if hasattr(obj, "get_json") else obj
                return status, payload
            return 200, resp
    finally:
        session.close()


def test_auto_dedup_products_merges_token_set_duplicates(app):
    """Backfill: Red Onions + Onions Red → one row, image inherited."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Product, ProductSnapshot
    from datetime import datetime as _dt

    user_id = _make_user(app, email="prod_dedup@test.local", name="Prod Dedup")
    unique_tag = uuid.uuid4().hex[:6]

    _, SF = _get_db()
    session = SF()
    try:
        # "Onions Red" — has image, less rich name
        with_image = Product(
            name=f"Onions Red {unique_tag}",
            display_name=f"Onions Red {unique_tag}",
            category="produce",
        )
        session.add(with_image); session.flush()
        session.add(ProductSnapshot(
            product_id=with_image.id,
            source_context="auto_fetch",
            status="auto",
            image_path=f"/tmp/onions_{unique_tag}.jpg",
            captured_at=_dt.utcnow(),
        ))

        # "Red Onions" — typed later, no image
        no_image = Product(
            name=f"Red Onions {unique_tag}",
            display_name=f"Red Onions {unique_tag}",
            category="produce",
        )
        session.add(no_image); session.commit()
        with_image_id = with_image.id
        no_image_id = no_image.id
    finally:
        session.close()

    status, body = _invoke_auto_dedup_products(app, user_id)
    assert status == 200
    assert body["merged"] >= 1

    # Find the group involving our products
    relevant = [g for g in body["groups"]
                if with_image_id in [g["keeper_id"]] + g["dropped_ids"]
                or no_image_id in [g["keeper_id"]] + g["dropped_ids"]]
    assert len(relevant) == 1
    grp = relevant[0]
    # Keeper should be the one with image (with_image_id)
    assert grp["keeper_id"] == with_image_id
    assert no_image_id in grp["dropped_ids"]

    # Verify final state
    session = SF()
    try:
        assert session.get(Product, no_image_id) is None
        kept = session.get(Product, with_image_id)
        assert kept is not None
        # Image still attached to keeper
        snaps = session.query(ProductSnapshot).filter_by(product_id=with_image_id).count()
        assert snaps >= 1
    finally:
        session.close()


def test_auto_dedup_products_skips_different_categories(app):
    """Same tokens in different categories must NOT merge."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Product

    user_id = _make_user(app, email="prod_cat@test.local", name="Prod Cat")
    unique_tag = uuid.uuid4().hex[:6]

    _, SF = _get_db()
    session = SF()
    try:
        produce = Product(
            name=f"Bell Pepper {unique_tag}", category="produce",
        )
        snack = Product(
            name=f"Pepper Bell {unique_tag}", category="snacks",
        )
        session.add_all([produce, snack]); session.commit()
        produce_id = produce.id
        snack_id = snack.id
    finally:
        session.close()

    status, body = _invoke_auto_dedup_products(app, user_id)
    assert status == 200

    session = SF()
    try:
        # Both still exist
        assert session.get(Product, produce_id) is not None
        assert session.get(Product, snack_id) is not None
    finally:
        session.close()

def test_compute_remaining_auto_decay_midway():
    """No override, 3 days into 7-day shelf → ~57% remaining, status low."""
    from datetime import datetime, timedelta
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = datetime(2026, 5, 1, 12, 0, 0)
        last_updated = None
        consumed_pct_override = None

    now = datetime(2026, 5, 4, 12, 0, 0)  # 3 days later
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["shelf_days"] == 7
    assert abs(result["remaining_pct"] - 57.1) < 0.2
    assert result["status"] == "low"
    assert result["is_estimated"] is True


def test_compute_remaining_override_wins():
    """Manual override beats auto-decay regardless of date math."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = datetime(2020, 1, 1)
        last_updated = None
        consumed_pct_override = 10.0

    now = datetime(2026, 5, 4)
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["remaining_pct"] == 90.0
    assert result["status"] == "fresh"
    assert result["is_estimated"] is False


def test_compute_remaining_uses_product_override_shelf_days():
    """Product.expected_shelf_days beats category default."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"
        expected_shelf_days = 30
    class FakeInv:
        last_purchased_at = datetime(2026, 5, 1)
        last_updated = None
        consumed_pct_override = None

    now = datetime(2026, 5, 16)
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["shelf_days"] == 30
    assert abs(result["remaining_pct"] - 50.0) < 0.2
    assert result["status"] == "low"


def test_compute_remaining_uses_other_when_category_unknown():
    """Null category falls back to 'other' (30 days)."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = None
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = datetime(2026, 5, 1)
        last_updated = None
        consumed_pct_override = None

    now = datetime(2026, 5, 4)
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["shelf_days"] == 30
    assert result["remaining_pct"] == 90.0
    assert result["status"] == "fresh"


def test_compute_remaining_clamps_to_zero():
    """Far past shelf life → 0% remaining, status out."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = datetime(2026, 1, 1)
        last_updated = None
        consumed_pct_override = None

    now = datetime(2026, 5, 1)
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["remaining_pct"] == 0.0
    assert result["status"] == "out"


def test_compute_remaining_falls_back_to_last_updated():
    """When last_purchased_at is null, last_updated anchors decay."""
    from datetime import datetime
    from src.backend.inventory_status import compute_inventory_status

    class FakeProduct:
        category = "dairy"
        expected_shelf_days = None
    class FakeInv:
        last_purchased_at = None
        last_updated = datetime(2026, 5, 1)
        consumed_pct_override = None

    now = datetime(2026, 5, 4)
    result = compute_inventory_status(FakeProduct(), FakeInv(), now=now)
    assert result["shelf_days"] == 7
    assert abs(result["remaining_pct"] - 57.1) < 0.2


def _invoke_list_inventory(app, user_id):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User
    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        with app.test_request_context("/inventory", method="GET"):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match("/inventory", method="GET")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn()
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                return resp[1], (resp[0].get_json() if hasattr(resp[0], "get_json") else resp[0])
            return 200, resp
    finally:
        session.close()


def test_list_inventory_emits_status_fields(app):
    """GET /inventory rows carry remaining_pct, status, shelf_days, is_estimated."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product

    user_id = _make_user(app, email=f"truinv_{uuid.uuid4().hex[:6]}@test.local", name="True Inv")
    unique = uuid.uuid4().hex[:6]
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"TestMilk-{unique}", category="dairy")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=2, location="Fridge",
            is_active_window=True,
            last_purchased_at=_dt.utcnow(),
        )
        session.add(inv); session.commit()
    finally:
        session.close()

    status, body = _invoke_list_inventory(app, user_id)
    assert status == 200, body
    rows = body["inventory"]
    matches = [r for r in rows if (r.get("product_name") or "").startswith(f"TestMilk-{unique}") or (r.get("raw_name") or "").startswith(f"TestMilk-{unique}")]
    assert len(matches) >= 1, f"No matching row found among {len(rows)} rows"
    row = matches[0]
    assert "remaining_pct" in row
    assert "status" in row
    assert "shelf_days" in row
    assert "is_estimated" in row
    assert row["shelf_days"] == 7  # dairy
    assert row["remaining_pct"] >= 90.0
    assert row["status"] == "fresh"
    assert row["is_estimated"] is True


def _invoke_consume(app, user_id, item_id, amount=1):
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User
    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/inventory/{item_id}/consume"
        with app.test_request_context(path, method="PUT", json={"amount": amount}):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn(item_id=item_id)
            if hasattr(resp, "status_code"):
                return resp.status_code, resp.get_json()
            if isinstance(resp, tuple) and len(resp) >= 2:
                return resp[1], (resp[0].get_json() if hasattr(resp[0], "get_json") else resp[0])
            return 200, resp
    finally:
        session.close()


def test_consume_action_bumps_consumed_override(app):
    """-1 from qty=4 sets override to ~25 (one quarter consumed)."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product

    user_id = _make_user(app, email=f"consume_{uuid.uuid4().hex[:6]}@test.local", name="Consume")
    unique = uuid.uuid4().hex[:6]
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"Bagel-{unique}", category="baked")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=4, location="Pantry",
            is_active_window=True, last_purchased_at=_dt.utcnow(),
        )
        session.add(inv); session.commit()
        item_id = inv.id
    finally:
        session.close()

    status, _body = _invoke_consume(app, user_id, item_id, amount=1)
    assert status == 200

    session = SF()
    try:
        inv = session.get(Inventory, item_id)
        assert inv.consumed_pct_override is not None
        # 1 of original 4 consumed -> ~25%
        assert 20.0 <= inv.consumed_pct_override <= 30.0
    finally:
        session.close()


def test_used_up_sets_override_high(app):
    """Consuming entire quantity drives override toward 100%."""
    from datetime import datetime as _dt
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product

    user_id = _make_user(app, email=f"useup_{uuid.uuid4().hex[:6]}@test.local", name="Use Up")
    unique = uuid.uuid4().hex[:6]
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"Yogurt-{unique}", category="dairy")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=1, location="Fridge",
            is_active_window=True, last_purchased_at=_dt.utcnow(),
        )
        session.add(inv); session.commit()
        item_id = inv.id
    finally:
        session.close()

    status, _ = _invoke_consume(app, user_id, item_id, amount=1)
    assert status == 200
    session = SF()
    try:
        inv = session.get(Inventory, item_id)
        # Consumed all -> override should be high (>=95)
        assert inv.consumed_pct_override is not None
        assert inv.consumed_pct_override >= 95.0
    finally:
        session.close()


def test_update_item_accepts_consumed_pct_override(app):
    """PUT /inventory/<id>/update with body {consumed_pct_override: N} persists it."""
    from datetime import datetime as _dt
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product, User

    user_id = _make_user(app, email=f"override_{uuid.uuid4().hex[:6]}@test.local", name="Override")
    unique = uuid.uuid4().hex[:6]
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"Apples-{unique}", category="fruit")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=3, location="Pantry",
            is_active_window=True, last_purchased_at=_dt.utcnow(),
        )
        session.add(inv); session.commit()
        item_id = inv.id
    finally:
        session.close()

    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/inventory/{item_id}/update"
        with app.test_request_context(path, method="PUT", json={"consumed_pct_override": 30.0}):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            fn(item_id=item_id)
    finally:
        session.close()

    session = SF()
    try:
        inv = session.get(Inventory, item_id)
        assert inv.consumed_pct_override == 30.0
    finally:
        session.close()


def test_update_item_clears_override_with_null(app):
    """PUT with consumed_pct_override=null clears the override."""
    from datetime import datetime as _dt
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product, User

    user_id = _make_user(app, email=f"clear_{uuid.uuid4().hex[:6]}@test.local", name="Clear")
    unique = uuid.uuid4().hex[:6]
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"Pears-{unique}", category="fruit")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=3, location="Pantry",
            is_active_window=True, last_purchased_at=_dt.utcnow(),
            consumed_pct_override=50.0,
        )
        session.add(inv); session.commit()
        item_id = inv.id
    finally:
        session.close()

    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/inventory/{item_id}/update"
        with app.test_request_context(path, method="PUT", json={"consumed_pct_override": None}):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            fn(item_id=item_id)
    finally:
        session.close()

    session = SF()
    try:
        inv = session.get(Inventory, item_id)
        assert inv.consumed_pct_override is None
    finally:
        session.close()


def test_update_item_rejects_out_of_range_override(app):
    """PUT with consumed_pct_override > 100 returns 400."""
    from datetime import datetime as _dt
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Inventory, Product, User

    user_id = _make_user(app, email=f"oor_{uuid.uuid4().hex[:6]}@test.local", name="OOR")
    unique = uuid.uuid4().hex[:6]
    _, SF = _get_db()
    session = SF()
    try:
        prod = Product(name=f"Plums-{unique}", category="fruit")
        session.add(prod); session.flush()
        inv = Inventory(
            product_id=prod.id, quantity=2, location="Pantry",
            is_active_window=True, last_purchased_at=_dt.utcnow(),
        )
        session.add(inv); session.commit()
        item_id = inv.id
    finally:
        session.close()

    session = SF()
    try:
        user = session.get(User, user_id)
        path = f"/inventory/{item_id}/update"
        with app.test_request_context(path, method="PUT", json={"consumed_pct_override": 150.0}):
            g.current_user = user
            g.db_session = session
            endpoint, _args = app.url_map.bind("").match(path, method="PUT")
            fn = app.view_functions[endpoint]
            while hasattr(fn, "__wrapped__"):
                fn = fn.__wrapped__
            resp = fn(item_id=item_id)
            if hasattr(resp, "status_code"):
                assert resp.status_code == 400
            else:
                assert resp[1] == 400
    finally:
        session.close()
