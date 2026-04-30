from datetime import datetime, timedelta, timezone

import pytest

from src.backend.initialize_database_schema import (
    Base,
    Purchase,
    Store,
    create_db_engine,
    create_session_factory,
)
from src.backend.manage_stores import classify_store, get_store_buckets


NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(n):
    return NOW - timedelta(days=n)


@pytest.mark.parametrize(
    "override, artifact, last_purchase, count, expected",
    [
        # Auto: recency-based.
        (None, False, _days_ago(30), 2, "frequent"),
        (None, False, _days_ago(89), 1, "frequent"),
        (None, False, _days_ago(91), 1, "low_freq"),
        (None, False, _days_ago(200), 1, "low_freq"),
        (None, False, _days_ago(365), 1, "low_freq"),
        (None, False, _days_ago(366), 1, "hidden"),
        (None, False, _days_ago(540), 7, "hidden"),
        (None, False, None, 0, "hidden"),
        # Override pins ignore recency.
        ("frequent", False, _days_ago(540), 0, "frequent"),
        ("low_freq", False, _days_ago(30), 10, "low_freq"),
        ("hidden", False, _days_ago(30), 10, "hidden"),
        # Artifact always wins.
        ("frequent", True, _days_ago(30), 10, "hidden"),
        (None, True, _days_ago(30), 10, "hidden"),
    ],
)
def test_classify_store_truth_table(override, artifact, last_purchase, count, expected):
    bucket = classify_store(
        override=override,
        is_payment_artifact=artifact,
        last_purchase_at=last_purchase,
        purchase_count=count,
        now=NOW,
    )
    assert bucket == expected


def test_classify_store_defaults_now_to_utcnow():
    bucket = classify_store(
        override=None,
        is_payment_artifact=False,
        last_purchase_at=datetime.now(timezone.utc) - timedelta(days=10),
        purchase_count=1,
    )
    assert bucket == "frequent"


@pytest.fixture
def session(tmp_path):
    db_path = tmp_path / "buckets.db"
    engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = create_session_factory(engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _add_store(session, name, override=None, is_payment_artifact=False):
    store = Store(name=name, visibility_override=override, is_payment_artifact=is_payment_artifact)
    session.add(store)
    session.flush()
    return store


def _add_purchase(session, store_id, days_ago):
    p = Purchase(
        store_id=store_id,
        date=datetime.now(timezone.utc) - timedelta(days=days_ago),
        total_amount=10.0,
    )
    session.add(p)
    session.flush()
    return p


def test_get_store_buckets_groups_by_recency(session):
    fresh = _add_store(session, "Costco")
    _add_purchase(session, fresh.id, 10)
    older = _add_store(session, "Chowka")
    _add_purchase(session, older.id, 200)
    ancient = _add_store(session, "Random Diner")
    _add_purchase(session, ancient.id, 800)
    _add_store(session, "Apple Store")
    session.commit()

    buckets = get_store_buckets(session)
    names = {b: [s["name"] for s in buckets[b]] for b in ("frequent", "low_freq", "hidden")}
    assert "Costco" in names["frequent"]
    assert "Chowka" in names["low_freq"]
    assert "Random Diner" in names["hidden"]
    assert "Apple Store" in names["hidden"]


def test_get_store_buckets_honours_override(session):
    _add_store(session, "Pinned Visible", override="frequent")
    session.commit()
    buckets = get_store_buckets(session)
    assert any(row["name"] == "Pinned Visible" for row in buckets["frequent"])


def test_get_store_buckets_artifact_always_hidden(session):
    _add_store(session, "Chase Credit Crd", is_payment_artifact=True)
    session.commit()
    buckets = get_store_buckets(session)
    assert any(row["name"] == "Chase Credit Crd" for row in buckets["hidden"])


def test_get_store_buckets_includes_usage_stats(session):
    s = _add_store(session, "Kroger")
    _add_purchase(session, s.id, 5)
    _add_purchase(session, s.id, 30)
    _add_purchase(session, s.id, 60)
    session.commit()
    buckets = get_store_buckets(session)
    row = next(r for r in buckets["frequent"] if r["name"] == "Kroger")
    assert row["purchase_count"] == 3
    assert row["last_purchase_at"] is not None
    assert row["override"] is None
    assert row["is_payment_artifact"] is False
