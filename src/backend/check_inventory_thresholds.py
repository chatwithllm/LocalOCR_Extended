"""
Step 15: Add Low-Stock Alert System
=====================================
PROMPT Reference: Phase 4, Step 15

Checks inventory against per-product thresholds every 5 minutes.
Publishes MQTT alerts and avoids duplicate alerts (24-hour repeat interval).

MQTT Topic: home/grocery/alerts/low_stock
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

# Track last alert time per product to avoid duplicates
_last_alert_times = {}
_scheduler = None


def start_threshold_checker():
    """Start the 5-minute threshold checking scheduler."""
    global _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        check_all_thresholds,
        trigger="interval",
        minutes=5,
        id="threshold_check",
        name="Low-Stock Threshold Check",
    )
    _scheduler.start()
    logger.info("Threshold checking scheduler started (every 5 minutes).")


def check_all_thresholds():
    """Check all inventory items against their thresholds.

    Runs every 5 minutes via APScheduler.
    Publishes MQTT alert for items below threshold.
    """
    try:
        from src.backend.active_inventory import rebuild_active_inventory
        from src.backend.initialize_database_schema import create_db_engine, create_session_factory, Inventory, Product
        from src.backend.publish_mqtt_events import publish_low_stock_alert

        # Create a standalone session (this runs outside Flask request context)
        engine = create_db_engine()
        Session = create_session_factory(engine)
        session = Session()

        try:
            rebuild_active_inventory(session)
            session.flush()
            items = session.query(Inventory).join(Product).filter(
                Inventory.is_active_window.is_(True),
                Inventory.threshold.isnot(None),
                Inventory.quantity < Inventory.threshold
            ).all()

            alerted_count = 0
            for item in items:
                if _should_alert(item.product_id):
                    product = session.query(Product).filter_by(id=item.product_id).first()
                    if product:
                        publish_low_stock_alert(
                            product_id=product.id,
                            product_name=product.name,
                            current_qty=item.quantity,
                            threshold=item.threshold,
                        )
                        _last_alert_times[item.product_id] = datetime.now(timezone.utc)
                        alerted_count += 1

            if alerted_count > 0:
                logger.info(f"Low-stock alerts: {alerted_count} products below threshold.")
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Threshold check failed: {e}")


def _should_alert(product_id: int) -> bool:
    """Check if we should send an alert (24-hour dedup)."""
    last_alert = _last_alert_times.get(product_id)
    if last_alert is None:
        return True
    return datetime.now(timezone.utc) - last_alert > timedelta(hours=24)


def set_threshold(product_id: int, threshold: float):
    """Set the low-stock threshold for a product."""
    try:
        from src.backend.initialize_database_schema import create_db_engine, create_session_factory, Inventory
        engine = create_db_engine()
        Session = create_session_factory(engine)
        session = Session()
        try:
            item = session.query(Inventory).filter_by(product_id=product_id).first()
            if item:
                item.threshold = threshold
                session.commit()
                logger.info(f"Threshold set for product {product_id}: {threshold}")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to set threshold: {e}")


def stop_threshold_checker():
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
