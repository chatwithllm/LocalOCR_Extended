from datetime import datetime, timedelta, timezone

import pytest

from src.backend.manage_stores import classify_store


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
