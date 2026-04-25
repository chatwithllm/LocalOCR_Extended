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
