"""
Step 4: Configure MQTT Broker Connection
=========================================
PROMPT Reference: Phase 1, Step 4

Initializes and manages the MQTT client connection to the Mosquitto broker.
Provides publish/subscribe helpers used by all modules that need real-time sync.

Broker: configurable via MQTT_BROKER / MQTT_PORT
QoS: 1 (at least once delivery)
Retain: True for inventory state
"""

import os
import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MQTT Topics
# ---------------------------------------------------------------------------

MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "home/localocr_extended").strip().rstrip("/")
TOPICS = {
    "inventory": f"{MQTT_TOPIC_PREFIX}/inventory" + "/{product_id}",
    "low_stock": f"{MQTT_TOPIC_PREFIX}/alerts/low_stock",
    "recommendations": f"{MQTT_TOPIC_PREFIX}/recommendations/daily",
    "budget_alert": f"{MQTT_TOPIC_PREFIX}/alerts/budget",
}

# ---------------------------------------------------------------------------
# MQTT Client Management
# ---------------------------------------------------------------------------

_client = None
_intentional_disconnect = False


def _reason_code_value(reason_code):
    """Normalize paho v5 reason codes into a comparable/loggable value."""
    if reason_code is None:
        return 0

    for attr in ("value", "_value"):
        if hasattr(reason_code, attr):
            raw = getattr(reason_code, attr)
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass

    text = str(reason_code).strip()
    if text.lower() in {"success", "normal disconnection"}:
        return 0
    try:
        return int(text)
    except (TypeError, ValueError):
        return text or "unknown"


def _on_connect(client, userdata, flags, reason_code, properties=None):
    """Callback when connected to MQTT broker."""
    code = _reason_code_value(reason_code)
    if code == 0:
        logger.info("Connected to MQTT broker successfully.")
    else:
        logger.error(f"MQTT connection failed with code: {code}")


def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    """Callback when disconnected from MQTT broker."""
    global _intentional_disconnect
    code = _reason_code_value(reason_code)
    if _intentional_disconnect:
        _intentional_disconnect = False
        logger.info("MQTT client disconnected cleanly.")
        return
    if code != 0:
        logger.warning(f"Unexpected MQTT disconnect (rc={code}). Will auto-reconnect.")


def _on_message(client, userdata, msg):
    """Callback when a message is received."""
    logger.debug(f"MQTT message received: {msg.topic} → {msg.payload.decode()}")


def get_mqtt_client():
    """Get or create the MQTT client singleton."""
    global _client
    if _client is None:
        _client = setup_mqtt_connection()
    return _client


def setup_mqtt_connection():
    """Initialize and connect the MQTT client."""
    broker = os.getenv("MQTT_BROKER", "mqtt")
    port = int(os.getenv("MQTT_PORT", 1883))
    username = os.getenv("MQTT_USERNAME", "").strip()
    password = os.getenv("MQTT_PASSWORD", "")
    client_id = os.getenv("MQTT_CLIENT_ID", "localocr-extended")

    callback_api = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_api:
        client = mqtt.Client(
            callback_api_version=callback_api.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )
    else:
        client = mqtt.Client(
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )

    # Callbacks
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message

    if username:
        client.username_pw_set(username=username, password=password or None)

    # Auto-reconnect
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    try:
        client.connect(broker, port, keepalive=60)
        client.loop_start()  # Non-blocking background loop
        logger.info(f"MQTT client connecting to {broker}:{port}")
    except Exception as e:
        logger.error(f"Failed to connect to MQTT broker: {e}")

    return client


def publish_message(topic: str, payload: dict, retain: bool = True):
    """Publish a JSON message to an MQTT topic.

    Args:
        topic: MQTT topic string
        payload: Dictionary to serialize as JSON
        retain: Whether broker should retain the message (default: True)
    """
    client = get_mqtt_client()
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    message = json.dumps(payload)

    result = client.publish(topic, message, qos=1, retain=retain)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.debug(f"Published to {topic}: {message[:100]}...")
    else:
        logger.error(f"Failed to publish to {topic}: rc={result.rc}")

    return result


def publish_raw_message(topic: str, payload: str, retain: bool = True):
    """Publish a raw string payload without JSON mutation."""
    client = get_mqtt_client()
    result = client.publish(topic, payload, qos=1, retain=retain)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.debug(f"Published raw payload to {topic}")
    else:
        logger.error(f"Failed to publish raw payload to {topic}: rc={result.rc}")
    return result


def disconnect_mqtt():
    """Gracefully disconnect the MQTT client."""
    global _client, _intentional_disconnect
    if _client:
        _intentional_disconnect = True
        _client.loop_stop()
        _client.disconnect()
        _client = None


# ---------------------------------------------------------------------------
# Entry point for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    client = setup_mqtt_connection()
    publish_message(f"{MQTT_TOPIC_PREFIX}/test", {"message": "MQTT connection test"})
    logger.info("Test message published. Press Ctrl+C to exit.")
    try:
        import time
        time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        disconnect_mqtt()
