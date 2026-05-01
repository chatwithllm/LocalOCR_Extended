"""Nightly DB-layer backfill: download images for products with no
ProductSnapshot and persist as new snapshot rows tagged ``auto_fetch``.

Per-product commit so partial failures preserve previous successes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import not_

from src.backend.fetch_product_image import fetch_product_image
from src.backend.initialize_database_schema import (
    Product, ProductSnapshot, ReceiptItem, ShoppingListItem,
)
from src.backend.manage_product_snapshots import get_snapshot_root


logger = logging.getLogger(__name__)

RETRY_INTERVAL = timedelta(days=1)

_NON_PRODUCT_PATTERNS = frozenset({
    "fee", "fees", "charge", "charges", "service charge",
    "bag fee", "bag charge", "bottle deposit", "deposit",
    "tax", "taxes", "gst", "hst", "vat", "tip", "gratuity",
    "credit", "refund", "return", "rebate", "discount", "coupon",
    "savings", "promo", "promotion",
    "subtotal", "total", "balance", "amount due",
    "delivery", "shipping", "handling",
    "misc", "miscellaneous", "other", "unknown", "n/a",
})


def _is_meaningful_product(product) -> bool:
    name = ((product.display_name or product.name) or "").strip().lower()
    if not name or len(name) < 3:
        return False
    return not any(pat in name for pat in _NON_PRODUCT_PATTERNS)


def find_products_needing_images(session, max_products: int = 20) -> list[Product]:
    """Products with NO snapshot, referenced by receipt or shopping list,
    not attempted in the last RETRY_INTERVAL. Ordered by oldest-attempt-first."""
    cutoff = datetime.now(timezone.utc) - RETRY_INTERVAL

    has_snapshot_subq = (
        session.query(ProductSnapshot.product_id)
        .filter(ProductSnapshot.product_id.isnot(None))
        .distinct()
        .subquery()
    )
    receipts_subq = (
        session.query(ReceiptItem.product_id)
        .filter(ReceiptItem.product_id.isnot(None))
        .distinct()
        .subquery()
    )
    shopping_subq = (
        session.query(ShoppingListItem.product_id)
        .filter(ShoppingListItem.product_id.isnot(None))
        .distinct()
        .subquery()
    )

    query = (
        session.query(Product)
        .filter(not_(Product.id.in_(session.query(has_snapshot_subq.c.product_id))))
        .filter(
            Product.id.in_(session.query(receipts_subq.c.product_id))
            | Product.id.in_(session.query(shopping_subq.c.product_id))
        )
        .filter(
            (Product.last_image_fetch_attempt_at.is_(None))
            | (Product.last_image_fetch_attempt_at < cutoff)
        )
        .order_by(Product.last_image_fetch_attempt_at.asc().nullsfirst(),
                  Product.id.asc())
        .limit(max_products * 2)
    )
    products = query.all()
    return [p for p in products if _is_meaningful_product(p)][:max_products]


def backfill_images_for_products(session, products, *, provider: str = "auto") -> dict:
    """For each product: fetch image bytes, persist as ProductSnapshot row,
    update last_image_fetch_attempt_at. Per-product commit.

    provider: ``"auto"`` (gemini→openai fallback), ``"gemini"``, ``"openai"``.
    """
    fetched = 0
    failed = 0
    providers_used: dict[str, int] = {}
    for product in products:
        query_name = (product.display_name or product.name or "").strip()
        if not query_name:
            product.last_image_fetch_attempt_at = datetime.now(timezone.utc)
            session.commit()
            failed += 1
            continue
        try:
            data, prov_used = fetch_product_image(
                query_name, product.category, provider=provider,
            )
        except Exception as exc:
            logger.exception("fetch_product_image raised for %s: %s", product.id, exc)
            data, prov_used = None, None

        if data:
            now = datetime.now(timezone.utc)
            year_month = now.strftime("%Y/%m")
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{uuid4().hex[:8]}.jpg"
            save_dir = get_snapshot_root() / year_month
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / filename
            save_path.write_bytes(data)

            session.add(ProductSnapshot(
                product_id=product.id,
                source_context="auto_fetch",
                status="auto",
                image_path=str(save_path),
                captured_at=now,
            ))
            fetched += 1
            if prov_used:
                providers_used[prov_used] = providers_used.get(prov_used, 0) + 1
        else:
            failed += 1

        product.last_image_fetch_attempt_at = datetime.now(timezone.utc)
        session.commit()
    return {"fetched": fetched, "failed": failed, "providers_used": providers_used}
