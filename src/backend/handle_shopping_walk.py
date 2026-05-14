"""Telegram /shopping walk — state machine, dispatch, rendering.

See docs/superpowers/specs/2026-05-14-telegram-shopping-walk-design.md
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


WALK_ENABLED = _bool_env("TELEGRAM_SHOPPING_WALK_ENABLED", False)
PILOT_CHATS: set[str] = _csv_env("TELEGRAM_SHOPPING_WALK_PILOT_CHATS")
IDLE_TIMEOUT_MIN = _int_env("SHOPPING_WALK_IDLE_TIMEOUT_MIN", 30)


def is_walk_enabled(chat_id: str) -> bool:
    if not WALK_ENABLED:
        return False
    if PILOT_CHATS and chat_id not in PILOT_CHATS:
        return False
    return True


def get_or_create_session(session, chat_id: str):
    """Fetch the TelegramShoppingSession row for chat_id, creating one if absent."""
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = (
        session.query(TelegramShoppingSession)
        .filter_by(chat_id=chat_id)
        .one_or_none()
    )
    if row is None:
        row = TelegramShoppingSession(chat_id=chat_id, status="active")
        session.add(row)
        session.flush()
    return row


def reset_for_start_over(row) -> None:
    """Reset walk state in place, preserving nudge prefs (nudge_muted_until,
    last_nudge_sent_at) per spec §5."""
    row.status = "active"
    row.category_queue = []
    row.current_category = None
    row.item_queue = []
    row.cursor = 0
    row.pending_prompt = "category"
    row.pending_action = None
    row.last_item_id = None
    row.pending_name = None
    row.pending_qty = None
    row.stats = {}


def abandon_if_idle(row) -> bool:
    """Return True if session was just marked abandoned due to idle timeout."""
    if row.status != "active":
        return False
    if row.last_action_at is None:
        return False
    cutoff = datetime.utcnow() - timedelta(minutes=IDLE_TIMEOUT_MIN)
    last_action = row.last_action_at
    # Normalize tz-aware values (fresh in-memory rows use tz-aware defaults;
    # rows reloaded from SQLite come back naive) so the compare is consistent.
    if last_action.tzinfo is not None:
        last_action = last_action.replace(tzinfo=None)
    if last_action < cutoff:
        row.status = "abandoned"
        return True
    return False


def _reason_label(rec: dict) -> str:
    """Short human label for the per-item reason."""
    kind = rec.get("reason", "")
    if kind == "manual_low":
        return "Low stock — marked manually"
    if kind == "low_stock":
        qty = rec.get("current_quantity")
        thr = rec.get("threshold")
        if qty is not None and thr is not None:
            return f"Low stock · {qty:g} left (threshold {thr:g})"
        return "Low stock"
    if kind == "seasonal_purchase" or kind == "seasonal":
        return "Seasonal pick"
    if kind == "price_deal":
        reg = rec.get("regular_price")
        deal = rec.get("deal_price")
        if reg and deal:
            return f"Price drop · was ${reg:.2f} now ${deal:.2f}"
        return "Price drop"
    if kind == "regular_use":
        days = rec.get("days_since_last_buy")
        if days is not None:
            return f"Regular item · {days} days since last buy"
        return "Regular item"
    return kind or "Suggested"


def _to_item_dict(rec: dict) -> dict:
    """Compact representation stored in item_queue JSON."""
    return {
        "product_id": rec.get("product_id"),
        "name": rec.get("product_name") or rec.get("name") or "Item",
        "category": (rec.get("category") or "other"),
        "reason_label": _reason_label(rec),
    }


def fetch_recommendations(session) -> list[dict]:
    """Call generate_all_recommendations under a Flask app context.

    Production path is always inside a Flask request context (Telegram webhook
    is a Flask route). The no-context fallback below pushes a throwaway context
    and binds g.db_session=session so unit tests can call this helper directly.
    """
    import flask
    from src.backend.generate_recommendations import generate_all_recommendations

    if flask.has_app_context():
        if not hasattr(flask.g, "db_session"):
            flask.g.db_session = session
        return generate_all_recommendations()

    _ctx_app = flask.Flask("shopping_walk_ctx")
    with _ctx_app.app_context():
        flask.g.db_session = session
        return generate_all_recommendations()


def bucketize_by_category(recs: list[dict]) -> tuple[list[str], dict[str, list[dict]]]:
    """Split recs into per-category lists, return (ordered_categories, items_by_category).

    Categories sorted by item-count desc, ties broken by alpha. NULL/empty
    category → "other" bucket.
    """
    items_by: dict[str, list[dict]] = {}
    for rec in recs:
        item = _to_item_dict(rec)
        items_by.setdefault(item["category"], []).append(item)
    cat_queue = sorted(items_by.keys(), key=lambda c: (-len(items_by[c]), c))
    return cat_queue, items_by
