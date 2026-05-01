"""Persisted admin-tweakable schedule for the image-backfill cron job.

Stored as a small JSON file inside the existing ``/data`` volume (already
backed up). No schema migration needed; survives container restarts.

Defaults: ``{"enabled": true, "hour": 4, "minute": 0}``.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_HOUR = 4
DEFAULT_MINUTE = 0
DEFAULT_ENABLED = True

DATA_DIR = Path(os.getenv("DATA_DIR") or "/data")
_SCHEDULE_FILE = DATA_DIR / "image_backfill_schedule.json"


def _coerce(raw: dict) -> dict:
    """Sanitize loaded values; fall back to defaults on bad input."""
    enabled = bool(raw.get("enabled", DEFAULT_ENABLED))
    try:
        hour = int(raw.get("hour", DEFAULT_HOUR))
    except (TypeError, ValueError):
        hour = DEFAULT_HOUR
    try:
        minute = int(raw.get("minute", DEFAULT_MINUTE))
    except (TypeError, ValueError):
        minute = DEFAULT_MINUTE
    if not 0 <= hour <= 23:
        hour = DEFAULT_HOUR
    if not 0 <= minute <= 59:
        minute = DEFAULT_MINUTE
    return {"enabled": enabled, "hour": hour, "minute": minute}


def load_schedule() -> dict:
    """Return current schedule config. Never raises — defaults on any error."""
    try:
        if _SCHEDULE_FILE.exists():
            return _coerce(json.loads(_SCHEDULE_FILE.read_text()))
    except Exception as exc:
        logger.warning("Failed to read schedule file %s: %s", _SCHEDULE_FILE, exc)
    return _coerce({})


def save_schedule(*, enabled: bool, hour: int, minute: int) -> dict:
    """Validate + persist new schedule config. Raises on invalid input."""
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    if not (isinstance(hour, int) and 0 <= hour <= 23):
        raise ValueError("hour must be an integer in [0, 23]")
    if not (isinstance(minute, int) and 0 <= minute <= 59):
        raise ValueError("minute must be an integer in [0, 59]")
    payload = {"enabled": enabled, "hour": hour, "minute": minute}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SCHEDULE_FILE.write_text(json.dumps(payload))
    return payload
