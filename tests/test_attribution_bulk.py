"""Unit tests for the bulk-attribution + attribution-stats endpoints
and the auto-suggest helper. Mirror tests/test_chat_temporal.py:
in-memory SQLite, no Flask app, env vars set BEFORE imports.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FERNET_SECRET_KEY", "test-fernet-key-for-unit-tests-only")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backend.initialize_database_schema import (
    Base, Purchase, ReceiptItem, Store, User,
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
    mom = User(name="Mom", email="mom@example.com")
    dad = User(name="Dad", email="dad@example.com")
    session.add_all([mom, dad])
    session.flush()

    costco = Store(name="Costco")
    target = Store(name="Target")
    session.add_all([costco, target])
    session.flush()

    NOW = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    def _purchase(days_ago, uploader, store, attr=None, kind=None,
                  attr_ids=None, amount=50.0):
        p = Purchase(
            store_id=store.id,
            total_amount=amount,
            date=NOW - timedelta(days=days_ago),
            domain="grocery",
            transaction_type="purchase",
            user_id=uploader.id,
            attribution_user_id=attr.id if attr else None,
            attribution_user_ids=(
                json.dumps([u.id for u in attr_ids]) if attr_ids else None
            ),
            attribution_kind=kind,
        )
        session.add(p)
        session.flush()
        return p

    return {
        "mom": mom, "dad": dad,
        "costco": costco, "target": target,
        "now": NOW, "_purchase": _purchase,
    }


def test_bulk_attribution_updates_multiple_rows(session, household):
    from src.backend.handle_receipt_upload import _bulk_apply_attribution

    p1 = household["_purchase"](1, household["mom"], household["costco"])
    p2 = household["_purchase"](2, household["mom"], household["costco"])
    p3 = household["_purchase"](3, household["dad"], household["target"])
    session.commit()

    result = _bulk_apply_attribution(
        session,
        purchase_ids=[p1.id, p2.id, p3.id],
        user_ids=[household["mom"].id],
        kind="personal",
        apply_to_items=False,
    )
    assert result["updated"] == 3
    assert result["skipped"] == []

    for pid in [p1.id, p2.id, p3.id]:
        row = session.query(Purchase).get(pid)
        assert row.attribution_user_id == household["mom"].id
        assert row.attribution_kind == "personal"


def test_bulk_attribution_skips_missing_ids(session, household):
    from src.backend.handle_receipt_upload import _bulk_apply_attribution

    p1 = household["_purchase"](1, household["mom"], household["costco"])
    session.commit()

    result = _bulk_apply_attribution(
        session,
        purchase_ids=[p1.id, 9999, 8888],
        user_ids=[household["mom"].id],
        kind="personal",
        apply_to_items=False,
    )
    assert result["updated"] == 1
    assert {row["purchase_id"] for row in result["skipped"]} == {9999, 8888}


def test_bulk_attribution_household_clears_user_ids(session, household):
    from src.backend.handle_receipt_upload import _bulk_apply_attribution

    p1 = household["_purchase"](1, household["mom"], household["costco"])
    session.commit()

    result = _bulk_apply_attribution(
        session,
        purchase_ids=[p1.id],
        user_ids=[],
        kind="household",
        apply_to_items=False,
    )
    assert result["updated"] == 1
    row = session.query(Purchase).get(p1.id)
    assert row.attribution_kind == "household"
    assert row.attribution_user_id is None
    # JSON list either None or "[]" — both acceptable.
    assert row.attribution_user_ids in (None, "[]")


def test_bulk_attribution_apply_to_items_propagates(session, household):
    from src.backend.handle_receipt_upload import _bulk_apply_attribution

    p1 = household["_purchase"](1, household["mom"], household["costco"])
    item = ReceiptItem(
        purchase_id=p1.id, product_id=1, quantity=1, unit_price=10.0,
    )
    session.add(item)
    session.commit()

    _bulk_apply_attribution(
        session,
        purchase_ids=[p1.id],
        user_ids=[household["dad"].id],
        kind="personal",
        apply_to_items=True,
    )
    refreshed = session.query(ReceiptItem).get(item.id)
    assert refreshed.attribution_user_id == household["dad"].id
    assert refreshed.attribution_kind == "personal"


def test_attribution_stats_counts_correctly(session, household):
    from src.backend.handle_receipt_upload import _compute_attribution_stats

    # 3 untagged, 2 tagged (one personal, one household)
    household["_purchase"](1, household["mom"], household["costco"])
    household["_purchase"](2, household["mom"], household["costco"])
    household["_purchase"](3, household["dad"], household["target"])
    household["_purchase"](
        4, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    household["_purchase"](
        5, household["dad"], household["target"], kind="household",
    )
    session.commit()

    stats = _compute_attribution_stats(session)
    assert stats["untagged_count"] == 3
    assert stats["tagged_count"] == 2
    assert len(stats["untagged_sample_ids"]) == 3
    # Sample ids should all be in the untagged set (any order).
    untagged_actual = {
        row.id
        for row in session.query(Purchase).filter(
            Purchase.attribution_user_id.is_(None),
            Purchase.attribution_kind.is_(None),
        ).all()
    }
    assert set(stats["untagged_sample_ids"]).issubset(untagged_actual)


def test_attribution_stats_zero_untagged(session, household):
    from src.backend.handle_receipt_upload import _compute_attribution_stats

    household["_purchase"](
        1, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    session.commit()
    stats = _compute_attribution_stats(session)
    assert stats["untagged_count"] == 0
    assert stats["tagged_count"] == 1
    assert stats["untagged_sample_ids"] == []


def test_suggest_high_confidence(session, household):
    """4 of last 5 Costco uploads by Mom were personal/Mom → high."""
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    for d in [10, 8, 6, 4, 2]:
        household["_purchase"](
            d, household["mom"], household["costco"],
            attr=household["mom"], kind="personal",
        )
    # Add one outlier: shared with Dad
    household["_purchase"](
        12, household["mom"], household["costco"],
        attr_ids=[household["mom"], household["dad"]], kind="shared",
    )
    session.commit()

    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is not None
    assert s["confidence"] == "high"
    assert s["kind"] == "personal"
    assert s["user_ids"] == [household["mom"].id]


def test_suggest_medium_confidence(session, household):
    """2 of last 5 split — medium confidence."""
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    # 2 personal/Mom, 1 personal/Dad, 1 household, 1 shared
    household["_purchase"](
        10, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    household["_purchase"](
        8, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    household["_purchase"](
        6, household["mom"], household["costco"],
        attr=household["dad"], kind="personal",
    )
    household["_purchase"](
        4, household["mom"], household["costco"], kind="household",
    )
    household["_purchase"](
        2, household["mom"], household["costco"],
        attr_ids=[household["mom"], household["dad"]], kind="shared",
    )
    session.commit()

    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is not None
    assert s["confidence"] == "medium"


def test_suggest_none_when_no_history(session, household):
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is None


def test_suggest_none_when_low_diversity(session, household):
    """5 different attributions in last 5 → no modal majority → None."""
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    # Each row has a different (user, kind) combination
    household["_purchase"](
        10, household["mom"], household["costco"],
        attr=household["mom"], kind="personal",
    )
    household["_purchase"](
        8, household["mom"], household["costco"],
        attr=household["dad"], kind="personal",
    )
    household["_purchase"](
        6, household["mom"], household["costco"], kind="household",
    )
    household["_purchase"](
        4, household["mom"], household["costco"],
        attr_ids=[household["mom"], household["dad"]], kind="shared",
    )
    session.commit()

    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is None  # No group reaches the 2-of-5 threshold


def test_suggest_scoped_per_uploader(session, household):
    """History from a different uploader doesn't influence this one."""
    from src.backend.handle_receipt_upload import _suggest_attribution_for_upload

    # Dad's strong history at Costco
    for d in [10, 8, 6, 4, 2]:
        household["_purchase"](
            d, household["dad"], household["costco"],
            attr=household["dad"], kind="personal",
        )
    session.commit()

    # Mom asks → no history of her own at Costco → None
    s = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert s is None


def test_approve_receipt_auto_applies_high_confidence(session, household):
    """End-to-end-ish: seed strong history, then call the helper
    chain that approve_receipt uses, confirm the new row is tagged."""
    from src.backend.handle_receipt_upload import (
        _bulk_apply_attribution, _suggest_attribution_for_upload,
    )
    from src.backend.initialize_database_schema import Purchase

    # Strong Mom history at Costco
    for d in [10, 8, 6, 4, 2]:
        household["_purchase"](
            d, household["mom"], household["costco"],
            attr=household["mom"], kind="personal",
        )
    # New, unattributed purchase
    new_p = household["_purchase"](
        0, household["mom"], household["costco"],
    )
    session.commit()

    suggestion = _suggest_attribution_for_upload(
        session,
        uploader_id=household["mom"].id,
        store_id=household["costco"].id,
    )
    assert suggestion["confidence"] == "high"

    _bulk_apply_attribution(
        session,
        purchase_ids=[new_p.id],
        user_ids=suggestion["user_ids"],
        kind=suggestion["kind"],
        apply_to_items=True,
    )
    session.commit()

    refreshed = session.query(Purchase).get(new_p.id)
    assert refreshed.attribution_user_id == household["mom"].id
    assert refreshed.attribution_kind == "personal"
