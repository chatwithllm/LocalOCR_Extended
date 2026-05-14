"""Daily proactive nudge for stale Telegram inventory.

See docs/superpowers/specs/2026-05-13-telegram-inventory-walk-design.md §8.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func

from src.backend.handle_inventory_walk import (
    INVENTORY_STALE_DAYS,
    _bool_env,
    _csv_env,
    render_nudge,
    send_telegram_message,
)

logger = logging.getLogger(__name__)

NUDGE_MIN_STALE = 3
NUDGE_GAP_DAYS = 5


def _allowlist() -> set[str] | None:
    cs = _csv_env("TELEGRAM_AUTHORIZED_CHAT_IDS")
    return cs or None


def _candidate_chat_ids(session) -> set[str]:
    """Return chat_ids that can receive nudges.

    Prefers env allowlist; falls back to distinct telegram_user_id from
    TelegramReceipt (chats that have actually used the bot).
    """
    from src.backend.initialize_database_schema import TelegramReceipt
    allow = _allowlist()
    if allow:
        return allow
    rows = session.query(TelegramReceipt.telegram_user_id).distinct().all()
    return {r[0] for r in rows if r[0]}


def _stale_count_total(session) -> int:
    from src.backend.initialize_database_schema import Inventory, Product
    cutoff = datetime.utcnow() - timedelta(days=INVENTORY_STALE_DAYS)
    return (
        session.query(func.count(Inventory.id))
        .join(Product, Product.id == Inventory.product_id)
        .filter(Inventory.is_active_window.is_(True))
        .filter(Inventory.last_updated < cutoff)
        .scalar()
    ) or 0


def eligible_chat_ids(session) -> list[str]:
    from src.backend.initialize_database_schema import TelegramInventorySession
    now = datetime.utcnow()
    out: list[str] = []
    for chat_id in _candidate_chat_ids(session):
        sess_row = (
            session.query(TelegramInventorySession)
            .filter_by(chat_id=chat_id)
            .one_or_none()
        )
        # Active mid-walk -> skip.
        if sess_row and sess_row.status == "active" and sess_row.item_queue:
            continue
        # Currently muted -> skip.
        if sess_row and sess_row.nudge_muted_until:
            mute_until = sess_row.nudge_muted_until
            if mute_until.tzinfo is not None:
                mute_until = mute_until.replace(tzinfo=None)
            if mute_until > now:
                continue
        # Nudged in last N days -> skip.
        if sess_row and sess_row.last_nudge_sent_at:
            last_sent = sess_row.last_nudge_sent_at
            if last_sent.tzinfo is not None:
                last_sent = last_sent.replace(tzinfo=None)
            if last_sent > now - timedelta(days=NUDGE_GAP_DAYS):
                continue
        # Under threshold -> skip.
        if _stale_count_total(session) < NUDGE_MIN_STALE:
            continue
        out.append(chat_id)
    return out


def run_daily_nudge(session) -> None:
    if not _bool_env("INVENTORY_NUDGES_ENABLED", False):
        logger.info("inventory nudges disabled via env")
        return

    from src.backend.initialize_database_schema import TelegramInventorySession

    for chat_id in eligible_chat_ids(session):
        stale_count = _stale_count_total(session)
        if stale_count < NUDGE_MIN_STALE:
            continue
        text, kb = render_nudge(stale_count)
        try:
            send_telegram_message(chat_id, text, reply_markup=kb)
        except Exception as e:
            logger.warning("nudge send failed for %s: %s", chat_id, e)
            continue
        row = (
            session.query(TelegramInventorySession)
            .filter_by(chat_id=chat_id)
            .one_or_none()
        )
        if row is None:
            row = TelegramInventorySession(chat_id=chat_id, status="done")
            session.add(row)
            session.flush()
        row.last_nudge_sent_at = datetime.utcnow()
