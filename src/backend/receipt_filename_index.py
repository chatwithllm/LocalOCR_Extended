"""
Human-readable index of stored receipt files.

The receipt files on disk keep their stable UUID names so backups,
restores, and the database FK to image_path never break. This module
adds an append-only text index at <receipts_root>/_index.txt with one
line per receipt:

    relative/path.pdf  AES_Indiana       2026-04-16  $87.40   purchase_id=92

so an operator SSH-ing into the box can `grep`, `tail`, or `less`
the file without touching the database.

The same `format_receipt_label()` is used by the download endpoint
to set Content-Disposition, so what the user sees in their browser
matches what the index file says on disk.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)

INDEX_FILENAME = "_index.txt"

# Single-process lock so concurrent uploads can't interleave half-lines into
# the index file. Inter-process safety is good enough for our scale (single
# Flask worker / single Docker container); upgrade to fcntl.flock() if we
# ever run multi-worker.
_INDEX_LOCK = threading.Lock()


def _safe_slug(value: str, *, fallback: str = "Unknown", max_len: int = 60) -> str:
    """Turn a free-form store / provider name into a filesystem-safe slug.

    'AES Indiana, LLC.' -> 'AES_Indiana_LLC'
    Empty / whitespace-only values fall back to `fallback`.
    """
    if not value:
        return fallback
    cleaned = re.sub(r"[^\w\s\-]", "", str(value), flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("_") or fallback
    return cleaned[:max_len]


def _format_date(value) -> str:
    """Coerce a date / datetime / 'YYYY-MM-DD' string into 'YYYY-MM-DD'."""
    if value is None or value == "":
        return "unknown-date"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else "unknown-date"


def format_receipt_label(
    *,
    store: Optional[str],
    date,
    extension: str,
    fallback_store: str = "Receipt",
) -> str:
    """Return 'AES_Indiana_2026-04-16.pdf' style filename.

    `extension` should include the leading dot (e.g. '.pdf'). If empty, no
    extension is appended (some image_paths have none in test fixtures).
    """
    slug = _safe_slug(store, fallback=fallback_store)
    date_str = _format_date(date)
    ext = (extension or "").lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    return f"{slug}_{date_str}{ext}"


def _format_money(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"${amount:,.2f}"


def _format_index_line(
    *,
    relative_path: str,
    store: Optional[str],
    date,
    total,
    purchase_id: Optional[int],
) -> str:
    """One column-aligned line; columns are wide enough to look tidy in `less`."""
    label = format_receipt_label(store=store, date=date, extension="")
    parts = [
        f"{relative_path:<48}",
        f"{label:<48}",
        f"{_format_date(date):<12}",
        f"{_format_money(total):>10}",
        f"purchase_id={purchase_id if purchase_id is not None else '-'}",
    ]
    return "  ".join(parts) + "\n"


def receipts_root() -> Path:
    """Resolve the receipts root the same way handle_receipt_upload does."""
    configured = os.getenv("RECEIPTS_DIR")
    if configured:
        cfg = Path(configured)
        if cfg.exists() or (cfg.parent.exists() and os.access(cfg.parent, os.W_OK)):
            return cfg
    container = Path("/data/receipts")
    if container.exists():
        return container
    return Path(__file__).resolve().parents[2] / "data" / "receipts"


def index_path() -> Path:
    return receipts_root() / INDEX_FILENAME


def _relative_image_path(image_path: str) -> str:
    """Return the path of the receipt file relative to the receipts root.

    Falls back to the absolute path if it lives outside the configured root,
    so operators can still grep for it.
    """
    if not image_path:
        return ""
    try:
        return str(Path(image_path).resolve().relative_to(receipts_root().resolve()))
    except (ValueError, OSError):
        return image_path


def append_receipt_to_index(
    *,
    image_path: str,
    store: Optional[str],
    date,
    total,
    purchase_id: Optional[int],
) -> None:
    """Best-effort append of one row to the receipts index file.

    Never raises — failure to update the index should not block a successful
    receipt save. Logs a warning so the operator can rebuild later.
    """
    if not image_path:
        return
    try:
        relative = _relative_image_path(image_path)
        line = _format_index_line(
            relative_path=relative,
            store=store,
            date=date,
            total=total,
            purchase_id=purchase_id,
        )
        target = index_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with _INDEX_LOCK:
            with target.open("a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to append receipt to index: %s", exc)


def rewrite_index_from_records(records: list[dict]) -> int:
    """Atomically rewrite the index file from an iterable of receipt records.

    Each record is a dict with keys: image_path, store, date, total, purchase_id.
    Returns the number of lines written.
    """
    target = index_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    written = 0
    with _INDEX_LOCK:
        with tmp.open("w", encoding="utf-8") as fh:
            for rec in records:
                if not rec.get("image_path"):
                    continue
                relative = _relative_image_path(rec["image_path"])
                fh.write(
                    _format_index_line(
                        relative_path=relative,
                        store=rec.get("store"),
                        date=rec.get("date"),
                        total=rec.get("total"),
                        purchase_id=rec.get("purchase_id"),
                    )
                )
                written += 1
        os.replace(tmp, target)
    return written
