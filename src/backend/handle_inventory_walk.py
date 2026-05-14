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


def get_or_create_session(session, chat_id: str):
    """Fetch the TelegramInventorySession row for chat_id, creating one if absent."""
    from src.backend.initialize_database_schema import TelegramInventorySession
    row = (
        session.query(TelegramInventorySession)
        .filter_by(chat_id=chat_id)
        .one_or_none()
    )
    if row is None:
        row = TelegramInventorySession(chat_id=chat_id, status="active")
        session.add(row)
        session.flush()
    return row


def reset_for_start_over(row) -> None:
    """Reset walk state in place, preserving nudge prefs."""
    row.status = "active"
    row.current_category = None
    row.item_queue = []
    row.cursor = 0
    row.page = 1
    row.pending_prompt = "category"
    row.last_item_id = None
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


_LEVEL_TO_PCT = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25, 4: 0.0}


def apply_level(session, inventory_id: int, level_idx: int, user_id: int | None):
    """Write consumed_pct_override + manual_low for a level button.

    level_idx 0..4 maps to Empty / ¼ / ½ / ¾ / Full.
    Empty (0) sets manual_low=True; other levels clear manual_low.
    Returns the Inventory row, or None if the row vanished.
    """
    from src.backend.initialize_database_schema import Inventory, InventoryAdjustment

    if level_idx not in _LEVEL_TO_PCT:
        raise ValueError(f"invalid level_idx {level_idx}")

    inv = session.query(Inventory).filter_by(id=inventory_id).one_or_none()
    if inv is None:
        logger.warning("apply_level: inventory %s vanished", inventory_id)
        return None

    inv.consumed_pct_override = _LEVEL_TO_PCT[level_idx]
    inv.manual_low = (level_idx == 0)
    inv.last_updated = datetime.utcnow()

    session.add(InventoryAdjustment(
        product_id=inv.product_id,
        quantity_delta=0.0,
        reason="telegram_walk",
        user_id=user_id,
    ))
    return inv


def mark_no_longer_have(session, inventory_id: int, user_id: int | None):
    """Deactivate an inventory row (is_active_window=False) + audit row.

    Returns the Inventory row, or None if the row vanished.
    """
    from src.backend.initialize_database_schema import Inventory, InventoryAdjustment

    inv = session.query(Inventory).filter_by(id=inventory_id).one_or_none()
    if inv is None:
        return None
    inv.is_active_window = False
    inv.last_updated = datetime.utcnow()
    session.add(InventoryAdjustment(
        product_id=inv.product_id,
        quantity_delta=0.0,
        reason="telegram_walk_remove",
        user_id=user_id,
    ))
    return inv


def add_empty_to_shopping_list(session, inventory_id: int):
    """Insert the product backing this inventory row into the active shopping session.

    Reuses manage_shopping_list._ensure_current_session. De-duplicates: if an
    OPEN ShoppingListItem already exists for this product in the active
    shopping session, returns it without inserting again.

    Production path is always inside a Flask request context (the Telegram
    webhook is a Flask route), so `_ensure_current_session` reads `flask.g`
    cleanly. The no-context fallback below exists only for direct unit-test
    invocations of this helper.
    """
    import flask
    from src.backend.initialize_database_schema import (
        Inventory, ShoppingListItem,
    )
    from src.backend.manage_shopping_list import _ensure_current_session

    inv = session.query(Inventory).filter_by(id=inventory_id).one_or_none()
    if inv is None or inv.product is None:
        return None

    if flask.has_app_context():
        shop_session = _ensure_current_session(session)
    else:
        # Test-only fallback: tests call this helper directly without
        # pushing a Flask request context. `_ensure_current_session` only
        # needs `g` for an optional `current_user.id`, which resolves to
        # None under a fresh app context — same as an unauthenticated webhook.
        _ctx_app = flask.Flask("telegram_walk_ctx")
        with _ctx_app.app_context():
            shop_session = _ensure_current_session(session)

    existing = (
        session.query(ShoppingListItem)
        .filter_by(
            shopping_session_id=shop_session.id,
            product_id=inv.product_id,
            status="open",
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    item = ShoppingListItem(
        shopping_session_id=shop_session.id,
        product_id=inv.product_id,
        name=inv.product.name,
        category=inv.product.category,
        quantity=1,
        source="telegram_walk",
        status="open",
    )
    session.add(item)
    session.flush()
    return item


_CATEGORY_EMOJI = {
    "pantry": "🥫", "fridge": "🥶", "freezer": "🧊", "bathroom": "🧴",
    "household": "🧹", "personal_care": "🧴", "produce": "🥦",
    "dairy": "🥛", "meat": "🥩", "snacks": "🍿", "beverages": "🥤",
    "frozen": "🧊", "bakery": "🍞", "canned": "🥫", "condiments": "🧂",
}


def _cat_emoji(category: str | None) -> str:
    return _CATEGORY_EMOJI.get((category or "").lower(), "📦")


def _days_ago_phrase(days: int) -> str:
    if days >= 60:
        return "2+ months ago"
    return f"{days} days ago"


def render_category_screen(counts: list[tuple[str, int]]) -> tuple[str, dict]:
    n = len(counts)
    lines = [
        "📦 Update inventory",
        "",
        f"{n} categories have stale items (>{INVENTORY_STALE_DAYS} days):",
    ]
    rows: list[list[dict]] = []
    pair: list[dict] = []
    for category, count in counts:
        label = f"{_cat_emoji(category)} {category.title()} · {count}"
        pair.append({"text": label, "callback_data": f"inv:cat:{category}"})
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([{"text": "Cancel", "callback_data": "inv:cancel"}])
    return "\n".join(lines), {"inline_keyboard": rows}


def render_level_prompt(
    *, product_name: str, category: str, idx: int, total: int, days_old: int
) -> tuple[str, dict]:
    text = (
        f"{_cat_emoji(category)} {category.title()} · {idx}/{total}\n\n"
        f"{product_name}\n"
        f"Last updated {_days_ago_phrase(days_old)}\n\n"
        "How much left?"
    )
    kb = {"inline_keyboard": [
        [
            {"text": "Empty", "callback_data": "inv:lvl:0"},
            {"text": "¼",     "callback_data": "inv:lvl:1"},
            {"text": "½",     "callback_data": "inv:lvl:2"},
            {"text": "¾",     "callback_data": "inv:lvl:3"},
            {"text": "Full",  "callback_data": "inv:lvl:4"},
        ],
        [
            {"text": "Skip",            "callback_data": "inv:skip"},
            {"text": "No longer have",  "callback_data": "inv:nohave"},
        ],
        [{"text": "✓ Done for now", "callback_data": "inv:done"}],
    ]}
    return text, kb


def render_cart_prompt(product_name: str) -> tuple[str, dict]:
    text = (
        f"{product_name} → empty.\n\n"
        "Add to shopping list?"
    )
    kb = {"inline_keyboard": [[
        {"text": "✓ Yes",            "callback_data": "inv:cart:y"},
        {"text": "✗ No",             "callback_data": "inv:cart:n"},
        {"text": "Already have it",  "callback_data": "inv:cart:a"},
    ]]}
    return text, kb


def render_continue(category: str, done: int, remaining: int) -> tuple[str, dict]:
    text = (
        f"{_cat_emoji(category)} {category.title()} · {done} done\n\n"
        f"{remaining} more stale items left. Continue?"
    )
    kb = {"inline_keyboard": [[
        {"text": "▶ Continue",     "callback_data": "inv:cont"},
        {"text": "✓ Done for now", "callback_data": "inv:done"},
    ]]}
    return text, kb


def render_summary(category: str, stats: dict[str, int]) -> tuple[str, dict]:
    updated = stats.get("updated", 0)
    skipped = stats.get("skipped", 0)
    removed = stats.get("removed", 0)
    cart_added = stats.get("cart_added", 0)
    text = (
        f"✅ Walk complete · {category.title()}\n\n"
        f"Updated: {updated}\n"
        f"Skipped: {skipped}\n"
        f"Removed: {removed}\n"
        f"Added to shopping list: {cart_added}"
    )
    rows = [[{"text": "📦 Another category", "callback_data": "inv:restart"}]]
    public_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if public_url:
        rows[0].append({"text": "📋 View shopping list", "url": f"{public_url}/shopping/list"})
    return text, {"inline_keyboard": rows}


def render_resume(category: str, cursor: int, total: int) -> tuple[str, dict]:
    text = (
        "You have a walk in progress.\n\n"
        f"{category.title()} · {cursor}/{total} done"
    )
    kb = {"inline_keyboard": [[
        {"text": "▶ Resume",     "callback_data": "inv:resume"},
        {"text": "↻ Start over", "callback_data": "inv:restart"},
    ]]}
    return text, kb


def render_nudge(stale_count: int) -> tuple[str, dict]:
    text = f"📦 {stale_count} items haven't been counted in 2+ weeks. Update now?"
    kb = {"inline_keyboard": [
        [{"text": "▶ Yes, walk me through", "callback_data": "nudge:yes"}],
        [{"text": "⏰ Later",                "callback_data": "nudge:later"}],
        [{"text": "🔕 Mute 7d",              "callback_data": "nudge:mute"}],
    ]}
    return text, kb


def send_telegram_message(chat_id: str, text: str, reply_markup: dict | None = None):
    """Thin wrapper so tests can monkeypatch this symbol in this module.

    Delegates to handle_telegram_messages.send_telegram_message.
    """
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
    """Entry point for `/inventory`. Sends category screen, resume offer, or 'all caught up'."""
    row = get_or_create_session(session, chat_id)
    if abandon_if_idle(row):
        # Treat as fresh start once idle-abandoned.
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

    counts = categories_with_stale_counts(session)
    if not counts:
        # Park the row in a clean terminal state so future taps don't trip
        # the stale-verb guard against a half-set pending_prompt.
        row.status = "done"
        row.pending_prompt = None
        send_telegram_message(chat_id, "🎉 All caught up — nothing stale.")
        return

    reset_for_start_over(row)
    text, kb = render_category_screen(counts)
    send_telegram_message(chat_id, text, reply_markup=kb)


def _render_current_item(session, row, message_id: int | None) -> None:
    """Re-render the LEVEL prompt for the item at row.cursor.

    Advances cursor and recurses if the inventory row vanished.
    """
    from src.backend.initialize_database_schema import Inventory

    if row.cursor >= len(row.item_queue):
        return  # caller handles end-of-page

    inv_id = row.item_queue[row.cursor]
    inv = session.query(Inventory).filter_by(id=inv_id).one_or_none()
    if inv is None:
        row.cursor += 1
        logger.warning("inventory %s vanished mid-walk for chat %s", inv_id, row.chat_id)
        if row.cursor < len(row.item_queue):
            return _render_current_item(session, row, message_id)
        return

    last_updated = inv.last_updated
    if last_updated and last_updated.tzinfo is not None:
        last_updated = last_updated.replace(tzinfo=None)
    days_old = (datetime.utcnow() - last_updated).days if last_updated else INVENTORY_STALE_DAYS

    text, kb = render_level_prompt(
        product_name=inv.product.name,
        category=row.current_category or "other",
        idx=row.cursor + 1,
        total=len(row.item_queue),
        days_old=days_old,
    )
    row.pending_prompt = "level"
    row.last_item_id = inv_id
    _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)


def handle_category(session, chat_id: str, category: str, message_id: int | None) -> None:
    """User picked a category — load page 1 of stale items, render first level prompt."""
    row = get_or_create_session(session, chat_id)
    if not category:
        # Malformed `inv:cat:` callback. Don't mutate state; leave the category screen up.
        row.pending_prompt = "category"
        return
    items = stale_items_in_category(session, category, page=1)
    row.current_category = category
    row.item_queue = [i.id for i in items]
    row.cursor = 0
    row.page = 1
    row.stats = {"updated": 0, "skipped": 0, "removed": 0, "cart_added": 0}
    if not row.item_queue:
        send_telegram_message(chat_id, f"No stale items in {category}.")
        row.pending_prompt = "category"
        return
    _render_current_item(session, row, message_id)


def _advance_or_end(session, row, message_id: int | None) -> None:
    """After a non-Empty action: cursor+1 then either render next, prompt continue, or end."""
    from src.backend.initialize_database_schema import Inventory, Product

    row.cursor += 1
    if row.cursor < len(row.item_queue):
        _render_current_item(session, row, message_id)
        return

    # End of current page. Are there more stale items in this category?
    cutoff = _stale_cutoff()
    total_stale = (
        session.query(func.count(Inventory.id))
        .join(Product, Product.id == Inventory.product_id)
        .filter(Inventory.is_active_window.is_(True))
        .filter(Inventory.last_updated < cutoff)
        .filter(func.lower(func.coalesce(Product.category, "other")) == (row.current_category or "").lower())
        .scalar()
    ) or 0
    done_on_page = row.cursor  # cursor == len(item_queue) here
    remaining_after = max(0, total_stale - (row.page - 1) * PAGE_SIZE - done_on_page)

    if remaining_after > 0:
        text, kb = render_continue(row.current_category or "other", done=done_on_page, remaining=remaining_after)
        row.pending_prompt = "continue"
        _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)
        return

    _end_walk(session, row, message_id)


def _end_walk(session, row, message_id: int | None) -> None:
    text, kb = render_summary(row.current_category or "other", row.stats or {})
    _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)
    row.status = "done"
    row.pending_prompt = None


def handle_level(session, chat_id: str, level_idx: int, message_id: int | None) -> None:
    """User tapped Empty/¼/½/¾/Full for the current item.

    Empty (level_idx=0) → cart prompt. Other levels → advance to next item.
    """
    row = get_or_create_session(session, chat_id)
    if row.cursor >= len(row.item_queue):
        return  # Defensive — shouldn't happen if dispatch is correct.

    inv_id = row.item_queue[row.cursor]
    apply_level(session, inv_id, level_idx, user_id=row.user_id)
    stats = dict(row.stats or {})
    stats["updated"] = stats.get("updated", 0) + 1
    row.stats = stats

    if level_idx == 0:
        # Show cart prompt before advancing.
        from src.backend.initialize_database_schema import Inventory
        inv = session.query(Inventory).filter_by(id=inv_id).one_or_none()
        product_name = inv.product.name if (inv and inv.product) else "Item"
        text, kb = render_cart_prompt(product_name)
        row.pending_prompt = "cart"
        row.last_item_id = inv_id
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
        return

    _advance_or_end(session, row, message_id)


def handle_cart(session, chat_id: str, choice: str, message_id: int | None) -> None:
    """User answered the cart prompt: 'y' (Yes), 'n' (No), or 'a' (Already have it).

    On Yes: insert ShoppingListItem for last_item_id, bump stats.cart_added.
    Then advance to next item regardless of choice.
    """
    row = get_or_create_session(session, chat_id)
    if choice == "y" and row.last_item_id is not None:
        added = add_empty_to_shopping_list(session, row.last_item_id)
        if added is not None:
            stats = dict(row.stats or {})
            stats["cart_added"] = stats.get("cart_added", 0) + 1
            row.stats = stats
    # No/Already → no insert.
    _advance_or_end(session, row, message_id)


def handle_skip(session, chat_id: str, message_id: int | None) -> None:
    """User skipped the current item. No inventory write; advance."""
    row = get_or_create_session(session, chat_id)
    stats = dict(row.stats or {})
    stats["skipped"] = stats.get("skipped", 0) + 1
    row.stats = stats
    _advance_or_end(session, row, message_id)


def handle_nohave(session, chat_id: str, message_id: int | None) -> None:
    """User said 'No longer have'. Deactivate the inventory row, advance."""
    row = get_or_create_session(session, chat_id)
    if row.cursor < len(row.item_queue):
        inv_id = row.item_queue[row.cursor]
        mark_no_longer_have(session, inv_id, user_id=row.user_id)
    stats = dict(row.stats or {})
    stats["removed"] = stats.get("removed", 0) + 1
    row.stats = stats
    _advance_or_end(session, row, message_id)


def handle_done(session, chat_id: str, message_id: int | None) -> None:
    """User tapped Done for now. End the walk and render summary."""
    row = get_or_create_session(session, chat_id)
    _end_walk(session, row, message_id)


def handle_continue(session, chat_id: str, message_id: int | None) -> None:
    """User tapped Continue at end of page. Load next page."""
    row = get_or_create_session(session, chat_id)
    row.page += 1
    row.cursor = 0
    items = stale_items_in_category(session, row.current_category or "", page=row.page)
    row.item_queue = [i.id for i in items]
    if not row.item_queue:
        _end_walk(session, row, message_id)
        return
    _render_current_item(session, row, message_id)


def handle_cancel(session, chat_id: str, message_id: int | None) -> None:
    """User tapped Cancel on category screen. Mark abandoned, edit message."""
    row = get_or_create_session(session, chat_id)
    row.status = "abandoned"
    row.pending_prompt = None
    _edit_telegram_message(chat_id, message_id, "Cancelled.")


def handle_resume(session, chat_id: str, message_id: int | None) -> None:
    """User tapped Resume on the resume-offer screen. Re-render current item."""
    row = get_or_create_session(session, chat_id)
    if not row.item_queue or row.cursor >= len(row.item_queue):
        # Nothing to resume; fall back to fresh start.
        start_walk(session, chat_id)
        return
    _render_current_item(session, row, message_id)


def handle_restart(session, chat_id: str, message_id: int | None) -> None:
    """User tapped Start Over (or Another Category). Reset + render category screen."""
    row = get_or_create_session(session, chat_id)
    reset_for_start_over(row)
    counts = categories_with_stale_counts(session)
    if not counts:
        _edit_telegram_message(chat_id, message_id, "🎉 All caught up — nothing stale.")
        return
    text, kb = render_category_screen(counts)
    _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)


_VERB_TO_EXPECTED_PROMPT: dict[str, "str | set[str] | None"] = {
    "cat":     "category",
    "lvl":     "level",
    "skip":    "level",
    "nohave":  "level",
    "done":    {"level", "continue"},
    "cont":    "continue",
    "cart":    "cart",
    "resume":  "resume",
    "restart": {None, "resume"},
    "cancel":  {"category"},
}


def _matches_expected(prompt: str | None, expected) -> bool:
    if isinstance(expected, set):
        return prompt in expected
    return prompt == expected


def _rerender_current_prompt(session, row, message_id: int | None) -> None:
    """Send a fresh prompt matching row.pending_prompt (not an edit — Telegram message may be gone)."""
    from src.backend.initialize_database_schema import Inventory, Product

    prompt = row.pending_prompt
    if prompt == "category":
        counts = categories_with_stale_counts(session)
        text, kb = render_category_screen(counts)
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif prompt == "level":
        if row.cursor < len(row.item_queue):
            inv = session.query(Inventory).filter_by(id=row.item_queue[row.cursor]).one_or_none()
            if inv is not None and inv.product is not None:
                last_updated = inv.last_updated
                if last_updated and last_updated.tzinfo is not None:
                    last_updated = last_updated.replace(tzinfo=None)
                days_old = (datetime.utcnow() - last_updated).days if last_updated else 0
                text, kb = render_level_prompt(
                    product_name=inv.product.name,
                    category=row.current_category or "other",
                    idx=row.cursor + 1,
                    total=len(row.item_queue),
                    days_old=days_old,
                )
                send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif prompt == "cart":
        if row.last_item_id is not None:
            inv = session.query(Inventory).filter_by(id=row.last_item_id).one_or_none()
            if inv is not None and inv.product is not None:
                text, kb = render_cart_prompt(inv.product.name)
                send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif prompt == "continue":
        cutoff = _stale_cutoff()
        total_left = session.query(func.count(Inventory.id)).join(
            Product, Product.id == Inventory.product_id
        ).filter(
            Inventory.is_active_window.is_(True),
            Inventory.last_updated < cutoff,
            func.lower(func.coalesce(Product.category, "other")) == (row.current_category or "").lower(),
        ).scalar() or 0
        remaining = max(0, total_left - (row.page - 1) * PAGE_SIZE - row.cursor)
        text, kb = render_continue(row.current_category or "other", done=row.cursor, remaining=remaining)
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif prompt == "resume":
        if row.current_category and row.item_queue:
            text, kb = render_resume(row.current_category, row.cursor, len(row.item_queue))
            send_telegram_message(row.chat_id, text, reply_markup=kb)
        else:
            # Stale resume state; show fresh category screen.
            counts = categories_with_stale_counts(session)
            if counts:
                text, kb = render_category_screen(counts)
                send_telegram_message(row.chat_id, text, reply_markup=kb)
            else:
                send_telegram_message(row.chat_id, "🎉 All caught up — nothing stale.")
    elif prompt is None:
        # End-of-walk summary state, or freshly abandoned. Offer fresh category screen.
        counts = categories_with_stale_counts(session)
        if counts:
            text, kb = render_category_screen(counts)
            send_telegram_message(row.chat_id, text, reply_markup=kb)
            # Re-enter the category state.
            row.pending_prompt = "category"
        else:
            send_telegram_message(row.chat_id, "🎉 All caught up — nothing stale.")


def dispatch_inv_callback(session, chat_id: str, data: str, message_id: int | None) -> None:
    """Route an `inv:*` callback. `data` is the raw callback_data."""
    row = get_or_create_session(session, chat_id)

    if abandon_if_idle(row):
        send_telegram_message(chat_id, "Session timed out. /inventory to restart.")
        return

    parts = data.split(":", 2)
    if len(parts) < 2 or parts[0] != "inv":
        return
    verb = parts[1]
    arg = parts[2] if len(parts) == 3 else ""

    expected = _VERB_TO_EXPECTED_PROMPT.get(verb)
    if expected is not None and not _matches_expected(row.pending_prompt, expected):
        _edit_telegram_message(chat_id, message_id, "That button is stale. Showing current step:")
        _rerender_current_prompt(session, row, message_id=None)
        return

    if verb == "cat":
        handle_category(session, chat_id, arg, message_id)
    elif verb == "lvl":
        try:
            level = int(arg)
        except ValueError:
            return
        handle_level(session, chat_id, level, message_id)
    elif verb == "skip":
        handle_skip(session, chat_id, message_id)
    elif verb == "nohave":
        handle_nohave(session, chat_id, message_id)
    elif verb == "done":
        handle_done(session, chat_id, message_id)
    elif verb == "cont":
        handle_continue(session, chat_id, message_id)
    elif verb == "cart":
        handle_cart(session, chat_id, arg, message_id)
    elif verb == "resume":
        handle_resume(session, chat_id, message_id)
    elif verb == "restart":
        handle_restart(session, chat_id, message_id)
    elif verb == "cancel":
        handle_cancel(session, chat_id, message_id)


def dispatch_nudge_callback(session, chat_id: str, data: str, message_id: int | None) -> None:
    """Route `nudge:yes` / `nudge:later` / `nudge:mute` callbacks.

    Unlike `dispatch_inv_callback`, this handler intentionally does NOT validate
    `pending_prompt`. Nudges arrive out-of-band so the user's state can
    legitimately be anything (None after a summary, "level" mid-walk, etc.),
    and all three actions are state-independent: Yes restarts via start_walk
    (which has its own resume logic), Later/Mute only adjust nudge_muted_until.
    """
    row = get_or_create_session(session, chat_id)
    if data == "nudge:yes":
        _edit_telegram_message(chat_id, message_id, "Starting walk…")
        start_walk(session, chat_id)
    elif data == "nudge:later":
        row.nudge_muted_until = datetime.utcnow() + timedelta(days=3)
        _edit_telegram_message(chat_id, message_id, "OK, I'll ask again in a few days.")
    elif data == "nudge:mute":
        row.nudge_muted_until = datetime.utcnow() + timedelta(days=7)
        _edit_telegram_message(chat_id, message_id, "Muted for a week.")
