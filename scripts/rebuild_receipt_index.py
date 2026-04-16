#!/usr/bin/env python3
"""
Rebuild <receipts_root>/_index.txt from the current database.

Use cases:
- After restoring a backup that doesn't carry the index file
- After mass-deleting failed receipts
- After any manual file rename / cleanup that left the index stale

Usage (from inside the container):
    docker exec localocr-extended-backend python /app/scripts/rebuild_receipt_index.py

Usage (locally, with the venv activated):
    python scripts/rebuild_receipt_index.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `src.backend.*` importable when run directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backend.initialize_database_schema import (  # noqa: E402
    TelegramReceipt,
    Purchase,
    Store,
)
from src.backend.receipt_filename_index import (  # noqa: E402
    index_path,
    rewrite_index_from_records,
)


def _db_url() -> str:
    return os.getenv("DATABASE_URL") or "sqlite:////data/db/localocr_extended.db"


def main() -> int:
    engine = create_engine(_db_url())
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    try:
        rows = (
            session.query(TelegramReceipt, Purchase, Store)
            .outerjoin(Purchase, TelegramReceipt.purchase_id == Purchase.id)
            .outerjoin(Store, Store.id == Purchase.store_id)
            .filter(TelegramReceipt.image_path.isnot(None))
            .filter(TelegramReceipt.image_path != "")
            .order_by(Purchase.date.asc().nullslast(), TelegramReceipt.id.asc())
            .all()
        )
        records = []
        for receipt, purchase, store in rows:
            records.append({
                "image_path": receipt.image_path,
                "store": store.name if store else None,
                "date": purchase.date if purchase else None,
                "total": purchase.total_amount if purchase else None,
                "purchase_id": purchase.id if purchase else None,
            })
        written = rewrite_index_from_records(records)
        print(f"Rebuilt index: {written} entries → {index_path()}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
