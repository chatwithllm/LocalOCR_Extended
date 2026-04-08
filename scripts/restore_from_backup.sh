#!/bin/bash
set -euo pipefail

BACKUP_FILE="${1:-}"
shift || true

ASSUME_YES="0"
NO_RESTART="0"
TARGET_ENV_FILE="${TARGET_ENV_FILE:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES="1"; shift ;;
    --no-restart) NO_RESTART="1"; shift ;;
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
BACKUP_PREFIX="${BACKUP_PREFIX:-localocr_extended}"
RESTORE_DIR="$(mktemp -d)"
trap 'rm -rf "${RESTORE_DIR}"' EXIT

if [ -z "${BACKUP_FILE}" ]; then
  echo "Usage: $0 <backup_file.tar.gz> [--yes] [--no-restart] [--target-env-file <path>]"
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

if [ -f "${RESTORE_DIR}/database.db" ]; then
  mkdir -p "$(dirname "${DB_PATH}")"
  cp "${RESTORE_DIR}/database.db" "${DB_PATH}"
fi

mkdir -p "${RECEIPTS_DIR}"
find "${RECEIPTS_DIR}" -mindepth 1 -exec rm -rf {} +
if [ -d "${RESTORE_DIR}/receipts" ]; then
  cp -R "${RESTORE_DIR}/receipts/." "${RECEIPTS_DIR}/"
fi

if [ -n "${TARGET_ENV_FILE}" ] && [ -f "${RESTORE_DIR}/meta/env.snapshot" ]; then
  mkdir -p "$(dirname "${TARGET_ENV_FILE}")"
  cp "${RESTORE_DIR}/meta/env.snapshot" "${TARGET_ENV_FILE}"
fi

cat > "${BACKUP_DIR}/last_restore_report.json" <<EOF
{
  "status": "restored",
  "backup_file": "$(basename "${BACKUP_FILE}")",
  "restored_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "db_path": "${DB_PATH}",
  "receipts_dir": "${RECEIPTS_DIR}",
  "target_env_file": "${TARGET_ENV_FILE}"
}
EOF

if [ "${NO_RESTART}" = "1" ]; then
  echo "⚠️  Restore finished without restarting the service."
else
  echo "ℹ️  Restore finished. Restart the service to ensure clean file handles."
fi

echo "═══════════════════════════════════════════"
echo "✅ Restore complete!"
echo "═══════════════════════════════════════════"
