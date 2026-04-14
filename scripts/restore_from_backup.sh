#!/bin/bash
set -euo pipefail

BACKUP_FILE="${1:-}"
shift || true

ASSUME_YES="0"
NO_RESTART="0"
TARGET_ENV_FILE="${TARGET_ENV_FILE:-}"
RESTORE_DB="1"
RESTORE_RECEIPTS="1"
RESTORE_ENV="1"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES="1"; shift ;;
    --no-restart) NO_RESTART="1"; shift ;;
    --skip-db) RESTORE_DB="0"; shift ;;
    --skip-receipts) RESTORE_RECEIPTS="0"; shift ;;
    --skip-env) RESTORE_ENV="0"; shift ;;
    --target-env-file)
      TARGET_ENV_FILE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DB_PATH="${DB_PATH:-/data/db/localocr_extended.db}"
RECEIPTS_DIR="${RECEIPTS_DIR:-/data/receipts}"
PRODUCT_SNAPSHOTS_DIR="${PRODUCT_SNAPSHOTS_DIR:-/data/product_snapshots}"
BACKUP_PREFIX="${BACKUP_PREFIX:-localocr_extended}"
RESTORE_DIR="$(mktemp -d)"
trap 'rm -rf "${RESTORE_DIR}"' EXIT

if [ -z "${BACKUP_FILE}" ]; then
  echo "Usage: $0 <backup_file.tar.gz> [--yes] [--no-restart] [--skip-db] [--skip-receipts] [--skip-env] [--target-env-file <path>]"
  exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "❌ Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

echo "═══════════════════════════════════════════"
echo "🔄 ${BACKUP_PREFIX} Restore — $(date)"
echo "   Source: ${BACKUP_FILE}"
echo "═══════════════════════════════════════════"

if [ "${ASSUME_YES}" != "1" ]; then
  read -p "⚠️  This will overwrite current data. Continue? (y/N) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

tar -xzf "${BACKUP_FILE}" -C "${RESTORE_DIR}"

if [ "${RESTORE_DB}" = "1" ] && [ ! -f "${RESTORE_DIR}/database.db" ]; then
  echo "❌ Backup archive does not contain database.db"
  exit 1
fi

if [ "${RESTORE_DB}" = "1" ]; then
  mkdir -p "$(dirname "${DB_PATH}")"
  rm -f "${DB_PATH}" "${DB_PATH}-wal" "${DB_PATH}-shm"
  cp "${RESTORE_DIR}/database.db" "${DB_PATH}"
  sync || true
fi

if [ "${RESTORE_RECEIPTS}" = "1" ]; then
  mkdir -p "${RECEIPTS_DIR}"
  find "${RECEIPTS_DIR}" -mindepth 1 -exec rm -rf {} +
  if [ -d "${RESTORE_DIR}/receipts" ]; then
    cp -R "${RESTORE_DIR}/receipts/." "${RECEIPTS_DIR}/"
  fi
  mkdir -p "${PRODUCT_SNAPSHOTS_DIR}"
  find "${PRODUCT_SNAPSHOTS_DIR}" -mindepth 1 -exec rm -rf {} +
  if [ -d "${RESTORE_DIR}/product_snapshots" ]; then
    cp -R "${RESTORE_DIR}/product_snapshots/." "${PRODUCT_SNAPSHOTS_DIR}/"
  fi
  sync || true
fi

if [ "${RESTORE_ENV}" = "1" ] && [ -n "${TARGET_ENV_FILE}" ] && [ -f "${RESTORE_DIR}/meta/env.snapshot" ]; then
  mkdir -p "$(dirname "${TARGET_ENV_FILE}")"
  cp "${RESTORE_DIR}/meta/env.snapshot" "${TARGET_ENV_FILE}"
fi

RESTORE_REPORT="$(python3 - <<'PY' "${DB_PATH}" "${RECEIPTS_DIR}" "${PRODUCT_SNAPSHOTS_DIR}" "$(basename "${BACKUP_FILE}")" "${TARGET_ENV_FILE}" "${RESTORE_DB}" "${RESTORE_RECEIPTS}" "${RESTORE_ENV}"
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

db_path = Path(sys.argv[1])
receipts_root = Path(sys.argv[2])
snapshots_root = Path(sys.argv[3])
backup_file = sys.argv[4]
target_env_file = sys.argv[5]

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def scalar(query):
    row = c.execute(query).fetchone()
    return row[0] if row else 0

receipt_refs = c.execute("select image_path from telegram_receipts where image_path is not null and image_path != ''").fetchall()
missing = []
for row in receipt_refs:
    image_path = row["image_path"]
    parts = Path(image_path).parts
    try:
        idx = parts.index("data")
        rel = Path(*parts[idx + 2:]) if idx + 1 < len(parts) and parts[idx + 1] == "receipts" else Path(image_path)
    except ValueError:
        rel = Path(image_path)
    if not (receipts_root / rel).exists():
        missing.append(rel.as_posix())

receipt_file_count = sum(1 for path in receipts_root.rglob("*") if path.is_file()) if receipts_root.exists() else 0
snapshot_file_count = sum(1 for path in snapshots_root.rglob("*") if path.is_file()) if snapshots_root.exists() else 0
report = {
    "status": "restored",
    "backup_file": backup_file,
    "restored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "db_path": str(db_path),
    "receipts_dir": str(receipts_root),
    "product_snapshots_dir": str(snapshots_root),
    "target_env_file": target_env_file,
    "restored_sections": {
        "database": sys.argv[6] == "1",
        "receipts": sys.argv[7] == "1",
        "env": sys.argv[8] == "1",
    },
    "users": scalar("select count(*) from users"),
    "purchases": scalar("select count(*) from purchases"),
    "trusted_devices": scalar("select count(*) from trusted_devices where status = 'active'"),
    "receipt_rows": scalar("select count(*) from telegram_receipts"),
    "receipt_files": receipt_file_count,
    "product_snapshot_rows": scalar("select count(*) from product_snapshots"),
    "product_snapshot_files": snapshot_file_count,
    "missing_receipt_images": len(missing),
    "missing_receipt_samples": missing[:10],
}
print(json.dumps(report, indent=2))
PY
)"

printf '%s\n' "${RESTORE_REPORT}" > "${BACKUP_DIR}/last_restore_report.json"
printf '%s\n' "${RESTORE_REPORT}"

if [ "${NO_RESTART}" = "1" ]; then
  echo "⚠️  Restore finished without restarting the service."
else
  echo "ℹ️  Restore finished. Restart the service to ensure clean file handles."
fi

echo "═══════════════════════════════════════════"
echo "✅ Restore complete!"
echo "═══════════════════════════════════════════"
