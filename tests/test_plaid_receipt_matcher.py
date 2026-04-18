"""Unit tests for the fuzzy Plaid↔Purchase matcher.

These tests pin the alias table + tolerance semantics that guard the
bulk-confirm dedup path. They use an in-memory SQLite DB so the SQL
amount filter (`func.abs(func.coalesce(...))`) is exercised for real.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

# Force in-memory SQLite even if the shell has DATABASE_URL exported (e.g.
# inside the prod container). `setdefault` would be a no-op and the test
# would try `DELETE FROM purchases` on the real DB — FK violations at
# best, data loss at worst.
os.environ["DATABASE_URL"] = "sqlite://"


from src.backend.plaid_receipt_matcher import (
    find_matching_purchase,
    merchants_match,
)


# ---------------------------------------------------------------------------
# merchants_match — alias + token overlap
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Anthropic, PBC", "Claude.Ai Su"),
    ("CLAUDE AI", "anthropic"),
    ("Amazon.com",   "AMZN Mktp"),
    ("Apple.com/Bill", "Apple Services"),
    ("Tesla Inc", "TESLA MOTORS"),
    ("AT&T ", "att*wireless"),
    ("CITIZENS ENERGY GROUP", "Citizens Energy"),
    ("Chase Credit Crd", "CHASE CARD"),
    ("Whole Foods Market", "WFM #123"),
    ("Trader Joe's #456", "traderjoe"),
    ("Walmart Supercenter", "WM SUPERCENTER"),
    ("Netflix.com", "NETFLIX"),
    ("Spotify USA", "SPOTIFY"),
])
def test_merchants_match_aliases(a, b):
    assert merchants_match(a, b), f"expected {a!r} ≈ {b!r}"


@pytest.mark.parametrize("a,b", [
    ("Starbucks", "Dunkin"),
    ("Shell Oil", "Chevron"),
    ("Uber", "Lyft"),
    (None, "anything"),
    ("", "anything"),
])
def test_merchants_match_negatives(a, b):
    assert not merchants_match(a, b)


def test_merchants_match_token_overlap():
    # 4+ char shared token → match (both contain "coffee")
    assert merchants_match("Blue Bottle Coffee", "Coffee Bean Tea Leaf")
    # Short shared token (<4 chars) → no match
    assert not merchants_match("AB Corp", "AB Inc")


# ---------------------------------------------------------------------------
# find_matching_purchase — SQL integration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def session_factory():
    """Module-scoped in-memory SQLite session factory + seeded users."""
    from src.backend.create_flask_application import _get_db
    from src.backend.initialize_database_schema import User
    _, SF = _get_db()
    s = SF()
    # Tests reference user_ids 1 and 2 — seed both so FK constraints pass.
    for uid in (1, 2):
        if s.get(User, uid) is None:
            s.add(User(
                id=uid,
                name=f"u{uid}",
                email=f"u{uid}@test.local",
                role="user",
                is_active=1,
                password_hash="x",
                session_version=0,
            ))
    s.commit()
    s.close()
    return SF


@pytest.fixture
def session(session_factory):
    s = session_factory()
    yield s
    # Tests only flush (not commit) the in-test Purchase/Store they create,
    # so a plain rollback is enough to clear per-test state — safer than a
    # DELETE (autoflush + SQLite FK cascade semantics can trip
    # "FOREIGN KEY constraint failed" on pending rows). Any row that a test
    # does commit will persist; no test currently does so.
    from src.backend.initialize_database_schema import Purchase, Store
    s.rollback()
    s.query(Purchase).delete()
    s.query(Store).delete()
    s.commit()
    s.close()


def _mk_purchase(session, user_id, store_name, amount, when):
    from datetime import datetime, time as time_cls
    from src.backend.initialize_database_schema import Purchase, Store
    store = Store(name=store_name)
    session.add(store)
    session.flush()
    dt = datetime.combine(when, time_cls.min) if not isinstance(when, datetime) else when
    p = Purchase(
        user_id=user_id,
        store_id=store.id,
        total_amount=amount,
        date=dt,
    )
    session.add(p)
    session.commit()
    return p


def test_find_matching_purchase_happy_path(session):
    today = date.today()
    p = _mk_purchase(session, user_id=1, store_name="Anthropic, PBC",
                     amount=20.00, when=today)
    match = find_matching_purchase(session, 1, 20.00, today, "Claude.Ai Su")
    assert match is not None
    assert match.id == p.id


def test_find_matching_purchase_amount_epsilon(session):
    today = date.today()
    _mk_purchase(session, 1, "Costco Whse", 123.45, today)
    # $0.02 tolerance: 123.47 hits, 123.48 misses
    assert find_matching_purchase(session, 1, 123.47, today, "Costco") is not None
    assert find_matching_purchase(session, 1, 123.48, today, "Costco") is None


def test_find_matching_purchase_date_window(session):
    today = date.today()
    _mk_purchase(session, 1, "Target", 50.00, today)
    assert find_matching_purchase(session, 1, 50.00, today - timedelta(days=3), "TGT") is not None
    assert find_matching_purchase(session, 1, 50.00, today + timedelta(days=3), "TGT") is not None
    assert find_matching_purchase(session, 1, 50.00, today - timedelta(days=4), "TGT") is None


def test_find_matching_purchase_user_isolation(session):
    today = date.today()
    _mk_purchase(session, user_id=1, store_name="Netflix", amount=15.00, when=today)
    # Same amount/date/merchant but different user → no match
    assert find_matching_purchase(session, 2, 15.00, today, "Netflix.com") is None


def test_find_matching_purchase_merchant_mismatch(session):
    today = date.today()
    _mk_purchase(session, 1, "Starbucks", 8.75, today)
    # Same amount/date but unrelated merchant → no match
    assert find_matching_purchase(session, 1, 8.75, today, "Shell Oil") is None


def test_find_matching_purchase_none_inputs(session):
    today = date.today()
    assert find_matching_purchase(session, 1, None, today, "anything") is None
    assert find_matching_purchase(session, 1, 10.0, None, "anything") is None
