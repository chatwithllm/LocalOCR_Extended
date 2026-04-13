"""
Product snapshot management.

Adds item-level photo upload and retrieval for shopping list items and
receipt line items.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, g, jsonify, request, send_file

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import (
    Product,
    ProductSnapshot,
    Purchase,
    ReceiptItem,
    ShoppingListItem,
    Store,
)

logger = logging.getLogger(__name__)

product_snapshots_bp = Blueprint("product_snapshots", __name__, url_prefix="/product-snapshots")

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
ALLOWED_SOURCE_CONTEXTS = {
    "before_purchase",
    "during_purchase",
    "after_purchase",
    "receipt_backfill",
}
ALLOWED_STATUSES = {"unreviewed", "linked", "needs_review", "archived"}


def _get_snapshot_root() -> Path:
    configured = os.getenv("PRODUCT_SNAPSHOTS_DIR")
    if configured:
        return Path(configured)

    container_path = Path("/data/product_snapshots")
    if container_path.parent.exists():
        return container_path

    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "data" / "product_snapshots"


def _resolve_snapshot_path(image_path: str | None) -> Path | None:
    if not image_path:
        return None

    root = _get_snapshot_root()
    path = Path(image_path)
    if not path.is_absolute():
        path = root / path

    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except Exception:
        return None
    return resolved


def _parse_int(value):
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _validate_links(session, linked_ids: dict) -> str | None:
    checks = (
        ("product_id", Product),
        ("shopping_list_item_id", ShoppingListItem),
        ("receipt_item_id", ReceiptItem),
        ("purchase_id", Purchase),
        ("store_id", Store),
    )
    for field_name, model in checks:
        value = linked_ids.get(field_name)
        if value is None:
            continue
        exists = session.query(model.id).filter_by(id=value).first()
        if not exists:
            return f"{field_name} does not reference an existing record"
    return None


def _serialize_snapshot(snapshot: ProductSnapshot) -> dict:
    return {
        "id": snapshot.id,
        "product_id": snapshot.product_id,
        "shopping_list_item_id": snapshot.shopping_list_item_id,
        "receipt_item_id": snapshot.receipt_item_id,
        "purchase_id": snapshot.purchase_id,
        "store_id": snapshot.store_id,
        "user_id": snapshot.user_id,
        "source_context": snapshot.source_context,
        "status": snapshot.status,
        "notes": snapshot.notes,
        "image_url": f"/product-snapshots/{snapshot.id}/image",
        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
    }


def _require_admin():
    current_user = getattr(g, "current_user", None)
    if not current_user or current_user.role != "admin":
        return jsonify({"error": "Admin access required"}), 403
    return None


def _derive_snapshot_context(session, snapshot: ProductSnapshot) -> dict:
    product = session.query(Product).filter_by(id=snapshot.product_id).first() if snapshot.product_id else None
    shopping_item = session.query(ShoppingListItem).filter_by(id=snapshot.shopping_list_item_id).first() if snapshot.shopping_list_item_id else None
    receipt_item = session.query(ReceiptItem).filter_by(id=snapshot.receipt_item_id).first() if snapshot.receipt_item_id else None
    purchase = session.query(Purchase).filter_by(id=snapshot.purchase_id).first() if snapshot.purchase_id else None
    store = session.query(Store).filter_by(id=snapshot.store_id).first() if snapshot.store_id else None
    if not store and purchase and purchase.store_id:
        store = session.query(Store).filter_by(id=purchase.store_id).first()

    display_name = None
    if product:
        display_name = getattr(product, "display_name", None) or getattr(product, "name", None)
    elif shopping_item:
        display_name = shopping_item.name
    elif receipt_item and receipt_item.product_id:
        linked_product = session.query(Product).filter_by(id=receipt_item.product_id).first()
        display_name = (getattr(linked_product, "display_name", None) or getattr(linked_product, "name", None)) if linked_product else None

    return {
        "product_name": display_name,
        "shopping_item_name": shopping_item.name if shopping_item else None,
        "receipt_item_id": receipt_item.id if receipt_item else None,
        "shopping_list_item_id": shopping_item.id if shopping_item else None,
        "purchase_id": purchase.id if purchase else snapshot.purchase_id,
        "store_name": store.name if store else None,
    }


def _serialize_review_snapshot(session, snapshot: ProductSnapshot) -> dict:
    payload = _serialize_snapshot(snapshot)
    payload.update(_derive_snapshot_context(session, snapshot))
    payload["linked_product"] = None
    if snapshot.product_id:
        product = session.query(Product).filter_by(id=snapshot.product_id).first()
        if product:
            payload["linked_product"] = {
                "id": product.id,
                "name": getattr(product, "display_name", None) or product.name,
                "category": product.category,
            }
    return payload


@product_snapshots_bp.route("/upload", methods=["POST"])
@require_auth
@require_write_access
def upload_product_snapshot():
    session = g.db_session

    if "image" not in request.files:
        return jsonify({"error": "No image provided. Use the 'image' field."}), 400

    image_file = request.files["image"]
    if not image_file or image_file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type: {ext}",
            "allowed": sorted(ALLOWED_IMAGE_EXTENSIONS),
        }), 400

    source_context = (request.form.get("source_context") or "after_purchase").strip().lower()
    if source_context not in ALLOWED_SOURCE_CONTEXTS:
        return jsonify({
            "error": "Invalid source_context",
            "allowed": sorted(ALLOWED_SOURCE_CONTEXTS),
        }), 400

    status = (request.form.get("status") or "unreviewed").strip().lower()
    if status not in ALLOWED_STATUSES:
        return jsonify({
            "error": "Invalid status",
            "allowed": sorted(ALLOWED_STATUSES),
        }), 400

    linked_ids = {
        "product_id": _parse_int(request.form.get("product_id")),
        "shopping_list_item_id": _parse_int(request.form.get("shopping_list_item_id")),
        "receipt_item_id": _parse_int(request.form.get("receipt_item_id")),
        "purchase_id": _parse_int(request.form.get("purchase_id")),
        "store_id": _parse_int(request.form.get("store_id")),
    }
    if not any(value is not None for value in linked_ids.values()):
        return jsonify({"error": "Provide at least one linked target for the snapshot"}), 400

    link_error = _validate_links(session, linked_ids)
    if link_error:
        return jsonify({"error": link_error}), 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    year_month = datetime.now().strftime("%Y/%m")
    filename = f"{timestamp}_{uuid4().hex[:8]}{ext}"
    save_dir = _get_snapshot_root() / year_month
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / filename

    try:
        image_file.save(save_path)
    except Exception as exc:
        logger.error("Failed to save product snapshot: %s", exc)
        return jsonify({"error": "Failed to save snapshot image"}), 500

    snapshot = ProductSnapshot(
        **linked_ids,
        user_id=getattr(getattr(g, "current_user", None), "id", None),
        source_context=source_context,
        status=status,
        notes=(request.form.get("notes") or "").strip() or None,
        image_path=str(save_path),
        captured_at=_parse_datetime(request.form.get("captured_at")),
    )
    session.add(snapshot)
    session.commit()

    return jsonify({"snapshot": _serialize_snapshot(snapshot)}), 201


@product_snapshots_bp.route("", methods=["GET"])
@require_auth
def list_product_snapshots():
    session = g.db_session
    query = session.query(ProductSnapshot)

    filters = {
        "product_id": _parse_int(request.args.get("product_id")),
        "shopping_list_item_id": _parse_int(request.args.get("shopping_list_item_id")),
        "receipt_item_id": _parse_int(request.args.get("receipt_item_id")),
        "purchase_id": _parse_int(request.args.get("purchase_id")),
    }
    for field_name, field_value in filters.items():
        if field_value is not None:
            query = query.filter(getattr(ProductSnapshot, field_name) == field_value)

    snapshots = query.order_by(ProductSnapshot.created_at.desc(), ProductSnapshot.id.desc()).all()
    return jsonify({
        "snapshots": [_serialize_snapshot(snapshot) for snapshot in snapshots],
        "count": len(snapshots),
    }), 200


@product_snapshots_bp.route("/<int:snapshot_id>", methods=["GET"])
@require_auth
def get_product_snapshot(snapshot_id: int):
    session = g.db_session
    snapshot = session.query(ProductSnapshot).filter_by(id=snapshot_id).first()
    if not snapshot:
        return jsonify({"error": "Snapshot not found"}), 404
    return jsonify({"snapshot": _serialize_snapshot(snapshot)}), 200


@product_snapshots_bp.route("/<int:snapshot_id>/image", methods=["GET"])
@require_auth
def get_product_snapshot_image(snapshot_id: int):
    session = g.db_session
    snapshot = session.query(ProductSnapshot).filter_by(id=snapshot_id).first()
    if not snapshot:
        return jsonify({"error": "Snapshot not found"}), 404

    image_path = _resolve_snapshot_path(snapshot.image_path)
    if not image_path:
        return jsonify({"error": "Snapshot image missing"}), 404

    return send_file(image_path)


@product_snapshots_bp.route("/review-queue", methods=["GET"])
@require_auth
def list_snapshot_review_queue():
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    session = g.db_session
    status = (request.args.get("status") or "pending").strip().lower()
    limit = min(max(request.args.get("limit", 50, type=int), 1), 200)

    query = session.query(ProductSnapshot).order_by(ProductSnapshot.created_at.desc(), ProductSnapshot.id.desc())
    snapshots = query.all()
    items = []
    for snapshot in snapshots:
        derived_status = snapshot.status or "unreviewed"
        if status == "pending":
            if derived_status not in {"unreviewed", "needs_review"}:
                continue
        elif status != "all" and derived_status != status:
            continue
        items.append(_serialize_review_snapshot(session, snapshot))
        if len(items) >= limit:
            break

    return jsonify({"items": items, "count": len(items)}), 200


@product_snapshots_bp.route("/<int:snapshot_id>/review", methods=["PUT"])
@require_auth
@require_write_access
def review_product_snapshot(snapshot_id: int):
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    session = g.db_session
    snapshot = session.query(ProductSnapshot).filter_by(id=snapshot_id).first()
    if not snapshot:
        return jsonify({"error": "Snapshot not found"}), 404

    data = request.get_json(silent=True) or {}
    requested_status = (data.get("status") or snapshot.status or "unreviewed").strip().lower()
    if requested_status not in ALLOWED_STATUSES:
        return jsonify({"error": "Invalid status"}), 400

    product = None
    product_id = _parse_int(data.get("product_id"))
    product_name = (data.get("product_name") or "").strip()
    product_category = (data.get("category") or "other").strip() or "other"

    if product_id is not None:
        product = session.query(Product).filter_by(id=product_id).first()
        if not product:
            return jsonify({"error": "product_id does not reference an existing record"}), 400
    elif product_name:
        from src.backend.normalize_product_names import canonicalize_product_identity, find_matching_product
        canonical_name, canonical_category = canonicalize_product_identity(product_name, product_category)
        product = find_matching_product(session, canonical_name, canonical_category)
        if not product:
            product = Product(
                name=canonical_name,
                raw_name=product_name,
                display_name=canonical_name,
                category=canonical_category,
                review_state="resolved",
                reviewed_by_id=getattr(getattr(g, "current_user", None), "id", None),
            )
            session.add(product)
            session.flush()

    if product:
        snapshot.product_id = product.id
        requested_status = "linked" if requested_status in {"unreviewed", "needs_review"} else requested_status

        if snapshot.shopping_list_item_id:
            shopping_item = session.query(ShoppingListItem).filter_by(id=snapshot.shopping_list_item_id).first()
            if shopping_item:
                shopping_item.product_id = product.id
                shopping_item.name = getattr(product, "display_name", None) or product.name
                shopping_item.category = product.category

        if snapshot.receipt_item_id:
            receipt_item = session.query(ReceiptItem).filter_by(id=snapshot.receipt_item_id).first()
            if receipt_item:
                receipt_item.product_id = product.id

    snapshot.status = requested_status
    if "notes" in data:
        snapshot.notes = (data.get("notes") or "").strip() or None

    session.commit()
    return jsonify({"snapshot": _serialize_review_snapshot(session, snapshot)}), 200
