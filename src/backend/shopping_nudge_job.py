"""Daily proactive shopping nudge.

See docs/superpowers/specs/2026-05-14-telegram-shopping-walk-design.md §8.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.backend.handle_shopping_walk import (
    _bool_env, _csv_env, _int_env,
    bucketize_by_category, fetch_recommendations,
    render_nudge, send_telegram_message,
)

logger = logging.getLogger(__name__)

NUDGE_MIN_RECS = _int_env("SHOPPING_NUDGE_MIN_RECS", 8)
NUDGE_GAP_DAYS = _int_env("SHOPPING_NUDGE_GAP_DAYS", 3)


def _allowlist() -> set[str] | None:
    cs = _csv_env("TELEGRAM_AUTHORIZED_CHAT_IDS")
    return cs or None


def _candidate_chat_ids(session) -> set[str]:
    from src.backend.initialize_database_schema import TelegramReceipt
    allow = _allowlist()
    if allow:
        return allow
    rows = session.query(TelegramReceipt.telegram_user_id).distinct().all()
    return {r[0] for r in rows if r[0]}


def eligible_chat_ids(session) -> list[str]:
    from src.backend.initialize_database_schema import TelegramShoppingSession
    now = datetime.utcnow()
    out: list[str] = []
    recs = fetch_recommendations(session)
    rec_count = len(recs)
    if rec_count < NUDGE_MIN_RECS:
        return out
    for chat_id in _candidate_chat_ids(session):
        sess_row = (
            session.query(TelegramShoppingSession)
            .filter_by(chat_id=chat_id)
            .one_or_none()
        )
        if sess_row and sess_row.status == "active" and sess_row.item_queue:
            continue
        if sess_row and sess_row.nudge_muted_until:
            mute_until = sess_row.nudge_muted_until
            if mute_until.tzinfo is not None:
                mute_until = mute_until.replace(tzinfo=None)
            if mute_until > now:
                continue
        if sess_row and sess_row.last_nudge_sent_at:
            last_sent = sess_row.last_nudge_sent_at
            if last_sent.tzinfo is not None:
                last_sent = last_sent.replace(tzinfo=None)
            if last_sent > now - timedelta(days=NUDGE_GAP_DAYS):
                continue
        out.append(chat_id)
    return out


def run_daily_shopping_nudge(session) -> None:
    if not _bool_env("SHOPPING_NUDGE_ENABLED", False):
        logger.info("shopping nudges disabled via env")
        return

    from src.backend.initialize_database_schema import TelegramShoppingSession

    recs = fetch_recommendations(session)
    if len(recs) < NUDGE_MIN_RECS:
        return
    cat_queue, _items_by = bucketize_by_category(recs)
    rec_count = len(recs)
    category_count = len(cat_queue)

    for chat_id in eligible_chat_ids(session):
        text, kb = render_nudge(rec_count=rec_count, category_count=category_count)
        try:
            send_telegram_message(chat_id, text, reply_markup=kb)
        except Exception as e:
            logger.warning("shopping nudge send failed for %s: %s", chat_id, e)
            continue
        row = (
            session.query(TelegramShoppingSession)
            .filter_by(chat_id=chat_id)
            .one_or_none()
        )
        if row is None:
            row = TelegramShoppingSession(chat_id=chat_id, status="done")
            session.add(row); session.flush()
        row.last_nudge_sent_at = datetime.utcnow()


def register_daily_shopping_nudge_job(scheduler) -> None:
    """Register daily 09:30 nudge job. No-op when SHOPPING_NUDGE_ENABLED is off."""
    if not _bool_env("SHOPPING_NUDGE_ENABLED", False):
        return
    from apscheduler.triggers.cron import CronTrigger

    def _job_wrapper():
        from src.backend.initialize_database_schema import (
            create_db_engine, create_session_factory,
        )
        engine = create_db_engine()
        Session = create_session_factory(engine)
        sess = Session()
        try:
            run_daily_shopping_nudge(sess)
            sess.commit()
        except Exception:
            sess.rollback()
            logger.exception("daily shopping nudge job failed")
        finally:
            sess.close()

    scheduler.add_job(
        _job_wrapper,
        trigger=CronTrigger(hour=9, minute=30),
        id="shopping_daily_nudge",
        name="Daily Shopping Nudge",
        replace_existing=True,
    )
