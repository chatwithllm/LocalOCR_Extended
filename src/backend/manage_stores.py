"""Store visibility bucketing.

Pure ``classify_store`` plus the aggregator ``get_store_buckets`` that
runs one SQL roundtrip to compute (last_purchase_at, purchase_count) per
store and groups them into the three buckets. Used by the stores
blueprint and by the shopping-list dropdown emitter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

FREQUENT_DAYS = 90
LOW_FREQ_DAYS = 365

_VALID_OVERRIDES = {"frequent", "low_freq", "hidden"}


def classify_store(
    override: Optional[str],
    is_payment_artifact: bool,
    last_purchase_at: Optional[datetime],
    purchase_count: int,
    now: Optional[datetime] = None,
) -> str:
    """Return the bucket ('frequent' | 'low_freq' | 'hidden') for a store.

    Order of precedence:
      1. Payment artifacts are always 'hidden'.
      2. Manual override pins the bucket.
      3. Auto rule based on last purchase recency.
    """
    if is_payment_artifact:
        return "hidden"
    if override in _VALID_OVERRIDES:
        return override
    if last_purchase_at is None:
        return "hidden"
    now = now or datetime.now(timezone.utc)
    if last_purchase_at.tzinfo is None:
        last_purchase_at = last_purchase_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_days = (now - last_purchase_at).days
    if age_days <= FREQUENT_DAYS:
        return "frequent"
    if age_days <= LOW_FREQ_DAYS:
        return "low_freq"
    return "hidden"
