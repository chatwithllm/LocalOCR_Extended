#!/usr/bin/env python3
"""Re-encrypt stored API keys with a new FERNET_SECRET_KEY.

Use this after restoring a backup onto a host that has a *different*
FERNET_SECRET_KEY than the one the backup was encrypted with. Without
rekeying, the ai_model_configs.api_key_encrypted rows are unreadable
on the new host because Fernet decryption would fail.

Usage:
  rekey_encrypted_credentials.py --old-key <FERNET> [--new-key <FERNET>] [options]

The old key is REQUIRED (you must know what the rows were encrypted with).
The new key defaults to the FERNET_SECRET_KEY environment variable, which
on a running container is the value the app is currently configured to use.

Options:
  --db-path PATH      SQLite path (default: $DB_PATH or /data/db/localocr_extended.db)
  --dry-run           Report what would change, do not write
  --allow-passthrough Skip rows that already decrypt cleanly under the new key
                      (this is the default; flag is accepted for clarity)
  --json              Emit a machine-readable summary on stdout

Exit codes:
  0   success (or dry-run completed without unrecoverable rows)
  1   argument / setup error
  2   one or more rows could not be decrypted with the old key
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Optional

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        "error: cryptography.Fernet is required. Run inside the backend "
        "container or `pip install cryptography`.\n"
    )
    raise SystemExit(1) from exc


DEFAULT_DB = os.getenv("DB_PATH", "/data/db/localocr_extended.db")


def _build_fernet(label: str, key: str) -> Fernet:
    cleaned = (key or "").strip()
    if not cleaned:
        raise SystemExit(f"error: {label} is empty")
    try:
        return Fernet(cleaned.encode())
    except (ValueError, TypeError) as exc:
        raise SystemExit(f"error: {label} is not a valid Fernet key: {exc}")


def _try_decrypt(fernet: Fernet, token: str) -> Optional[str]:
    try:
        return fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-encrypt stored API keys under a new FERNET_SECRET_KEY."
    )
    parser.add_argument(
        "--old-key",
        default=os.getenv("OLD_FERNET_SECRET_KEY", ""),
        help="Fernet key the rows are currently encrypted with. "
        "Defaults to $OLD_FERNET_SECRET_KEY.",
    )
    parser.add_argument(
        "--new-key",
        default=os.getenv("FERNET_SECRET_KEY", ""),
        help="Fernet key to re-encrypt with. Defaults to $FERNET_SECRET_KEY.",
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB,
        help=f"SQLite database path (default: {DEFAULT_DB}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes.")
    parser.add_argument(
        "--allow-passthrough",
        action="store_true",
        default=True,
        help="(default) Skip rows that already decrypt under the new key.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
    args = parser.parse_args(argv)

    if not args.old_key:
        parser.error("--old-key is required (or set $OLD_FERNET_SECRET_KEY)")
    if not args.new_key:
        parser.error("--new-key is required (or set $FERNET_SECRET_KEY)")

    old_fernet = _build_fernet("old key", args.old_key)
    new_fernet = _build_fernet("new key", args.new_key)

    if args.old_key.strip() == args.new_key.strip():
        summary = {
            "status": "noop",
            "reason": "old and new keys are identical",
            "scanned": 0,
            "rekeyed": 0,
            "already_new": 0,
            "failed": 0,
            "dry_run": args.dry_run,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print("Old and new keys are identical — nothing to rekey.")
        return 0

    if not os.path.isfile(args.db_path):
        raise SystemExit(f"error: database not found at {args.db_path}")

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    # Tolerate older schemas that don't yet have ai_model_configs.
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "ai_model_configs" not in tables:
        summary = {
            "status": "ok",
            "scanned": 0,
            "rekeyed": 0,
            "already_new": 0,
            "failed": 0,
            "dry_run": args.dry_run,
            "note": "ai_model_configs table not present — nothing to rekey.",
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(summary["note"])
        return 0

    rows = conn.execute(
        "SELECT id, provider, name, api_key_encrypted "
        "FROM ai_model_configs "
        "WHERE api_key_encrypted IS NOT NULL AND api_key_encrypted != ''"
    ).fetchall()

    scanned = len(rows)
    rekeyed = 0
    already_new = 0
    failed: list[dict] = []
    updates: list[tuple[str, int]] = []

    for row in rows:
        rid = int(row["id"])
        token = row["api_key_encrypted"] or ""
        # If the row already decrypts under the NEW key, skip. This makes the
        # script safely idempotent: run it twice and the second pass is a no-op.
        if _try_decrypt(new_fernet, token) is not None:
            already_new += 1
            continue
        plaintext = _try_decrypt(old_fernet, token)
        if plaintext is None:
            failed.append(
                {
                    "id": rid,
                    "provider": row["provider"],
                    "name": row["name"],
                    "reason": "decrypt_failed_with_old_key",
                }
            )
            continue
        new_token = new_fernet.encrypt(plaintext.encode()).decode()
        updates.append((new_token, rid))
        rekeyed += 1

    if not args.dry_run and updates:
        conn.executemany(
            "UPDATE ai_model_configs SET api_key_encrypted = ? WHERE id = ?",
            updates,
        )
        conn.commit()

    conn.close()

    summary = {
        "status": "ok" if not failed else "partial",
        "scanned": scanned,
        "rekeyed": rekeyed,
        "already_new": already_new,
        "failed": len(failed),
        "failures": failed,
        "dry_run": args.dry_run,
        "db_path": args.db_path,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        mode = "(dry-run) " if args.dry_run else ""
        print(f"{mode}scanned={scanned} rekeyed={rekeyed} already_new={already_new} failed={len(failed)}")
        for fail in failed:
            print(f"  ✗ id={fail['id']} provider={fail['provider']} name={fail['name']} ({fail['reason']})")

    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
