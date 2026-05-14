"""Telegram /inventory walk — state machine, dispatch, rendering.

See docs/superpowers/specs/2026-05-13-telegram-inventory-walk-design.md
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

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
