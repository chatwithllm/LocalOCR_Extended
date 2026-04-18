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
    # Pin to 005 explicitly (not "head") so this test continues to exercise
    # the 005-specific invariants even as later migrations (006+) land.
    subprocess.run(
        [alembic_bin, "-c", ini, "upgrade", "005_accounts_dashboard"],
        check=True, env=env, cwd=repo_root,
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

    # Re-upgrade to 005 (pinned, see above).
    subprocess.run(
        [alembic_bin, "-c", ini, "upgrade", "005_accounts_dashboard"],
        check=True, env=env, cwd=repo_root,
    )

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT version_num FROM alembic_version")
    assert c.fetchone()[0] == "005_accounts_dashboard"
    conn.close()


# ---------------------------------------------------------------------------
# POST /plaid/staged-transactions/bulk-confirm (Phase 2)
# ---------------------------------------------------------------------------

def _seed_staged(app, user_id, item_id, account_id, count, date=None):
    """Insert `count` ready_to_import staged transactions for a user.

    Returns the list of inserted IDs in creation order.
    """
    from datetime import date as date_cls
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    _, SF = _get_db()
    session = SF()
    ids = []
    try:
        for i in range(count):
            row = PlaidStagedTransaction(
                plaid_item_id=item_id,
                user_id=user_id,
                # plaid_transaction_id has a UNIQUE constraint, so randomise
                # per insertion and per test to avoid collisions between
                # tests in the module-scoped fixture.
                plaid_transaction_id=f"ptx_{user_id}_{item_id}_{i}_{os.urandom(3).hex()}",
                plaid_account_id=account_id,
                amount=12.34 + i,
                iso_currency_code="USD",
                transaction_date=date or date_cls.today(),
                name=f"Test merchant {i}",
                merchant_name=f"Test merchant {i}",
                suggested_receipt_type="general_expense",
                suggested_spending_domain="general_expense",
                suggested_budget_category="other",
                status="ready_to_import",
                raw_json="{}",
            )
            session.add(row)
            session.flush()
            ids.append(row.id)
        session.commit()
    finally:
        session.close()
    return ids


def _cleanup_staged(app):
    """Delete every staged + downstream purchase/receipt/store row so tests
    don't bleed state into each other.

    Confirming a staged txn creates a Purchase (and possibly a Store +
    TelegramReceipt); without cleaning those, the next test's seeded
    staged rows can auto-match the previous test's leftovers via Guard B
    in bulk-confirm — producing matched_existing hits instead of fresh
    confirmations.
    """
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        PlaidStagedTransaction,
        Purchase,
        Store,
        TelegramReceipt,
    )

    _, SF = _get_db()
    session = SF()
    try:
        session.query(PlaidStagedTransaction).delete()
        session.query(TelegramReceipt).delete()
        session.query(Purchase).delete()
        session.query(Store).delete()
        session.commit()
    finally:
        session.close()


def test_bulk_confirm_happy_path_with_explicit_ids(app, seeded_ids):
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    _cleanup_staged(app)
    staged_ids = _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=2,
    )

    status, body = _invoke(
        app,
        "POST",
        "/plaid/staged-transactions/bulk-confirm",
        seeded_ids["user_a"],
        json_data={"ids": staged_ids},
    )
    assert status == 200, body
    assert body["attempted"] == 2
    assert body["confirmed"] == 2
    assert body["failed"] == []

    _, SF = _get_db()
    session = SF()
    try:
        rows = (
            session.query(PlaidStagedTransaction)
            .filter(PlaidStagedTransaction.id.in_(staged_ids))
            .all()
        )
        assert all(r.status == "confirmed" for r in rows)
        assert all(r.confirmed_purchase_id is not None for r in rows)
    finally:
        session.close()
    _cleanup_staged(app)


def test_bulk_confirm_isolation_user_b_cannot_confirm_user_a_rows(app, seeded_ids):
    """User B targeting User A's staged IDs must confirm zero rows."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    _cleanup_staged(app)
    staged_ids = _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=2,
    )

    status, body = _invoke(
        app,
        "POST",
        "/plaid/staged-transactions/bulk-confirm",
        seeded_ids["user_b"],
        json_data={"ids": staged_ids},
    )
    assert status == 200, body
    assert body["attempted"] == 0
    assert body["confirmed"] == 0

    _, SF = _get_db()
    session = SF()
    try:
        rows = (
            session.query(PlaidStagedTransaction)
            .filter(PlaidStagedTransaction.id.in_(staged_ids))
            .all()
        )
        # User A's rows must be untouched.
        assert all(r.status == "ready_to_import" for r in rows)
        assert all(r.confirmed_purchase_id is None for r in rows)
    finally:
        session.close()
    _cleanup_staged(app)


def test_bulk_confirm_all_ready_respects_max_cap(app, seeded_ids):
    _cleanup_staged(app)
    _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=3,
    )

    status, body = _invoke(
        app,
        "POST",
        "/plaid/staged-transactions/bulk-confirm",
        seeded_ids["user_a"],
        json_data={"all_ready": True, "max": 2},
    )
    assert status == 200, body
    assert body["attempted"] == 2  # cap honored
    assert body["confirmed"] == 2
    _cleanup_staged(app)


def test_bulk_confirm_rejects_empty_payload(app, seeded_ids):
    """Without ids or all_ready the endpoint must 400 rather than silently
    confirming nothing."""
    status, body = _invoke(
        app,
        "POST",
        "/plaid/staged-transactions/bulk-confirm",
        seeded_ids["user_a"],
        json_data={},
    )
    assert status == 400, body
    assert "error" in body


# ---------------------------------------------------------------------------
# Phase 2 — /staged-transactions/<id>/match-candidates
# Phase 2 — /staged-transactions/<id>/link-receipt
# ---------------------------------------------------------------------------

def _mk_purchase_for_user(app, user_id, store_name, amount, when):
    """Helper: create a Store + Purchase owned by user_id."""
    from datetime import datetime as _dt, time as _time
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import Purchase, Store

    _, SF = _get_db()
    s = SF()
    try:
        store = Store(name=store_name)
        s.add(store)
        s.flush()
        dt = _dt.combine(when, _time.min) if hasattr(when, "year") and not isinstance(when, _dt) else when
        p = Purchase(user_id=user_id, store_id=store.id, total_amount=amount, date=dt)
        s.add(p)
        s.commit()
        return p.id
    finally:
        s.close()


def test_match_candidates_returns_ranked_list(app, seeded_ids):
    """match-candidates should return the closest Purchase first (merchant match)."""
    from datetime import date as _date
    _cleanup_staged(app)
    today = _date.today()

    # Owned by user_a: near-perfect match (+$0.01, same day, alias merchant).
    _mk_purchase_for_user(app, seeded_ids["user_a"], "Anthropic, PBC", 25.00, today)
    # A distractor: same amount but different merchant + 10 days off.
    _mk_purchase_for_user(app, seeded_ids["user_a"], "Target", 25.00, today - timedelta(days=10))

    staged_ids = _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=1,
    )
    # Rewrite the staged row so it looks like a Claude.ai $25 charge today.
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction
    _, SF = _get_db()
    s = SF()
    try:
        row = s.get(PlaidStagedTransaction, staged_ids[0])
        row.amount = 25.00
        row.merchant_name = "CLAUDE.AI SU"
        row.transaction_date = today
        s.commit()
    finally:
        s.close()

    status, body = _invoke(
        app,
        "GET",
        f"/plaid/staged-transactions/{staged_ids[0]}/match-candidates",
        seeded_ids["user_a"],
    )
    assert status == 200, body
    cands = body["candidates"]
    assert len(cands) >= 1
    # First candidate should be the alias-matched Anthropic purchase.
    assert cands[0]["store"] == "Anthropic, PBC"
    assert cands[0]["merchant_match"] is True
    _cleanup_staged(app)


def test_match_candidates_isolation(app, seeded_ids):
    """User B must not see match candidates for User A's staged tx."""
    _cleanup_staged(app)
    staged_ids = _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=1,
    )
    status, body = _invoke(
        app,
        "GET",
        f"/plaid/staged-transactions/{staged_ids[0]}/match-candidates",
        seeded_ids["user_b"],
    )
    assert status == 404, body
    _cleanup_staged(app)


def test_link_receipt_happy_path(app, seeded_ids):
    """Linking a staged tx to an existing Purchase should mark it confirmed."""
    from datetime import date as _date
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import PlaidStagedTransaction

    _cleanup_staged(app)
    today = _date.today()
    pid = _mk_purchase_for_user(app, seeded_ids["user_a"], "Tesla Inc", 100.00, today)
    staged_ids = _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=1,
    )

    status, body = _invoke(
        app,
        "POST",
        f"/plaid/staged-transactions/{staged_ids[0]}/link-receipt",
        seeded_ids["user_a"],
        json_data={"purchase_id": pid},
    )
    assert status == 200, body
    assert body["matched_existing"] is True
    assert body["purchase_id"] == pid

    _, SF = _get_db()
    s = SF()
    try:
        row = s.get(PlaidStagedTransaction, staged_ids[0])
        assert row.status == "confirmed"
        assert row.confirmed_purchase_id == pid
    finally:
        s.close()
    _cleanup_staged(app)


def test_link_receipt_rejects_other_users_purchase(app, seeded_ids):
    """User A must not be able to link to a Purchase owned by User B."""
    from datetime import date as _date
    _cleanup_staged(app)
    today = _date.today()
    pid_b = _mk_purchase_for_user(app, seeded_ids["user_b"], "Netflix", 15.00, today)
    staged_ids = _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=1,
    )
    status, body = _invoke(
        app,
        "POST",
        f"/plaid/staged-transactions/{staged_ids[0]}/link-receipt",
        seeded_ids["user_a"],
        json_data={"purchase_id": pid_b},
    )
    assert status == 404, body
    _cleanup_staged(app)


def test_link_receipt_rejects_empty_body(app, seeded_ids):
    _cleanup_staged(app)
    staged_ids = _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=1,
    )
    status, body = _invoke(
        app,
        "POST",
        f"/plaid/staged-transactions/{staged_ids[0]}/link-receipt",
        seeded_ids["user_a"],
        json_data={},
    )
    assert status == 400, body
    _cleanup_staged(app)


def test_link_receipt_conflict_when_already_confirmed(app, seeded_ids):
    """Re-linking a confirmed staged row must 409."""
    from datetime import date as _date
    _cleanup_staged(app)
    today = _date.today()
    pid = _mk_purchase_for_user(app, seeded_ids["user_a"], "Kroger", 40.00, today)
    staged_ids = _seed_staged(
        app,
        seeded_ids["user_a"],
        seeded_ids["item"],
        "acc_1",
        count=1,
    )
    # First link succeeds.
    status, _ = _invoke(
        app,
        "POST",
        f"/plaid/staged-transactions/{staged_ids[0]}/link-receipt",
        seeded_ids["user_a"],
        json_data={"purchase_id": pid},
    )
    assert status == 200
    # Second link on the same staged row must 409.
    status, body = _invoke(
        app,
        "POST",
        f"/plaid/staged-transactions/{staged_ids[0]}/link-receipt",
        seeded_ids["user_a"],
        json_data={"purchase_id": pid},
    )
    assert status == 409, body
    _cleanup_staged(app)
