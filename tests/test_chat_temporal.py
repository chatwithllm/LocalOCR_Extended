"""Unit tests for the chat-assistant temporal-intent extractor and
shopping-activity aggregator. In-memory SQLite, no Flask, no network.
"""
import os

# Configure env BEFORE importing the project — chat_assistant.py touches
# AIModelConfig at import time which expects FERNET_SECRET_KEY.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FERNET_SECRET_KEY", "test-fernet-key-for-unit-tests-only")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")

import pytest

from src.backend.chat_assistant import _extract_temporal_intent


@pytest.mark.parametrize(
    "message",
    [
        "When did we shop lately?",
        "how often do we shop",
        "what's our consumption rate?",
        "show me recent shopping",
        "when was the last trip to the store",
        "we go pretty frequently right?",
        "how much are we consuming",
        "trend in our buying",
    ],
)
def test_temporal_intent_positive(message):
    assert _extract_temporal_intent(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "how much did we spend on milk last month",
        "where do property taxes belong",
        "list uncategorized receipts",
        "show me the top stores",
        "what's the grocery total",
        "",
    ],
)
def test_temporal_intent_negative(message):
    assert _extract_temporal_intent(message) is False


@pytest.mark.parametrize(
    "message",
    [
        # These look temporal but are NOT shopping-related. The regex
        # intentionally lets them through — the cost is ~1 KB of extra
        # context on the rare occasion they hit. We accept the FP and
        # rely on the LLM to ignore irrelevant data when answering.
        # Locked in here so a regex tightening is a deliberate change,
        # not an accidental one. See chat_assistant.py:457.
        "what is the interest rate on this card",
        "show me the exchange rate",
        "consumption tax",
        "when in doubt show all",
    ],
)
def test_temporal_intent_accepted_false_positives(message):
    assert _extract_temporal_intent(message) is True


from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backend.initialize_database_schema import (
    Base,
    Purchase,
    ReceiptItem,
    Store,
    User,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def household(session):
    """Two users + one store + a spread of receipts across 90 days.

    Layout (relative to NOW = 2026-04-25 UTC):
      - mom: 4 purchases inside 7d window, 12 in 30d total, 30 in 90d
      - dad: 2 purchases inside 7d, 6 in 30d, 18 in 90d
      - one refund row inside 7d (must be excluded from counts/spend)
    """
    mom = User(name="Mom", email="mom@example.com")
    dad = User(name="Dad", email="dad@example.com")
    session.add_all([mom, dad])
    session.flush()

    store = Store(name="Costco")
    session.add(store)
    session.flush()

    NOW = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    def _add_purchase(days_ago, attr_user, amount, items=1, refund=False):
        p = Purchase(
            store_id=store.id,
            total_amount=amount,
            date=NOW - timedelta(days=days_ago),
            domain="grocery",
            transaction_type="refund" if refund else "purchase",
            attribution_user_id=attr_user.id,
            attribution_kind="personal",
            user_id=attr_user.id,
        )
        session.add(p)
        session.flush()
        for _ in range(items):
            session.add(ReceiptItem(
                purchase_id=p.id,
                product_id=1,
                quantity=1,
                unit_price=amount / max(items, 1),
                attribution_user_id=attr_user.id,
                attribution_kind="personal",
            ))
        return p

    # Mom: 4 in last 7d, 8 more in 8-30d (=12 in 30d), 18 more in 31-90d
    for d in [1, 2, 4, 6]:
        _add_purchase(d, mom, 50.0, items=3)
    for d in [10, 12, 14, 18, 22, 25, 27, 29]:
        _add_purchase(d, mom, 60.0, items=4)
    for d in range(31, 91, 4)[:18]:
        _add_purchase(d, mom, 70.0, items=2)

    # Dad: 2 in 7d, 4 more in 30d, 12 more in 90d
    for d in [3, 5]:
        _add_purchase(d, dad, 40.0, items=2)
    for d in [11, 16, 20, 24]:
        _add_purchase(d, dad, 45.0, items=3)
    for d in range(33, 91, 5)[:12]:
        _add_purchase(d, dad, 55.0, items=2)

    # Refund inside 7d — should NOT count
    _add_purchase(2, mom, 25.0, items=1, refund=True)

    session.commit()
    return {"mom": mom, "dad": dad, "store": store, "now": NOW}


def test_shopping_activity_windows_excludes_refunds(session, household):
    from src.backend.chat_assistant import _compute_shopping_activity

    result = _compute_shopping_activity(
        session, household["mom"], household["now"]
    )
    assert result is not None
    # 4 (mom) + 2 (dad) = 6 in 7d; refund excluded
    assert result["windows"]["last_7d"]["trips"] == 6
    # mom 12 + dad 6 = 18 in 30d
    assert result["windows"]["last_30d"]["trips"] == 18


def test_shopping_activity_recent_receipts_top5(session, household):
    from src.backend.chat_assistant import _compute_shopping_activity

    result = _compute_shopping_activity(
        session, household["mom"], household["now"]
    )
    rec = result["recent_receipts"]
    assert len(rec) == 5
    # Sorted desc by date — first is the most recent (1 day ago)
    assert rec[0]["date"] == "2026-04-24"
    assert rec[0]["store"] == "Costco"
    assert rec[0]["attribution"] in ("Mom", "Dad")
    # The refund row had amount=25.0 — confirm it isn't in recent_receipts.
    assert 25.0 not in {r["amount"] for r in rec}


def test_shopping_activity_per_person_split(session, household):
    from src.backend.chat_assistant import _compute_shopping_activity

    result = _compute_shopping_activity(
        session, household["mom"], household["now"]
    )
    names = [p["name"] for p in result["per_person"]]
    assert "Mom" in names
    assert "Dad" in names
    mom_block = next(p for p in result["per_person"] if p["name"] == "Mom")
    # Mom had 4 purchases inside 7d (refund excluded)
    assert mom_block["windows"]["last_7d"]["trips"] == 4
    assert mom_block["last_trip"]["store"] == "Costco"


def test_shopping_activity_cadence_trend_classification(session, household):
    from src.backend.chat_assistant import _compute_shopping_activity

    result = _compute_shopping_activity(
        session, household["mom"], household["now"]
    )
    cad = result["cadence"]
    assert "trips_per_week_30d" in cad
    assert "trips_per_week_90d" in cad
    assert cad["trend"] in ("up", "down", "steady")


def test_shopping_activity_trend_inactive_when_no_recent_trips(session, household):
    """rows_30 empty but rows_90 present → trend should be 'inactive',
    not 'down'. Avoids LLM misreading inactivity as a decline."""
    from src.backend.chat_assistant import _compute_shopping_activity
    from src.backend.initialize_database_schema import Purchase

    # Wipe rows in the last 30 days but keep older ones.
    NOW = household["now"]
    cutoff_30 = NOW - timedelta(days=30)
    session.query(Purchase).filter(Purchase.date >= cutoff_30).delete()
    session.commit()

    result = _compute_shopping_activity(session, household["mom"], NOW)
    assert result is not None
    assert result["cadence"]["trend"] == "inactive"
    assert result["cadence"]["trips_per_week_30d"] == 0.0


def test_shopping_activity_returns_none_on_empty_db(session):
    from src.backend.chat_assistant import _compute_shopping_activity
    user = User(name="Lonely", email="alone@example.com")
    session.add(user)
    session.commit()
    NOW = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
    assert _compute_shopping_activity(session, user, NOW) is None


def test_build_data_context_includes_shopping_activity_when_intent_hits(
    session, household,
):
    from src.backend import chat_assistant
    NOW = household["now"]
    real_datetime = chat_assistant.datetime

    class _FrozenDT(real_datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    chat_assistant.datetime = _FrozenDT
    try:
        ctx = chat_assistant.build_data_context(
            session, household["mom"], user_message="when did we shop lately"
        )
        assert ctx["shopping_activity"] is not None
        assert ctx["shopping_activity"]["windows"]["last_7d"]["trips"] >= 1

        ctx2 = chat_assistant.build_data_context(
            session, household["mom"], user_message="how much did we spend on milk"
        )
        assert ctx2["shopping_activity"] is None
    finally:
        chat_assistant.datetime = real_datetime
