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
    if kind == "seasonal":
        return "Seasonal pick"
    if kind == "deal":
        avg = rec.get("avg_price")
        cur = rec.get("current_price")
        if avg is not None and cur is not None:
            return f"Price drop · was ${avg:.2f} now ${cur:.2f}"
        return "Price drop"
    return "Suggested"


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


def _active_shopping_session(session):
    """Get or create the active shopping session, handling Flask context.

    Production path is inside a Flask request context. Tests call this
    helper without one, so we push a throwaway app context just like
    fetch_recommendations does.
    """
    import flask
    from src.backend.manage_shopping_list import _ensure_current_session
    if flask.has_app_context():
        return _ensure_current_session(session)
    _ctx_app = flask.Flask("shopping_walk_ctx")
    with _ctx_app.app_context():
        return _ensure_current_session(session)


def insert_recommendation(session, *, product_id: int, name: str,
                          category: str | None, quantity: float = 1.0,
                          preferred_store: str | None = None):
    """Insert a ShoppingListItem for an existing Product. Dedups against
    existing OPEN item in the same shopping session for this product_id.
    """
    from src.backend.initialize_database_schema import ShoppingListItem
    shop_session = _active_shopping_session(session)
    existing = (
        session.query(ShoppingListItem)
        .filter_by(
            shopping_session_id=shop_session.id,
            product_id=product_id,
            status="open",
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    item = ShoppingListItem(
        shopping_session_id=shop_session.id,
        product_id=product_id,
        name=name,
        category=category,
        quantity=quantity,
        preferred_store=preferred_store,
        source="telegram_shopping",
        status="open",
    )
    session.add(item)
    session.flush()
    return item


def insert_custom_item(session, *, name: str, category: str | None,
                       quantity: float = 1.0, preferred_store: str | None = None):
    """Insert a free-text ShoppingListItem (product_id=NULL)."""
    from src.backend.initialize_database_schema import ShoppingListItem
    shop_session = _active_shopping_session(session)
    item = ShoppingListItem(
        shopping_session_id=shop_session.id,
        product_id=None,
        name=name,
        category=category,
        quantity=quantity,
        preferred_store=preferred_store,
        source="telegram_shopping",
        status="open",
    )
    session.add(item)
    session.flush()
    return item


def top_stores(session, limit: int = 3) -> list[str]:
    """Return up to `limit` most-frequent store names from purchases."""
    from src.backend.initialize_database_schema import Store, Purchase
    rows = (
        session.query(Store.name, func.count(Purchase.id))
        .join(Purchase, Purchase.store_id == Store.id)
        .filter(func.coalesce(Store.is_payment_artifact, 0) == 0)
        .group_by(Store.id, Store.name)
        .order_by(func.count(Purchase.id).desc(), Store.name.asc())
        .limit(limit)
        .all()
    )
    return [name for name, _cnt in rows]


_CATEGORY_EMOJI = {
    "pantry": "🥫", "fridge": "🥶", "freezer": "🧊", "bathroom": "🧴",
    "household": "🧹", "personal_care": "🧴", "produce": "🥦",
    "dairy": "🥛", "meat": "🥩", "snacks": "🍿", "beverages": "🥤",
    "frozen": "🧊", "bakery": "🍞", "canned": "🥫", "condiments": "🧂",
}


def _cat_emoji(category: str | None) -> str:
    return _CATEGORY_EMOJI.get((category or "").lower(), "📦")


def render_category_screen(counts: list[tuple[str, int]]) -> tuple[str, dict]:
    total = sum(n for _, n in counts)
    n_cats = len(counts)
    lines = [
        "📋 Plan shopping",
        "",
        f"{total} items recommended across {n_cats} categor"
        f"{'y' if n_cats == 1 else 'ies'}:",
    ]
    rows: list[list[dict]] = []
    pair: list[dict] = []
    for category, count in counts:
        label = f"{_cat_emoji(category)} {category.title()} · {count}"
        pair.append({"text": label, "callback_data": f"shop:cat:{category}"})
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([{"text": "Cancel", "callback_data": "shop:cancel"}])
    return "\n".join(lines), {"inline_keyboard": rows}


def render_nudge(rec_count: int, category_count: int) -> tuple[str, dict]:
    text = (
        f"📋 {rec_count} items recommended across {category_count} categories.\n"
        "Plan this week's shop?"
    )
    kb = {"inline_keyboard": [
        [{"text": "▶ Yes",     "callback_data": "nudge:shop:yes"}],
        [{"text": "⏰ Later",   "callback_data": "nudge:shop:later"}],
        [{"text": "🔕 Mute 7d", "callback_data": "nudge:shop:mute"}],
    ]}
    return text, kb


def render_resume(category: str, cursor: int, total: int) -> tuple[str, dict]:
    text = (
        "You have a shopping plan in progress.\n\n"
        f"{category.title()} · {cursor}/{total} done"
    )
    kb = {"inline_keyboard": [[
        {"text": "▶ Resume",     "callback_data": "shop:resume"},
        {"text": "↻ Start over", "callback_data": "shop:restart"},
    ]]}
    return text, kb


def render_summary(stats: dict[str, int]) -> tuple[str, dict]:
    added = stats.get("added", 0)
    skipped = stats.get("skipped", 0)
    already = stats.get("already_have", 0)
    custom = stats.get("custom_added", 0)
    text = (
        "✅ Shopping plan complete\n\n"
        f"Added:        {added}\n"
        f"Skipped:      {skipped}\n"
        f"Already had:  {already}\n"
        f"Custom added: {custom}"
    )
    rows = []
    bottom = [{"text": "📦 Inventory walk", "callback_data": "inv:restart"}]
    public_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if public_url:
        rows.append([
            {"text": "📋 View shopping list", "url": f"{public_url}/shopping/list"},
        ])
    rows.append(bottom)
    return text, {"inline_keyboard": rows}
