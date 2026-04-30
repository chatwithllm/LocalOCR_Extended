"""
Shopping list endpoints.
"""

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from flask import Blueprint, jsonify, request, g
from sqlalchemy import case, func, or_

logger = logging.getLogger(__name__)

from src.backend.contribution_scores import (
    award_contribution_event,
    confirm_recommendation_peer,
    finalize_recommendation_confirmation,
    meaningful_text_change,
    reverse_shopping_item_contributions,
    unfinalize_recommendation_confirmation,
)
from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.enrich_product_names import should_enrich_product_name
from src.backend.initialize_database_schema import AccessLink, ContributionEvent, PriceHistory, Product, ProductSnapshot, ShoppingListItem, ShoppingSession, Store
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


VALID_SESSION_STATUSES = {"active", "ready_to_bill", "closed"}


def _default_session_name() -> str:
    return datetime.now(timezone.utc).strftime("Shopping trip · %b %d, %Y")


def _get_current_session(session) -> ShoppingSession | None:
    """Return the newest non-closed session, if any."""
    return (
        session.query(ShoppingSession)
        .filter(ShoppingSession.status.in_(("active", "ready_to_bill")))
        .order_by(ShoppingSession.created_at.desc(), ShoppingSession.id.desc())
        .first()
    )


def _ensure_current_session(session) -> ShoppingSession:
    """Return the newest non-closed session, creating one if none exists.

    Read-safe: does NOT demote `ready_to_bill` back to `active`. Use this
    for read paths (e.g. GET /shopping-list) so the reconcile status sticks
    across refreshes.
    """
    current = _get_current_session(session)
    if current is None:
        current = ShoppingSession(
            name=_default_session_name(),
            status="active",
            created_by_id=getattr(getattr(g, "current_user", None), "id", None),
        )
        session.add(current)
        session.flush()
    return current


def _get_or_create_active_session(session) -> ShoppingSession:
    """Return the newest non-closed session, creating one if none exists.

    If the newest non-closed session is in `ready_to_bill`, it is demoted back
    to `active` so newly-added items don't get trapped on a list the user is
    already trying to reconcile. Use for write paths that append items.
    """
    current = _ensure_current_session(session)
    if current.status == "ready_to_bill":
        current.status = "active"
        session.flush()
    return current


def _adopt_orphan_items_into(session, shopping_session: ShoppingSession) -> None:
    """Sweep any items with no session assignment into the given session.

    This keeps the upgrade path smooth when a fresh-install DB, or any other
    edge case, leaves items without a session_id.
    """
    session.query(ShoppingListItem).filter(
        ShoppingListItem.shopping_session_id.is_(None)
    ).update(
        {"shopping_session_id": shopping_session.id},
        synchronize_session=False,
    )


def _serialize_session(shopping_session: ShoppingSession | None) -> dict | None:
    if shopping_session is None:
        return None
    return {
        "id": shopping_session.id,
        "name": shopping_session.name or _default_session_name(),
        "status": shopping_session.status,
        "store_hint": shopping_session.store_hint,
        "estimated_total_snapshot": (
            float(shopping_session.estimated_total_snapshot)
            if shopping_session.estimated_total_snapshot is not None else None
        ),
        "actual_total_snapshot": (
            float(shopping_session.actual_total_snapshot)
            if shopping_session.actual_total_snapshot is not None else None
        ),
        "created_at": shopping_session.created_at.isoformat() if shopping_session.created_at else None,
        "closed_at": shopping_session.closed_at.isoformat() if shopping_session.closed_at else None,
    }


def _serialize_item(item: ShoppingListItem) -> dict:
    latest_price = _latest_price_for_item(g.db_session, item)
    latest_snapshot = _latest_snapshot_for_item(g.db_session, item)
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
        "shopping_session_id": getattr(item, "shopping_session_id", None),
        "name": item.name,
        "product_display_name": product_display_name,
        "product_full_name": product_full_name,
        "category": item.category,
        "quantity": item.quantity,
        "unit": getattr(item, "unit", None) or getattr(product, "default_unit", None) or "each",
        "size_label": getattr(item, "size_label", None) or getattr(product, "default_size_label", None),
        "status": item.status,
        "source": item.source,
        "note": item.note,
        "preferred_store": preferred_store,
        "manual_estimated_price": float(item.manual_estimated_price) if item.manual_estimated_price is not None else None,
        "actual_price": float(item.actual_price) if getattr(item, "actual_price", None) is not None else None,
        "effective_store": preferred_store or (latest_price or {}).get("store"),
        "latest_price": latest_price,
        "latest_snapshot": latest_snapshot,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _latest_snapshot_for_item(session, item: ShoppingListItem) -> dict | None:
    snapshot = (
        session.query(ProductSnapshot)
        .filter(ProductSnapshot.shopping_list_item_id == item.id)
        .order_by(ProductSnapshot.created_at.desc(), ProductSnapshot.id.desc())
        .first()
    )
    if not snapshot:
        return None

    snapshot_count = (
        session.query(ProductSnapshot)
        .filter(ProductSnapshot.shopping_list_item_id == item.id)
        .count()
    )
    return {
        "id": snapshot.id,
        "image_url": f"/product-snapshots/{snapshot.id}/image",
        "status": snapshot.status,
        "source_context": snapshot.source_context,
        "notes": snapshot.notes,
        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        "count": snapshot_count,
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

    if row:
        price, _product, store = row
        return {
            "price": float(price.price or 0),
            "store": store.name if store else None,
            "date": price.date.strftime("%Y-%m-%d") if price.date else None,
        }

    if item.manual_estimated_price is not None:
        return {
            "price": float(item.manual_estimated_price or 0),
            "store": canonicalize_store_name(item.preferred_store) if item.preferred_store else None,
            "date": None,
        }

    return None


def _ensure_store(session, store_name: str | None):
    normalized = canonicalize_store_name(store_name) if store_name else None
    if not normalized:
        return None
    store = session.query(Store).filter(func.lower(Store.name) == normalized.lower()).first()
    if store:
        return store
    store = Store(name=normalized)
    session.add(store)
    session.flush()
    return store


def _build_shopping_list_payload(session, *, status: str = "", helper_mode: bool = False):
    """Build the shopping list payload scoped to the current session.

    The payload always carries a `session` object so the frontend can pick
    the right view (active vs ready_to_bill vs closed). Totals are computed
    in terms of the current session only, and now include an `actual_total`
    for items where the user has recorded what they actually paid.
    """

    current_session = _ensure_current_session(session)
    _adopt_orphan_items_into(session, current_session)
    session.commit()

    query = session.query(ShoppingListItem).filter(
        ShoppingListItem.shopping_session_id == current_session.id
    )
    if status:
        query = query.filter(ShoppingListItem.status == status)

    raw_items = query.order_by(
        ShoppingListItem.status.asc(),
        ShoppingListItem.created_at.desc(),
    ).all()
    items = [_serialize_item(item) for item in raw_items]
    open_items = [item for item in items if item["status"] == "open"]
    purchased_items = [item for item in items if item["status"] == "purchased"]

    def _estimated_line_total(item: dict) -> float:
        price = (item.get("latest_price") or {}).get("price") or 0
        return float(price) * float(item.get("quantity") or 0)

    def _actual_line_total(item: dict) -> float:
        """Actual total for a purchased item — counts entered actual_price only."""
        actual = item.get("actual_price")
        if actual is None:
            return 0.0
        return float(actual) * float(item.get("quantity") or 0)

    priced_purchased = [i for i in purchased_items if i.get("actual_price") is not None]
    total_estimated_cost = round(sum(_estimated_line_total(i) for i in open_items), 2)
    bought_estimated_total = round(sum(_estimated_line_total(i) for i in purchased_items), 2)
    actual_total = round(sum(_actual_line_total(i) for i in priced_purchased), 2)
    # Variance compares entered actuals vs the estimate of just the priced
    # subset — so it's meaningful even when the user is partway through
    # reconciling. Zero-returns when nothing is priced yet.
    priced_estimate_total = round(sum(_estimated_line_total(i) for i in priced_purchased), 2)
    variance = round(actual_total - priced_estimate_total, 2) if priced_purchased else 0.0
    actuals_entered = len(priced_purchased)

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
        for store in session.query(Store).filter(
            (Store.is_payment_artifact.is_(False)) | (Store.is_payment_artifact.is_(None))
        ).all()
        if store.name
    })

    open_count_in_session = session.query(ShoppingListItem).filter(
        ShoppingListItem.shopping_session_id == current_session.id,
        ShoppingListItem.status == "open",
    ).count()
    purchased_count_in_session = session.query(ShoppingListItem).filter(
        ShoppingListItem.shopping_session_id == current_session.id,
        ShoppingListItem.status == "purchased",
    ).count()

    return {
        "items": items,
        "count": len(items),
        "open_count": open_count_in_session,
        "purchased_count": purchased_count_in_session,
        "estimated_total_cost": total_estimated_cost,
        "bought_estimated_total": bought_estimated_total,
        "actual_total": actual_total,
        "variance": variance,
        "actuals_entered_count": actuals_entered,
        "suggested_stores": suggested_stores,
        "available_stores": available_stores,
        "helper_mode": helper_mode,
        "session": _serialize_session(current_session),
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


@shopping_list_bp.route("/identify-product-photo", methods=["POST"])
@require_write_access
def identify_product_photo():
    """Photo-first manual add: run Gemini on the uploaded product photo and
    return structured suggestions {name, brand, size, category, ...} so the
    Shopping manual-add form can prefill. Also saves the photo as a pending
    ProductSnapshot so it can be linked to the product after the user saves.

    Request: multipart/form-data with a single `image` file.
    Response 200: { "suggestion": {...}, "snapshot": { "id": N, "image_url": "..." } }
    Response 4xx: { "error": "..." }
    """
    from src.backend.call_gemini_vision_api import identify_product_via_gemini
    from src.backend.manage_product_snapshots import _get_snapshot_root

    image_file = request.files.get("image")
    if not image_file or not image_file.filename:
        return jsonify({"error": "image field is required"}), 400

    filename = image_file.filename or "photo.jpg"
    ext = Path(filename).suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
        return jsonify({"error": "unsupported image format"}), 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    year_month = datetime.now().strftime("%Y/%m")
    unique = f"{timestamp}_{uuid4().hex[:8]}{ext}"
    save_dir = _get_snapshot_root() / year_month
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / unique
    try:
        image_file.save(save_path)
    except Exception as exc:
        logger.error("Failed to save product-identify upload: %s", exc)
        return jsonify({"error": "Could not save photo"}), 500

    session = g.db_session
    snapshot = ProductSnapshot(
        user_id=getattr(getattr(g, "current_user", None), "id", None),
        source_context="manual",
        status="unreviewed",
        image_path=str(save_path),
        captured_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(snapshot)
    session.commit()

    try:
        suggestion = identify_product_via_gemini(str(save_path))
    except ValueError as exc:
        # GEMINI_API_KEY not configured — return the snapshot anyway so the
        # user can type manually, but flag the failure.
        logger.warning("Gemini identify unavailable: %s", exc)
        return jsonify({
            "error": str(exc),
            "snapshot": {
                "id": snapshot.id,
                "image_url": f"/product-snapshots/{snapshot.id}/image",
            },
        }), 503
    except Exception as exc:
        logger.error("Gemini product-identify failed: %s", exc, exc_info=True)
        return jsonify({
            "error": "Could not analyze photo. Type the item name manually.",
            "snapshot": {
                "id": snapshot.id,
                "image_url": f"/product-snapshots/{snapshot.id}/image",
            },
        }), 502

    return jsonify({
        "suggestion": suggestion,
        "snapshot": {
            "id": snapshot.id,
            "image_url": f"/product-snapshots/{snapshot.id}/image",
        },
    }), 200


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
    manual_estimated_price = data.get("manual_estimated_price")
    manual_estimated_price = float(manual_estimated_price) if manual_estimated_price not in (None, "", False) else None
    unit = (str(data.get("unit", "each") or "each").strip().lower() or "each")
    size_label = (str(data.get("size_label", "") or "").strip() or None)

    product = None
    product_id = data.get("product_id")
    if product_id:
        product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        product = find_matching_product(session, name, category)
    if not product and source == "manual":
        product = Product(
            name=name,
            raw_name=raw_name,
            display_name=name,
            category=category,
            default_unit=unit,
            default_size_label=size_label,
        )
        product.review_state = "pending" if should_enrich_product_name(raw_name, category) else "resolved"
        session.add(product)
        session.flush()

    active_session = _get_or_create_active_session(session)
    existing = (
        session.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_session_id == active_session.id)
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
        if manual_estimated_price is not None:
            existing.manual_estimated_price = manual_estimated_price
        if "unit" in data:
            existing.unit = unit
        if "size_label" in data:
            existing.size_label = size_label
        if source == "recommendation":
            _ensure_pending_recommendation_event(session, existing)
        session.commit()
        return jsonify({"item": _serialize_item(existing), "merged": True}), 200

    item = ShoppingListItem(
        product_id=product.id if product else None,
        user_id=getattr(getattr(g, "current_user", None), "id", None),
        shopping_session_id=active_session.id,
        name=get_product_display_name(product) if product else name,
        category=category,
        quantity=quantity,
        status="open",
        source=source,
        note=note,
        preferred_store=preferred_store,
        manual_estimated_price=manual_estimated_price,
        unit=unit,
        size_label=size_label,
    )
    session.add(item)
    session.flush()

    # Photo-first manual add: identify-product-photo endpoint created an
    # unlinked ProductSnapshot; wire it to the freshly-created item + product
    # so the photo shows up alongside future views of either.
    snapshot_id = data.get("snapshot_id")
    if snapshot_id:
        try:
            snapshot_id_int = int(snapshot_id)
        except (TypeError, ValueError):
            snapshot_id_int = None
        if snapshot_id_int:
            snapshot = (
                session.query(ProductSnapshot)
                .filter_by(id=snapshot_id_int)
                .first()
            )
            if snapshot:
                snapshot.shopping_list_item_id = item.id
                if product and not snapshot.product_id:
                    snapshot.product_id = product.id
                if snapshot.status == "unreviewed":
                    snapshot.status = "linked"
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
    previous_price = item.manual_estimated_price
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
    if "manual_estimated_price" in data:
        item.manual_estimated_price = float(data["manual_estimated_price"]) if data.get("manual_estimated_price") not in (None, "", False) else None
    if "actual_price" in data:
        raw_actual = data.get("actual_price")
        item.actual_price = float(raw_actual) if raw_actual not in (None, "", False) else None
    if "unit" in data:
        item.unit = (str(data.get("unit", "each") or "each").strip().lower() or "each")
    if "size_label" in data:
        item.size_label = (str(data.get("size_label", "") or "").strip() or None)

    persist_latest_price = bool(data.get("persist_latest_price"))
    if persist_latest_price and item.manual_estimated_price not in (None, "", False):
        price_value = float(item.manual_estimated_price or 0)
        if price_value > 0 and item.product_id:
            store_name = data.get("price_store") or item.preferred_store
            if not store_name:
                latest = _latest_price_for_item(session, item)
                store_name = (latest or {}).get("store")
            store = _ensure_store(session, store_name)
            if store:
                session.add(
                    PriceHistory(
                        product_id=item.product_id,
                        store_id=store.id,
                        price=price_value,
                        date=datetime.now(timezone.utc).date(),
                    )
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

    from src.backend.initialize_database_schema import ProductSnapshot

    reverse_shopping_item_contributions(session, shopping_item_id=item.id)
    
    # Unlink any product snapshots attached to this item before deleting to prevent IntegrityError
    session.query(ProductSnapshot).filter(
        ProductSnapshot.shopping_list_item_id == item.id
    ).update({"shopping_list_item_id": None})

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


@shopping_list_bp.route("/session/ready-to-bill", methods=["POST"])
@require_write_access
def mark_session_ready_to_bill():
    """Transition the current session from `active` to `ready_to_bill`.

    This is the "I'm done shopping, let me reconcile" button. Items stay put;
    the frontend flips into reconcile mode where purchased items get editable
    actual-price fields.
    """
    session = g.db_session
    current = _get_current_session(session)
    if current is None or current.status == "closed":
        return jsonify({"error": "No current shopping session to reconcile"}), 400
    if current.status == "ready_to_bill":
        return jsonify({"session": _serialize_session(current), "unchanged": True}), 200
    current.status = "ready_to_bill"
    session.commit()
    return jsonify({"session": _serialize_session(current)}), 200


@shopping_list_bp.route("/session/finalize", methods=["POST"])
@require_write_access
def finalize_session():
    """Close the current session and auto-create a fresh `active` successor.

    The closed session keeps its items for history; totals are snapshotted
    onto the session so they can be reviewed without recomputing from the
    (possibly later mutated) item rows.
    """
    session = g.db_session
    current = _get_current_session(session)
    if current is None or current.status == "closed":
        return jsonify({"error": "No current shopping session to finalize"}), 400

    items = (
        session.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_session_id == current.id)
        .all()
    )
    purchased_items = [i for i in items if i.status == "purchased"]
    open_items = [i for i in items if i.status == "open"]

    def _estimated_line_total_row(item: ShoppingListItem) -> float:
        price = None
        resolved = _latest_price_for_item(session, item)
        if resolved:
            price = resolved.get("price")
        if price is None and item.manual_estimated_price is not None:
            price = item.manual_estimated_price
        return float(price or 0) * float(item.quantity or 0)

    def _actual_line_total_row(item: ShoppingListItem) -> float:
        if item.actual_price is not None:
            return float(item.actual_price) * float(item.quantity or 0)
        return _estimated_line_total_row(item)

    # Snapshot totals against purchased items only. The session's history is
    # what the user actually rang up — items still open weren't part of this
    # trip and will carry over to the successor session.
    estimated_snapshot = round(sum(_estimated_line_total_row(i) for i in purchased_items), 2)
    actual_snapshot = round(sum(_actual_line_total_row(i) for i in purchased_items), 2)

    current.status = "closed"
    current.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    current.estimated_total_snapshot = estimated_snapshot
    current.actual_total_snapshot = actual_snapshot

    # Auto-spawn a fresh active session so the shopping page stays usable.
    successor = ShoppingSession(
        name=_default_session_name(),
        status="active",
        created_by_id=getattr(getattr(g, "current_user", None), "id", None),
    )
    session.add(successor)
    session.flush()

    # Carry still-open items forward so multi-store planning isn't lost —
    # e.g., if the user finalized a Kroger trip, their Costco items stay
    # on the next list instead of being archived into the closed session.
    for item in open_items:
        item.shopping_session_id = successor.id

    session.commit()
    return jsonify({
        "closed_session": _serialize_session(current),
        "active_session": _serialize_session(successor),
        "carried_over_count": len(open_items),
    }), 200


@shopping_list_bp.route("/session/reopen", methods=["POST"])
@require_write_access
def reopen_session():
    """Reopen a session — either the latest closed one, or by explicit id.

    If the current session is already `ready_to_bill`, reopen demotes it to
    `active`. If the caller passes `{"session_id": N}`, that specific session
    is reopened.

    When reopening a specific closed session while a *different* non-closed
    session already exists, we swap intelligently:
      - Current session is empty → it's deleted to make room (no data lost).
      - Current session has items → 409 so the caller can finalize it first.
    """
    session = g.db_session
    data = request.get_json(silent=True) or {}
    target_id = data.get("session_id")

    target: ShoppingSession | None = None
    if target_id is not None:
        target = session.query(ShoppingSession).filter_by(id=int(target_id)).first()
        if target is None:
            return jsonify({"error": "Shopping session not found"}), 404
    else:
        current = _get_current_session(session)
        if current is not None and current.status == "ready_to_bill":
            target = current
        else:
            target = (
                session.query(ShoppingSession)
                .filter(ShoppingSession.status == "closed")
                .order_by(ShoppingSession.closed_at.desc(), ShoppingSession.id.desc())
                .first()
            )
        if target is None:
            return jsonify({"error": "No session available to reopen"}), 400

    # When reopening a past/closed trip explicitly, clear the way for it to
    # become the canonical current session.
    if target.status == "closed":
        current = _get_current_session(session)
        if current is not None and current.id != target.id:
            current_item_count = (
                session.query(ShoppingListItem)
                .filter(ShoppingListItem.shopping_session_id == current.id)
                .count()
            )
            if current_item_count > 0:
                return jsonify({
                    "error": (
                        "Your current shopping list has items. Finalize it "
                        "first, then reopen this past trip."
                    ),
                    "conflict_session_id": current.id,
                }), 409
            session.delete(current)
            session.flush()

    target.status = "active"
    target.closed_at = None
    session.commit()
    return jsonify({"session": _serialize_session(target)}), 200


@shopping_list_bp.route("/sessions", methods=["GET"])
@require_auth
def list_sessions():
    """History endpoint: list sessions, newest first, with item counts.

    Optional query params:
      ?status=closed  — only closed sessions (for Past Trips UI)
      ?status=all     — every session (default)
    """
    session = g.db_session
    status_filter = (request.args.get("status") or "all").lower()

    purchased_flag = case((ShoppingListItem.status == "purchased", 1), else_=0)
    query = (
        session.query(
            ShoppingSession,
            func.count(ShoppingListItem.id).label("item_count"),
            func.coalesce(func.sum(purchased_flag), 0).label("purchased_count"),
        )
        .outerjoin(
            ShoppingListItem,
            ShoppingListItem.shopping_session_id == ShoppingSession.id,
        )
        .group_by(ShoppingSession.id)
        .order_by(ShoppingSession.created_at.desc(), ShoppingSession.id.desc())
    )
    if status_filter == "closed":
        query = query.filter(ShoppingSession.status == "closed")

    rows = query.all()
    payload = []
    for shopping_session, item_count, purchased_count in rows:
        row = _serialize_session(shopping_session) or {}
        row["item_count"] = int(item_count or 0)
        row["purchased_count"] = int(purchased_count or 0)
        est = row.get("estimated_total_snapshot")
        act = row.get("actual_total_snapshot")
        row["variance"] = (
            round(float(act) - float(est), 2)
            if est is not None and act is not None
            else None
        )
        payload.append(row)
    return jsonify({"sessions": payload, "count": len(payload)}), 200


@shopping_list_bp.route("/sessions/<int:session_id>", methods=["GET"])
@require_auth
def get_session_detail(session_id: int):
    """Detail endpoint for a past/current session — session metadata + items.

    Used by the Past Trips expand-to-view behaviour so we don't fetch every
    closed session's line items upfront.
    """
    session = g.db_session
    shopping_session = (
        session.query(ShoppingSession).filter_by(id=session_id).first()
    )
    if shopping_session is None:
        return jsonify({"error": "Shopping session not found"}), 404

    items = (
        session.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_session_id == shopping_session.id)
        .order_by(
            ShoppingListItem.status.asc(),
            ShoppingListItem.created_at.asc(),
            ShoppingListItem.id.asc(),
        )
        .all()
    )
    return jsonify({
        "session": _serialize_session(shopping_session),
        "items": [_serialize_item(item) for item in items],
        "count": len(items),
    }), 200


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
