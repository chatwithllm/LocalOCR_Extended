"""Telegram /inventory walk — state machine, dispatch, rendering.

See docs/superpowers/specs/2026-05-13-telegram-inventory-walk-design.md
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _csv_env(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {chunk.strip() for chunk in raw.split(",") if chunk.strip()}


INVENTORY_STALE_DAYS = _int_env("INVENTORY_STALE_DAYS", 14)
PAGE_SIZE = _int_env("INVENTORY_WALK_PAGE_SIZE", 10)
IDLE_TIMEOUT_MIN = _int_env("INVENTORY_WALK_IDLE_TIMEOUT_MIN", 30)
WALK_ENABLED = _bool_env("TELEGRAM_INVENTORY_WALK_ENABLED", False)
PILOT_CHATS: set[str] = _csv_env("TELEGRAM_INVENTORY_WALK_PILOT_CHATS")


def is_walk_enabled(chat_id: str) -> bool:
    if not WALK_ENABLED:
        return False
    if PILOT_CHATS and chat_id not in PILOT_CHATS:
        return False
    return True


def _stale_cutoff() -> datetime:
    return datetime.utcnow() - timedelta(days=INVENTORY_STALE_DAYS)


def categories_with_stale_counts(session) -> list[tuple[str, int]]:
    """Return [(category, n_stale_items), ...] sorted by count desc.

    Category is normalized: NULL and missing values map to "other", and
    matching is case-insensitive. Returned category strings are lowercased.
    """
    from src.backend.initialize_database_schema import Inventory, Product

    cutoff = _stale_cutoff()
    norm = func.lower(func.coalesce(Product.category, "other"))
    rows = (
        session.query(norm.label("category"), func.count(Inventory.id))
        .join(Inventory, Inventory.product_id == Product.id)
        .filter(Inventory.is_active_window.is_(True))
        .filter(Inventory.last_updated < cutoff)
        .group_by(norm)
        .order_by(func.count(Inventory.id).desc())
        .all()
    )
    return [(cat, n) for cat, n in rows]


def stale_items_in_category(session, category: str, page: int = 1):
    """Return Inventory rows for one page (oldest-first) in the given category."""
    from src.backend.initialize_database_schema import Inventory, Product

    if not category:
        return []

    cutoff = _stale_cutoff()
    offset = (page - 1) * PAGE_SIZE
    return (
        session.query(Inventory)
        .join(Product, Product.id == Inventory.product_id)
        .filter(Inventory.is_active_window.is_(True))
        .filter(Inventory.last_updated < cutoff)
        .filter(func.lower(func.coalesce(Product.category, "other")) == category.lower())
        .order_by(Inventory.last_updated.asc())
        .offset(offset)
        .limit(PAGE_SIZE)
        .all()
    )
