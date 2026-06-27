"""
Global unified search — GET /api/search?q=<term>

Fans out to inventory, product catalog, and receipts simultaneously
and returns up to 5 hits from each source.
"""

import logging
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, or_

from src.backend.create_flask_application import require_auth
from src.backend.initialize_database_schema import (
    Inventory,
    Product,
    Purchase,
    ReceiptItem,
    Store,
)

logger = logging.getLogger(__name__)

search_bp = Blueprint("search", __name__, url_prefix="/api/search")

_LIMIT = 5


@search_bp.route("", methods=["GET"])
@require_auth
def unified_search():
    """Search inventory, products, and receipts in one call."""
    session = g.db_session
    q = request.args.get("q", "").strip()

    if not q or len(q) < 2:
        return jsonify({"error": "Query must be at least 2 characters"}), 400

    pattern = f"%{q}%"

    # ── Inventory hits ────────────────────────────────────────────────────────
    inv_rows = (
        session.query(Inventory)
        .join(Product)
        .filter(
            Inventory.is_active_window.is_(True),
            or_(Product.is_non_product.is_(None), Product.is_non_product.is_(False)),
            or_(
                Product.name.ilike(pattern),
                func.coalesce(Product.display_name, "").ilike(pattern),
                func.coalesce(Product.brand, "").ilike(pattern),
                func.coalesce(Product.category, "").ilike(pattern),
            ),
        )
        .order_by(Product.name)
        .limit(_LIMIT)
        .all()
    )

    inventory_hits = []
    for row in inv_rows:
        p = row.product
        expiry = None
        if row.expires_at:
            expiry = row.expires_at.strftime("%Y-%m-%d")
        elif row.expires_at_system:
            expiry = row.expires_at_system.strftime("%Y-%m-%d")
        inventory_hits.append({
            "id": row.id,
            "product_id": p.id,
            "product_name": p.display_name or p.name,
            "brand": p.brand,
            "category": p.category,
            "quantity": row.quantity,
            "unit": p.default_unit,
            "location": row.location,
            "expiry_date": expiry,
        })

    # ── Product catalog hits ──────────────────────────────────────────────────
    prod_rows = (
        session.query(Product)
        .filter(
            or_(Product.is_non_product.is_(None), Product.is_non_product.is_(False)),
            or_(
                Product.name.ilike(pattern),
                func.coalesce(Product.display_name, "").ilike(pattern),
                func.coalesce(Product.brand, "").ilike(pattern),
                func.coalesce(Product.category, "").ilike(pattern),
            ),
        )
        .order_by(Product.name)
        .limit(_LIMIT)
        .all()
    )

    product_hits = []
    for p in prod_rows:
        # Up to 3 most recent receipts for this product
        recent_rows = (
            session.query(ReceiptItem, Purchase, Store)
            .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
            .join(Store, Purchase.store_id == Store.id)
            .filter(ReceiptItem.product_id == p.id)
            .order_by(Purchase.date.desc())
            .limit(3)
            .all()
        )
        recent_receipts = []
        last_date = None
        last_price = None
        for ri, pu, st in recent_rows:
            date_str = pu.date.strftime("%Y-%m-%d") if pu.date else None
            if last_date is None:
                last_date = date_str
                last_price = ri.unit_price
            recent_receipts.append({
                "receipt_id": pu.id,
                "store": st.name,
                "date": date_str,
                "total": pu.total_amount,
            })
        product_hits.append({
            "id": p.id,
            "product_name": p.display_name or p.name,
            "brand": p.brand,
            "category": p.category,
            "last_purchase_date": last_date,
            "last_purchase_price": last_price,
            "recent_receipts": recent_receipts,
        })

    # ── Receipt hits ──────────────────────────────────────────────────────────
    # Match on store name OR receipt line-item product name/brand
    receipt_rows = (
        session.query(Purchase)
        .join(Store, Purchase.store_id == Store.id)
        .filter(Store.name.ilike(pattern))
        .order_by(Purchase.date.desc())
        .limit(_LIMIT)
        .all()
    )

    # Also match on line-item product names
    item_purchase_ids = (
        session.query(ReceiptItem.purchase_id)
        .join(Product, ReceiptItem.product_id == Product.id)
        .filter(
            or_(
                Product.name.ilike(pattern),
                func.coalesce(Product.display_name, "").ilike(pattern),
                func.coalesce(Product.brand, "").ilike(pattern),
            )
        )
        .distinct()
        .limit(20)
        .all()
    )
    item_purchase_ids = [r[0] for r in item_purchase_ids]

    if item_purchase_ids:
        extra = (
            session.query(Purchase)
            .filter(Purchase.id.in_(item_purchase_ids))
            .order_by(Purchase.date.desc())
            .limit(_LIMIT)
            .all()
        )
        seen = {r.id for r in receipt_rows}
        for r in extra:
            if r.id not in seen and len(receipt_rows) < _LIMIT:
                receipt_rows.append(r)
                seen.add(r.id)

    receipt_hits = []
    for pu in receipt_rows[:_LIMIT]:
        store_name = pu.store.name if pu.store else "Unknown store"
        date_str = pu.date.strftime("%Y-%m-%d") if pu.date else None

        # Matched line items
        matched = (
            session.query(ReceiptItem)
            .join(Product, ReceiptItem.product_id == Product.id)
            .filter(
                ReceiptItem.purchase_id == pu.id,
                or_(
                    Product.name.ilike(pattern),
                    func.coalesce(Product.display_name, "").ilike(pattern),
                    func.coalesce(Product.brand, "").ilike(pattern),
                ),
            )
            .limit(5)
            .all()
        )
        matched_items = [
            {
                "name": (ri.product.display_name or ri.product.name) if ri.product else "?",
                "price": ri.unit_price,
            }
            for ri in matched
        ]

        receipt_hits.append({
            "purchase_id": pu.id,
            "store": store_name,
            "date": date_str,
            "total": pu.total_amount,
            "matched_items": matched_items,
        })

    return jsonify({
        "query": q,
        "results": {
            "inventory": inventory_hits,
            "products": product_hits,
            "receipts": receipt_hits,
        },
    }), 200
