"""
Step 14: Implement Inventory Tracking
=======================================
PROMPT Reference: Phase 4, Step 14

CRUD endpoints for household inventory. Every change publishes an MQTT
event for real-time sync. Tracks user attribution for audit trail.

MQTT Topic: home/grocery/inventory/{product_id}
"""

import logging
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func

from src.backend.active_inventory import get_active_inventory_cutoff, rebuild_active_inventory, record_inventory_adjustment
from src.backend.contribution_scores import (
    award_contribution_event,
    cancel_pending_low_event,
    confirm_low_peer,
    meaningful_text_change,
    reverse_low_confirmation,
)
from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.enrich_product_names import should_enrich_product_name
from src.backend.initialize_database_schema import Inventory, PriceHistory, Product
from src.backend.normalize_product_names import canonicalize_product_identity, get_product_display_name
from src.backend.initialize_database_schema import Purchase, ReceiptItem, Store, TelegramReceipt

logger = logging.getLogger(__name__)

inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")


def _is_item_low(item: Inventory) -> bool:
    return bool(item.manual_low or (item.threshold and item.quantity < item.threshold))


def _get_latest_price(session, product_id: int) -> dict | None:
    price_row = (
        session.query(PriceHistory)
        .filter(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
        .first()
    )
    if not price_row:
        return None
    return {
        "price": price_row.price,
        "date": price_row.date.strftime("%Y-%m-%d") if price_row.date else None,
    }


def _get_product_receipt_links(session, product_id: int, limit: int = 3) -> list[dict]:
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


@inventory_bp.route("", methods=["GET"])
@require_auth
def list_inventory():
    """View current household inventory."""
    session = g.db_session
    location = request.args.get("location")
    low_stock = request.args.get("low_stock", "false").lower() == "true"

    rebuild_active_inventory(session)
    session.flush()

    query = session.query(Inventory).join(Product).filter(Inventory.is_active_window.is_(True))

    if location:
        query = query.filter(Inventory.location == location)

    if low_stock:
        query = query.filter(
            (Inventory.manual_low.is_(True)) |
            ((Inventory.threshold.isnot(None)) & (Inventory.quantity < Inventory.threshold))
        )

    items = query.order_by(Product.name).all()

    return jsonify({
        "inventory": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": get_product_display_name(item.product),
                "raw_name": item.product.raw_name or item.product.name,
                "size": item.product.size,
                "brand": item.product.brand,
                "category": item.product.category,
                "latest_price": _get_latest_price(session, item.product_id),
                "recent_receipts": _get_product_receipt_links(session, item.product_id),
                "quantity": item.quantity,
                "location": item.location,
                "threshold": item.threshold,
                "manual_low": bool(item.manual_low),
                "is_low": _is_item_low(item),
                "updated_by": item.updated_by,
                "last_updated": item.last_updated.isoformat() if item.last_updated else None,
            }
            for item in items
        ],
        "count": len(items),
        "window_start": get_active_inventory_cutoff().strftime("%Y-%m-%d"),
        "window_label": "Current month + previous month",
    }), 200


@inventory_bp.route("/add-item", methods=["POST"])
@require_write_access
def add_item():
    """Add a product to inventory with quantity."""
    session = g.db_session
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "JSON body required"}), 400

    # Accept either product_id or product_name
    product_id = data.get("product_id")
    product_name = data.get("product_name")
    quantity = data.get("quantity", 1)
    location = data.get("location", "Pantry")
    threshold = data.get("threshold")
    category_hint = data.get("category", "other")
    size_hint = (data.get("size") or "").strip() or None

    if not product_id and not product_name:
        return jsonify({"error": "product_id or product_name required"}), 400

    # Find or create product
    if product_id:
        product = session.query(Product).filter_by(id=product_id).first()
        if not product:
            return jsonify({"error": f"Product {product_id} not found"}), 404
        if size_hint and meaningful_text_change(product.size, size_hint):
            product.size = size_hint
        normalized_category = (category_hint or "").strip().lower()
        if normalized_category and meaningful_text_change(product.category, normalized_category):
            product.category = normalized_category
    else:
        product_name, category = canonicalize_product_identity(
            product_name,
            category_hint,
        )
        product = (
            session.query(Product)
            .filter(func.lower(Product.name) == product_name.lower())
            .filter(func.lower(func.coalesce(Product.category, "other")) == category)
            .first()
        )
        if not product:
            product = Product(
                name=product_name,
                raw_name=data.get("product_name"),
                display_name=product_name,
                category=category,
                size=size_hint,
            )
            product.review_state = "pending" if should_enrich_product_name(data.get("product_name"), category) else "resolved"
            session.add(product)
            session.flush()
        elif size_hint and meaningful_text_change(product.size, size_hint):
            product.size = size_hint

    user_id = getattr(g, "current_user", None)
    user_id = user_id.id if user_id else None

    existing = session.query(Inventory).filter_by(product_id=product.id).first()
    if existing:
        existing.location = location
        existing.updated_by = user_id
        if threshold is not None:
            existing.threshold = threshold
        item = existing
    else:
        item = Inventory(
            product_id=product.id,
            quantity=0,
            location=location,
            threshold=threshold,
            manual_low=False,
            is_active_window=True,
            updated_by=user_id,
        )
        session.add(item)

    record_inventory_adjustment(session, product.id, float(quantity or 0), user_id, "manual_add")
    rebuild_active_inventory(session)
    session.commit()

    # Publish MQTT event
    _publish_update(product, item)

    return jsonify({
        "id": item.id,
        "product_id": product.id,
        "product_name": product.name,
        "product_display_name": get_product_display_name(product),
        "quantity": item.quantity,
        "location": item.location,
        "threshold": item.threshold,
        "manual_low": bool(item.manual_low),
    }), 201


@inventory_bp.route("/<int:item_id>/consume", methods=["PUT"])
@require_write_access
def consume_item(item_id):
    """Decrease quantity by 1 (or specified amount)."""
    session = g.db_session
    data = request.get_json(silent=True) or {}
    amount = data.get("amount", 1)

    item = session.query(Inventory).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Inventory item not found"}), 404

    user_id = getattr(g, "current_user", None)
    user_id = user_id.id if user_id else None
    actual_amount = min(float(item.quantity or 0), float(amount or 0))
    if actual_amount > 0:
        item.updated_by = user_id
        record_inventory_adjustment(session, item.product_id, -actual_amount, user_id, "consume")
        rebuild_active_inventory(session)
    session.commit()

    product = session.query(Product).filter_by(id=item.product_id).first()
    _publish_update(product, item)

    # Check if below threshold
    if _is_item_low(item):
        _trigger_low_stock_alert(product, item)

    return jsonify({
        "id": item.id,
        "product_name": product.name if product else None,
        "quantity": item.quantity,
        "consumed": actual_amount,
        "manual_low": bool(item.manual_low),
        "is_low": _is_item_low(item),
    }), 200


@inventory_bp.route("/<int:item_id>/update", methods=["PUT"])
@require_write_access
def update_item(item_id):
    """Set quantity directly."""
    session = g.db_session
    data = request.get_json(silent=True) or {}

    item = session.query(Inventory).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Inventory item not found"}), 404
    previous_location = item.location
    previous_threshold = item.threshold

    if "quantity" in data:
        target_quantity = max(0, float(data["quantity"]))
        delta = target_quantity - float(item.quantity or 0)
        if delta != 0:
            record_inventory_adjustment(
                session,
                item.product_id,
                delta,
                getattr(getattr(g, "current_user", None), "id", None),
                "update",
            )
    if "location" in data:
        item.location = data["location"]
    if "threshold" in data:
        item.threshold = data["threshold"]

    user_id = getattr(g, "current_user", None)
    item.updated_by = user_id.id if user_id else None
    if "location" in data and meaningful_text_change(previous_location, item.location):
        award_contribution_event(
            session,
            user_id=item.updated_by,
            event_type="inventory_location_updated",
            description=f"Updated location for {get_product_display_name(item.product)} to {item.location}",
            subject_type="inventory",
            subject_id=item.id,
            dedupe_minutes=720,
            metadata={"from": previous_location, "to": item.location, "threshold_before": previous_threshold},
        )
    rebuild_active_inventory(session)
    session.commit()

    product = session.query(Product).filter_by(id=item.product_id).first()
    _publish_update(product, item)

    return jsonify({
        "id": item.id,
        "product_name": product.name if product else None,
        "quantity": item.quantity,
        "location": item.location,
        "threshold": item.threshold,
        "manual_low": bool(item.manual_low),
    }), 200


@inventory_bp.route("/products/<int:product_id>/low-status", methods=["PUT"])
@require_write_access
def set_low_status(product_id):
    """Manually mark or clear a product as low without changing quantity."""
    session = g.db_session
    data = request.get_json(silent=True) or {}
    manual_low = bool(data.get("manual_low", True))

    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    user_id = getattr(getattr(g, "current_user", None), "id", None)
    item = session.query(Inventory).filter_by(product_id=product_id).first()
    previous_manual_low = bool(item.manual_low) if item else False
    if not item:
        item = Inventory(
            product_id=product_id,
            quantity=0,
            location="Pantry",
            threshold=None,
            manual_low=manual_low,
            is_active_window=manual_low,
            updated_by=user_id,
        )
        session.add(item)
    else:
        item.manual_low = manual_low
        item.updated_by = user_id

    if previous_manual_low != manual_low:
        if manual_low:
            award_contribution_event(
                session,
                user_id=user_id,
                event_type="inventory_low_marked",
                description=f"Marked {get_product_display_name(product)} as low",
                subject_type="product",
                subject_id=product.id,
                status="pending_validation",
                dedupe_minutes=720,
                metadata={"manual_low": True},
            )
        else:
            cancel_pending_low_event(session, product_id=product.id)
            reverse_low_confirmation(session, product_id=product.id)
            award_contribution_event(
                session,
                user_id=user_id,
                event_type="inventory_low_cleared",
                description=f"Cleared low flag for {get_product_display_name(product)}",
                subject_type="product",
                subject_id=product.id,
                dedupe_minutes=720,
                metadata={"manual_low": False},
            )

    rebuild_active_inventory(session)
    session.commit()

    item = session.query(Inventory).filter_by(product_id=product_id).first()
    _publish_update(product, item)
    if _is_item_low(item):
        _trigger_low_stock_alert(product, item)

    return jsonify({
        "product_id": product.id,
        "inventory_id": item.id if item else None,
        "product_name": get_product_display_name(product),
        "manual_low": bool(item.manual_low if item else manual_low),
        "is_low": _is_item_low(item) if item else manual_low,
    }), 200


@inventory_bp.route("/products/<int:product_id>/confirm-low", methods=["POST"])
@require_write_access
def confirm_low_status(product_id):
    """Allow a second household member to confirm a low-stock call."""
    session = g.db_session
    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    result = confirm_low_peer(
        session,
        confirmer_user_id=getattr(getattr(g, "current_user", None), "id", None),
        product_id=product_id,
        product_name=get_product_display_name(product),
    )
    if result.get("error"):
        session.rollback()
        return jsonify({"error": result["error"]}), 400
    session.commit()
    return jsonify({
        "status": result.get("status", "peer_confirmed"),
        "product_id": product_id,
        "product_name": get_product_display_name(product),
    }), 200


@inventory_bp.route("/<int:item_id>", methods=["DELETE"])
@require_write_access
def remove_item(item_id):
    """Remove an item from inventory."""
    session = g.db_session
    item = session.query(Inventory).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Inventory item not found"}), 404

    product = session.query(Product).filter_by(id=item.product_id).first()
    current_quantity = float(item.quantity or 0)
    if current_quantity > 0:
        record_inventory_adjustment(
            session,
            item.product_id,
            -current_quantity,
            getattr(getattr(g, "current_user", None), "id", None),
            "delete",
        )
    rebuild_active_inventory(session)
    session.commit()

    return jsonify({
        "message": f"'{product.name if product else 'Item'}' removed from inventory",
    }), 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _publish_update(product, item):
    """Publish MQTT event for inventory change."""
    try:
        from src.backend.publish_mqtt_events import publish_inventory_update
        publish_inventory_update(
            product_id=product.id,
            name=product.name,
            quantity=item.quantity,
            location=item.location or "Pantry",
            updated_by=str(item.updated_by or "system"),
        )
    except Exception as e:
        logger.warning(f"Failed to publish MQTT inventory update: {e}")


def _trigger_low_stock_alert(product, item):
    """Publish low-stock alert via MQTT."""
    try:
        from src.backend.publish_mqtt_events import publish_low_stock_alert
        publish_low_stock_alert(
            product_id=product.id,
            product_name=product.name,
            current_qty=item.quantity,
            threshold=item.threshold,
        )
    except Exception as e:
        logger.warning(f"Failed to publish low-stock alert: {e}")
