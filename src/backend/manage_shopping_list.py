"""
Shopping list endpoints.
"""

from flask import Blueprint, jsonify, request, g
from sqlalchemy import func

from src.backend.contribution_scores import award_contribution_event
from src.backend.create_flask_application import require_auth
from src.backend.initialize_database_schema import Product, ShoppingListItem
from src.backend.normalize_product_names import (
    canonicalize_product_identity,
    find_matching_product,
    get_product_display_name,
)

shopping_list_bp = Blueprint("shopping_list", __name__, url_prefix="/shopping-list")


def _serialize_item(item: ShoppingListItem) -> dict:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "name": item.name,
        "category": item.category,
        "quantity": item.quantity,
        "status": item.status,
        "source": item.source,
        "note": item.note,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@shopping_list_bp.route("", methods=["GET"])
@require_auth
def list_shopping_items():
    session = g.db_session
    status = request.args.get("status", "").strip().lower()

    query = session.query(ShoppingListItem)
    if status:
        query = query.filter(ShoppingListItem.status == status)

    items = query.order_by(
        ShoppingListItem.status.asc(),
        ShoppingListItem.created_at.desc(),
    ).all()

    return jsonify({
        "items": [_serialize_item(item) for item in items],
        "count": len(items),
        "open_count": session.query(ShoppingListItem).filter(ShoppingListItem.status == "open").count(),
        "purchased_count": session.query(ShoppingListItem).filter(ShoppingListItem.status == "purchased").count(),
    }), 200


@shopping_list_bp.route("/items", methods=["POST"])
@require_auth
def add_shopping_item():
    session = g.db_session
    data = request.get_json(silent=True) or {}

    raw_name = (data.get("name") or data.get("product_name") or "").strip()
    if not raw_name:
        return jsonify({"error": "Item name is required"}), 400

    name, category = canonicalize_product_identity(raw_name, data.get("category", "other"))
    quantity = float(data.get("quantity") or 1)
    source = (data.get("source") or "manual").strip().lower()
    note = (data.get("note") or "").strip() or None

    product = None
    product_id = data.get("product_id")
    if product_id:
        product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        product = find_matching_product(session, name, category)

    existing = (
        session.query(ShoppingListItem)
        .filter(ShoppingListItem.status == "open")
        .filter(func.lower(ShoppingListItem.name) == name.lower())
        .filter(func.lower(func.coalesce(ShoppingListItem.category, "other")) == category)
        .first()
    )
    if existing:
        existing.quantity += quantity
        if note and not existing.note:
            existing.note = note
        if source and not existing.source:
            existing.source = source
        if product and not existing.product_id:
            existing.product_id = product.id
        if product:
            existing.name = get_product_display_name(product)
        session.commit()
        return jsonify({"item": _serialize_item(existing), "merged": True}), 200

    item = ShoppingListItem(
        product_id=product.id if product else None,
        user_id=getattr(getattr(g, "current_user", None), "id", None),
        name=get_product_display_name(product) if product else name,
        category=category,
        quantity=quantity,
        status="open",
        source=source,
        note=note,
    )
    session.add(item)
    session.flush()
    award_contribution_event(
        session,
        user_id=getattr(getattr(g, "current_user", None), "id", None),
        event_type="shopping_item_added",
        description=f"Added {item.name} to the shopping list",
        subject_type="shopping_item",
        subject_id=item.id,
        dedupe_minutes=360,
        metadata={"source": source},
    )
    session.commit()
    return jsonify({"item": _serialize_item(item), "merged": False}), 201


@shopping_list_bp.route("/items/<int:item_id>", methods=["PUT"])
@require_auth
def update_shopping_item(item_id):
    session = g.db_session
    item = session.query(ShoppingListItem).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Shopping list item not found"}), 404

    data = request.get_json(silent=True) or {}
    previous_status = item.status
    if "name" in data:
        next_name, next_category = canonicalize_product_identity(
            data["name"],
            data.get("category", item.category),
        )
        item.name = next_name
        item.category = next_category
    elif "category" in data:
        _next_name, next_category = canonicalize_product_identity(item.name, data["category"])
        item.category = next_category
    if "quantity" in data:
        item.quantity = float(data["quantity"])
    if "status" in data:
        item.status = str(data["status"]).strip().lower() or item.status
    if "note" in data:
        item.note = (data["note"] or "").strip() or None

    if previous_status != "purchased" and item.status == "purchased":
        award_contribution_event(
            session,
            user_id=getattr(getattr(g, "current_user", None), "id", None),
            event_type="shopping_item_purchased",
            description=f"Marked {item.name} as bought",
            subject_type="shopping_item",
            subject_id=item.id,
            dedupe_minutes=360,
        )

    session.commit()
    return jsonify({"item": _serialize_item(item)}), 200


@shopping_list_bp.route("/items/<int:item_id>", methods=["DELETE"])
@require_auth
def delete_shopping_item(item_id):
    session = g.db_session
    item = session.query(ShoppingListItem).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Shopping list item not found"}), 404

    session.delete(item)
    session.commit()
    return jsonify({"message": "Shopping list item deleted"}), 200
