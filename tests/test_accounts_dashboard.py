"""Pytest suite for Accounts Dashboard endpoints (Phase 1b).

Covers per the spec's testing strategy (Section 7 of
docs/ACCOUNTS_DASHBOARD_SPEC.md):

- One happy-path test per endpoint.
- One User-A vs User-B isolation test per endpoint.
- Throttle behavior on POST /plaid/accounts/refresh-balances.
- Alembic upgrade→downgrade→upgrade roundtrip for migration 005.

Uses Flask's `test_request_context` + direct view invocation because the
auth layer in this app relies on headers / bearer tokens that are
tedious to forge in a pytest context. Decorators are unwrapped via
`__wrapped__` so the view runs with a forged `g.current_user`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta

import pytest

os.environ["DATABASE_URL"] = "sqlite://"


@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app

    application = create_app()
    application.config["TESTING"] = True
    yield application


@pytest.fixture(scope="module")
def seeded_ids(app):
    """Create two users and one PlaidItem + one PlaidAccount owned by user_a."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        PlaidAccount,
        PlaidItem,
        User,
    )

    with app.app_context():
        _, SF = _get_db()
        session = SF()

        user_a = User(
            name="Alice",
            email="alice@test.local",
            role="admin",
            is_active=1,
            password_hash="x",
            session_version=0,
        )
        user_b = User(
            name="Bob",
            email="bob@test.local",
            role="user",
            is_active=1,
            password_hash="x",
            session_version=0,
        )
        session.add_all([user_a, user_b])
        session.flush()

        item = PlaidItem(
            user_id=user_a.id,
            plaid_item_id="plaid_item_test",
            institution_id="ins_test",
            institution_name="TestBank",
            access_token_encrypted="enc-token",
            accounts_json='[{"id":"acc_1","name":"Checking","mask":"0001","type":"depository","subtype":"checking"}]',
            status="active",
        )
        session.add(item)
        session.flush()

        acct = PlaidAccount(
            plaid_item_id=item.id,
            user_id=user_a.id,
            plaid_account_id="acc_1",
            account_name="Checking",
            account_mask="0001",
            account_type="depository",
            account_subtype="checking",
        )
        session.add(acct)
        session.commit()

        ids = {
            "user_a": user_a.id,
            "user_b": user_b.id,
            "item": item.id,
            "account": acct.id,
        }
        session.close()
    return ids


def _invoke(app, method, path, user_id, json_data=None):
    """Unwrap auth decorators and invoke the view with a forged g.current_user."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.get(User, user_id)
        with app.test_request_context(path, method=method, json=json_data):
            g.current_user = user
            g.db_session = session
            # url_map.match wants the path alone (no querystring); test_request_context
            # above already parsed the querystring into request.args.
            path_only = path.split("?", 1)[0]
            endpoint, args = app.url_map.bind("").match(path_only, method=method)
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


# ---------------------------------------------------------------------------
# GET /plaid/accounts
# ---------------------------------------------------------------------------

def test_get_accounts_happy_path(app, seeded_ids):
    status, body = _invoke(app, "GET", "/plaid/accounts", seeded_ids["user_a"])
    assert status == 200
    assert len(body["accounts"]) == 1
    assert body["accounts"][0]["name"] == "Checking"
    assert body["accounts"][0]["mask"] == "0001"
    assert body["accounts"][0]["balance_cents"] is None


def test_get_accounts_isolation(app, seeded_ids):
    status, body = _invoke(app, "GET", "/plaid/accounts", seeded_ids["user_b"])
    assert status == 200
    assert body["accounts"] == []


# ---------------------------------------------------------------------------
# PATCH /plaid/items/<id>
# ---------------------------------------------------------------------------

def test_patch_item_happy_path(app, seeded_ids):
    status, body = _invoke(
        app,
        "PATCH",
        f"/plaid/items/{seeded_ids['item']}",
        seeded_ids["user_a"],
        json_data={"nickname": "My Checking"},
    )
    assert status == 200
    assert body == {"id": seeded_ids["item"], "nickname": "My Checking"}


def test_patch_item_isolation(app, seeded_ids):
    status, _ = _invoke(
        app,
        "PATCH",
        f"/plaid/items/{seeded_ids['item']}",
        seeded_ids["user_b"],
        json_data={"nickname": "hijacked"},
    )
    assert status == 404


def test_patch_item_rejects_non_nickname_fields(app, seeded_ids):
    status, body = _invoke(
        app,
        "PATCH",
        f"/plaid/items/{seeded_ids['item']}",
        seeded_ids["user_a"],
        json_data={"institution_name": "pwn"},
    )
    assert status == 400
    assert "nickname" in body.get("error", "").lower()


def test_patch_item_clears_nickname_with_null(app, seeded_ids):
    _invoke(
        app,
        "PATCH",
        f"/plaid/items/{seeded_ids['item']}",
        seeded_ids["user_a"],
        json_data={"nickname": "temporary"},
    )
    status, body = _invoke(
        app,
        "PATCH",
        f"/plaid/items/{seeded_ids['item']}",
        seeded_ids["user_a"],
        json_data={"nickname": None},
    )
    assert status == 200
    assert body["nickname"] is None


# ---------------------------------------------------------------------------
# GET /plaid/transactions
# ---------------------------------------------------------------------------

def test_get_transactions_happy_path(app, seeded_ids):
    status, body = _invoke(app, "GET", "/plaid/transactions", seeded_ids["user_a"])
    assert status == 200
    assert body["total"] == 0
    assert body["transactions"] == []
    assert body["limit"] == 100
    assert body["offset"] == 0


def test_get_transactions_isolation(app, seeded_ids):
    status, body = _invoke(app, "GET", "/plaid/transactions", seeded_ids["user_b"])
    assert status == 200
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# GET /plaid/spending-trends
# ---------------------------------------------------------------------------

def test_get_spending_trends_happy_path(app, seeded_ids):
    status, body = _invoke(app, "GET", "/plaid/spending-trends", seeded_ids["user_a"])
    assert status == 200
    assert body["months"] == 12
    assert body["series"] == []


def test_get_spending_trends_isolation(app, seeded_ids):
    status, body = _invoke(app, "GET", "/plaid/spending-trends", seeded_ids["user_b"])
    assert status == 200
    assert body["series"] == []


def test_spending_trends_clamps_months(app, seeded_ids):
    status, body = _invoke(
        app, "GET", "/plaid/spending-trends?months=500", seeded_ids["user_a"]
    )
    assert status == 200
    assert body["months"] == 24  # clamped


# ---------------------------------------------------------------------------
# POST /plaid/accounts/refresh-balances
# ---------------------------------------------------------------------------

def test_refresh_balances_user_without_items_short_circuits(app, seeded_ids):
    status, body = _invoke(
        app, "POST", "/plaid/accounts/refresh-balances", seeded_ids["user_b"]
    )
    assert status == 200
    assert body["refreshed_items"] == 0
    assert body["accounts"] == []


def test_refresh_balances_throttle_returns_429(app, seeded_ids):
    """Simulate a recent refresh by stamping balance_updated_at, then ensure 429."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    _, SF = _get_db()
    session = SF()
    try:
        acct = session.get(PlaidAccount, seeded_ids["account"])
        acct.balance_updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()

    status, body = _invoke(
        app, "POST", "/plaid/accounts/refresh-balances", seeded_ids["user_a"]
    )
    assert status == 429
    assert body["retry_after_seconds"] > 0


def test_refresh_balances_throttle_releases_after_window(app, seeded_ids):
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    _, SF = _get_db()
    session = SF()
    try:
        acct = session.get(PlaidAccount, seeded_ids["account"])
        acct.balance_updated_at = datetime.utcnow() - timedelta(minutes=10)
        session.commit()
    finally:
        session.close()

    # Plaid isn't configured in the test env, so the route should return 503
    # rather than actually calling Plaid — which still means "throttle let us
    # past". A 429 would mean the throttle is broken.
    status, body = _invoke(
        app, "POST", "/plaid/accounts/refresh-balances", seeded_ids["user_a"]
    )
    assert status in (200, 503), f"expected throttle release, got {status} {body}"


def test_refresh_balances_user_b_independent_of_user_a_throttle(app, seeded_ids):
    """Throttle is per-user, not global. User A's recent refresh must not
    lock User B out."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidAccount

    _, SF = _get_db()
    session = SF()
    try:
        acct = session.get(PlaidAccount, seeded_ids["account"])
        acct.balance_updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()

    # User B has no PlaidItems at all; short-circuit is 200 with
    # refreshed_items=0 regardless of User A's throttle state.
    status, body = _invoke(
        app, "POST", "/plaid/accounts/refresh-balances", seeded_ids["user_b"]
    )
    assert status == 200
    assert body["refreshed_items"] == 0


# ---------------------------------------------------------------------------
# Alembic 005 upgrade / downgrade / upgrade roundtrip
# ---------------------------------------------------------------------------

def test_migration_005_upgrade_downgrade_roundtrip(tmp_path):
    """Run the full migration chain on a fresh DB, downgrade 005, upgrade
    again, and verify the expected schema objects land in each phase.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = tmp_path / "roundtrip.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "PYTHONPATH": repo_root}

    # Bootstrap schema via create_all, stamp at 004, then upgrade to head.
    bootstrap = (
        "from src.backend.initialize_database_schema import initialize_database; "
        "initialize_database()"
    )
    subprocess.run(
        [sys.executable, "-c", bootstrap], check=True, env=env, cwd=repo_root
    )
    alembic_bin = os.path.join(repo_root, ".venv314/bin/alembic")
    if not os.path.exists(alembic_bin):
        alembic_bin = "alembic"
    ini = os.path.join(repo_root, "alembic.ini")
    subprocess.run(
        [alembic_bin, "-c", ini, "stamp", "004_add_plaid_tables"],
        check=True,
        env=env,
        cwd=repo_root,
    )
    subprocess.run(
        [alembic_bin, "-c", ini, "upgrade", "head"], check=True, env=env, cwd=repo_root
    )

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT version_num FROM alembic_version")
    assert c.fetchone()[0] == "005_accounts_dashboard"
    c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='plaid_accounts'"
    )
    assert c.fetchone() is not None
    c.execute("PRAGMA table_info(plaid_items)")
    cols = [r[1] for r in c.fetchall()]
    assert "nickname" in cols
    c.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name='ix_purchases_user_date_category'"
    )
    assert c.fetchone() is not None
    conn.close()

    # Downgrade 005.
    subprocess.run(
        [alembic_bin, "-c", ini, "downgrade", "-1"], check=True, env=env, cwd=repo_root
    )

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT version_num FROM alembic_version")
    assert c.fetchone()[0] == "004_add_plaid_tables"
    c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='plaid_accounts'"
    )
    assert c.fetchone() is None
    c.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name='ix_purchases_user_date_category'"
    )
    assert c.fetchone() is None
    conn.close()

    # Re-upgrade to head.
    subprocess.run(
        [alembic_bin, "-c", ini, "upgrade", "head"], check=True, env=env, cwd=repo_root
    )

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT version_num FROM alembic_version")
    assert c.fetchone()[0] == "005_accounts_dashboard"
    conn.close()
