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
    ShoppingListItem, ShoppingSession, PriceHistory, Inventory,
)


def _frequent_tiles(session, *, now, exclude_ids):
    """Top frequent purchases (last FREQUENCY_WINDOW_DAYS), as ProductTiles,
    excluding any product ids in `exclude_ids`. Used to seed suggestions."""
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
        session.query(Product, snapshot_subq.c.snapshot_id, count_subq.c.purchase_count)
        .join(count_subq, count_subq.c.product_id == Product.id)
        .outerjoin(snapshot_subq, snapshot_subq.c.product_id == Product.id)
        .filter(Product.is_non_product.isnot(True))
        .all()
    )
    tiles = []
    for product, snapshot_id, count in rows:
        if product.id in exclude_ids:
            continue
        if not count:
            continue
        bucket = category_for_product(product)
        tiles.append({
            "product_id": product.id,
            "name": product.display_name or product.name,
            "category": bucket,
            "image_url": f"/product-snapshots/{snapshot_id}/image" if snapshot_id else None,
            "fallback_emoji": CATEGORY_EMOJI.get(bucket, CATEGORY_EMOJI["Other"]),
            "purchase_count": int(count or 0),
        })
    tiles.sort(key=lambda t: (-t["purchase_count"], t["name"]))
    return tiles[:8]


def get_kitchen_essentials(session, *, now=None) -> dict:
    """Return the user-curated essentials grid plus (only when empty) a
    frequency-seeded suggestion list.

    Shape:
        {
          "essentials": [
            {"product_id", "name", "category", "image_url", "fallback_emoji",
             "quantity": float, "has_backup": bool, "on_list": bool,
             "latest_unit_price": float | None},
            ...
          ],
          "suggested": [<ProductTile>, ...]   # [] once any essential exists
        }
    """
    now = now or datetime.now(timezone.utc)

    snapshot_subq = (
        session.query(
            ProductSnapshot.product_id.label("product_id"),
            func.max(ProductSnapshot.id).label("snapshot_id"),
        )
        .filter(ProductSnapshot.product_id.isnot(None))
        .group_by(ProductSnapshot.product_id)
        .subquery()
    )
    qty_subq = (
        session.query(
            Inventory.product_id.label("product_id"),
            func.coalesce(func.sum(Inventory.quantity), 0.0).label("qty"),
        )
        .group_by(Inventory.product_id)
        .subquery()
    )
    latest_price_subq = (
        session.query(
            PriceHistory.product_id.label("product_id"),
            func.max(PriceHistory.id).label("price_history_id"),
        )
        .filter(PriceHistory.product_id.isnot(None))
        .group_by(PriceHistory.product_id)
        .subquery()
    )

    rows = (
        session.query(
            Product,
            snapshot_subq.c.snapshot_id,
            qty_subq.c.qty,
            PriceHistory.price.label("latest_price"),
        )
        .outerjoin(snapshot_subq, snapshot_subq.c.product_id == Product.id)
        .outerjoin(qty_subq, qty_subq.c.product_id == Product.id)
        .outerjoin(latest_price_subq, latest_price_subq.c.product_id == Product.id)
        .outerjoin(PriceHistory, PriceHistory.id == latest_price_subq.c.price_history_id)
        .filter(Product.is_essential.is_(True))
        .filter(Product.is_non_product.isnot(True))
        .all()
    )

    current_ids = [
        s.id for s in session.query(ShoppingSession.id)
        .filter(ShoppingSession.status.in_(("active", "ready_to_bill")))
        .all()
    ]
    on_list_ids = set()
    if current_ids:
        on_list_ids = {
            row[0] for row in session.query(ShoppingListItem.product_id)
            .filter(
                ShoppingListItem.shopping_session_id.in_(current_ids),
                ShoppingListItem.product_id.isnot(None),
                ShoppingListItem.status.in_(["open", "skipped"]),
            )
            .distinct()
            .all()
        }

    essentials = []
    for product, snapshot_id, qty, latest_price in rows:
        bucket = category_for_product(product)
        essentials.append({
            "product_id": product.id,
            "name": product.display_name or product.name,
            "category": bucket,
            "image_url": f"/product-snapshots/{snapshot_id}/image" if snapshot_id else None,
            "fallback_emoji": CATEGORY_EMOJI.get(bucket, CATEGORY_EMOJI["Other"]),
            "quantity": float(qty or 0.0),
            "has_backup": bool(product.has_backup),
            "on_list": product.id in on_list_ids,
            "latest_unit_price": float(latest_price) if latest_price is not None else None,
        })
    essentials.sort(key=lambda t: t["name"].lower())

    suggested = []
    if not essentials:
        suggested = _frequent_tiles(session, now=now, exclude_ids=set())

    return {"essentials": essentials, "suggested": suggested}
