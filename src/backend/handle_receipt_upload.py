"""
Step 5: Create Stub Receipt Upload Endpoint
============================================
PROMPT Reference: Phase 1, Step 5

Provides POST /receipts/upload endpoint that accepts image and PDF files directly.
Enables testing the OCR → inventory pipeline without Telegram/Nginx/SSL.
Also serves as the Home Assistant upload channel long-term.

Auth: Bearer token required
"""

import os
import logging
import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, g, send_file

from src.backend.active_inventory import rebuild_active_inventory
from src.backend.create_flask_application import require_auth

logger = logging.getLogger(__name__)

receipts_bp = Blueprint("receipts", __name__, url_prefix="/receipts")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}


def _get_receipts_root() -> str:
    """Return the receipt storage root.

    Prefer RECEIPTS_DIR when set. Otherwise use /data/receipts for containerized
    deployments if /data exists, and fall back to a repo-local data directory for
    local development runs.
    """
    configured = os.getenv("RECEIPTS_DIR")
    if configured:
        return configured

    container_path = Path("/data/receipts")
    if container_path.parent.exists():
        return str(container_path)

    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "data" / "receipts")


def _resolve_receipt_path(image_path: str) -> Path | None:
    """Return a safe local path for a stored receipt image."""
    if not image_path:
        return None

    path = Path(image_path)
    if not path.is_absolute():
        path = Path(_get_receipts_root()) / path

    try:
        resolved = path.resolve(strict=True)
        root = Path(_get_receipts_root()).resolve()
        resolved.relative_to(root)
    except Exception:
        return None

    return resolved


def _detect_receipt_file_type(image_path: str | None) -> str | None:
    """Infer the stored receipt file type from its path."""
    if not image_path:
        return None
    ext = Path(image_path).suffix.lower().lstrip(".")
    return ext or None


def _parse_raw_ocr_json(raw_value: str | None) -> dict | None:
    """Parse stored OCR JSON safely for review flows."""
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        logger.warning("Failed to parse stored OCR JSON for receipt review.")
        return None


def _cleanup_receipt_files(image_paths: list[str]):
    """Best-effort cleanup for stored receipt files and empty parent folders."""
    for image_path in set(path for path in image_paths if path):
        resolved = _resolve_receipt_path(image_path)
        if not resolved:
            continue
        try:
            resolved.unlink(missing_ok=True)
            parent = resolved.parent
            root = Path(_get_receipts_root()).resolve()
            while parent != root and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        except Exception as exc:
            logger.warning("Failed to remove stored receipt file %s: %s", resolved, exc)


def _parse_filter_date(value: str | None):
    """Parse YYYY-MM-DD filter values safely."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


@receipts_bp.route("/upload", methods=["POST"])
@require_auth
def upload_receipt():
    """Upload a receipt file for OCR processing.

    Accepts multipart/form-data with an 'image' file field.
    Routes to the hybrid OCR processor (extract_receipt_data.py).

    Returns:
        JSON with extracted receipt data or error message.
    """
    # Validate file presence
    if "image" not in request.files:
        return jsonify({"error": "No receipt file provided. Use 'image' field."}), 400

    image_file = request.files["image"]
    if image_file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # Validate file type
    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type: {ext}",
            "allowed": list(ALLOWED_EXTENSIONS),
        }), 400

    # Save to receipts directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{uuid4().hex[:8]}{ext}"
    year_month = datetime.now().strftime("%Y/%m")
    save_dir = os.path.join(_get_receipts_root(), year_month)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)

    try:
        image_file.save(save_path)
        logger.info(f"Receipt file saved: {save_path}")
    except Exception as e:
        logger.error(f"Failed to save receipt image: {e}")
        return jsonify({"error": "Failed to save receipt file"}), 500

    # Get user ID from auth context
    user_id = None
    current_user = getattr(g, "current_user", None)
    if current_user:
        user_id = current_user.id

    # Route to hybrid OCR processor
    try:
        from src.backend.extract_receipt_data import process_receipt
        result = process_receipt(
            image_path=save_path,
            source="upload",
            user_id=user_id,
        )

        status_code = {
            "processed": 200,
            "review": 200,
            "failed": 422,
            "not_implemented": 202,
        }.get(result["status"], 200)

        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"OCR processing failed: {e}")
        return jsonify({
            "error": "OCR processing failed",
            "message": str(e),
            "image_path": save_path,
        }), 500


@receipts_bp.route("/<int:receipt_id>", methods=["GET"])
@require_auth
def get_receipt(receipt_id):
    """Retrieve details for a specific receipt/purchase."""
    from src.backend.initialize_database_schema import Purchase, ReceiptItem, Store, Product, TelegramReceipt

    session = g.db_session
    purchase = session.query(Purchase).filter_by(id=receipt_id).first()
    receipt_record = (
        session.query(TelegramReceipt)
        .filter(
            (TelegramReceipt.purchase_id == receipt_id) |
            (TelegramReceipt.id == receipt_id)
        )
        .order_by(TelegramReceipt.created_at.desc())
        .first()
    )
    if not purchase and receipt_record and receipt_record.purchase_id:
        purchase = session.query(Purchase).filter_by(id=receipt_record.purchase_id).first()
    if not purchase and not receipt_record:
        return jsonify({"error": "Receipt not found"}), 404

    store = session.query(Store).filter_by(id=purchase.store_id).first() if purchase else None
    items = []
    if purchase:
        items = (
            session.query(ReceiptItem, Product)
            .join(Product, ReceiptItem.product_id == Product.id)
            .filter(ReceiptItem.purchase_id == purchase.id)
            .all()
        )
    raw_ocr_data = _parse_raw_ocr_json(receipt_record.raw_ocr_json if receipt_record else None)

    return jsonify({
        "id": purchase.id if purchase else receipt_record.id,
        "store": store.name if store else None,
        "total": purchase.total_amount if purchase else None,
        "date": purchase.date.strftime("%Y-%m-%d") if purchase and purchase.date else None,
        "status": receipt_record.status if receipt_record else "processed",
        "ocr_engine": receipt_record.ocr_engine if receipt_record else None,
        "confidence": receipt_record.ocr_confidence if receipt_record else None,
        "receipt_type": receipt_record.receipt_type if receipt_record else None,
        "source": "telegram" if receipt_record and not str(receipt_record.telegram_user_id).startswith("upload") else "upload",
        "created_at": receipt_record.created_at.isoformat() if receipt_record and receipt_record.created_at else None,
        "image_url": f"/receipts/{purchase.id if purchase else receipt_record.id}/image" if receipt_record and receipt_record.image_path else None,
        "file_type": _detect_receipt_file_type(receipt_record.image_path if receipt_record else None),
        "raw_ocr_data": raw_ocr_data,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "extracted_by": item.extracted_by,
            }
            for item, product in items
        ],
    }), 200


@receipts_bp.route("", methods=["GET"])
@require_auth
def list_receipts():
    """List saved receipt records for review in the web app."""
    from sqlalchemy import func

    from src.backend.initialize_database_schema import (
        TelegramReceipt,
        Purchase,
        ReceiptItem,
        Product,
        Store,
    )

    session = g.db_session
    limit = request.args.get("limit", 50, type=int)
    store_filter = request.args.get("store", "").strip()
    status_filter = request.args.get("status", "").strip().lower()
    source_filter = request.args.get("source", "").strip().lower()
    purchase_date_from = _parse_filter_date(request.args.get("purchase_date_from"))
    purchase_date_to = _parse_filter_date(request.args.get("purchase_date_to"))
    upload_date_from = _parse_filter_date(request.args.get("upload_date_from"))
    upload_date_to = _parse_filter_date(request.args.get("upload_date_to"))

    query = (
        session.query(TelegramReceipt, Purchase, Store)
        .outerjoin(Purchase, TelegramReceipt.purchase_id == Purchase.id)
        .outerjoin(Store, Purchase.store_id == Store.id)
    )

    if store_filter:
        query = query.filter(Store.name == store_filter)
    if status_filter:
        query = query.filter(TelegramReceipt.status == status_filter)
    if source_filter == "telegram":
        query = query.filter(~TelegramReceipt.telegram_user_id.startswith("upload"))
    elif source_filter == "upload":
        query = query.filter(TelegramReceipt.telegram_user_id.startswith("upload"))
    if purchase_date_from:
        query = query.filter(Purchase.date >= purchase_date_from)
    if purchase_date_to:
        query = query.filter(Purchase.date < purchase_date_to + timedelta(days=1))
    if upload_date_from:
        query = query.filter(TelegramReceipt.created_at >= upload_date_from)
    if upload_date_to:
        query = query.filter(TelegramReceipt.created_at < upload_date_to + timedelta(days=1))

    records = query.order_by(TelegramReceipt.created_at.desc()).all()
    limited_records = records[:max(1, min(limit, 200))]

    stores = sorted({
        row[0] for row in session.query(Store.name).filter(Store.name.isnot(None)).distinct().all() if row[0]
    })

    store_counts = {}
    month_summary = {}
    for record, purchase, store in records:
        store_name = store.name if store else "Unknown"
        store_counts[store_name] = store_counts.get(store_name, 0) + 1
        if purchase and purchase.date:
            month_key = purchase.date.strftime("%Y-%m")
            month_entry = month_summary.setdefault(
                month_key,
                {"count": 0, "total_amount": 0.0, "receipts": []},
            )
            month_entry["count"] += 1
            month_entry["total_amount"] += float(purchase.total_amount or 0)
            month_entry["receipts"].append({
                "receipt_id": purchase.id,
                "record_id": record.id,
                "store": store_name,
                "date": purchase.date.strftime("%Y-%m-%d"),
                "total": float(purchase.total_amount or 0),
                "source": "telegram" if not str(record.telegram_user_id).startswith("upload") else "upload",
                "status": record.status,
            })

    purchase_ids = sorted({
        purchase.id
        for _record, purchase, _store in records
        if purchase and purchase.id
    })

    total_items = 0
    unique_items = 0
    most_bought_items = []
    if purchase_ids:
        total_items = int(
            session.query(func.coalesce(func.sum(ReceiptItem.quantity), 0))
            .filter(ReceiptItem.purchase_id.in_(purchase_ids))
            .scalar()
            or 0
        )
        unique_items = int(
            session.query(func.count(func.distinct(ReceiptItem.product_id)))
            .filter(ReceiptItem.purchase_id.in_(purchase_ids))
            .scalar()
            or 0
        )
        most_bought_items = [
            {
                "product_name": product_name,
                "quantity": float(quantity or 0),
            }
            for product_name, quantity in (
                session.query(
                    Product.name,
                    func.coalesce(func.sum(ReceiptItem.quantity), 0).label("quantity"),
                )
                .join(Product, ReceiptItem.product_id == Product.id)
                .filter(ReceiptItem.purchase_id.in_(purchase_ids))
                .group_by(Product.id, Product.name)
                .order_by(func.sum(ReceiptItem.quantity).desc(), Product.name.asc())
                .limit(5)
                .all()
            )
        ]

    return jsonify({
        "receipts": [
            {
                "id": purchase.id if purchase else record.id,
                "record_id": record.id,
                "purchase_id": purchase.id if purchase else None,
                "store": store.name if store else None,
                "total": purchase.total_amount if purchase else None,
                "date": purchase.date.strftime("%Y-%m-%d") if purchase and purchase.date else None,
                "status": record.status,
                "ocr_engine": record.ocr_engine,
                "confidence": record.ocr_confidence,
                "receipt_type": record.receipt_type,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "source": "telegram" if not str(record.telegram_user_id).startswith("upload") else "upload",
                "image_url": f"/receipts/{purchase.id if purchase else record.id}/image" if record.image_path else None,
                "file_type": _detect_receipt_file_type(record.image_path),
            }
            for record, purchase, store in limited_records
        ],
        "count": len(records),
        "filters": {
            "stores": stores,
            "sources": ["upload", "telegram"],
            "statuses": sorted({
                row[0]
                for row in session.query(TelegramReceipt.status).distinct().all()
                if row[0]
            }),
        },
        "summary": {
            "total_receipts": len(records),
            "total_items": total_items,
            "unique_items": unique_items,
            "most_bought_items": most_bought_items,
            "receipts_by_store": [
                {"store": store_name, "count": count}
                for store_name, count in sorted(store_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "purchases_by_month": [
                {
                    "month": month,
                    "count": values["count"],
                    "total_amount": round(values["total_amount"], 2),
                    "receipts": values["receipts"],
                }
                for month, values in sorted(month_summary.items(), reverse=True)
            ],
        },
    }), 200


@receipts_bp.route("/<int:receipt_id>/image", methods=["GET"])
@require_auth
def get_receipt_image(receipt_id):
    """Serve the stored image for a processed receipt."""
    from src.backend.initialize_database_schema import TelegramReceipt

    session = g.db_session
    record = (
        session.query(TelegramReceipt)
        .filter(
            (TelegramReceipt.purchase_id == receipt_id) |
            (TelegramReceipt.id == receipt_id)
        )
        .order_by(TelegramReceipt.created_at.desc())
        .first()
    )
    if not record or not record.image_path:
        return jsonify({"error": "Receipt image not found"}), 404

    image_path = _resolve_receipt_path(record.image_path)
    if not image_path:
        return jsonify({"error": "Receipt image not found"}), 404

    return send_file(image_path)


@receipts_bp.route("/<int:receipt_id>/approve", methods=["POST"])
@require_auth
def approve_receipt(receipt_id):
    """Approve a review receipt using edited or stored OCR payload."""
    from src.backend.initialize_database_schema import TelegramReceipt
    from src.backend.extract_receipt_data import _save_to_database, classify_receipt_data

    session = g.db_session
    record = (
        session.query(TelegramReceipt)
        .filter(
            (TelegramReceipt.purchase_id == receipt_id) |
            (TelegramReceipt.id == receipt_id)
        )
        .order_by(TelegramReceipt.created_at.desc())
        .first()
    )
    if not record:
        return jsonify({"error": "Receipt not found"}), 404
    if record.purchase_id:
        return jsonify({"error": "Receipt is already approved", "purchase_id": record.purchase_id}), 409

    payload = request.get_json(silent=True) or {}
    ocr_data = payload.get("data") or _parse_raw_ocr_json(record.raw_ocr_json)
    if not isinstance(ocr_data, dict):
        return jsonify({"error": "No OCR data available for review approval"}), 400

    missing = [field for field in ("store", "date", "items", "total") if not ocr_data.get(field)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    if not isinstance(ocr_data.get("items"), list) or not ocr_data["items"]:
        return jsonify({"error": "At least one receipt item is required"}), 400

    current_user = getattr(g, "current_user", None)
    user_id = current_user.id if current_user else None
    receipt_type = payload.get("receipt_type") or record.receipt_type or classify_receipt_data(ocr_data)
    purchase_id = _save_to_database(
        ocr_data,
        record.ocr_engine or "manual_review",
        record.image_path,
        user_id,
        receipt_type,
    )

    record.purchase_id = purchase_id
    record.status = "processed"
    record.receipt_type = receipt_type
    record.raw_ocr_json = json.dumps(ocr_data)
    session.commit()

    return jsonify({
        "status": "processed",
        "purchase_id": purchase_id,
        "receipt_id": record.id,
        "receipt_type": receipt_type,
    }), 200


@receipts_bp.route("/<int:receipt_id>/reprocess", methods=["POST"])
@require_auth
def reprocess_receipt(receipt_id):
    """Re-run OCR for an existing stored receipt and update its review payload."""
    from src.backend.initialize_database_schema import TelegramReceipt
    from src.backend.extract_receipt_data import process_receipt

    session = g.db_session
    record = (
        session.query(TelegramReceipt)
        .filter(
            (TelegramReceipt.purchase_id == receipt_id) |
            (TelegramReceipt.id == receipt_id)
        )
        .order_by(TelegramReceipt.created_at.desc())
        .first()
    )
    if not record or not record.image_path:
        return jsonify({"error": "Receipt not found"}), 404

    current_user = getattr(g, "current_user", None)
    user_id = current_user.id if current_user else None
    result = process_receipt(
        image_path=record.image_path,
        source="review",
        user_id=user_id,
        receipt_record_id=record.id,
    )

    return jsonify(result), 200


@receipts_bp.route("/<int:receipt_id>", methods=["DELETE"])
@require_auth
def delete_receipt(receipt_id):
    """Delete a receipt record, its stored file, and any associated purchase data."""
    from src.backend.initialize_database_schema import (
        TelegramReceipt, Purchase, ReceiptItem, PriceHistory, Inventory
    )

    session = g.db_session
    record = (
        session.query(TelegramReceipt)
        .filter(
            (TelegramReceipt.purchase_id == receipt_id) |
            (TelegramReceipt.id == receipt_id)
        )
        .order_by(TelegramReceipt.created_at.desc())
        .first()
    )
    purchase = session.query(Purchase).filter_by(id=receipt_id).first()
    if not record and not purchase:
        return jsonify({"error": "Receipt not found"}), 404

    if not purchase and record and record.purchase_id:
        purchase = session.query(Purchase).filter_by(id=record.purchase_id).first()

    linked_records = []
    if purchase:
        linked_records = (
            session.query(TelegramReceipt)
            .filter(TelegramReceipt.purchase_id == purchase.id)
            .all()
        )
    elif record:
        linked_records = [record]

    image_paths = [item.image_path for item in linked_records if item.image_path]
    deleted_purchase_id = purchase.id if purchase else None
    deleted_record_ids = [item.id for item in linked_records]

    try:
        if purchase:
            receipt_items = session.query(ReceiptItem).filter_by(purchase_id=purchase.id).all()
            purchase_product_ids = {receipt_item.product_id for receipt_item in receipt_items}

            if purchase_product_ids:
                session.query(PriceHistory).filter(
                    PriceHistory.product_id.in_(purchase_product_ids),
                    PriceHistory.store_id == purchase.store_id,
                    PriceHistory.date == purchase.date,
                ).delete(synchronize_session=False)

            session.query(ReceiptItem).filter_by(purchase_id=purchase.id).delete(synchronize_session=False)
            session.query(TelegramReceipt).filter(TelegramReceipt.purchase_id == purchase.id).delete(synchronize_session=False)
            session.query(Purchase).filter_by(id=purchase.id).delete(synchronize_session=False)
        elif linked_records:
            session.query(TelegramReceipt).filter(
                TelegramReceipt.id.in_(deleted_record_ids)
            ).delete(synchronize_session=False)

        session.flush()
        rebuild_active_inventory(session)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Failed to delete receipt %s: %s", receipt_id, exc)
        return jsonify({"error": "Failed to delete receipt"}), 500

    _cleanup_receipt_files(image_paths)

    return jsonify({
        "status": "deleted",
        "receipt_id": receipt_id,
        "deleted_record_ids": deleted_record_ids,
        "deleted_purchase_id": deleted_purchase_id,
    }), 200
