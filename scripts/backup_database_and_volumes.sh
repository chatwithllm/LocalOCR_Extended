#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DB_PATH="${DB_PATH:-/data/db/localocr_extended.db}"
RECEIPTS_DIR="${RECEIPTS_DIR:-/data/receipts}"
PRODUCT_SNAPSHOTS_DIR="${PRODUCT_SNAPSHOTS_DIR:-/data/product_snapshots}"
BACKUP_PREFIX="${BACKUP_PREFIX:-localocr_extended}"
KEEP_BACKUP_COUNT="${KEEP_BACKUP_COUNT:-3}"
APP_NAME="${APP_DISPLAY_NAME:-LocalOCR Extended}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TIMESTAMP_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ARCHIVE_NAME="${BACKUP_PREFIX}_backup_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="${BACKUP_DIR}/${ARCHIVE_NAME}"
MANIFEST_PATH="${BACKUP_DIR}/${BACKUP_PREFIX}_backup_${TIMESTAMP}.manifest.json"
STAGING_DIR="$(mktemp -d)"
DB_COPY="${STAGING_DIR}/database.db"
META_DIR="${STAGING_DIR}/meta"
RECEIPTS_STAGE="${STAGING_DIR}/receipts"
SNAPSHOTS_STAGE="${STAGING_DIR}/product_snapshots"
trap 'rm -rf "${STAGING_DIR}"' EXIT

mkdir -p "${BACKUP_DIR}" "${META_DIR}" "${RECEIPTS_STAGE}" "${SNAPSHOTS_STAGE}"

echo "═══════════════════════════════════════════"
echo "🗄️  ${BACKUP_PREFIX} Full Environment Backup — $(date)"
echo "═══════════════════════════════════════════"

if [ ! -f "${DB_PATH}" ]; then
  echo "❌ Database not found at ${DB_PATH}"
  exit 1
fi

python3 - <<'PY' "${DB_PATH}" "${DB_COPY}"
import sqlite3
import sys

source_path, backup_path = sys.argv[1], sys.argv[2]
source = sqlite3.connect(source_path)
backup = sqlite3.connect(backup_path)
source.backup(backup)
backup.close()
source.close()
PY

if [ -d "${RECEIPTS_DIR}" ]; then
  cp -R "${RECEIPTS_DIR}/." "${RECEIPTS_STAGE}/" 2>/dev/null || true
fi

if [ -d "${PRODUCT_SNAPSHOTS_DIR}" ]; then
  cp -R "${PRODUCT_SNAPSHOTS_DIR}/." "${SNAPSHOTS_STAGE}/" 2>/dev/null || true
fi

cat > "${META_DIR}/env.snapshot" <<EOF
APP_DISPLAY_NAME=${APP_DISPLAY_NAME:-}
APP_SLUG=${APP_SLUG:-}
APP_SERVICE_NAME=${APP_SERVICE_NAME:-}
PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-}
FLASK_PORT=${FLASK_PORT:-}
DATABASE_URL=${DATABASE_URL:-}
DB_PATH=${DB_PATH:-}
RECEIPTS_DIR=${RECEIPTS_DIR:-}
PRODUCT_SNAPSHOTS_DIR=${PRODUCT_SNAPSHOTS_DIR:-}
BACKUP_DIR=${BACKUP_DIR:-}
BACKUP_PREFIX=${BACKUP_PREFIX:-}
SESSION_SECRET=${SESSION_SECRET:-}
INITIAL_ADMIN_NAME=${INITIAL_ADMIN_NAME:-}
INITIAL_ADMIN_EMAIL=${INITIAL_ADMIN_EMAIL:-}
INITIAL_ADMIN_PASSWORD=${INITIAL_ADMIN_PASSWORD:-}
INITIAL_ADMIN_TOKEN=${INITIAL_ADMIN_TOKEN:-}
ENABLE_GROCERY=${ENABLE_GROCERY:-}
ENABLE_RESTAURANT=${ENABLE_RESTAURANT:-}
EOF

if [ -f "/app/docker-compose.yml" ]; then
  cp "/app/docker-compose.yml" "${META_DIR}/docker-compose.yml"
fi

python3 - <<'PY' "${DB_COPY}" "${RECEIPTS_STAGE}" "${SNAPSHOTS_STAGE}" "${META_DIR}/manifest.json" "${APP_NAME}" "${BACKUP_PREFIX}" "${ARCHIVE_NAME}" "${TIMESTAMP}" "${TIMESTAMP_UTC}"
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
receipts_dir = Path(sys.argv[2])
snapshots_dir = Path(sys.argv[3])
manifest_path = Path(sys.argv[4])
app_name = sys.argv[5]
backup_prefix = sys.argv[6]
archive_name = sys.argv[7]
timestamp = sys.argv[8]
timestamp_utc = sys.argv[9]

conn = sqlite3.connect(db_path)
c = conn.cursor()

def scalar(query):
    row = c.execute(query).fetchone()
    return row[0] if row else 0

receipt_rows = scalar("select count(*) from telegram_receipts")
purchase_rows = scalar("select count(*) from purchases")
user_rows = scalar("select count(*) from users")
trusted_devices = scalar("select count(*) from trusted_devices")
active_trusted_devices = scalar("select count(*) from trusted_devices where status = 'active'")

receipt_files = 0
receipt_bytes = 0
for path in receipts_dir.rglob("*"):
    if path.is_file():
        receipt_files += 1
        receipt_bytes += path.stat().st_size

snapshot_files = 0
snapshot_bytes = 0
for path in snapshots_dir.rglob("*"):
    if path.is_file():
        snapshot_files += 1
        snapshot_bytes += path.stat().st_size

digest = hashlib.sha256()
with db_path.open("rb") as fh:
    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
        digest.update(chunk)

manifest = {
    "app_name": app_name,
    "backup_prefix": backup_prefix,
    "archive_name": archive_name,
    "created_at": timestamp,
    "created_at_utc": timestamp_utc,
    "database": {
        "filename": db_path.name,
        "sha256": digest.hexdigest(),
        "purchase_rows": purchase_rows,
        "receipt_rows": receipt_rows,
        "user_rows": user_rows,
        "trusted_devices": trusted_devices,
        "trusted_device_rows": trusted_devices,
        "active_trusted_devices": active_trusted_devices,
    },
    "receipts": {
        "file_count": receipt_files,
        "total_bytes": receipt_bytes,
    },
    "product_snapshots": {
        "file_count": snapshot_files,
        "total_bytes": snapshot_bytes,
    },
}

manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
PY

tar -czf "${ARCHIVE_PATH}" -C "${STAGING_DIR}" .
cp "${META_DIR}/manifest.json" "${MANIFEST_PATH}"

if [[ "${KEEP_BACKUP_COUNT}" =~ ^[0-9]+$ ]] && [ "${KEEP_BACKUP_COUNT}" -gt 0 ]; then
  mapfile -t EXISTING_ARCHIVES < <(
    find "${BACKUP_DIR}" -maxdepth 1 -type f -name "${BACKUP_PREFIX}_backup_*.tar.gz" \
      -print0 | xargs -0 ls -1t 2>/dev/null || true
  )
  if [ "${#EXISTING_ARCHIVES[@]}" -gt "${KEEP_BACKUP_COUNT}" ]; then
    for OLD_ARCHIVE in "${EXISTING_ARCHIVES[@]:${KEEP_BACKUP_COUNT}}"; do
      [ -f "${OLD_ARCHIVE}" ] || continue
      rm -f "${OLD_ARCHIVE}"
      OLD_MANIFEST="${OLD_ARCHIVE%.tar.gz}.manifest.json"
      rm -f "${OLD_MANIFEST}"
      echo "🧹 Pruned old backup: ${OLD_ARCHIVE}"
    done
  fi
fi

SIZE="$(du -h "${ARCHIVE_PATH}" | cut -f1)"
echo "✅ Backup created: ${ARCHIVE_PATH} (${SIZE})"
echo "🧾 Manifest: ${MANIFEST_PATH}"
echo "📚 Retention: keeping newest ${KEEP_BACKUP_COUNT} backup(s)"
echo "═══════════════════════════════════════════"
