# src/backend/manage_kitchen.py
"""Kitchen view aggregator and product categorization.

Pure functions only — no Flask request context. Endpoint layer lives in
`manage_kitchen_endpoint.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

FREQUENCY_WINDOW_DAYS = 90
FREQUENT_LIMIT = 12
CATEGORY_LIMIT = 50

DEFAULT_CATEGORIES = ["Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other"]

CATEGORY_EMOJI = {
    "Produce": "🥬",
    "Meat": "🥩",
    "Dairy": "🥛",
    "Bakery": "🍞",
    "Pantry": "🥫",
    "Other": "🧴",
}

# Raw Product.category values that map into each bucket. Lowercased
# substring match — first hit wins, evaluated in DEFAULT_CATEGORIES order.
_CATEGORY_KEYWORDS = {
    "Produce": ("produce", "vegetable", "veggie", "fruit"),
    "Meat":    ("meat", "poultry", "chicken", "beef", "pork", "seafood", "fish"),
    "Dairy":   ("dairy", "milk", "cheese", "yogurt", "butter"),
    "Bakery":  ("bakery", "bread", "pastry", "cake"),
    "Pantry":  ("pantry", "snack", "beverage", "drink", "spice", "condiment",
                "grain", "rice", "pasta", "cereal", "canned", "frozen"),
}


def category_for_product(product) -> str:
    """Map a Product (or anything with a `.category` string attribute) to one
    of DEFAULT_CATEGORIES. Unknown / missing raw values fall back to "Other"."""
    raw = getattr(product, "category", None) or ""
    lowered = str(raw).strip().lower()
    if not lowered:
        return "Other"
    for bucket in DEFAULT_CATEGORIES:
        if bucket == "Other":
            continue
        keywords = _CATEGORY_KEYWORDS.get(bucket, ())
        for kw in keywords:
            if kw in lowered:
                return bucket
    return "Other"


from sqlalchemy import func

from src.backend.initialize_database_schema import (
    Product, ProductSnapshot, Purchase, ReceiptItem,
    ShoppingListItem, ShoppingSession,
)


def get_kitchen_catalog(session, *, now=None) -> dict:
    """Return catalog grid + on-list product ids in one shape.

    Shape:
        {
          "frequent": [<ProductTile>, ...],
          "categories": {
            "Produce": [<ProductTile>, ...],
            "Meat":    [...], "Dairy": [...], "Bakery": [...],
            "Pantry":  [...], "Other": [...],
          },
          "on_list_product_ids": [<int>, ...]
        }

    ProductTile shape:
        {"product_id": int, "name": str, "category": str,
         "image_url": str | None, "fallback_emoji": str,
         "purchase_count": int, "_latest_snapshot_id": int | None}
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=FREQUENCY_WINDOW_DAYS)

    snapshot_subq = (
        session.query(
            ProductSnapshot.product_id.label("product_id"),
            func.max(ProductSnapshot.id).label("snapshot_id"),
        )
        .filter(ProductSnapshot.product_id.isnot(None))
        .group_by(ProductSnapshot.product_id)
        .subquery()
    )

    count_subq = (
        session.query(
            ReceiptItem.product_id.label("product_id"),
            func.count(ReceiptItem.id).label("purchase_count"),
        )
        .join(Purchase, Purchase.id == ReceiptItem.purchase_id)
        .filter(Purchase.date >= cutoff)
        .group_by(ReceiptItem.product_id)
        .subquery()
    )

    rows = (
        session.query(
            Product,
            snapshot_subq.c.snapshot_id,
            count_subq.c.purchase_count,
        )
        .outerjoin(snapshot_subq, snapshot_subq.c.product_id == Product.id)
        .outerjoin(count_subq, count_subq.c.product_id == Product.id)
        .all()
    )

    categories = {cat: [] for cat in DEFAULT_CATEGORIES}
    all_tiles = []
    for product, snapshot_id, count in rows:
        bucket = category_for_product(product)
        emoji = CATEGORY_EMOJI.get(bucket, CATEGORY_EMOJI["Other"])
        image_url = (
            f"/product-snapshots/{snapshot_id}/image" if snapshot_id else None
        )
        tile = {
            "product_id": product.id,
            "name": product.display_name or product.name,
            "category": bucket,
            "image_url": image_url,
            "fallback_emoji": emoji,
            "purchase_count": int(count or 0),
            "_latest_snapshot_id": snapshot_id,
        }
        categories[bucket].append(tile)
        all_tiles.append(tile)

    for tiles in categories.values():
        tiles.sort(key=lambda t: (-t["purchase_count"], t["name"]))
        del tiles[CATEGORY_LIMIT:]

    purchased = [t for t in all_tiles if t["purchase_count"] > 0]
    purchased.sort(key=lambda t: (-t["purchase_count"], t["name"]))
    frequent = purchased[:FREQUENT_LIMIT]

    active = (
        session.query(ShoppingSession.id)
        .filter(ShoppingSession.status == "active")
        .all()
    )
    active_ids = [s.id for s in active]
    on_list = []
    if active_ids:
        on_list = [
            row[0]
            for row in session.query(ShoppingListItem.product_id)
            .filter(
                ShoppingListItem.shopping_session_id.in_(active_ids),
                ShoppingListItem.product_id.isnot(None),
                ShoppingListItem.status.in_(["open", "skipped"]),
            )
            .distinct()
            .all()
        ]

    return {
        "frequent": frequent,
        "categories": categories,
        "on_list_product_ids": on_list,
    }
