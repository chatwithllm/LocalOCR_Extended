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
USE_BACKUP_FERNET="0"
REKEY="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES="1"; shift ;;
    --no-restart) NO_RESTART="1"; shift ;;
    --skip-db) RESTORE_DB="0"; shift ;;
    --skip-receipts) RESTORE_RECEIPTS="0"; shift ;;
    --skip-env) RESTORE_ENV="0"; shift ;;
    --use-backup-fernet) USE_BACKUP_FERNET="1"; shift ;;
    --rekey) REKEY="1"; shift ;;
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

if [ "${USE_BACKUP_FERNET}" = "1" ] && [ "${REKEY}" = "1" ]; then
  echo "❌ --use-backup-fernet and --rekey are mutually exclusive."
  echo "   --use-backup-fernet adopts the backup's key verbatim on this host."
  echo "   --rekey keeps this host's key and re-encrypts stored credentials."
  exit 1
fi

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DB_PATH="${DB_PATH:-/data/db/localocr_extended.db}"
RECEIPTS_DIR="${RECEIPTS_DIR:-/data/receipts}"
PRODUCT_SNAPSHOTS_DIR="${PRODUCT_SNAPSHOTS_DIR:-/data/product_snapshots}"
BACKUP_PREFIX="${BACKUP_PREFIX:-localocr_extended}"
RESTORE_DIR="$(mktemp -d)"
trap 'rm -rf "${RESTORE_DIR}"' EXIT

if [ -z "${BACKUP_FILE}" ]; then
  echo "Usage: $0 <backup_file.tar.gz> [--yes] [--no-restart] [--skip-db] [--skip-receipts] [--skip-env] [--target-env-file <path>] [--use-backup-fernet | --rekey]"
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

# Extract FERNET_SECRET_KEY from the backup's env snapshot (if present) so
# it's available for either --use-backup-fernet (adopt verbatim) or --rekey
# (use as OLD_FERNET_SECRET_KEY while re-encrypting under the host's current key).
BACKUP_FERNET_KEY=""
if [ -f "${RESTORE_DIR}/meta/env.snapshot" ]; then
  BACKUP_FERNET_KEY="$(grep -E '^FERNET_SECRET_KEY=' "${RESTORE_DIR}/meta/env.snapshot" | tail -n 1 | cut -d= -f2- || true)"
fi

if [ "${USE_BACKUP_FERNET}" = "1" ]; then
  if [ -z "${BACKUP_FERNET_KEY}" ]; then
    echo "❌ --use-backup-fernet requested but backup does not contain FERNET_SECRET_KEY."
    exit 1
  fi
  if [ -z "${TARGET_ENV_FILE}" ]; then
    echo "❌ --use-backup-fernet requires --target-env-file <path> so the key can be persisted."
    exit 1
  fi
  mkdir -p "$(dirname "${TARGET_ENV_FILE}")"
  touch "${TARGET_ENV_FILE}"
  python3 - <<'PY' "${TARGET_ENV_FILE}" "${BACKUP_FERNET_KEY}"
import sys
from pathlib import Path
env_path = Path(sys.argv[1])
value = sys.argv[2]
lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
out = []
replaced = False
for line in lines:
    if line.startswith("FERNET_SECRET_KEY="):
        out.append(f"FERNET_SECRET_KEY={value}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"FERNET_SECRET_KEY={value}")
env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  echo "🔐 Adopted FERNET_SECRET_KEY from backup in ${TARGET_ENV_FILE}"
fi

if [ "${REKEY}" = "1" ]; then
  if [ "${RESTORE_DB}" != "1" ]; then
    echo "⚠️  --rekey skipped because --skip-db was set (no DB was restored)."
  elif [ -z "${BACKUP_FERNET_KEY}" ]; then
    echo "❌ --rekey requested but backup does not contain FERNET_SECRET_KEY."
    echo "   Back up a newer bundle (with FERNET_SECRET_KEY in env.snapshot) or restore the old key manually via OLD_FERNET_SECRET_KEY."
    exit 1
  else
    CURRENT_FERNET_KEY="${FERNET_SECRET_KEY:-}"
    if [ -z "${CURRENT_FERNET_KEY}" ]; then
      echo "❌ --rekey requires FERNET_SECRET_KEY to be set in this environment (the new key to re-encrypt under)."
      exit 1
    fi
    REKEY_SCRIPT="$(dirname "$0")/rekey_encrypted_credentials.py"
    if [ ! -f "${REKEY_SCRIPT}" ]; then
      echo "❌ rekey script not found: ${REKEY_SCRIPT}"
      exit 1
    fi
    echo "🔁 Re-encrypting stored credentials under this host's FERNET_SECRET_KEY..."
    OLD_FERNET_SECRET_KEY="${BACKUP_FERNET_KEY}" \
      FERNET_SECRET_KEY="${CURRENT_FERNET_KEY}" \
      python3 "${REKEY_SCRIPT}" --db-path "${DB_PATH}" --json \
      > "${BACKUP_DIR}/last_rekey_report.json" || REKEY_STATUS="$?"
    REKEY_STATUS="${REKEY_STATUS:-0}"
    cat "${BACKUP_DIR}/last_rekey_report.json"
    if [ "${REKEY_STATUS}" != "0" ]; then
      echo "⚠️  Rekey finished with status ${REKEY_STATUS}. See ${BACKUP_DIR}/last_rekey_report.json"
    fi
  fi
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
