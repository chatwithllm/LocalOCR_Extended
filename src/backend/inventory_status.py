"""Pure-function helpers for inventory %-remaining + status computation.

Single source of truth for the auto-decaying shelf-life model. Used by
the inventory list endpoint and any future consumer (recommendations,
shopping suggestions, etc.).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


# Per-category shelf-life defaults in days. User-tunable in Phase 2.
CATEGORY_SHELF_DAYS: dict[str, int] = {
    "dairy": 7,
    "milk": 7,
    "eggs": 21,
    "leafy_produce": 5,
    "produce": 7,
    "root_vegetables": 14,
    "fruit": 7,
    "meat": 4,
    "fish": 2,
    "frozen": 90,
    "pantry": 60,
    "snacks": 30,
    "beverages": 14,
    "condiments": 90,
    "baked": 5,
    "household": 180,
    "other": 30,
}


def shelf_days_for(product: Any) -> int:
    """Resolve effective shelf days: product override → category default → 30."""
    explicit = getattr(product, "expected_shelf_days", None)
    if isinstance(explicit, int) and explicit > 0:
        return explicit
    category = (getattr(product, "category", None) or "other").lower()
    return CATEGORY_SHELF_DAYS.get(category, CATEGORY_SHELF_DAYS["other"])


def compute_inventory_status(
    product: Any,
    inventory: Any,
    *,
    now: datetime | None = None,
) -> dict:
    """Return {shelf_days, remaining_pct, status, is_estimated} for a row.

    Override (`inventory.consumed_pct_override`) wins when present. Otherwise
    auto-decays linearly from `last_purchased_at` (or `last_updated` as
    fallback) over `shelf_days`.
    """
    if now is None:
        now = datetime.utcnow()

    shelf_days = shelf_days_for(product)
    override = getattr(inventory, "consumed_pct_override", None)

    if override is not None:
        consumed = max(0.0, min(100.0, float(override)))
        is_estimated = False
    else:
        anchor = (
            getattr(inventory, "last_purchased_at", None)
            or getattr(inventory, "last_updated", None)
            or now
        )
        days_elapsed = max(0, (now - anchor).days)
        consumed = min(100.0, (days_elapsed / max(1, shelf_days)) * 100.0)
        is_estimated = True

    remaining_pct = round(100.0 - consumed, 1)
    if remaining_pct >= 60:
        status = "fresh"
    elif remaining_pct >= 20:
        status = "low"
    else:
        status = "out"

    return {
        "shelf_days": shelf_days,
        "remaining_pct": remaining_pct,
        "status": status,
        "is_estimated": is_estimated,
    }
