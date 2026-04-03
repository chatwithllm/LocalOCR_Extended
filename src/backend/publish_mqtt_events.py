"""
Step 20: Create MQTT Real-Time Sync Handler
=============================================
PROMPT Reference: Phase 7, Step 20

Centralized MQTT publishing functions used by all modules that need
real-time sync. Every state change publishes a retained JSON message.

QoS: 1 (at least once delivery)
Retain: True (Home Assistant sees last state on reconnect)

Topics:
    home/grocery/inventory/{product_id}  — inventory updates
    home/grocery/alerts/low_stock        — low-stock alerts
    home/grocery/alerts/budget           — budget threshold alerts
    home/grocery/recommendations/daily   — daily recommendations
"""

import logging
import json
import os
from datetime import datetime, timezone

from src.backend.setup_mqtt_connection import publish_message, publish_raw_message, TOPICS

logger = logging.getLogger(__name__)

DISCOVERY_PREFIX = os.getenv("HOME_ASSISTANT_DISCOVERY_PREFIX", "homeassistant").strip() or "homeassistant"
DISCOVERY_ENABLED = os.getenv("MQTT_DISCOVERY_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
APP_SLUG = os.getenv("APP_SLUG", "localocr_extended").strip() or "localocr_extended"
APP_DISPLAY_NAME = os.getenv("APP_DISPLAY_NAME", "LocalOCR Extended").strip() or "LocalOCR Extended"
DEVICE = {
    "identifiers": [APP_SLUG],
    "name": APP_DISPLAY_NAME,
    "manufacturer": "LocalOCR",
    "model": "Household Inventory Platform",
    "sw_version": "current",
}


def _publish_discovery(component: str, object_id: str, payload: dict):
    if not DISCOVERY_ENABLED:
        return
    topic = f"{DISCOVERY_PREFIX}/{component}/{object_id}/config"
    publish_raw_message(topic, json.dumps(payload), retain=True)


def publish_inventory_update(product_id: int, name: str, quantity: float,
                              location: str, updated_by: str):
    """Publish an inventory state change."""
    topic = TOPICS["inventory"].format(product_id=product_id)
    object_id = f"{APP_SLUG}_inventory_{product_id}"
    _publish_discovery("sensor", object_id, {
        "name": f"{name} Quantity",
        "unique_id": object_id,
        "state_topic": topic,
        "value_template": "{{ value_json.quantity }}",
        "json_attributes_topic": topic,
        "icon": "mdi:package-variant",
        "device": DEVICE,
    })
    payload = {
        "product_id": product_id,
        "name": name,
        "quantity": quantity,
        "location": location,
        "updated_by": updated_by,
    }
    publish_message(topic, payload, retain=True)
    logger.info(f"Published inventory update: {name} → {quantity}")


def publish_low_stock_alert(product_id: int, product_name: str,
                             current_qty: float, threshold: float):
    """Publish a low-stock alert."""
    topic = TOPICS["low_stock"]
    object_id = f"{APP_SLUG}_low_stock_alert"
    _publish_discovery("sensor", object_id, {
        "name": f"{APP_DISPLAY_NAME} Low Stock Alert",
        "unique_id": object_id,
        "state_topic": topic,
        "value_template": "{{ value_json.name }}",
        "json_attributes_topic": topic,
        "icon": "mdi:alert",
        "device": DEVICE,
    })
    payload = {
        "product_id": product_id,
        "name": product_name,
        "current": current_qty,
        "threshold": threshold,
        "alert_type": "low_stock",
    }
    publish_message(topic, payload, retain=False)
    logger.info(f"Published low-stock alert: {product_name} ({current_qty} < {threshold})")


def publish_budget_alert(budget_amount: float, spent: float, percentage: float):
    """Publish a budget threshold alert."""
    topic = TOPICS["budget_alert"]
    object_id = f"{APP_SLUG}_budget_alert"
    _publish_discovery("sensor", object_id, {
        "name": f"{APP_DISPLAY_NAME} Budget Alert",
        "unique_id": object_id,
        "state_topic": topic,
        "value_template": "{{ value_json.percentage }}",
        "unit_of_measurement": "%",
        "json_attributes_topic": topic,
        "icon": "mdi:cash-alert",
        "device": DEVICE,
    })
    payload = {
        "budget_amount": budget_amount,
        "spent": spent,
        "percentage": round(percentage, 1),
        "alert_type": "budget",
    }
    publish_message(topic, payload, retain=False)
    logger.info(f"Published budget alert: {percentage:.1f}% spent")


def publish_recommendations(recommendations: list):
    """Publish daily recommendations."""
    topic = TOPICS["recommendations"]
    object_id = f"{APP_SLUG}_recommendations_count"
    _publish_discovery("sensor", object_id, {
        "name": f"{APP_DISPLAY_NAME} Recommendations",
        "unique_id": object_id,
        "state_topic": topic,
        "value_template": "{{ value_json.count }}",
        "json_attributes_topic": topic,
        "icon": "mdi:lightbulb-on-outline",
        "device": DEVICE,
    })
    payload = {
        "recommendations": recommendations,
        "count": len(recommendations),
    }
    publish_message(topic, payload, retain=True)
    logger.info(f"Published {len(recommendations)} recommendations")
