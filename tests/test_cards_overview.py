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


def test_plaid_account_has_original_loan_amount_column():
    """Migration 026 must add original_loan_amount_cents."""
    cols = {c.name for c in Base.metadata.tables["plaid_accounts"].columns}
    assert "original_loan_amount_cents" in cols


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
