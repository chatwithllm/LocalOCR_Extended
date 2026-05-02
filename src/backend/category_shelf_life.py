"""Category shelf-life defaults — small lookup helper used by inventory writes.

Two safety nets:
  1. Unknown category falls back to the seeded "other" row.
  2. If the table is empty / corrupt, returns a hardcoded sentinel so the
     app stays up and the inventory page still loads.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging

from src.backend.initialize_database_schema import CategoryShelfLifeDefault


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Sentinel:
    category: str = "other"
    location_default: str = "Pantry"
    shelf_life_days: int = 0


_SENTINEL = _Sentinel()


def get_category_default(session, category: str | None):
    """Return the shelf-life default row for ``category``. Never raises."""
    cat = (category or "").strip().lower()
    try:
        if cat:
            row = session.query(CategoryShelfLifeDefault).filter_by(category=cat).first()
            if row:
                return row
        other = session.query(CategoryShelfLifeDefault).filter_by(category="other").first()
        if other:
            return other
        logger.warning("CategoryShelfLifeDefault table appears empty; using sentinel")
        return _SENTINEL
    except Exception as exc:  # noqa: BLE001
        logger.warning("CategoryShelfLifeDefault lookup failed (%s); using sentinel", exc)
        return _SENTINEL
