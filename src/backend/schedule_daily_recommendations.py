"""
Step 17: Implement Daily Recommendation Push
==============================================
PROMPT Reference: Phase 5, Step 17

Scheduled task that generates and publishes recommendations daily at 8 AM
(configurable via RECOMMENDATION_TIME env var).

Uses APScheduler for scheduling. Publishes to MQTT topic:
home/grocery/recommendations/daily
"""

import os
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

RECOMMENDATION_TIME = os.getenv("RECOMMENDATION_TIME", "08:00")

_scheduler = None


def start_recommendation_scheduler():
    """Start the daily recommendation scheduler."""
    global _scheduler

    if _scheduler is not None:
        return  # Already running

    hour, minute = RECOMMENDATION_TIME.split(":")
    hour, minute = int(hour), int(minute)

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        push_daily_recommendations,
        trigger="cron",
        hour=hour,
        minute=minute,
        id="daily_recommendations",
        name="Daily Recommendation Push",
        misfire_grace_time=3600,  # Allow 1 hour late execution
    )

    # Also schedule image retention cleanup (weekly, Sunday 3 AM)
    _scheduler.add_job(
        _run_retention_cleanup,
        trigger="cron",
        day_of_week="sun",
        hour=3,
        id="retention_cleanup",
        name="Receipt Image Retention Cleanup",
    )

    # Also schedule threshold checks (every 5 minutes)
    _scheduler.add_job(
        _run_threshold_check,
        trigger="interval",
        minutes=5,
        id="threshold_check",
        name="Low-Stock Threshold Check",
    )

    # Hourly Plaid transaction sync for active items (skips when Plaid is unconfigured).
    _scheduler.add_job(
        _run_plaid_sync,
        trigger="interval",
        hours=1,
        id="plaid_transaction_sync",
        name="Plaid Transaction Sync",
    )

    # Nightly proactive product image backfill — schedule loaded from
    # admin-tweakable JSON file in /data so it survives restarts.
    from src.backend.image_backfill_schedule import load_schedule
    sched = load_schedule()
    _scheduler.add_job(
        _run_image_backfill,
        trigger="cron",
        hour=sched["hour"],
        minute=sched["minute"],
        id="image_backfill",
        name="Proactive Product Image Backfill",
        misfire_grace_time=3600,
    )
    _scheduler.start()
    if not sched["enabled"]:
        try:
            _scheduler.pause_job("image_backfill")
        except Exception as exc:
            logger.warning("Could not pause image_backfill job: %s", exc)
    logger.info(
        "Schedulers started — recommendations daily at %s, threshold checks "
        "every 5 min, image cleanup Sundays at 3 AM, Plaid sync hourly, "
        "image_backfill@%02d:%02d (%s)",
        RECOMMENDATION_TIME, sched["hour"], sched["minute"],
        "enabled" if sched["enabled"] else "PAUSED",
    )


def reschedule_image_backfill(*, enabled: bool, hour: int, minute: int) -> dict | None:
    """Apply a new schedule to the live APScheduler. Returns next-run info."""
    global _scheduler
    if _scheduler is None:
        return None
    from apscheduler.triggers.cron import CronTrigger
    try:
        _scheduler.reschedule_job(
            "image_backfill", trigger=CronTrigger(hour=hour, minute=minute),
        )
    except Exception as exc:
        logger.exception("Failed to reschedule image_backfill: %s", exc)
        raise
    try:
        if enabled:
            _scheduler.resume_job("image_backfill")
        else:
            _scheduler.pause_job("image_backfill")
    except Exception as exc:
        logger.warning("Could not toggle image_backfill pause state: %s", exc)
    job = _scheduler.get_job("image_backfill")
    next_run = getattr(job, "next_run_time", None) if job else None
    return {
        "enabled": enabled, "hour": hour, "minute": minute,
        "next_run_at": next_run.isoformat() if next_run else None,
    }


def get_image_backfill_runtime() -> dict | None:
    """Return current live job state (next_run_time, paused) for the admin UI."""
    if _scheduler is None:
        return None
    job = _scheduler.get_job("image_backfill")
    if job is None:
        return None
    next_run = getattr(job, "next_run_time", None)
    return {
        "next_run_at": next_run.isoformat() if next_run else None,
        "enabled": next_run is not None,
    }


def push_daily_recommendations():
    """Generate and publish daily recommendations via MQTT."""
    try:
        from src.backend.initialize_database_schema import create_db_engine, create_session_factory
        from flask import g

        # Create standalone session (runs outside Flask request context)
        engine = create_db_engine()
        Session = create_session_factory(engine)

        # We need a mock Flask context for modules that use g.db_session
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            g.db_session = Session()
            try:
                from src.backend.generate_recommendations import generate_all_recommendations
                from src.backend.publish_mqtt_events import publish_recommendations

                recommendations = generate_all_recommendations()
                publish_recommendations(recommendations)

                logger.info(f"Published {len(recommendations)} daily recommendations")
            finally:
                g.db_session.close()

    except Exception as e:
        logger.error(f"Failed to push daily recommendations: {e}")


def _run_retention_cleanup():
    """Run receipt image retention cleanup."""
    try:
        from src.backend.save_receipt_images import cleanup_old_images
        deleted = cleanup_old_images()
        logger.info(f"Retention cleanup completed: {deleted} images deleted")
    except Exception as e:
        logger.error(f"Retention cleanup failed: {e}")


def _run_threshold_check():
    """Run low-stock threshold checks."""
    try:
        from src.backend.check_inventory_thresholds import check_all_thresholds
        check_all_thresholds()
    except Exception as e:
        logger.error(f"Threshold check failed: {e}")


def _run_plaid_sync():
    """Hourly Plaid sync; no-ops gracefully when Plaid is not configured."""
    try:
        from src.backend.plaid_integration import run_scheduled_plaid_sync
        run_scheduled_plaid_sync()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Plaid scheduled sync failed: {e}")


def _run_image_backfill():
    """Nightly: fetch images for products missing a ProductSnapshot."""
    try:
        from src.backend.initialize_database_schema import (
            create_db_engine, create_session_factory,
        )
        from src.backend.backfill_product_images import (
            find_products_needing_images, backfill_images_for_products,
        )
        engine = create_db_engine()
        Session = create_session_factory(engine)
        session = Session()
        try:
            products = find_products_needing_images(session, max_products=50)
            if not products:
                logger.info("Image backfill: nothing to do.")
                return
            # Cron uses Gemini-only (free tier) — never burns OpenAI credit.
            # Failures cool down per RETRY_INTERVAL and retry on a later run.
            stats = backfill_images_for_products(
                session, products, provider="gemini",
            )
            logger.info(
                "Image backfill: fetched=%d failed=%d providers=%s (cap=50, gemini-only)",
                stats["fetched"], stats["failed"],
                stats.get("providers_used", {}),
            )
        finally:
            session.close()
    except Exception as exc:
        logger.error("Image backfill failed: %s", exc)


def stop_recommendation_scheduler():
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("All schedulers stopped.")
