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


# ---------------------------------------------------------------------------
# Task 5: 'skipped' status must be excluded from open count, ready-to-bill,
# and finalize_session billing/carry-over. These are contract tests — the
# production code already behaves correctly; locking it down so a future
# refactor can't accidentally widen the open filter to include "skipped".
# ---------------------------------------------------------------------------

def _seed_session_with_items(SF, *, statuses, email):
    """Create a fresh active ShoppingSession with one item per status.

    Returns (user_id, session_id, [item_id, ...]). Caller is responsible for
    cleanup. Closes any existing non-closed session first so there's a clean
    slate (the helpers under test pick the newest non-closed session).
    """
    from src.backend.initialize_database_schema import (
        ShoppingListItem,
        ShoppingSession,
        User,
    )

    s = SF()
    try:
        user = s.query(User).filter_by(email=email).first()
        if user is None:
            user = User(
                name="Task5Tester",
                email=email,
                role="admin",
                is_active=1,
                password_hash="x",
                session_version=0,
            )
            s.add(user)
            s.flush()

        # Park any pre-existing non-closed sessions so _get_current_session
        # picks ours. (Cheap: we don't care about their items here.)
        for prev in s.query(ShoppingSession).filter(
            ShoppingSession.status.in_(("active", "ready_to_bill"))
        ).all():
            prev.status = "closed"

        sess = ShoppingSession(
            name="Task5 trip",
            status="active",
            created_by_id=user.id,
        )
        s.add(sess)
        s.flush()

        item_ids = []
        for idx, st in enumerate(statuses):
            it = ShoppingListItem(
                user_id=user.id,
                name=f"task5-{st}-{idx}",
                category="dairy",
                quantity=1.0,
                status=st,
                shopping_session_id=sess.id,
            )
            s.add(it)
            s.flush()
            item_ids.append(it.id)

        s.commit()
        return user.id, sess.id, item_ids
    finally:
        s.close()


def _cleanup_session_and_items(SF, session_id, item_ids):
    from src.backend.initialize_database_schema import (
        ShoppingListItem,
        ShoppingSession,
    )

    s = SF()
    try:
        # Items may have been moved to a successor session (finalize) — delete
        # by id regardless of which session they ended up on.
        for iid in item_ids:
            row = s.get(ShoppingListItem, iid)
            if row is not None:
                s.delete(row)
        # Drop both the original session AND any successor created by finalize.
        # The simplest sweep: delete every session whose name starts with the
        # marker we used. Avoids leaking auto-spawned successors between tests.
        for sess in s.query(ShoppingSession).filter(
            ShoppingSession.id == session_id
        ).all():
            s.delete(sess)
        # Successor cleanup: any active session created during this test run.
        # Match by created_by + empty item set to avoid hitting unrelated data.
        for sess in s.query(ShoppingSession).filter(
            ShoppingSession.status == "active",
        ).all():
            remaining = s.query(ShoppingListItem).filter(
                ShoppingListItem.shopping_session_id == sess.id
            ).count()
            if remaining == 0 and sess.id != session_id:
                s.delete(sess)
        s.commit()
    finally:
        s.close()


def test_skipped_item_not_counted_in_open(app):
    """Open count excludes 'skipped' items. Locks the open-vs-resolved
    contract so future refactors don't widen the filter to `!= "purchased"`."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.manage_shopping_list import _build_shopping_list_payload

    _, SF = _get_db()
    user_id, session_id, item_ids = _seed_session_with_items(
        SF,
        statuses=["open", "skipped", "purchased"],
        email="task5_open@test.local",
    )
    try:
        s = SF()
        try:
            # _build_shopping_list_payload reaches into g.db_session via its
            # _serialize_item helper, so we need an active app context.
            with app.test_request_context("/shopping-list"):
                g.db_session = s
                payload = _build_shopping_list_payload(s)
            assert payload["open_count"] == 1, payload
            assert payload["purchased_count"] == 1, payload
            # Sanity: total item count includes the skipped row, so we can be
            # sure it really is in the session and just excluded from the open
            # count.
            assert payload["count"] == 3, payload
        finally:
            s.close()
    finally:
        _cleanup_session_and_items(SF, session_id, item_ids)


def test_skipped_item_does_not_carry_over_on_finalize(app):
    """Finalize attaches purchased + skipped items to the closed session and
    only carries `open` items to the successor. Skipped items must NOT move."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import (
        ShoppingListItem,
        ShoppingSession,
        User,
    )

    _, SF = SF_tuple = _get_db()
    _ = SF_tuple  # silence "unused" linting
    user_id, session_id, item_ids = _seed_session_with_items(
        SF,
        statuses=["open", "skipped", "purchased"],
        email="task5_finalize@test.local",
    )
    try:
        s = SF()
        try:
            user = s.query(User).filter_by(email="task5_finalize@test.local").first()
            with app.test_request_context("/shopping-list/session/finalize", method="POST", json={}):
                g.current_user = user
                g.db_session = s
                endpoint, args = app.url_map.bind("").match(
                    "/shopping-list/session/finalize", method="POST"
                )
                fn = app.view_functions[endpoint]
                while hasattr(fn, "__wrapped__"):
                    fn = fn.__wrapped__
                rv = fn(**args)
                if isinstance(rv, tuple):
                    status_code = rv[1]
                    body = rv[0].get_json()
                else:
                    status_code, body = 200, rv.get_json()
            assert status_code == 200, body
            # Only the single 'open' item should have been carried over.
            assert body["carried_over_count"] == 1, body
        finally:
            s.close()

        # Now verify the DB state: skipped item is still on the closed session.
        s = SF()
        try:
            closed_session = s.get(ShoppingSession, session_id)
            assert closed_session is not None
            assert closed_session.status == "closed"

            attached = s.query(ShoppingListItem).filter(
                ShoppingListItem.shopping_session_id == session_id
            ).all()
            attached_statuses = sorted(i.status for i in attached)
            # The closed session keeps purchased + skipped; the open one moved.
            assert attached_statuses == ["purchased", "skipped"], attached_statuses

            # And the successor active session should hold only the open item.
            successor = (
                s.query(ShoppingSession)
                .filter(ShoppingSession.status == "active")
                .order_by(ShoppingSession.id.desc())
                .first()
            )
            assert successor is not None and successor.id != session_id
            successor_items = s.query(ShoppingListItem).filter(
                ShoppingListItem.shopping_session_id == successor.id
            ).all()
            assert len(successor_items) == 1
            assert successor_items[0].status == "open"
        finally:
            s.close()
    finally:
        _cleanup_session_and_items(SF, session_id, item_ids)


def test_skipped_item_does_not_block_ready_to_bill(app):
    """ready-to-bill is a session-status transition, not item-state-checked.
    A list of all-skipped/all-purchased items must transition cleanly."""
    from flask import g
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User

    _, SF = _get_db()
    user_id, session_id, item_ids = _seed_session_with_items(
        SF,
        statuses=["skipped", "purchased"],
        email="task5_r2b@test.local",
    )
    try:
        s = SF()
        try:
            user = s.query(User).filter_by(email="task5_r2b@test.local").first()
            with app.test_request_context("/shopping-list/session/ready-to-bill", method="POST", json={}):
                g.current_user = user
                g.db_session = s
                endpoint, args = app.url_map.bind("").match(
                    "/shopping-list/session/ready-to-bill", method="POST"
                )
                fn = app.view_functions[endpoint]
                while hasattr(fn, "__wrapped__"):
                    fn = fn.__wrapped__
                rv = fn(**args)
                if isinstance(rv, tuple):
                    status_code, body = rv[1], rv[0].get_json()
                else:
                    status_code, body = 200, rv.get_json()
            assert status_code == 200, body
            assert body["session"]["status"] == "ready_to_bill", body
        finally:
            s.close()
    finally:
        _cleanup_session_and_items(SF, session_id, item_ids)
