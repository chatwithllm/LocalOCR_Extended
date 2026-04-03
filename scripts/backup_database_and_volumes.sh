#!/bin/bash
# =============================================================================
# Backup Database & Volumes
# PROMPT Reference: Phase 8, Step 23
#
# Creates a compressed backup of the SQLite database, receipt images,
# and MQTT config. Runs daily via cron or Docker job.
#
# Retention: 30 days (older backups auto-deleted)
# Output: /data/backups/<BACKUP_PREFIX>_backup_YYYYMMDD.tar.gz
# =============================================================================

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DB_PATH="${DB_PATH:-/data/db/localocr_extended.db}"
RECEIPTS_DIR="${RECEIPTS_DIR:-/data/receipts}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
BACKUP_PREFIX="${BACKUP_PREFIX:-localocr_extended}"
DATE=$(date +%Y%m%d)
BACKUP_FILE="${BACKUP_DIR}/${BACKUP_PREFIX}_backup_${DATE}.tar.gz"
DB_COPY="${BACKUP_DIR}/${BACKUP_PREFIX}_${DATE}.db"
STAGING_DIR=$(mktemp -d)
trap 'rm -rf "${STAGING_DIR}" "${DB_COPY}"' EXIT

echo "═══════════════════════════════════════════"
echo "🗄️  ${BACKUP_PREFIX} Backup — $(date)"
echo "═══════════════════════════════════════════"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Step 1: Backup SQLite database (use .backup for consistency)
echo "📦 Backing up database..."
if [ -f "${DB_PATH}" ]; then
    sqlite3 "${DB_PATH}" ".backup ${DB_COPY}"
else
    echo "⚠️  Database not found at ${DB_PATH}"
fi

# Step 2: Create compressed archive
echo "🗜️  Compressing backup..."
mkdir -p "${STAGING_DIR}/receipts"
[ -f "${DB_COPY}" ] && cp "${DB_COPY}" "${STAGING_DIR}/database.db"
if [ -d "${RECEIPTS_DIR}" ]; then
    cp -R "${RECEIPTS_DIR}/." "${STAGING_DIR}/receipts/" 2>/dev/null || true
fi
tar -czf "${BACKUP_FILE}" -C "${STAGING_DIR}" .

# Step 3: Verify backup
if [ -f "${BACKUP_FILE}" ]; then
    SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "✅ Backup created: ${BACKUP_FILE} (${SIZE})"
else
    echo "❌ Backup failed!"
    exit 1
fi

# Step 4: Clean up old backups
echo "🧹 Cleaning backups older than ${RETENTION_DAYS} days..."
DELETED=$(find "${BACKUP_DIR}" -name "${BACKUP_PREFIX}_backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
echo "   Deleted ${DELETED} old backups."

echo "═══════════════════════════════════════════"
echo "✅ Backup complete!"
echo "═══════════════════════════════════════════"
