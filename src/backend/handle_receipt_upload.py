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
import copy
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, g, send_file
from PIL import Image, ImageOps

from src.backend.active_inventory import rebuild_active_inventory
from src.backend.budgeting_domains import (
    default_budget_category_for_spending_domain,
    derive_receipt_budget_defaults,
    normalize_budget_category,
    normalize_spending_domain,
)
from src.backend.budgeting_rollups import normalize_transaction_type, signed_purchase_total
from src.backend.create_flask_application import require_auth, require_write_access

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

    receipts_root = Path(_get_receipts_root()).resolve()
    path = Path(image_path)
    if not path.is_absolute():
        path = receipts_root / path
    else:
        # Older records may store an absolute repo-local path from a prior
        # machine or non-container run. If the path contains a `data/receipts`
        # segment, remap that suffix into the current receipts root.
        parts = list(path.parts)
        try:
            idx = parts.index("data")
            if idx + 1 < len(parts) and parts[idx + 1] == "receipts":
                suffix = Path(*parts[idx + 2:])
                candidate = receipts_root / suffix
                if candidate.exists():
                    path = candidate
        except ValueError:
            pass

    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(receipts_root)
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


def _receipt_source_label(receipt_record) -> str:
    telegram_user_id = str(getattr(receipt_record, "telegram_user_id", "") or "")
    if telegram_user_id.startswith("manual:"):
        return "manual"
    if telegram_user_id.startswith("upload"):
        return "upload"
    return "telegram"


def _receipt_payload_from_purchase(receipt: dict) -> dict:
    """Build a stable editable payload from persisted receipt fields."""
    items = []
    for item in receipt.get("items", []) or []:
        items.append({
            "product_id": item.get("product_id"),
            "name": item.get("product_name") or item.get("name") or "",
            "quantity": item.get("quantity") or 1,
            "unit_price": item.get("unit_price") or 0,
            "unit": item.get("unit") or "each",
            "size_label": item.get("size_label"),
            "category": item.get("category") or "other",
            "spending_domain": item.get("spending_domain"),
            "budget_category": item.get("budget_category"),
        })
    return {
        "store": receipt.get("store") or "",
        "store_location": None,
        "date": receipt.get("date") or "",
        "time": None,
        "transaction_type": receipt.get("transaction_type") or "purchase",
        "default_spending_domain": receipt.get("default_spending_domain") or "grocery",
        "default_budget_category": receipt.get("default_budget_category") or "grocery",
        "items": items,
        "subtotal": receipt.get("total") or 0,
        "tax": 0,
        "tip": 0,
        "total": receipt.get("total") or 0,
        "confidence": receipt.get("confidence") or 1,
    }


def _build_editable_receipt_payload(receipt_record, purchase, store_name: str | None, items: list[dict]) -> dict:
    """Return the best editable structured payload for the review UI."""
    payload = _parse_raw_ocr_json(receipt_record.raw_ocr_json if receipt_record else None)
    if isinstance(payload, dict):
        payload = copy.deepcopy(payload)
        payload.setdefault("store", store_name or "")
        payload.setdefault("date", purchase.date.strftime("%Y-%m-%d") if purchase and purchase.date else None)
        payload.setdefault("items", [])
        payload.setdefault("total", purchase.total_amount if purchase else 0)
        payload.setdefault("subtotal", payload.get("total", 0))
        payload.setdefault("tax", 0)
        payload.setdefault("tip", 0)
        payload.setdefault("transaction_type", normalize_transaction_type(getattr(purchase, "transaction_type", None)))
        payload.setdefault("default_spending_domain", getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", "grocery"))
        payload.setdefault(
            "default_budget_category",
            getattr(purchase, "default_budget_category", None)
            or default_budget_category_for_spending_domain(getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", "grocery"))
        )
        return payload

    return _receipt_payload_from_purchase({
        "store": store_name or "",
        "date": purchase.date.strftime("%Y-%m-%d") if purchase and purchase.date else None,
        "total": purchase.total_amount if purchase else 0,
        "confidence": receipt_record.ocr_confidence if receipt_record else 1,
        "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None) if purchase else None),
        "default_spending_domain": getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", "grocery"),
        "default_budget_category": getattr(purchase, "default_budget_category", None)
            or default_budget_category_for_spending_domain(getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", "grocery")),
        "items": items,
    })


def _sanitize_receipt_payload(payload: dict) -> dict:
    """Normalize user-edited receipt payloads for persistence."""
    sanitized = {
        "store": str(payload.get("store", "") or "").strip(),
        "store_location": (str(payload.get("store_location", "") or "").strip() or None),
        "date": str(payload.get("date", "") or "").strip(),
        "time": (str(payload.get("time", "") or "").strip() or None),
        "transaction_type": normalize_transaction_type(payload.get("transaction_type"), default="purchase"),
        "default_spending_domain": normalize_spending_domain(payload.get("default_spending_domain"), default="grocery"),
        "default_budget_category": None,
        "subtotal": float(payload.get("subtotal") or 0),
        "tax": float(payload.get("tax") or 0),
        "tip": float(payload.get("tip") or 0),
        "total": float(payload.get("total") or 0),
        "confidence": float(payload.get("confidence") or 1),
        "items": [],
    }
    sanitized["default_budget_category"] = normalize_budget_category(
        payload.get("default_budget_category"),
        default=default_budget_category_for_spending_domain(sanitized["default_spending_domain"]),
    )

    for item in payload.get("items", []) or []:
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        sanitized["items"].append({
            "product_id": int(item.get("product_id")) if item.get("product_id") not in (None, "", 0, "0") else None,
            "name": name,
            "quantity": float(item.get("quantity") or 1),
            "unit_price": float(item.get("unit_price") or 0),
            "unit": (str(item.get("unit", "each") or "each").strip().lower() or "each"),
            "size_label": (str(item.get("size_label", "") or "").strip() or None),
            "category": str(item.get("category", "other") or "other").strip().lower(),
            "spending_domain": normalize_spending_domain(item.get("spending_domain"), default="") or None,
            "budget_category": normalize_budget_category(item.get("budget_category"), default="") or None,
        })
    return sanitized


def _delete_purchase_data(session, purchase):
    """Remove purchase-linked rows so a corrected receipt can be rebuilt cleanly."""
    from src.backend.initialize_database_schema import ReceiptItem, PriceHistory, TelegramReceipt, Purchase

    receipt_records = session.query(TelegramReceipt).filter(TelegramReceipt.purchase_id == purchase.id).all()
    for record in receipt_records:
        record.purchase_id = None

    receipt_items = session.query(ReceiptItem).filter_by(purchase_id=purchase.id).all()
    product_ids = {item.product_id for item in receipt_items if item.product_id}
    if product_ids:
        session.query(PriceHistory).filter(
            PriceHistory.product_id.in_(product_ids),
            PriceHistory.store_id == purchase.store_id,
            PriceHistory.date == purchase.date,
        ).delete(synchronize_session=False)

    session.query(ReceiptItem).filter_by(purchase_id=purchase.id).delete(synchronize_session=False)
    session.query(Purchase).filter_by(id=purchase.id).delete(synchronize_session=False)


def _clear_purchase_detail_data(session, purchase):
    """Remove item/price rows while preserving the purchase record itself."""
    from src.backend.initialize_database_schema import ReceiptItem, PriceHistory

    receipt_items = session.query(ReceiptItem).filter_by(purchase_id=purchase.id).all()
    product_ids = {item.product_id for item in receipt_items if item.product_id}
    if product_ids:
        session.query(PriceHistory).filter(
            PriceHistory.product_id.in_(product_ids),
            PriceHistory.store_id == purchase.store_id,
            PriceHistory.date == purchase.date,
        ).delete(synchronize_session=False)

    session.query(ReceiptItem).filter_by(purchase_id=purchase.id).delete(synchronize_session=False)


def _resolve_receipt_record(session, receipt_id):
    """Resolve a receipt reference by preferring purchase_id over raw receipt id."""
    from src.backend.initialize_database_schema import TelegramReceipt

    record = (
        session.query(TelegramReceipt)
        .filter(TelegramReceipt.purchase_id == receipt_id)
        .order_by(TelegramReceipt.created_at.desc())
        .first()
    )
    if record:
        return record
    return (
        session.query(TelegramReceipt)
        .filter(TelegramReceipt.id == receipt_id)
        .order_by(TelegramReceipt.created_at.desc())
        .first()
    )


def _create_manual_receipt_entry(session, payload: dict, receipt_type: str, user_id: int | None):
    """Create a manual purchase + receipt record so budgets stay accurate without an image."""
    from src.backend.active_inventory import rebuild_active_inventory
    from src.backend.contribution_scores import validate_low_workflow
    from src.backend.initialize_database_schema import (
        Purchase,
        ReceiptItem,
        Product,
        Store,
        PriceHistory,
        TelegramReceipt,
    )
    from src.backend.normalize_product_names import canonicalize_product_identity, find_matching_product
    from src.backend.normalize_store_names import canonicalize_store_name, find_matching_store
    from src.backend.manage_product_catalog import _merge_products

    sanitized = _sanitize_receipt_payload(payload)
    store_name = canonicalize_store_name(sanitized.get("store") or "Manual Entry")
    store = find_matching_store(session, store_name)
    if not store:
        store = Store(name=store_name, location=sanitized.get("store_location"))
        session.add(store)
        session.flush()

    purchase_date = datetime.strptime(sanitized["date"], "%Y-%m-%d")
    purchase_domain, purchase_budget_category = derive_receipt_budget_defaults(
        "general_expense" if receipt_type in {"general_expense", "retail_items"} else receipt_type
    )

    purchase = Purchase(
        store_id=store.id,
        total_amount=float(sanitized.get("total") or 0),
        date=purchase_date,
        domain=purchase_domain,
        transaction_type=normalize_transaction_type(sanitized.get("transaction_type"), default="purchase"),
        default_spending_domain=normalize_spending_domain(
            sanitized.get("default_spending_domain"),
            default=purchase_domain,
        ),
        default_budget_category=normalize_budget_category(
            sanitized.get("default_budget_category"),
            default=purchase_budget_category,
        ),
        user_id=user_id,
    )
    session.add(purchase)
    session.flush()

    persisted_items = []
    for item_data in sanitized.get("items", []) or []:
        name, category = canonicalize_product_identity(item_data.get("name", ""), item_data.get("category", "other"))
        if not name:
            continue
        product = None
        incoming_product_id = item_data.get("product_id")
        if incoming_product_id not in (None, "", 0, "0"):
            try:
                product = session.query(Product).filter_by(id=int(incoming_product_id)).first()
            except (TypeError, ValueError):
                product = None

        matched_product = find_matching_product(session, name, category)
        if product and matched_product and matched_product.id != product.id:
            product = _merge_products(session, product, matched_product)
            session.flush()
        elif not product:
            product = matched_product
        if not product:
            product = Product(
                name=name,
                raw_name=item_data.get("name", name),
                display_name=name,
                review_state="resolved",
                category=category,
            )
            session.add(product)
            session.flush()

        quantity = float(item_data.get("quantity") or 1)
        unit_price = float(item_data.get("unit_price") or 0)
        unit = (str(item_data.get("unit", "each") or "each").strip().lower() or "each")
        size_label = (str(item_data.get("size_label", "") or "").strip() or None)
        item_spending_domain = normalize_spending_domain(item_data.get("spending_domain"), default="") or None
        item_budget_category = normalize_budget_category(item_data.get("budget_category"), default="") or None
        if item_budget_category and not item_spending_domain:
            item_spending_domain = purchase.default_spending_domain
        if item_spending_domain and not item_budget_category:
            item_budget_category = default_budget_category_for_spending_domain(item_spending_domain)
        session.add(
            ReceiptItem(
                purchase_id=purchase.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=unit_price,
                unit=unit,
                size_label=size_label,
                spending_domain=item_spending_domain,
                budget_category=item_budget_category,
                extracted_by="manual",
            )
        )
        if unit_price > 0 and purchase.transaction_type != "refund":
            session.add(
                PriceHistory(
                    product_id=product.id,
                    store_id=store.id,
                    price=unit_price,
                    date=purchase.date,
                )
            )
        if purchase_domain == "grocery" and purchase.transaction_type != "refund":
            validate_low_workflow(
                session,
                product_id=product.id,
                purchase_id=purchase.id,
                product_name=product.display_name or product.name,
            )
        persisted_items.append(item_data)

    receipt_record = TelegramReceipt(
        telegram_user_id=f"manual:{user_id or 'web'}",
        message_id=None,
        image_path=None,
        status="processed",
        ocr_confidence=float(sanitized.get("confidence") or 1),
        ocr_engine="manual",
        receipt_type=receipt_type,
        raw_ocr_json=json.dumps(sanitized),
        purchase_id=purchase.id,
    )
    session.add(receipt_record)
    session.commit()

    if purchase_domain == "grocery":
        rebuild_active_inventory(session)
        session.commit()

    return receipt_record, purchase


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


def _rotate_receipt_file(image_path: str, direction: str) -> bool:
    """Rotate a stored receipt image in place."""
    resolved = _resolve_receipt_path(image_path)
    if not resolved:
        return False
    if resolved.suffix.lower() == ".pdf":
        raise ValueError("PDF receipts cannot be rotated in-app")

    degrees = 90 if direction == "left" else -90
    with Image.open(resolved) as image:
        normalized = ImageOps.exif_transpose(image)
        rotated = normalized.rotate(degrees, expand=True)
        rotated.save(resolved)
    return True


def _parse_filter_date(value: str | None):
    """Parse YYYY-MM-DD filter values safely."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


@receipts_bp.route("/upload", methods=["POST"])
@require_write_access
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

    receipt_intent = (request.form.get("receipt_intent") or "auto").strip().lower()
    if receipt_intent not in {"auto", "grocery", "restaurant", "general_expense"}:
        return jsonify({"error": "receipt_intent must be auto, grocery, restaurant, or general_expense"}), 400
    receipt_type_hint = None if receipt_intent == "auto" else receipt_intent

    # Route to hybrid OCR processor
    try:
        from src.backend.extract_receipt_data import process_receipt
        result = process_receipt(
            image_path=save_path,
            source="upload",
            user_id=user_id,
            receipt_type_hint=receipt_type_hint,
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
    receipt_record = None
    if purchase:
        receipt_record = (
            session.query(TelegramReceipt)
            .filter(TelegramReceipt.purchase_id == purchase.id)
            .order_by(TelegramReceipt.created_at.desc())
            .first()
        )
    if not receipt_record:
        receipt_record = (
            session.query(TelegramReceipt)
            .filter(TelegramReceipt.id == receipt_id)
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
    editable_data = _build_editable_receipt_payload(
        receipt_record,
        purchase,
        store.name if store else None,
        [
            {
                "product_id": item.product_id,
                "product_name": product.name,
                "category": product.category,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "unit": item.unit,
                "size_label": item.size_label,
                "spending_domain": item.spending_domain,
                "budget_category": item.budget_category,
                "extracted_by": item.extracted_by,
            }
            for item, product in items
        ],
    )

    return jsonify({
        "id": purchase.id if purchase else receipt_record.id,
        "store": store.name if store else None,
        "total": purchase.total_amount if purchase else None,
        "date": purchase.date.strftime("%Y-%m-%d") if purchase and purchase.date else None,
        "status": receipt_record.status if receipt_record else "processed",
        "ocr_engine": receipt_record.ocr_engine if receipt_record else None,
        "confidence": receipt_record.ocr_confidence if receipt_record else None,
        "receipt_type": receipt_record.receipt_type if receipt_record else None,
        "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None) if purchase else None),
        "default_spending_domain": getattr(purchase, "default_spending_domain", None) if purchase else None,
        "default_budget_category": getattr(purchase, "default_budget_category", None) if purchase else None,
        "source": _receipt_source_label(receipt_record) if receipt_record else "upload",
        "created_at": receipt_record.created_at.isoformat() if receipt_record and receipt_record.created_at else None,
        "image_url": f"/receipts/{purchase.id if purchase else receipt_record.id}/image" if receipt_record and receipt_record.image_path else None,
        "file_type": _detect_receipt_file_type(receipt_record.image_path if receipt_record else None),
        "signed_total": signed_purchase_total(purchase) if purchase else None,
        "raw_ocr_data": raw_ocr_data,
        "editable_data": editable_data,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": product.name,
                "category": product.category,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "unit": item.unit,
                "size_label": item.size_label,
                "spending_domain": item.spending_domain,
                "budget_category": item.budget_category,
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
    receipt_type_filter = request.args.get("receipt_type", "").strip().lower()
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
    if receipt_type_filter:
        query = query.filter(TelegramReceipt.receipt_type == receipt_type_filter)
    if source_filter == "manual":
        query = query.filter(TelegramReceipt.telegram_user_id.startswith("manual:"))
    elif source_filter == "telegram":
        query = query.filter(~TelegramReceipt.telegram_user_id.startswith("upload"))
        query = query.filter(~TelegramReceipt.telegram_user_id.startswith("manual:"))
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
            month_entry["total_amount"] += signed_purchase_total(purchase)
            month_entry["receipts"].append({
                "receipt_id": purchase.id,
                "record_id": record.id,
                "store": store_name,
                "date": purchase.date.strftime("%Y-%m-%d"),
                "total": signed_purchase_total(purchase),
                "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None)),
                "source": _receipt_source_label(record),
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
                "signed_total": signed_purchase_total(purchase) if purchase else None,
                "date": purchase.date.strftime("%Y-%m-%d") if purchase and purchase.date else None,
                "status": record.status,
                "ocr_engine": record.ocr_engine,
                "confidence": record.ocr_confidence,
                "receipt_type": record.receipt_type,
                "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None) if purchase else None),
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "source": _receipt_source_label(record),
                "image_url": f"/receipts/{purchase.id if purchase else record.id}/image" if record.image_path else None,
                "file_type": _detect_receipt_file_type(record.image_path),
            }
            for record, purchase, store in limited_records
        ],
        "count": len(records),
        "filters": {
            "stores": stores,
            "sources": ["manual", "upload", "telegram"],
            "statuses": sorted({
                row[0]
                for row in session.query(TelegramReceipt.status).distinct().all()
                if row[0]
            }),
            "receipt_types": sorted({
                row[0]
                for row in session.query(TelegramReceipt.receipt_type).distinct().all()
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


@receipts_bp.route("/manual", methods=["POST"])
@require_write_access
def create_manual_receipt():
    """Create a manual purchase/receipt entry when the image is unavailable."""
    payload = request.get_json(silent=True) or {}
    data = payload.get("data") or payload
    if not isinstance(data, dict):
        return jsonify({"error": "Manual receipt data is required"}), 400

    receipt_type = str(payload.get("receipt_type") or data.get("receipt_type") or "grocery").strip().lower()
    if receipt_type not in {"grocery", "restaurant", "general_expense"}:
        return jsonify({"error": "Receipt type must be grocery, restaurant, or general_expense"}), 400

    sanitized = _sanitize_receipt_payload(data)
    missing = [field for field in ("store", "date", "total") if not sanitized.get(field)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    if receipt_type in {"grocery", "restaurant"} and not sanitized.get("items"):
        return jsonify({"error": "Add at least one line item for grocery or restaurant manual entries"}), 400

    current_user = getattr(g, "current_user", None)
    user_id = current_user.id if current_user else None
    record, purchase = _create_manual_receipt_entry(g.db_session, sanitized, receipt_type, user_id)
    return jsonify({
        "status": "processed",
        "manual": True,
        "receipt_id": record.id,
        "purchase_id": purchase.id,
        "receipt_type": receipt_type,
    }), 201


@receipts_bp.route("/<int:receipt_id>/image", methods=["GET"])
@require_auth
def get_receipt_image(receipt_id):
    """Serve the stored image for a processed receipt."""
    from src.backend.initialize_database_schema import TelegramReceipt, Purchase

    session = g.db_session
    purchase = session.query(Purchase).filter_by(id=receipt_id).first()
    record = None
    if purchase:
        record = (
            session.query(TelegramReceipt)
            .filter(TelegramReceipt.purchase_id == purchase.id)
            .order_by(TelegramReceipt.created_at.desc())
            .first()
        )
    if not record:
        record = (
            session.query(TelegramReceipt)
            .filter(TelegramReceipt.id == receipt_id)
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
@require_write_access
def approve_receipt(receipt_id):
    """Approve a review receipt using edited or stored OCR payload."""
    from src.backend.initialize_database_schema import TelegramReceipt
    from src.backend.extract_receipt_data import _save_to_database, classify_receipt_data

    session = g.db_session
    record = _resolve_receipt_record(session, receipt_id)
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


@receipts_bp.route("/<int:receipt_id>/update", methods=["PUT"])
@require_write_access
def update_receipt(receipt_id):
    """Update an existing receipt using edited structured payload."""
    from src.backend.initialize_database_schema import TelegramReceipt, Purchase
    from src.backend.extract_receipt_data import _save_to_database, classify_receipt_data

    session = g.db_session
    record = _resolve_receipt_record(session, receipt_id)
    if not record:
        return jsonify({"error": "Receipt not found"}), 404

    payload = request.get_json(silent=True) or {}
    ocr_data = payload.get("data") or {}
    if not isinstance(ocr_data, dict):
        return jsonify({"error": "Edited receipt data is required"}), 400

    sanitized = _sanitize_receipt_payload(ocr_data)
    missing = [field for field in ("store", "date", "items", "total") if not sanitized.get(field)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    if not sanitized["items"]:
        return jsonify({"error": "At least one receipt item is required"}), 400

    current_user = getattr(g, "current_user", None)
    user_id = current_user.id if current_user else None
    purchase = session.query(Purchase).filter_by(id=record.purchase_id).first() if record.purchase_id else None
    if purchase:
        _clear_purchase_detail_data(session, purchase)
        session.flush()

    receipt_type = payload.get("receipt_type") or record.receipt_type or classify_receipt_data(sanitized)
    purchase_id = _save_to_database(
        sanitized,
        record.ocr_engine or "manual_review",
        record.image_path,
        user_id,
        receipt_type,
        existing_purchase=purchase,
    )
    record.purchase_id = purchase_id
    record.status = "processed"
    record.receipt_type = receipt_type
    record.raw_ocr_json = json.dumps(sanitized)
    record.ocr_engine = record.ocr_engine or "manual_review"
    record.ocr_confidence = sanitized.get("confidence") or record.ocr_confidence or 1.0
    session.commit()

    return jsonify({
        "status": "processed",
        "purchase_id": purchase_id,
        "receipt_id": record.id,
        "receipt_type": receipt_type,
    }), 200


@receipts_bp.route("/<int:receipt_id>/reprocess", methods=["POST"])
@require_write_access
def reprocess_receipt(receipt_id):
    """Re-run OCR for an existing stored receipt and update its review payload."""
    from src.backend.initialize_database_schema import TelegramReceipt
    from src.backend.extract_receipt_data import process_receipt

    session = g.db_session
    record = _resolve_receipt_record(session, receipt_id)
    if not record or not record.image_path:
        return jsonify({"error": "Receipt not found"}), 404

    current_user = getattr(g, "current_user", None)
    user_id = current_user.id if current_user else None
    existing_purchase = session.query(Purchase).filter_by(id=record.purchase_id).first() if record.purchase_id else None
    if existing_purchase:
        _delete_purchase_data(session, existing_purchase)
        record.status = "review"
        record.purchase_id = None
        session.flush()
    result = process_receipt(
        image_path=record.image_path,
        source="review",
        user_id=user_id,
        receipt_record_id=record.id,
    )

    return jsonify(result), 200


@receipts_bp.route("/<int:receipt_id>/rotate", methods=["PUT"])
@require_write_access
def rotate_receipt(receipt_id):
    """Rotate a stored receipt image in place for easier OCR and review."""
    from src.backend.initialize_database_schema import TelegramReceipt

    session = g.db_session
    record = _resolve_receipt_record(session, receipt_id)
    if not record or not record.image_path:
        return jsonify({"error": "Receipt not found"}), 404

    data = request.get_json(silent=True) or {}
    direction = (data.get("direction") or "right").strip().lower()
    if direction not in {"left", "right"}:
        return jsonify({"error": "direction must be left or right"}), 400

    try:
        _rotate_receipt_file(record.image_path, direction)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error("Failed to rotate receipt %s: %s", receipt_id, exc)
        return jsonify({"error": "Could not rotate receipt"}), 500

    return jsonify({"status": "rotated", "receipt_id": record.id, "direction": direction}), 200


@receipts_bp.route("/<int:receipt_id>", methods=["DELETE"])
@require_write_access
def delete_receipt(receipt_id):
    """Delete a receipt record, its stored file, and any associated purchase data."""
    from src.backend.initialize_database_schema import (
        TelegramReceipt, Purchase, ReceiptItem, PriceHistory, Inventory
    )

    session = g.db_session
    record = _resolve_receipt_record(session, receipt_id)
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
