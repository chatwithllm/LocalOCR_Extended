#!/usr/bin/env python3
"""One-shot Stores cleanup: re-canonicalize names, merge dupes, flag artifacts.

Walks every row in ``stores``:

  1. Compute canonical name via ``canonicalize_store_name``.
  2. If ``is_payment_artifact`` matches the row, set the flag.
  3. If a different Store row already exists under the canonical name,
     repoint Purchase / PriceHistory / ProductSnapshot FKs to that row,
     then delete the dupe. Pick the lower-id row as the survivor.
  4. Else just rename the row to its canonical name.

Run inside the backend container:
  docker compose exec backend python /app/scripts/cleanup_stores.py --dry-run
  docker compose exec backend python /app/scripts/cleanup_stores.py --apply

Idempotent — safe to re-run.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict

# Allow running as a script (no -m) by injecting /app into sys.path.
sys.path.insert(0, "/app")

from sqlalchemy import func

from src.backend.initialize_database_schema import (
    PriceHistory,
    ProductSnapshot,
    Purchase,
    Store,
    initialize_database,
)
from src.backend.normalize_store_names import (
    canonicalize_store_name,
    is_payment_artifact,
)


_engine, _SessionFactory = initialize_database()


def SessionLocal():
    return _SessionFactory()


def _repoint_fks(session, dupe_id: int, survivor_id: int) -> dict:
    counts = {}
    for model, label in (
        (Purchase, "purchases"),
        (PriceHistory, "price_history"),
        (ProductSnapshot, "product_snapshots"),
    ):
        n = (
            session.query(model)
            .filter(model.store_id == dupe_id)
            .update({model.store_id: survivor_id}, synchronize_session=False)
        )
        counts[label] = n
    return counts


def cleanup(apply: bool) -> int:
    session = SessionLocal()
    try:
        stores = session.query(Store).order_by(Store.id.asc()).all()
        # Group dupes by canonical name (lowercased) so the survivor is
        # deterministic — pick the smallest id within each group.
        by_canon: dict[str, list[Store]] = defaultdict(list)
        for s in stores:
            canon = canonicalize_store_name(s.name)
            by_canon[canon.lower()].append(s)

        rename_count = 0
        artifact_count = 0
        merge_count = 0
        fk_moves = defaultdict(int)
        deletes = 0

        for canon_lower, group in by_canon.items():
            group.sort(key=lambda s: s.id)
            survivor = group[0]
            canonical_name = canonicalize_store_name(survivor.name)

            # Rename survivor if different.
            if survivor.name != canonical_name:
                print(f"  RENAME store id={survivor.id}: {survivor.name!r} -> {canonical_name!r}")
                if apply:
                    survivor.name = canonical_name
                rename_count += 1

            # Flag artifact if any row in the group looks like one.
            should_flag = any(
                is_payment_artifact(s.name) or is_payment_artifact(canonicalize_store_name(s.name))
                for s in group
            )
            if should_flag and not survivor.is_payment_artifact:
                print(f"  FLAG artifact store id={survivor.id} name={canonical_name!r}")
                if apply:
                    survivor.is_payment_artifact = True
                artifact_count += 1

            # Merge dupes into survivor.
            for dupe in group[1:]:
                print(
                    f"  MERGE dupe id={dupe.id} name={dupe.name!r} -> survivor id={survivor.id} ({canonical_name!r})"
                )
                if apply:
                    moves = _repoint_fks(session, dupe.id, survivor.id)
                else:
                    moves = {
                        "purchases": session.query(Purchase).filter(Purchase.store_id == dupe.id).count(),
                        "price_history": session.query(PriceHistory).filter(PriceHistory.store_id == dupe.id).count(),
                        "product_snapshots": session.query(ProductSnapshot).filter(ProductSnapshot.store_id == dupe.id).count(),
                    }
                for k, v in moves.items():
                    fk_moves[k] += v
                    if v:
                        print(f"      moved {v} {k} rows")
                if apply:
                    session.delete(dupe)
                deletes += 1
                merge_count += 1

        if apply:
            session.commit()

        print()
        print("Summary:")
        print(f"  groups examined        : {len(by_canon)}")
        print(f"  store rows renamed     : {rename_count}")
        print(f"  artifact flags set     : {artifact_count}")
        print(f"  dupe stores merged     : {merge_count}")
        print(f"  dupe stores deleted    : {deletes}")
        print(f"  FK rows repointed      :")
        for k in ("purchases", "price_history", "product_snapshots"):
            print(f"    {k:<22}: {fk_moves[k]}")
        if not apply:
            print("\n(dry-run — no changes committed; pass --apply to commit)")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="report only, no commit")
    g.add_argument("--apply", action="store_true", help="commit changes")
    args = p.parse_args()
    return cleanup(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
