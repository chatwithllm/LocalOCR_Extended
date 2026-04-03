"""
Step 12: Handle Receipt Image Processing
==========================================
PROMPT Reference: Phase 3, Step 12

Manages receipt image storage, thumbnails, duplicate detection, and
retention policy cleanup. Images stored at /data/receipts/{year}/{month}/.

Retention: 12 months by default (configurable via RECEIPT_RETENTION_MONTHS)
"""

import os
import hashlib
import logging
import shutil
from uuid import uuid4
from datetime import datetime, timedelta

from PIL import Image

logger = logging.getLogger(__name__)

RECEIPTS_DIR = os.getenv("RECEIPTS_DIR", "/data/receipts")
RETENTION_MONTHS = int(os.getenv("RECEIPT_RETENTION_MONTHS", "12"))

# In-memory hash cache for duplicate detection
_seen_hashes = set()


def save_receipt_image(source_path: str, source: str = "upload") -> dict:
    """Save a receipt image with organized directory structure.

    Args:
        source_path: Path to the original image file.
        source: "telegram" or "upload"

    Returns:
        Dict with saved file metadata.
    """
    # Check for duplicate
    file_hash = compute_file_hash(source_path)
    if file_hash in _seen_hashes:
        logger.warning(f"Duplicate receipt detected (hash: {file_hash[:12]})")
        return {
            "status": "duplicate",
            "hash": file_hash,
            "path": source_path,
        }

    _seen_hashes.add(file_hash)

    # Organize into year/month directory
    year_month = datetime.now().strftime("%Y/%m")
    save_dir = os.path.join(RECEIPTS_DIR, year_month)
    os.makedirs(save_dir, exist_ok=True)

    ext = os.path.splitext(source_path)[1] or ".jpg"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{uuid4().hex[:8]}{ext}"
    dest_path = os.path.join(save_dir, filename)

    # Copy (don't move — source might still be needed)
    if source_path != dest_path:
        shutil.copy2(source_path, dest_path)

    # Generate thumbnail
    thumb_path = generate_thumbnail(dest_path)

    file_size = os.path.getsize(dest_path)

    logger.info(f"Receipt saved: {dest_path} ({file_size / 1024:.1f} KB)")

    return {
        "status": "saved",
        "path": dest_path,
        "thumbnail": thumb_path,
        "hash": file_hash,
        "size_bytes": file_size,
        "filename": filename,
    }


def generate_thumbnail(image_path: str, max_size: tuple = (400, 400)) -> str:
    """Create a compressed thumbnail for Home Assistant UI."""
    try:
        img = Image.open(image_path)
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        base, ext = os.path.splitext(image_path)
        thumb_path = f"{base}_thumb.jpg"
        img.save(thumb_path, "JPEG", quality=70, optimize=True)

        logger.debug(f"Thumbnail created: {thumb_path}")
        return thumb_path
    except Exception as e:
        logger.warning(f"Thumbnail generation failed: {e}")
        return ""


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def detect_duplicate(image_path: str) -> bool:
    """Check if an identical image has already been processed."""
    file_hash = compute_file_hash(image_path)
    return file_hash in _seen_hashes


def cleanup_old_images():
    """Delete receipt images older than retention period.

    Database records are preserved — only image files are deleted.
    Runs weekly via scheduler.
    """
    cutoff_date = datetime.now() - timedelta(days=RETENTION_MONTHS * 30)
    deleted_count = 0
    freed_bytes = 0

    if not os.path.exists(RECEIPTS_DIR):
        return deleted_count

    for root, dirs, files in os.walk(RECEIPTS_DIR):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff_date:
                    file_size = os.path.getsize(filepath)
                    os.remove(filepath)
                    deleted_count += 1
                    freed_bytes += file_size
                    logger.debug(f"Retention cleanup: deleted {filepath}")
            except Exception as e:
                logger.warning(f"Failed to check/delete {filepath}: {e}")

    freed_mb = freed_bytes / (1024 * 1024)
    logger.info(
        f"Retention cleanup: deleted {deleted_count} images "
        f"(freed {freed_mb:.1f} MB) older than {cutoff_date.date()}"
    )
    return deleted_count


def get_storage_stats() -> dict:
    """Get receipt storage statistics."""
    total_files = 0
    total_bytes = 0

    if os.path.exists(RECEIPTS_DIR):
        for root, dirs, files in os.walk(RECEIPTS_DIR):
            for f in files:
                filepath = os.path.join(root, f)
                total_files += 1
                total_bytes += os.path.getsize(filepath)

    return {
        "total_files": total_files,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "retention_months": RETENTION_MONTHS,
        "receipts_dir": RECEIPTS_DIR,
    }
