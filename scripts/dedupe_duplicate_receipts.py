#!/usr/bin/env python3
"""Find and remove duplicate receipts that share (store, date, total).

Why: the existing file_hash-based duplicate check only catches
byte-identical re-uploads. In practice the same bill gets re-uploaded as
a freshly generated PDF (different bytes, different hash), so many
legitimate duplicates slip past. This script clusters purchases by
(store_id, date, total) — where "total" is summed from receipt_items so
it's independent of OCR header parsing — and collapses each cluster to
one canonical row.

Keep priority within a cluster:
  1. The row that has a BillMeta sidecar (bill properly classified)
  2. Else the oldest id (first captured)

Delete cascade (mirrors handle_receipt_upload.delete_receipt logic):
  - PriceHistory rows matching (product_id, store_id, date)
  - ReceiptItem rows for the purchase
  - TelegramReceipt rows linked to the purchase (+ image files on disk)
  - BillMeta, BillAllocation, CashTransaction sidecars
  - Purchase row itself

Usage:
  dedupe_duplicate_receipts.py                    # dry-run, human output
  dedupe_duplicate_receipts.py --apply            # actually delete
  dedupe_duplicate_receipts.py --json             # machine-readable report
  dedupe_duplicate_receipts.py --db-path PATH     # override DB location
  dedupe_duplicate_receipts.py --keep-images      # leave image files on disk

Exit codes:
  0  success (or dry-run with clusters found)
  1  argument / setup error
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from typing import Optional

logger = logging.getLogger("dedupe")

DEFAULT_DB = os.getenv("DB_PATH", "/data/db/localocr_extended.db")


def _find_clusters(conn: sqlite3.Connection) -> list[dict]:
    """Return clusters of purchases that share (store_id, date, rounded_total)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT p.id,
               p.store_id,
               p.date,
               COALESCE(s.name, '') AS store_name,
               ROUND(COALESCE(
                   (SELECT SUM(ri.quantity * ri.unit_price)
                      FROM receipt_items ri WHERE ri.purchase_id = p.id),
                   0
               ), 2) AS total,
               (SELECT COUNT(*) FROM bill_meta bm WHERE bm.purchase_id = p.id) AS has_bill_meta
          FROM purchases p
          LEFT JOIN stores s ON s.id = p.store_id
         ORDER BY p.id ASC
        """
    ).fetchall()

    buckets: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        key = (row["store_id"], row["date"], row["total"])
        buckets[key].append(row)

    clusters = []
    for (store_id, date, total), members in buckets.items():
        if len(members) < 2:
            continue
        # Skip zero-total clusters — these are usually cash transactions
        # or receipts with no items; two $0 rows on the same date are not
        # reliable evidence of duplication. Handle those manually.
        if not total or float(total) == 0.0:
            continue
        # Pick keeper: prefer bill_meta, then lowest id
        keeper = sorted(
            members,
            key=lambda r: (0 if r["has_bill_meta"] else 1, r["id"]),
        )[0]
        victims = [r for r in members if r["id"] != keeper["id"]]
        clusters.append(
            {
                "store_id": store_id,
                "store_name": members[0]["store_name"],
                "date": date,
                "total": total,
                "keeper_id": keeper["id"],
                "keeper_has_bill_meta": bool(keeper["has_bill_meta"]),
                "victim_ids": [r["id"] for r in victims],
            }
        )
    # Sort clusters by size desc then store/date for stable output
    clusters.sort(
        key=lambda c: (-len(c["victim_ids"]), c["store_name"], c["date"]),
    )
    return clusters


def _delete_purchase(conn: sqlite3.Connection, purchase_id: int, *, keep_images: bool) -> dict:
    """Delete a single purchase and its associated rows. Returns per-table counts."""
    counts = {
        "price_history": 0,
        "receipt_items": 0,
        "telegram_receipts": 0,
        "bill_meta": 0,
        "bill_allocations": 0,
        "cash_transactions": 0,
        "image_files_removed": 0,
    }

    # Collect receipt_items to figure out which PriceHistory rows to delete.
    purchase_row = conn.execute(
        "SELECT store_id, date FROM purchases WHERE id = ?", (purchase_id,)
    ).fetchone()
    if not purchase_row:
        return counts
    store_id = purchase_row["store_id"]
    date = purchase_row["date"]

    product_ids = [
        row["product_id"]
        for row in conn.execute(
            "SELECT product_id FROM receipt_items WHERE purchase_id = ? AND product_id IS NOT NULL",
            (purchase_id,),
        ).fetchall()
    ]
    if product_ids and store_id is not None:
        placeholders = ",".join("?" * len(product_ids))
        cur = conn.execute(
            f"DELETE FROM price_history WHERE product_id IN ({placeholders}) "
            f"AND store_id = ? AND date = ?",
            [*product_ids, store_id, date],
        )
        counts["price_history"] = cur.rowcount or 0

    # telegram_receipts — capture image paths first so we can remove files.
    image_paths = [
        row["image_path"]
        for row in conn.execute(
            "SELECT image_path FROM telegram_receipts WHERE purchase_id = ? AND image_path IS NOT NULL",
            (purchase_id,),
        ).fetchall()
    ]
    counts["telegram_receipts"] = conn.execute(
        "DELETE FROM telegram_receipts WHERE purchase_id = ?", (purchase_id,)
    ).rowcount or 0

    # Sidecars: bill_meta, bill_allocations, cash_transactions, receipt_items
    for table, col in (
        ("bill_meta", "bill_meta"),
        ("bill_allocations", "bill_allocations"),
        ("cash_transactions", "cash_transactions"),
        ("receipt_items", "receipt_items"),
    ):
        try:
            cur = conn.execute(
                f"DELETE FROM {table} WHERE purchase_id = ?", (purchase_id,)
            )
            counts[col] = cur.rowcount or 0
        except sqlite3.OperationalError:
            # Table may not exist on older schemas; skip silently.
            pass

    # The purchase row itself
    conn.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))

    # Remove orphaned image files unless the user opts out
    if not keep_images:
        for path in image_paths:
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                    counts["image_files_removed"] += 1
                except OSError as exc:
                    logger.warning("Could not remove image %s: %s", path, exc)

    return counts


def _format_human(clusters: list[dict], totals: dict, *, dry_run: bool) -> str:
    lines = []
    header = "DRY-RUN — no changes" if dry_run else "APPLY — changes committed"
    lines.append(f"=== dedupe_duplicate_receipts [{header}] ===")
    if not clusters:
        lines.append("No duplicate clusters found. Nothing to do.")
        return "\n".join(lines)

    lines.append(
        f"Found {len(clusters)} cluster(s) covering {totals['victim_count']} "
        f"duplicate purchase(s)."
    )
    lines.append("")
    for cluster in clusters:
        lines.append(
            f"  {cluster['store_name'] or '(no store)'} · {cluster['date']} · ${cluster['total']}"
        )
        marker = " (has bill_meta)" if cluster["keeper_has_bill_meta"] else ""
        lines.append(f"    keep:   purchase #{cluster['keeper_id']}{marker}")
        lines.append(
            f"    delete: {', '.join(f'#{vid}' for vid in cluster['victim_ids'])}"
        )
    lines.append("")
    lines.append("Totals:")
    for key, value in totals.items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", default=DEFAULT_DB, help=f"SQLite path (default: {DEFAULT_DB})")
    parser.add_argument("--apply", action="store_true", help="Commit the deletions (default is dry-run).")
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout.")
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="Skip removing image files for deleted receipts (default removes them).",
    )
    args = parser.parse_args(argv)

    if not os.path.isfile(args.db_path):
        sys.stderr.write(f"error: database not found at {args.db_path}\n")
        return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    try:
        clusters = _find_clusters(conn)
        totals = {
            "cluster_count": len(clusters),
            "victim_count": sum(len(c["victim_ids"]) for c in clusters),
            "price_history_rows_deleted": 0,
            "receipt_items_deleted": 0,
            "telegram_receipts_deleted": 0,
            "bill_meta_deleted": 0,
            "bill_allocations_deleted": 0,
            "cash_transactions_deleted": 0,
            "image_files_removed": 0,
        }

        if args.apply and clusters:
            for cluster in clusters:
                for victim_id in cluster["victim_ids"]:
                    result = _delete_purchase(conn, victim_id, keep_images=args.keep_images)
                    totals["price_history_rows_deleted"] += result["price_history"]
                    totals["receipt_items_deleted"] += result["receipt_items"]
                    totals["telegram_receipts_deleted"] += result["telegram_receipts"]
                    totals["bill_meta_deleted"] += result["bill_meta"]
                    totals["bill_allocations_deleted"] += result["bill_allocations"]
                    totals["cash_transactions_deleted"] += result["cash_transactions"]
                    totals["image_files_removed"] += result["image_files_removed"]
            conn.commit()

        if args.json:
            print(
                json.dumps(
                    {
                        "dry_run": not args.apply,
                        "clusters": clusters,
                        "totals": totals,
                    },
                    indent=2,
                )
            )
        else:
            print(_format_human(clusters, totals, dry_run=not args.apply))
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
