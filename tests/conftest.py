"""
Shared pytest configuration.

Stubs out native/cloud dependencies that are installed inside the Docker
container but not in the local dev environment. Tests that need the full
Flask app (endpoint tests) rely on these stubs being in place before any
src.backend.* import happens.
"""
import os
import sys
from unittest.mock import MagicMock

# Ensure SQLite-only defaults so tests never need a real DB URL or cookie jar.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")

_STUB_MODULES = [
    # MQTT
    "paho", "paho.mqtt", "paho.mqtt.client",
    # Telegram
    "telegram", "telegram.ext",
    # Plaid + sub-packages
    "plaid", "plaid.exceptions",
    "plaid.api",
    "plaid.model",
    "plaid.model.accounts_balance_get_request",
    "plaid.model.accounts_get_request",
    "plaid.model.country_code",
    "plaid.model.item_public_token_exchange_request",
    "plaid.model.item_remove_request",
    "plaid.model.link_token_create_request",
    "plaid.model.link_token_create_request_user",
    "plaid.model.products",
    "plaid.model.transactions_sync_request",
    # AI SDKs
    "anthropic", "openai",
    "google", "google.genai",
    # Image / QR
    "PIL", "qrcode",
    # Cryptography
    "cryptography", "cryptography.fernet",
    # Scheduler
    "apscheduler",
    "apscheduler.schedulers",
    "apscheduler.schedulers.background",
]

for _mod in _STUB_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
