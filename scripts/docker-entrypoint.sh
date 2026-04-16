#!/bin/sh
# Container entrypoint: safely auto-apply Alembic migrations, then launch Flask.
#
# Handles three DB states:
#   1. Fresh DB (no tables)                    -> `alembic upgrade head` from scratch
#   2. Tracked DB (alembic_version present)    -> `alembic upgrade head` (runs only pending)
#   3. Legacy DB (tables exist, but no
#      alembic_version row — DB was originally
#      created by SQLAlchemy create_all())     -> skip migration, log a warning
#
# Case 3 is important: stamping blindly to head would falsely claim the schema
# matches the latest model definitions, which is not always true if the DB was
# bootstrapped by an older version of the code. The operator must run
# `alembic stamp <revision>` once to opt in to auto-upgrades.
set -e

python3 <<'PY'
import os
import sqlite3
import subprocess
import sys

DEFAULT_URL = "sqlite:////data/db/localocr_extended.db"
url = os.getenv("DATABASE_URL") or DEFAULT_URL

if not url.startswith("sqlite:///"):
    # Non-SQLite backends are not part of this project today. Just run upgrade
    # and let alembic report its own errors.
    sys.exit(subprocess.call(["alembic", "upgrade", "head"]))

db_path = url.replace("sqlite:///", "", 1)
if not os.path.exists(db_path):
    # Fresh install: fall through to normal upgrade so alembic creates tables.
    print(f"[entrypoint] No DB at {db_path} yet — running alembic upgrade head.")
    sys.exit(subprocess.call(["alembic", "upgrade", "head"]))

conn = sqlite3.connect(db_path)
try:
    cur = conn.cursor()
    alembic_table_exists = cur.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name='alembic_version'"
    ).fetchone() is not None
    # Empty alembic_version table is equivalent to "not tracked" — alembic
    # treats it as base state and will try to re-run migration 001 from
    # scratch, which crashes when tables already exist.
    alembic_row = cur.execute(
        "SELECT version_num FROM alembic_version LIMIT 1"
    ).fetchone() if alembic_table_exists else None
    has_app_tables = cur.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "AND name != 'alembic_version' LIMIT 1"
    ).fetchone() is not None
finally:
    conn.close()

if alembic_row is not None:
    print(f"[entrypoint] alembic at revision {alembic_row[0]} — running alembic upgrade head.")
    sys.exit(subprocess.call(["alembic", "upgrade", "head"]))

if has_app_tables:
    print(
        "[entrypoint] WARNING: DB has tables but no alembic_version row. "
        "Skipping auto-migration to avoid stamping the wrong revision. "
        "Run `docker compose exec backend alembic stamp <revision>` once to "
        "enable auto-upgrades (use the revision matching the current schema)."
    )
    sys.exit(0)

print("[entrypoint] Empty DB — running alembic upgrade head.")
sys.exit(subprocess.call(["alembic", "upgrade", "head"]))
PY

exec python -m src.backend.create_flask_application
