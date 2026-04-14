#!/bin/bash
set -euo pipefail

DB_PATH="${DB_PATH:-/data/db/localocr_extended.db}"
RECEIPTS_DIR="${RECEIPTS_DIR:-/data/receipts}"
PRODUCT_SNAPSHOTS_DIR="${PRODUCT_SNAPSHOTS_DIR:-/data/product_snapshots}"
OUT_PATH="${1:-}"

RESULT="$(python3 - <<'PY' "${DB_PATH}" "${RECEIPTS_DIR}" "${PRODUCT_SNAPSHOTS_DIR}"
import json
import os
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
receipts_root = Path(sys.argv[2])
snapshots_root = Path(sys.argv[3])

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
result = {
    "status": "ok" if not missing else "warning",
    "database_exists": db_path.exists(),
    "receipts_dir_exists": receipts_root.exists(),
    "product_snapshots_dir_exists": snapshots_root.exists(),
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
print(json.dumps(result, indent=2))
PY
)"

if [ -n "${OUT_PATH}" ]; then
  mkdir -p "$(dirname "${OUT_PATH}")"
  printf '%s\n' "${RESULT}" > "${OUT_PATH}"
fi

printf '%s\n' "${RESULT}"
