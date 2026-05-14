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


def _slug_store(name: str) -> str:
    """URL-safe lowercase slug for callback_data.

    Drops apostrophes (so "Trader Joe's" -> "trader_joes"); spaces/hyphens
    become "_".
    """
    out = []
    for ch in (name or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-"):
            out.append("_")
        # apostrophes and everything else: drop silently
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "store"


_QTY_BTNS = (1, 2, 3, 4, 5)


def render_item_prompt(*, product_name: str, category: str, idx: int,
                       total: int, reason_label: str,
                       stats: dict[str, int]) -> tuple[str, dict]:
    added = stats.get("added", 0)
    banner = f" (added: {added})" if added else ""
    text = (
        f"{_cat_emoji(category)} {category.title()} · {idx}/{total}{banner}\n\n"
        f"{product_name}\n"
        f"{reason_label}"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "+ Add",            "callback_data": "shop:add"},
            {"text": "+ Add w/ qty+store","callback_data": "shop:add+"},
        ],
        [
            {"text": "⏭ Skip",            "callback_data": "shop:skip"},
            {"text": "✓ Already have",    "callback_data": "shop:have"},
        ],
        [{"text": "✓ Done for now", "callback_data": "shop:done"}],
    ]}
    return text, kb


def render_qty_prompt(product_name: str) -> tuple[str, dict]:
    text = f"{product_name} — how many?"
    row1 = [{"text": str(n), "callback_data": f"shop:qty:{n}"} for n in _QTY_BTNS]
    row2 = [
        {"text": "✏ Custom qty", "callback_data": "shop:qty:cu"},
        {"text": "← Back",       "callback_data": "shop:back"},
    ]
    return text, {"inline_keyboard": [row1, row2]}


def render_store_prompt(*, product_name: str, qty: float,
                        stores: list[str]) -> tuple[str, dict]:
    text = f"{product_name} × {qty:g} — where?"
    rows = [[{"text": "⏭ Skip store", "callback_data": "shop:store:skip"}]]
    store_btns = []
    for s in stores[:3]:
        store_btns.append({
            "text": f"🛒 {s}",
            "callback_data": f"shop:store:{_slug_store(s)}",
        })
    if store_btns:
        rows.append(store_btns)
    rows.append([
        {"text": "✏ Other store", "callback_data": "shop:store:other"},
        {"text": "← Back",        "callback_data": "shop:back"},
    ])
    return text, {"inline_keyboard": rows}


def render_category_end(*, category: str, next_category: str | None,
                        stats: dict[str, int]) -> tuple[str, dict]:
    added = stats.get("added", 0)
    skipped = stats.get("skipped", 0)
    have = stats.get("already_have", 0)
    text = (
        f"{_cat_emoji(category)} {category.title()} — done.\n"
        f"Added {added} · skipped {skipped} · already had {have}\n\n"
        "Anything else?"
    )
    next_btn = (
        {"text": f"→ Next: {next_category.title()}",
         "callback_data": "shop:cat_done"}
        if next_category
        else {"text": "✓ Finish shopping plan", "callback_data": "shop:cat_done"}
    )
    kb = {"inline_keyboard": [
        [{"text": "+ Add custom item", "callback_data": "shop:custom"}],
        [next_btn, {"text": "✓ Done for now", "callback_data": "shop:done"}],
    ]}
    return text, kb


def render_custom_name_prompt() -> tuple[str, dict]:
    text = "What's the item name?\n(type and send)"
    kb = {"inline_keyboard": [[{"text": "← Cancel", "callback_data": "shop:back"}]]}
    return text, kb


def render_custom_qty_prompt(product_name: str) -> tuple[str, dict]:
    text = f"{product_name} — how many?"
    row1 = [{"text": str(n), "callback_data": f"shop:qty:{n}"} for n in _QTY_BTNS]
    row2 = [
        {"text": "✏ Custom qty", "callback_data": "shop:qty:cu"},
        {"text": "← Back",       "callback_data": "shop:back"},
    ]
    return text, {"inline_keyboard": [row1, row2]}


def send_telegram_message(chat_id: str, text: str, reply_markup: dict | None = None):
    """Thin wrapper so tests can monkeypatch this symbol in this module."""
    from src.backend.handle_telegram_messages import (
        send_telegram_message as _send,
    )
    return _send(chat_id, text, reply_markup=reply_markup)


def _edit_telegram_message(chat_id: str, message_id: int | None, text: str,
                           reply_markup: dict | None = None):
    """Thin wrapper for editMessageText so tests can monkeypatch."""
    from src.backend.handle_telegram_messages import (
        _edit_telegram_message as _edit,
    )
    return _edit(chat_id, message_id, text, reply_markup=reply_markup)


def start_walk(session, chat_id: str) -> None:
    """Entry point for /shopping. Sends category screen, resume offer, or 'nothing to suggest'."""
    row = get_or_create_session(session, chat_id)
    if abandon_if_idle(row):
        reset_for_start_over(row)

    # Resume offer if active mid-walk.
    if (row.status == "active"
            and row.current_category
            and row.item_queue
            and row.cursor < len(row.item_queue)):
        total = len(row.item_queue)
        text, kb = render_resume(row.current_category, row.cursor, total)
        row.pending_prompt = "resume"
        send_telegram_message(chat_id, text, reply_markup=kb)
        return

    recs = fetch_recommendations(session)
    if not recs:
        row.status = "done"
        row.pending_prompt = None
        send_telegram_message(
            chat_id,
            "🎉 Nothing to suggest right now — shopping list looks good.",
        )
        return

    cat_queue, items_by = bucketize_by_category(recs)
    reset_for_start_over(row)
    row.category_queue = cat_queue
    counts = [(c, len(items_by[c])) for c in cat_queue]
    text, kb = render_category_screen(counts)
    send_telegram_message(chat_id, text, reply_markup=kb)


def _render_current_item(row, message_id: int | None) -> None:
    """Edit the message to show the current item prompt."""
    if row.cursor >= len(row.item_queue):
        return
    item = row.item_queue[row.cursor]
    text, kb = render_item_prompt(
        product_name=item.get("name", "Item"),
        category=row.current_category or "other",
        idx=row.cursor + 1,
        total=len(row.item_queue),
        reason_label=item.get("reason_label") or "Suggested",
        stats=row.stats or {},
    )
    row.pending_prompt = "item"
    row.last_item_id = item.get("product_id")
    _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)


def handle_category(session, chat_id: str, category: str,
                    message_id: int | None) -> None:
    """User picked a category — load that bucket, render first item."""
    row = get_or_create_session(session, chat_id)
    if not category:
        row.pending_prompt = "category"
        return

    recs = fetch_recommendations(session)
    _, items_by = bucketize_by_category(recs)
    bucket = items_by.get(category, [])

    row.current_category = category
    row.item_queue = bucket
    row.cursor = 0
    row.stats = {"added": 0, "skipped": 0, "already_have": 0, "custom_added": 0}
    row.category_queue = [c for c in (row.category_queue or []) if c != category]

    if not row.item_queue:
        send_telegram_message(chat_id, f"No recommendations in {category}.")
        row.pending_prompt = "category"
        return

    _render_current_item(row, message_id)
