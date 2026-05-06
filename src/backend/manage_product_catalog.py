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
    """Move references from duplicate to keeper, then delete duplicate.

    Transfers brand / barcode / enrichment / display_name to keeper when
    keeper has none — so a freshly-typed "Onions Red" inheriting an
    image-bearing "Red Onions" duplicate keeps the image.
    """
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

    # Reparent product snapshots (the source-of-truth for product images)
    # so the keeper inherits any image that was attached to the duplicate.
    from src.backend.initialize_database_schema import ProductSnapshot
    session.query(ProductSnapshot).filter_by(product_id=duplicate.id).update(
        {"product_id": keeper.id}, synchronize_session=False
    )

    # Reparent shopping_list_items.product_id (nullable FK) — otherwise
    # PRAGMA foreign_keys=ON aborts the duplicate.delete with a FK
    # constraint violation.
    from src.backend.initialize_database_schema import ShoppingListItem
    session.query(ShoppingListItem).filter_by(product_id=duplicate.id).update(
        {"product_id": keeper.id}, synchronize_session=False
    )

    # Field-level upgrade: keeper "wins" identity, but inherits richer
    # metadata from duplicate when keeper's slot is empty.
    if not keeper.brand and duplicate.brand:
        keeper.brand = duplicate.brand
    if not keeper.barcode and duplicate.barcode:
        keeper.barcode = duplicate.barcode
    if not keeper.display_name and duplicate.display_name:
        keeper.display_name = duplicate.display_name
    if not keeper.size and duplicate.size:
        keeper.size = duplicate.size
    if not keeper.default_unit and duplicate.default_unit:
        keeper.default_unit = duplicate.default_unit
    if not keeper.default_size_label and duplicate.default_size_label:
        keeper.default_size_label = duplicate.default_size_label
    if keeper.enrichment_confidence is None and duplicate.enrichment_confidence is not None:
        keeper.enrichment_confidence = duplicate.enrichment_confidence
        keeper.enriched_at = duplicate.enriched_at

    from src.backend.initialize_database_schema import Inventory

    # Inventory has no unique constraint on product_id, so the duplicate
    # may have multiple rows. Process each: if keeper has a row at the
    # same location, merge quantities; else reparent the duplicate row.
    duplicate_inventories = session.query(Inventory).filter_by(product_id=duplicate.id).all()
    for dup_inv in duplicate_inventories:
        keeper_inv = (
            session.query(Inventory)
            .filter_by(product_id=keeper.id, location=dup_inv.location)
            .first()
        )
        if keeper_inv is None:
            # No keeper row at this location — reparent
            dup_inv.product_id = keeper.id
            continue
        # Merge quantities + carry over missing fields
        keeper_inv.quantity = (keeper_inv.quantity or 0) + (dup_inv.quantity or 0)
        if keeper_inv.threshold is None:
            keeper_inv.threshold = dup_inv.threshold
        if not keeper_inv.location:
            keeper_inv.location = dup_inv.location
        if keeper_inv.updated_by is None:
            keeper_inv.updated_by = dup_inv.updated_by
        if keeper_inv.expires_at is None and dup_inv.expires_at is not None:
            keeper_inv.expires_at = dup_inv.expires_at
        session.delete(dup_inv)

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
    if snapshot is None:
        # Fall back to a sibling product with the same canonical name (any category).
        product = session.query(Product).filter_by(id=product_id).first()
        if product:
            canonical_name, _ = canonicalize_product_identity(product.name)
            sibling_ids = [
                row.id
                for row in session.query(Product.id)
                .filter(
                    Product.id != product_id,
                    func.lower(func.coalesce(Product.display_name, Product.name)) == canonical_name.lower(),
                )
                .all()
            ]
            if sibling_ids:
                snapshot = (
                    session.query(ProductSnapshot)
                    .filter(ProductSnapshot.product_id.in_(sibling_ids))
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
        "is_regular_use": bool(getattr(product, "is_regular_use", False) or False),
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


@products_bp.route("/<int:product_id>", methods=["GET"])
@require_auth
def get_product(product_id):
    session = g.db_session
    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404
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


@products_bp.route("/auto-dedup-tokens", methods=["POST"])
@require_write_access
def auto_dedup_products_by_token_key():
    """Backfill: merge products that share a sorted-token fingerprint.

    Groups Products by (token_key, normalized category). When a group
    has 2+ rows, picks the keeper as the row with richest metadata
    (image > enriched > earliest id) and merges the rest into it via
    `_merge_products`. Same-tokens-different-category pairs are NEVER
    merged.

    Idempotent — running again finds no new groups (every duplicate
    becomes the same product after first run).

    Returns: { merged: N, scanned: M, groups: [{keeper_id, dropped_ids[]}] }
    """
    from src.backend.normalize_product_names import (
        normalize_product_category,
        product_token_key,
    )
    from src.backend.initialize_database_schema import ProductSnapshot

    session = g.db_session
    products = session.query(Product).order_by(Product.id.asc()).all()

    # Group by (token_key, category). product_token_key returns None for
    # single-token names — those are skipped (cannot safely auto-merge).
    buckets: dict[tuple, list[Product]] = {}
    for p in products:
        key = product_token_key(p.name)
        if not key and p.display_name:
            key = product_token_key(p.display_name)
        if not key:
            continue
        cat = normalize_product_category(p.category)
        buckets.setdefault((key, cat), []).append(p)

    # Pre-fetch which product ids have at least one snapshot — used to
    # bias keeper selection toward the row that already has an image.
    product_ids = [p.id for p in products]
    has_image_ids: set[int] = set()
    if product_ids:
        for (pid,) in (
            session.query(ProductSnapshot.product_id)
            .filter(ProductSnapshot.product_id.in_(product_ids))
            .filter(ProductSnapshot.image_path.isnot(None))
            .filter(ProductSnapshot.image_path != "")
            .distinct()
            .all()
        ):
            has_image_ids.add(pid)

    def _keeper_score(p: Product) -> tuple:
        # Higher tuple wins. Image presence is dominant.
        return (
            1 if p.id in has_image_ids else 0,
            1 if p.enriched_at else 0,
            1 if p.brand else 0,
            1 if p.display_name else 0,
            -p.id,  # earlier id wins on ties
        )

    merged = 0
    groups_log: list[dict] = []
    failed_groups: list[dict] = []
    for (_key, _cat), group in buckets.items():
        if len(group) < 2:
            continue
        ranked = sorted(group, key=_keeper_score, reverse=True)
        keeper = ranked[0]
        dropped_ids: list[int] = []
        # Try each merge in its own savepoint so a single bad pair
        # doesn't fail the whole backfill (and surface a 500). Failed
        # pairs are reported in `failed_groups` for visibility.
        for dup in ranked[1:]:
            try:
                with session.begin_nested():
                    _merge_products(session, keeper, dup)
                dropped_ids.append(dup.id)
                merged += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Auto-dedup merge failed: keeper=%s drop=%s err=%s",
                    keeper.id, dup.id, exc,
                )
                failed_groups.append({
                    "keeper_id": keeper.id,
                    "drop_id": dup.id,
                    "error": str(exc)[:200],
                })
        if dropped_ids:
            groups_log.append({
                "keeper_id": keeper.id,
                "keeper_name": keeper.name,
                "dropped_ids": dropped_ids,
            })

    if merged:
        session.commit()

    return jsonify({
        "merged": merged,
        "scanned": len(products),
        "groups": groups_log,
        "failed": failed_groups,
    }), 200
