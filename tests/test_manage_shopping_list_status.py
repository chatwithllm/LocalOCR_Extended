"""Tests for ShoppingListItem.status validation on PUT /shopping-list/items/<id>.

Task 4 of the Kitchen View feature: tighten the validator to reject anything
outside {"open", "purchased", "skipped"}. Mirrors the auth-bypass idiom used
in tests/test_accounts_dashboard.py — Flask `test_request_context` plus
`__wrapped__` to peel off the @require_write_access decorator. We forge
`g.current_user` and `g.db_session` directly rather than threading a real
session cookie, because the auth layer relies on header/bearer-token state
that's painful to fake in pytest.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")


@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app

    application = create_app()
    application.config["TESTING"] = True
    yield application


@pytest.fixture
def sample_shopping_item_id(app):
    """Create a fresh ShoppingListItem for each test (function scope so
    status mutations don't leak between cases)."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import ShoppingListItem, User

    _, SF = _get_db()
    session = SF()
    try:
        # Reuse a single test user across calls; harmless if it already exists.
        user = session.query(User).filter_by(email="shoplist_status@test.local").first()
        if user is None:
            user = User(
                name="ShopListTester",
                email="shoplist_status@test.local",
                role="admin",
                is_active=1,
                password_hash="x",
                session_version=0,
            )
            session.add(user)
            session.flush()

        item = ShoppingListItem(
            user_id=user.id,
            name="Test Milk",
            category="dairy",
            quantity=1.0,
            status="open",
        )
        session.add(item)
        session.commit()
        item_id = item.id
        user_id = user.id
    finally:
        session.close()

    yield item_id

    # Cleanup: drop the row so a re-run starts clean.
    session = SF()
    try:
        row = session.get(ShoppingListItem, item_id)
        if row is not None:
            session.delete(row)
            session.commit()
    finally:
        session.close()

    # Stash user_id for any future debugging — not strictly needed.
    _ = user_id


def _invoke_put(app, path, user_email, json_data):
    """Unwrap @require_write_access and invoke the PUT view with a forged
    g.current_user / g.db_session."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    session = SF()
    try:
        user = session.query(User).filter_by(email=user_email).first()
        with app.test_request_context(path, method="PUT", json=json_data):
            g.current_user = user
            g.db_session = session
            endpoint, args = app.url_map.bind("").match(path, method="PUT")
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
# Status validation
# ---------------------------------------------------------------------------

def test_put_status_skipped_accepted(app, sample_shopping_item_id):
    status, body = _invoke_put(
        app,
        f"/shopping-list/items/{sample_shopping_item_id}",
        "shoplist_status@test.local",
        {"status": "skipped"},
    )
    assert status == 200, body
    assert body["item"]["status"] == "skipped"


def test_put_status_purchased_accepted(app, sample_shopping_item_id):
    status, body = _invoke_put(
        app,
        f"/shopping-list/items/{sample_shopping_item_id}",
        "shoplist_status@test.local",
        {"status": "purchased"},
    )
    assert status == 200, body
    assert body["item"]["status"] == "purchased"


def test_put_status_open_accepted(app, sample_shopping_item_id):
    status, body = _invoke_put(
        app,
        f"/shopping-list/items/{sample_shopping_item_id}",
        "shoplist_status@test.local",
        {"status": "open"},
    )
    assert status == 200, body


def test_put_status_garbage_returns_400(app, sample_shopping_item_id):
    status, body = _invoke_put(
        app,
        f"/shopping-list/items/{sample_shopping_item_id}",
        "shoplist_status@test.local",
        {"status": "wat"},
    )
    assert status == 400, body
    assert body.get("error")


def test_put_no_status_field_is_noop(app, sample_shopping_item_id):
    status, body = _invoke_put(
        app,
        f"/shopping-list/items/{sample_shopping_item_id}",
        "shoplist_status@test.local",
        {"note": "hi"},
    )
    assert status == 200, body


def test_put_status_empty_string_is_noop(app, sample_shopping_item_id):
    # Empty status should not 400; it falls through and keeps the existing value.
    status, body = _invoke_put(
        app,
        f"/shopping-list/items/{sample_shopping_item_id}",
        "shoplist_status@test.local",
        {"status": ""},
    )
    assert status == 200, body
    assert body["item"]["status"] == "open"  # unchanged from default


def test_put_status_out_of_stock_accepted(app, sample_shopping_item_id):
    status, body = _invoke_put(
        app,
        f"/shopping-list/items/{sample_shopping_item_id}",
        "shoplist_status@test.local",
        {"status": "out_of_stock"},
    )
    assert status == 200, body
    assert body["item"]["status"] == "out_of_stock"
