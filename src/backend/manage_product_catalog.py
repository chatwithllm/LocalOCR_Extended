"""
Step 13: Create Product Catalog Management
============================================
PROMPT Reference: Phase 4, Step 13

CRUD endpoints for the product catalog. Handles duplicate detection,
price tracking, store associations, and search/autocomplete.
"""

import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, or_

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.contribution_scores import meaningful_text_change
from src.backend.enrich_product_names import maybe_enrich_product, product_needs_review, should_enrich_product_name
from src.backend.initialize_database_schema import (
    Inventory, InventoryAdjustment, Product, ProductSnapshot, PriceHistory, ReceiptItem, Purchase, Store, TelegramReceipt
)
from src.backend.normalize_product_names import canonicalize_product_identity, get_product_display_name

logger = logging.getLogger(__name__)

products_bp = Blueprint("products", __name__, url_prefix="/products")


def _require_admin():
    current_user = getattr(g, "current_user", None)
    if not current_user or current_user.role != "admin":
        return jsonify({"error": "Admin access required"}), 403
    return None


def _merge_products(session, keeper: Product, duplicate: Product):
    """Move references from duplicate to keeper, then delete duplicate."""
    if keeper.id == duplicate.id:
        return keeper

    receipt_items = session.query(ReceiptItem).filter_by(product_id=duplicate.id).all()
    for item in receipt_items:
        item.product_id = keeper.id

    price_rows = session.query(PriceHistory).filter_by(product_id=duplicate.id).all()
    for row in price_rows:
        row.product_id = keeper.id

    adjustments = session.query(InventoryAdjustment).filter_by(product_id=duplicate.id).all()
    for adjustment in adjustments:
        adjustment.product_id = keeper.id

    from src.backend.initialize_database_schema import Inventory

    duplicate_inventory = session.query(Inventory).filter_by(product_id=duplicate.id).first()
    keeper_inventory = session.query(Inventory).filter_by(product_id=keeper.id).first()
    if duplicate_inventory and keeper_inventory:
        keeper_inventory.quantity += duplicate_inventory.quantity or 0
        if keeper_inventory.threshold is None:
            keeper_inventory.threshold = duplicate_inventory.threshold
        if not keeper_inventory.location:
            keeper_inventory.location = duplicate_inventory.location
        if keeper_inventory.updated_by is None:
            keeper_inventory.updated_by = duplicate_inventory.updated_by
        session.delete(duplicate_inventory)
    elif duplicate_inventory:
        duplicate_inventory.product_id = keeper.id

    session.delete(duplicate)
    return keeper


def _get_product_receipt_links(session, product_id: int, limit: int = 3) -> list[dict]:
    """Return recent receipt links for a product."""
    rows = (
        session.query(ReceiptItem, Purchase, Store, TelegramReceipt)
        .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .outerjoin(TelegramReceipt, TelegramReceipt.purchase_id == Purchase.id)
        .filter(ReceiptItem.product_id == product_id)
        .order_by(Purchase.date.desc(), ReceiptItem.id.desc())
        .limit(limit)
        .all()
    )

    seen_purchase_ids = set()
    links = []
    for _receipt_item, purchase, store, telegram_record in rows:
        if not purchase or purchase.id in seen_purchase_ids:
            continue
        seen_purchase_ids.add(purchase.id)
        links.append({
            "receipt_id": purchase.id,
            "date": purchase.date.strftime("%Y-%m-%d") if purchase.date else None,
            "store": store.name if store else "Unknown",
            "source": "telegram" if telegram_record and not str(telegram_record.telegram_user_id).startswith("upload") else "upload",
            "status": telegram_record.status if telegram_record else "processed",
            "total": purchase.total_amount,
        })
    return links


def _get_latest_product_price(session, product_id: int) -> dict | None:
    row = (
        session.query(PriceHistory, Purchase, Store)
        .outerjoin(Purchase, Purchase.date == PriceHistory.date)
        .outerjoin(Store, Store.id == PriceHistory.store_id)
        .filter(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
        .first()
    )
    if not row:
        return None

    price_row, purchase, store = row
    return {
        "price": price_row.price,
        "date": price_row.date.strftime("%Y-%m-%d") if price_row.date else None,
        "store": store.name if store else None,
    }


def _latest_snapshot_for_product(session, product_id: int) -> dict | None:
    snapshot = (
        session.query(ProductSnapshot)
        .filter(ProductSnapshot.product_id == product_id)
        .order_by(ProductSnapshot.created_at.desc(), ProductSnapshot.id.desc())
        .first()
    )
    if not snapshot:
        return None
    return {
        "id": snapshot.id,
        "image_url": f"/product-snapshots/{snapshot.id}/image",
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def _serialize_product(session, product: Product) -> dict:
    recent_receipts = _get_product_receipt_links(session, product.id)
    latest_price = _get_latest_product_price(session, product.id)
    inventory_item = session.query(Inventory).filter_by(product_id=product.id).first()
    is_low = bool(inventory_item and (inventory_item.manual_low or (inventory_item.threshold and inventory_item.quantity < inventory_item.threshold)))
    return {
        "id": product.id,
        "name": get_product_display_name(product),
        "raw_name": product.raw_name or product.name,
        "display_name": product.display_name or product.name,
        "brand": product.brand,
        "size": product.size,
        "default_unit": product.default_unit or "each",
        "default_size_label": product.default_size_label,
        "enrichment_confidence": product.enrichment_confidence,
        "review_state": product.review_state or ("pending" if product_needs_review(product) else "resolved"),
        "reviewed_at": product.reviewed_at.isoformat() if product.reviewed_at else None,
        "category": product.category,
        "barcode": product.barcode,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "recent_receipts": recent_receipts,
        "last_purchase_date": recent_receipts[0]["date"] if recent_receipts else None,
        "latest_price": latest_price,
        "latest_snapshot": _latest_snapshot_for_product(session, product.id),
        "inventory_item_id": inventory_item.id if inventory_item else None,
        "inventory_quantity": inventory_item.quantity if inventory_item else None,
        "inventory_threshold": inventory_item.threshold if inventory_item else None,
        "manual_low": bool(inventory_item.manual_low) if inventory_item else False,
        "is_low": is_low,
    }


@products_bp.route("", methods=["GET"])
@require_auth
def list_products():
    """List all products with pagination."""
    session = g.db_session
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    category = request.args.get("category")

    query = session.query(Product)
    if category:
        query = query.filter(Product.category == category)

    total = query.count()
    products = query.order_by(func.coalesce(Product.display_name, Product.name)).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "products": [_serialize_product(session, p) for p in products],
        "total": total,
        "page": page,
        "per_page": per_page,
    }), 200


@products_bp.route("/search", methods=["GET"])
@require_auth
def search_products():
    """Search products by name (case-insensitive partial match)."""
    session = g.db_session
    q = request.args.get("q", "").strip()

    if not q or len(q) < 2:
        return jsonify({"error": "Query must be at least 2 characters", "results": []}), 400

    results = session.query(Product).filter(
        or_(
            Product.name.ilike(f"%{q}%"),
            func.coalesce(Product.display_name, "").ilike(f"%{q}%"),
            func.coalesce(Product.raw_name, "").ilike(f"%{q}%"),
        )
    ).order_by(func.coalesce(Product.display_name, Product.name)).limit(20).all()

    return jsonify({
        "query": q,
        "results": [_serialize_product(session, p) for p in results],
        "count": len(results),
    }), 200


@products_bp.route("/create", methods=["POST"])
@require_write_access
def create_product():
    """Add a new product to the catalog."""
    session = g.db_session
    data = request.get_json(silent=True)

    if not data or not data.get("name"):
        return jsonify({"error": "Product name is required"}), 400

    name, category = canonicalize_product_identity(data["name"], data.get("category", "other"))

    # Check for duplicates
    existing = (
        session.query(Product)
        .filter(func.lower(Product.name) == name.lower())
        .filter(func.lower(func.coalesce(Product.category, "other")) == category)
        .first()
    )
    if existing:
        return jsonify({
            "error": "Product already exists",
            "product": {"id": existing.id, "name": existing.name, "category": existing.category},
        }), 409

    product = Product(
        name=name,
        raw_name=data["name"],
        display_name=name,
        review_state="pending" if should_enrich_product_name(data["name"], category) else "resolved",
        category=category,
        barcode=data.get("barcode"),
    )
    session.add(product)
    session.flush()
    session.commit()

    return jsonify({
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "barcode": product.barcode,
    }), 201


@products_bp.route("/<int:product_id>/update", methods=["PUT"])
@require_write_access
def update_product(product_id):
    """Update an existing product."""
    session = g.db_session
    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    data = request.get_json(silent=True) or {}
    previous_name = product.display_name or product.name
    previous_category = product.category or "other"
    if "name" in data or "category" in data:
        next_name, next_category = canonicalize_product_identity(
            data.get("name", product.name),
            data.get("category", product.category),
        )
    else:
        next_name, next_category = product.name, product.category

    merge_target = (
        session.query(Product)
        .filter(Product.id != product.id)
        .filter(func.lower(Product.name) == next_name.lower())
        .filter(func.lower(func.coalesce(Product.category, "other")) == next_category)
        .first()
    )

    meaningful_name_update = "name" in data and meaningful_text_change(previous_name, next_name)
    meaningful_category_update = "category" in data and meaningful_text_change(previous_category, next_category)

    if meaningful_name_update:
        product.name = next_name
        product.raw_name = data["name"]
        product.display_name = next_name
        product.review_state = "resolved"
        product.reviewed_at = datetime.now(timezone.utc)
        product.reviewed_by_id = getattr(getattr(g, "current_user", None), "id", None)
    if meaningful_category_update:
        product.category = next_category
    if "barcode" in data:
        product.barcode = data["barcode"]
    if "default_unit" in data:
        next_unit = str(data.get("default_unit") or "each").strip().lower() or "each"
        product.default_unit = next_unit
    if "default_size_label" in data:
        next_size_label = str(data.get("default_size_label") or "").strip()
        product.default_size_label = next_size_label or None

    if merge_target and (meaningful_name_update or meaningful_category_update):
        if product.barcode and not merge_target.barcode:
            merge_target.barcode = product.barcode
        if product.default_unit and not merge_target.default_unit:
            merge_target.default_unit = product.default_unit
        if product.default_size_label and not merge_target.default_size_label:
            merge_target.default_size_label = product.default_size_label
        product = _merge_products(session, merge_target, product)
        product.review_state = "resolved"
        product.reviewed_at = datetime.now(timezone.utc)
        product.reviewed_by_id = getattr(getattr(g, "current_user", None), "id", None)
    session.commit()

    return jsonify({
        "id": product.id,
        "name": get_product_display_name(product),
        "raw_name": product.raw_name or product.name,
        "display_name": product.display_name or product.name,
        "category": product.category,
        "barcode": product.barcode,
        "default_unit": product.default_unit or "each",
        "default_size_label": product.default_size_label,
        "merged": bool(merge_target),
    }), 200


@products_bp.route("/review-queue", methods=["GET"])
@require_auth
def review_queue():
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    session = g.db_session
    status = (request.args.get("status") or "pending").strip().lower()
    limit = min(max(request.args.get("limit", 50, type=int), 1), 200)

    products = session.query(Product).order_by(Product.created_at.desc()).all()
    items = []
    for product in products:
        derived_state = product.review_state or ("pending" if product_needs_review(product) else "resolved")
        if status != "all" and derived_state != status:
            continue
        if status == "pending" and not product_needs_review(product) and product.review_state not in {None, "pending"}:
            continue
        serialized = _serialize_product(session, product)
        serialized["suggested_review"] = product_needs_review(product)
        items.append(serialized)
        if len(items) >= limit:
            break

    return jsonify({
        "items": items,
        "count": len(items),
    }), 200


@products_bp.route("/review-queue/enhance", methods=["POST"])
@require_write_access
def bulk_enhance_review_queue():
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    session = g.db_session
    data = request.get_json(silent=True) or {}
    limit = min(max(int(data.get("limit", 10) or 10), 1), 50)
    provider = (data.get("provider") or "gemini").strip().lower()
    if provider != "gemini":
        return jsonify({"error": "Only Gemini is supported right now"}), 400

    products = session.query(Product).order_by(Product.created_at.desc()).all()
    updated = []
    for product in products:
        if not product_needs_review(product):
            continue
        before = product.display_name or product.name
        maybe_enrich_product(session, product, force=True)
        after = product.display_name or product.name
        if after != before or product.enrichment_confidence:
            product.review_state = "resolved" if product.enrichment_confidence else "pending"
            product.reviewed_at = datetime.now(timezone.utc) if product.review_state == "resolved" else product.reviewed_at
            product.reviewed_by_id = getattr(getattr(g, "current_user", None), "id", None) if product.review_state == "resolved" else product.reviewed_by_id
            updated.append(_serialize_product(session, product))
        if len(updated) >= limit:
            break

    session.commit()
    return jsonify({"updated": updated, "count": len(updated)}), 200


@products_bp.route("/<int:product_id>/enhance", methods=["POST"])
@require_write_access
def enhance_product(product_id):
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    session = g.db_session
    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    maybe_enrich_product(session, product, force=True)
    if product.enrichment_confidence:
        product.review_state = "resolved"
        product.reviewed_at = datetime.now(timezone.utc)
        product.reviewed_by_id = getattr(getattr(g, "current_user", None), "id", None)
    else:
        product.review_state = "pending"
    session.commit()
    return jsonify({"product": _serialize_product(session, product)}), 200


@products_bp.route("/<int:product_id>/review-status", methods=["PUT"])
@require_write_access
def update_review_status(product_id):
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    session = g.db_session
    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    data = request.get_json(silent=True) or {}
    review_state = (data.get("review_state") or "").strip().lower()
    if review_state not in {"pending", "resolved", "dismissed"}:
        return jsonify({"error": "review_state must be pending, resolved, or dismissed"}), 400

    product.review_state = review_state
    product.reviewed_at = datetime.now(timezone.utc)
    if review_state == "resolved":
        if product_needs_review(product) and not product.enrichment_confidence:
            return jsonify({"error": "Make a meaningful fix before resolving this product"}), 400
        product.reviewed_by_id = getattr(getattr(g, "current_user", None), "id", None)
    session.commit()
    return jsonify({"product": _serialize_product(session, product)}), 200


@products_bp.route("/<int:product_id>", methods=["DELETE"])
@require_write_access
def delete_product(product_id):
    """Remove a product from the catalog."""
    session = g.db_session
    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    session.delete(product)
    session.commit()

    return jsonify({"message": f"Product '{product.name}' deleted"}), 200


@products_bp.route("/<int:product_id>/price-history", methods=["GET"])
@require_auth
def get_product_price_history(product_id):
    """Get price history for a specific product."""
    session = g.db_session
    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    prices = session.query(PriceHistory).filter_by(
        product_id=product_id
    ).order_by(PriceHistory.date.desc()).limit(50).all()

    price_values = [p.price for p in prices]

    return jsonify({
        "product_id": product_id,
        "product_name": product.name,
        "prices": [
            {
                "price": p.price,
                "store_id": p.store_id,
                "date": p.date.strftime("%Y-%m-%d") if p.date else None,
            }
            for p in prices
        ],
        "avg_price": round(sum(price_values) / len(price_values), 2) if price_values else None,
        "min_price": min(price_values) if price_values else None,
        "max_price": max(price_values) if price_values else None,
    }), 200
