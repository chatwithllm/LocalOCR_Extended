#!/bin/bash
# =============================================================================
# Restore from Backup
# PROMPT Reference: Phase 8, Step 23
#
# Restores the SQLite database and receipt images from a backup archive.
# Can restore on a different machine — fully portable.
#
# Usage: ./scripts/restore_from_backup.sh /path/to/<BACKUP_PREFIX>_backup_YYYYMMDD.tar.gz
# =============================================================================

set -euo pipefail

BACKUP_FILE="${1:-}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DB_PATH="${DB_PATH:-/data/db/localocr_extended.db}"
RECEIPTS_DIR="${RECEIPTS_DIR:-/data/receipts}"
BACKUP_PREFIX="${BACKUP_PREFIX:-localocr_extended}"

if [ -z "${BACKUP_FILE}" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -lh "${BACKUP_DIR}/${BACKUP_PREFIX}_backup_"*.tar.gz 2>/dev/null || echo "  No backups found in ${BACKUP_DIR}/"
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

# Confirm
read -p "⚠️  This will overwrite current data. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Step 1: Stop the backend (if running in Docker)
echo "🛑 Stopping backend service..."
docker compose stop backend 2>/dev/null || true

# Step 2: Extract backup
echo "📦 Extracting backup..."
RESTORE_DIR=$(mktemp -d)
trap 'rm -rf "${RESTORE_DIR}"' EXIT
tar -xzf "${BACKUP_FILE}" -C "${RESTORE_DIR}"

# Step 3: Restore database
BACKUP_DB="${RESTORE_DIR}/database.db"
if [ -f "${BACKUP_DB}" ]; then
    echo "🗄️  Restoring database..."
    mkdir -p "$(dirname "${DB_PATH}")"
    cp "${BACKUP_DB}" "${DB_PATH}"
fi

echo "🧾 Restoring receipt storage..."
mkdir -p "${RECEIPTS_DIR}"
find "${RECEIPTS_DIR}" -mindepth 1 -exec rm -rf {} +
if [ -d "${RESTORE_DIR}/receipts" ]; then
    cp -R "${RESTORE_DIR}/receipts/." "${RECEIPTS_DIR}/"
fi

# Step 4: Restart backend
echo "🚀 Restarting backend service..."
docker compose start backend 2>/dev/null || true

echo "═══════════════════════════════════════════"
echo "✅ Restore complete!"
echo "   Database and receipts restored from backup."
echo "═══════════════════════════════════════════"
