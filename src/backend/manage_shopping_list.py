"""
Shopping list endpoints.
"""

import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import Blueprint, jsonify, request, g
from sqlalchemy import func, or_

from src.backend.contribution_scores import (
    award_contribution_event,
    confirm_recommendation_peer,
    finalize_recommendation_confirmation,
    meaningful_text_change,
    reverse_shopping_item_contributions,
    unfinalize_recommendation_confirmation,
)
from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import AccessLink, ContributionEvent, PriceHistory, Product, ShoppingListItem, Store
from src.backend.normalize_product_names import (
    canonicalize_product_identity,
    find_matching_product,
    get_product_display_name,
    normalize_product_category,
)
from src.backend.normalize_store_names import canonicalize_store_name

shopping_list_bp = Blueprint("shopping_list", __name__, url_prefix="/shopping-list")


def _hash_access_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def _public_base_url() -> str:
    import os
    return (os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/") or request.host_url.rstrip("/"))


def _create_share_link(created_by_id: int | None, expires_in_hours: int = 24):
    token = secrets.token_urlsafe(24)
    link = AccessLink(
        created_by_id=created_by_id,
        purpose="shopping_helper",
        token_hash=_hash_access_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        metadata_json=json.dumps({"scope": "shopping_helper"}),
    )
    g.db_session.add(link)
    g.db_session.flush()
    return token, link


def _get_valid_share_link(token: str):
    if not token:
        return None
    link = (
        g.db_session.query(AccessLink)
        .filter(
            AccessLink.token_hash == _hash_access_token(token),
            AccessLink.purpose == "shopping_helper",
        )
        .first()
    )
    if not link:
        return None
    if link.expires_at:
        now = datetime.now(timezone.utc)
        expires_at = link.expires_at
        if expires_at.tzinfo is None:
            now = now.replace(tzinfo=None)
        if expires_at < now:
            return None
    return link


def _ensure_pending_recommendation_event(session, item: ShoppingListItem):
    """Backfill a pending recommendation acceptance event when needed."""
    if not item or item.source != "recommendation" or not item.user_id:
        return

    existing_event = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.event_type == "recommendation_accepted",
            ContributionEvent.subject_type == "shopping_item",
            ContributionEvent.subject_id == item.id,
            ContributionEvent.status.in_(["pending_confirmation", "confirmed", "validated", "finalized"]),
        )
        .first()
    )
    if existing_event:
        return

    award_contribution_event(
        session,
        user_id=item.user_id,
        event_type="recommendation_accepted",
        description=f"Accepted recommendation for {item.name}",
        subject_type="shopping_item",
        subject_id=item.id,
        status="pending_confirmation",
        dedupe_minutes=60 * 24 * 30,
        metadata={"source": item.source, "product_id": item.product_id},
    )


def _serialize_item(item: ShoppingListItem) -> dict:
    latest_price = _latest_price_for_item(g.db_session, item)
    preferred_store = canonicalize_store_name(item.preferred_store) if item.preferred_store else None
    product = None
    if item.product_id:
        product = g.db_session.query(Product).filter_by(id=item.product_id).first()
    product_display_name = get_product_display_name(product) if product else None
    product_full_name = None
    if product:
        for candidate in [getattr(product, "raw_name", None), getattr(product, "name", None)]:
            text = str(candidate or "").strip()
            if text and text != str(product_display_name or "").strip():
                product_full_name = text
                break
    return {
        "id": item.id,
        "product_id": item.product_id,
        "name": item.name,
        "product_display_name": product_display_name,
        "product_full_name": product_full_name,
        "category": item.category,
        "quantity": item.quantity,
        "status": item.status,
        "source": item.source,
        "note": item.note,
        "preferred_store": preferred_store,
        "effective_store": preferred_store or (latest_price or {}).get("store"),
        "latest_price": latest_price,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _latest_price_for_item(session, item: ShoppingListItem) -> dict | None:
    if item.product_id:
        row = (
            session.query(PriceHistory, Store)
            .outerjoin(Store, Store.id == PriceHistory.store_id)
            .filter(PriceHistory.product_id == item.product_id)
            .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
            .first()
        )
        if row:
            price, store = row
            return {
                "price": float(price.price or 0),
                "store": store.name if store else None,
                "date": price.date.strftime("%Y-%m-%d") if price.date else None,
            }

    category = normalize_product_category(getattr(item, "category", None))
    product = None
    if item.product_id:
        product = session.query(Product).filter_by(id=item.product_id).first()

    candidate_names: set[str] = set()
    for candidate in [
        getattr(item, "name", None),
        getattr(product, "display_name", None) if product else None,
        getattr(product, "name", None) if product else None,
        getattr(product, "raw_name", None) if product else None,
    ]:
        text = str(candidate or "").strip()
        if text:
            candidate_names.add(text.lower())
            canonical_name, _ = canonicalize_product_identity(text, category)
            if canonical_name:
                candidate_names.add(canonical_name.lower())

    row = None
    if candidate_names:
        matching_products = (
            session.query(Product.id)
            .filter(func.lower(func.coalesce(Product.category, "other")) == category)
            .filter(
                or_(
                    func.lower(Product.name).in_(candidate_names),
                    func.lower(func.coalesce(Product.display_name, "")).in_(candidate_names),
                    func.lower(func.coalesce(Product.raw_name, "")).in_(candidate_names),
                )
            )
            .all()
        )
        matching_product_ids = [product_id for (product_id,) in matching_products]
        if matching_product_ids:
            row = (
                session.query(PriceHistory, Product, Store)
                .join(Product, Product.id == PriceHistory.product_id)
                .outerjoin(Store, Store.id == PriceHistory.store_id)
                .filter(PriceHistory.product_id.in_(matching_product_ids))
                .order_by(PriceHistory.date.desc(), PriceHistory.id.desc())
                .first()
            )

    if not row:
        return None
    price, _product, store = row
    return {
        "price": float(price.price or 0),
        "store": store.name if store else None,
        "date": price.date.strftime("%Y-%m-%d") if price.date else None,
    }


def _build_shopping_list_payload(session, *, status: str = "", helper_mode: bool = False):
    query = session.query(ShoppingListItem)
    if status:
        query = query.filter(ShoppingListItem.status == status)

    raw_items = query.order_by(
        ShoppingListItem.status.asc(),
        ShoppingListItem.created_at.desc(),
    ).all()
    items = [_serialize_item(item) for item in raw_items]
    open_items = [item for item in items if item["status"] == "open"]
    total_estimated_cost = round(sum((item.get("latest_price") or {}).get("price", 0) * float(item.get("quantity") or 0) for item in open_items), 2)
    store_totals = {}
    for item in open_items:
        latest_price = item.get("latest_price") or {}
        store_name = item.get("preferred_store") or latest_price.get("store")
        if not store_name:
            continue
        store_totals.setdefault(store_name, {"store": store_name, "estimated_total": 0.0, "item_count": 0})
        store_totals[store_name]["estimated_total"] += latest_price.get("price", 0) * float(item.get("quantity") or 0)
        store_totals[store_name]["item_count"] += 1
    suggested_stores = sorted(store_totals.values(), key=lambda row: (-row["item_count"], row["store"]))
    for store in suggested_stores:
        store["estimated_total"] = round(store["estimated_total"], 2)
    available_stores = sorted({
        canonicalize_store_name(store.name)
        for store in session.query(Store).all()
        if store.name
    })

    return {
        "items": items,
        "count": len(items),
        "open_count": session.query(ShoppingListItem).filter(ShoppingListItem.status == "open").count(),
        "purchased_count": session.query(ShoppingListItem).filter(ShoppingListItem.status == "purchased").count(),
        "estimated_total_cost": total_estimated_cost,
        "suggested_stores": suggested_stores,
        "available_stores": available_stores,
        "helper_mode": helper_mode,
    }


@shopping_list_bp.route("", methods=["GET"])
@require_auth
def list_shopping_items():
    session = g.db_session
    status = request.args.get("status", "").strip().lower()
    return jsonify(_build_shopping_list_payload(session, status=status)), 200


@shopping_list_bp.route("/share-link", methods=["POST"])
@require_write_access
def create_shopping_share_link():
    token, link = _create_share_link(getattr(getattr(g, "current_user", None), "id", None))
    g.db_session.commit()
    url = f"{_public_base_url()}/shopping-helper/{token}"
    return jsonify({
        "url": url,
        "qr_image_url": f"{_public_base_url()}/auth/qr-image?data={quote(url, safe='')}",
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
    }), 200


@shopping_list_bp.route("/shared/<token>", methods=["GET"])
def list_shared_shopping_items(token: str):
    link = _get_valid_share_link(token)
    if not link:
        return jsonify({"error": "Shopping helper link is invalid or expired"}), 404
    status = request.args.get("status", "").strip().lower()
    response = jsonify(_build_shopping_list_payload(g.db_session, status=status, helper_mode=True))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response, 200


@shopping_list_bp.route("/items", methods=["POST"])
@require_write_access
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
    preferred_store = canonicalize_store_name(data.get("preferred_store")) if data.get("preferred_store") else None

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
        if preferred_store and not existing.preferred_store:
            existing.preferred_store = preferred_store
            award_contribution_event(
                session,
                user_id=getattr(getattr(g, "current_user", None), "id", None),
                event_type="shopping_store_preference_set",
                description=f"Set store preference for {existing.name} to {preferred_store}",
                subject_type="shopping_item",
                subject_id=existing.id,
                dedupe_minutes=60 * 24 * 30,
            )
        if source and (not existing.source or existing.source == "manual"):
            existing.source = source
        if product and not existing.product_id:
            existing.product_id = product.id
        if product:
            existing.name = get_product_display_name(product)
        if source == "recommendation":
            _ensure_pending_recommendation_event(session, existing)
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
        preferred_store=preferred_store,
    )
    session.add(item)
    session.flush()
    if source == "recommendation":
        award_contribution_event(
            session,
            user_id=getattr(getattr(g, "current_user", None), "id", None),
            event_type="recommendation_accepted",
            description=f"Accepted recommendation for {item.name}",
            subject_type="shopping_item",
            subject_id=item.id,
            status="pending_confirmation",
            dedupe_minutes=360,
            metadata={"source": source, "product_id": item.product_id},
        )
    else:
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
@require_write_access
def update_shopping_item(item_id):
    session = g.db_session
    item = session.query(ShoppingListItem).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Shopping list item not found"}), 404

    data = request.get_json(silent=True) or {}
    previous_status = item.status
    previous_preferred_store = item.preferred_store
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
    if "preferred_store" in data:
        item.preferred_store = canonicalize_store_name(data["preferred_store"]) if data.get("preferred_store") else None
        if meaningful_text_change(previous_preferred_store, item.preferred_store) and not previous_preferred_store and item.preferred_store:
            award_contribution_event(
                session,
                user_id=getattr(getattr(g, "current_user", None), "id", None),
                event_type="shopping_store_preference_set",
                description=f"Set store preference for {item.name} to {item.preferred_store}",
                subject_type="shopping_item",
                subject_id=item.id,
                dedupe_minutes=60 * 24 * 30,
            )

    if previous_status != "purchased" and item.status == "purchased":
        finalize_recommendation_confirmation(session, shopping_item_id=item.id)
        award_contribution_event(
            session,
            user_id=getattr(getattr(g, "current_user", None), "id", None),
            event_type="shopping_item_purchased",
            description=f"Marked {item.name} as bought",
            subject_type="shopping_item",
            subject_id=item.id,
            dedupe_minutes=360,
        )
    elif previous_status == "purchased" and item.status != "purchased":
        unfinalize_recommendation_confirmation(session, shopping_item_id=item.id)

    session.commit()
    return jsonify({"item": _serialize_item(item)}), 200


@shopping_list_bp.route("/items/<int:item_id>", methods=["DELETE"])
@require_write_access
def delete_shopping_item(item_id):
    session = g.db_session
    item = session.query(ShoppingListItem).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Shopping list item not found"}), 404

    reverse_shopping_item_contributions(session, shopping_item_id=item.id)
    session.delete(item)
    session.commit()
    return jsonify({"message": "Shopping list item deleted"}), 200


@shopping_list_bp.route("/shared/<token>/items/<int:item_id>", methods=["PUT"])
def update_shared_shopping_item(token: str, item_id: int):
    link = _get_valid_share_link(token)
    if not link:
        return jsonify({"error": "Shopping helper link is invalid or expired"}), 404

    session = g.db_session
    item = session.query(ShoppingListItem).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Shopping list item not found"}), 404

    data = request.get_json(silent=True) or {}
    next_status = str(data.get("status") or "").strip().lower()
    if next_status not in {"open", "purchased"}:
        return jsonify({"error": "Only open and purchased status updates are allowed"}), 400

    item.status = next_status
    session.commit()
    return jsonify({"item": _serialize_item(item)}), 200


@shopping_list_bp.route("/products/<int:product_id>/confirm-recommendation", methods=["POST"])
@require_write_access
def confirm_recommendation_for_product(product_id):
    session = g.db_session
    item = (
        session.query(ShoppingListItem)
        .filter(
            ShoppingListItem.product_id == product_id,
            ShoppingListItem.source == "recommendation",
            ShoppingListItem.status == "open",
        )
        .order_by(ShoppingListItem.created_at.desc())
        .first()
    )
    if not item:
        return jsonify({"error": "No open recommendation-based shopping item found"}), 404

    _ensure_pending_recommendation_event(session, item)

    result = confirm_recommendation_peer(
        session,
        confirmer_user_id=getattr(getattr(g, "current_user", None), "id", None),
        shopping_item_id=item.id,
        item_name=item.name,
    )
    if result.get("error"):
        session.rollback()
        return jsonify({"error": result["error"]}), 400
    session.commit()
    return jsonify({
        "status": result.get("status", "peer_confirmed"),
        "shopping_item_id": item.id,
        "name": item.name,
    }), 200
