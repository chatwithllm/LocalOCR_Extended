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
from sqlalchemy import or_, and_, not_, text as sql_text

from src.backend.active_inventory import rebuild_active_inventory
from src.backend.inventory_writes import upsert_inventory_for_receipt_item
from src.backend.budgeting_domains import (
    default_budget_category_for_spending_domain,
    derive_receipt_budget_defaults,
    normalize_budget_category,
    normalize_spending_domain,
    normalize_utility_service_types,
)
from src.backend.budgeting_rollups import normalize_transaction_type, signed_purchase_total
from src.backend.bill_cadence import normalize_billing_cycle
from src.backend.create_flask_application import require_auth, require_write_access

logger = logging.getLogger(__name__)

receipts_bp = Blueprint("receipts", __name__, url_prefix="/receipts")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}


def _attribution_user_ids(obj) -> list[int]:
    """Extract attribution user ids from a Purchase/ReceiptItem.

    Prefers the JSON array column `attribution_user_ids`; falls back to
    the legacy single-user column so rows that predate migration 009
    still work. Returns an empty list for untagged or household rows.
    """
    if obj is None:
        return []
    raw = getattr(obj, "attribution_user_ids", None)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [int(x) for x in parsed if x is not None]
        except (TypeError, ValueError):
            pass
    legacy = getattr(obj, "attribution_user_id", None)
    return [int(legacy)] if legacy else []


def _serialize_user_ids(user_ids) -> str | None:
    """Serialize a user_ids list for DB storage. Returns None for empty."""
    if not user_ids:
        return None
    cleaned = []
    seen = set()
    for uid in user_ids:
        try:
            i = int(uid)
        except (TypeError, ValueError):
            continue
        if i in seen:
            continue
        seen.add(i)
        cleaned.append(i)
    return json.dumps(cleaned) if cleaned else None


def _get_receipts_root() -> str:
    """Return the receipt storage root.

    Prefer RECEIPTS_DIR when set. Otherwise use /data/receipts for containerized
    deployments if /data exists, and fall back to a repo-local data directory for
    local development runs.
    """
    configured = os.getenv("RECEIPTS_DIR")
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return str(configured_path)
        if configured_path.parent.exists() and os.access(configured_path.parent, os.W_OK):
            return str(configured_path)
        logger.warning(
            "Configured RECEIPTS_DIR is not usable on this host; falling back to repo-local storage: %s",
            configured,
        )

    container_path = Path("/data/receipts")
    # Only prefer the container volume when it already exists. In containerized
    # deployments this path is normally created by the mounted volume or image
    # setup. Local/dev runs should fall back to the repo-local data directory
    # unless RECEIPTS_DIR is explicitly configured.
    if container_path.exists():
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
    if telegram_user_id.startswith("plaid:"):
        return "plaid"
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
        "refund_reason": receipt.get("refund_reason"),
        "refund_note": receipt.get("refund_note"),
        "default_spending_domain": receipt.get("default_spending_domain") or "grocery",
        "default_budget_category": receipt.get("default_budget_category") or "grocery",
        "bill_provider_name": receipt.get("bill_provider_name"),
        "bill_provider_type": receipt.get("bill_provider_type"),
        "bill_service_types": receipt.get("bill_service_types") or [],
        "bill_account_label": receipt.get("bill_account_label"),
        "bill_service_period_start": receipt.get("bill_service_period_start"),
        "bill_service_period_end": receipt.get("bill_service_period_end"),
        "bill_due_date": receipt.get("bill_due_date"),
        "bill_billing_cycle_month": receipt.get("bill_billing_cycle_month"),
        "bill_billing_cycle": receipt.get("bill_billing_cycle") or "monthly",
        "bill_is_recurring": receipt.get("bill_is_recurring"),
        "bill_provider_id": receipt.get("bill_provider_id"),
        "bill_service_line_id": receipt.get("bill_service_line_id"),
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
        payload.setdefault("refund_reason", getattr(purchase, "refund_reason", None))
        payload.setdefault("refund_note", getattr(purchase, "refund_note", None))
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
        "refund_reason": getattr(purchase, "refund_reason", None) if purchase else None,
        "refund_note": getattr(purchase, "refund_note", None) if purchase else None,
        "default_spending_domain": getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", "grocery"),
        "default_budget_category": getattr(purchase, "default_budget_category", None)
            or default_budget_category_for_spending_domain(getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", "grocery")),
        "items": items,
    })


def _sanitize_receipt_payload(payload: dict) -> dict:
    """Normalize user-edited receipt payloads for persistence."""
    bill_meta = payload.get("bill_meta") if isinstance(payload.get("bill_meta"), dict) else {}
    bill_source = {**bill_meta, **payload}
    provider_type = (
        str(bill_source.get("bill_provider_type") or bill_source.get("provider_type") or "").strip().lower() or None
    )
    sanitized = {
        "store": str(payload.get("store", "") or "").strip(),
        "store_location": (str(payload.get("store_location", "") or "").strip() or None),
        "date": str(payload.get("date", "") or "").strip(),
        "time": (str(payload.get("time", "") or "").strip() or None),
        "transaction_type": normalize_transaction_type(payload.get("transaction_type"), default="purchase"),
        "refund_reason": (str(payload.get("refund_reason", "") or "").strip().lower() or None),
        "refund_note": (str(payload.get("refund_note", "") or "").strip() or None),
        "default_spending_domain": normalize_spending_domain(payload.get("default_spending_domain"), default="grocery"),
        "default_budget_category": None,
        "bill_provider_name": (str(bill_source.get("bill_provider_name") or bill_source.get("provider_name") or "").strip() or None),
        "bill_provider_type": provider_type,
        "bill_service_types": normalize_utility_service_types(
            bill_source.get("bill_service_types") if bill_source.get("bill_service_types") is not None else bill_source.get("service_types"),
            provider_type=provider_type,
        ),
        "bill_account_label": (str(bill_source.get("bill_account_label") or bill_source.get("account_label") or "").strip() or None),
        "bill_service_period_start": (str(bill_source.get("bill_service_period_start") or bill_source.get("service_period_start") or "").strip() or None),
        "bill_service_period_end": (str(bill_source.get("bill_service_period_end") or bill_source.get("service_period_end") or "").strip() or None),
        "bill_due_date": (str(bill_source.get("bill_due_date") or bill_source.get("due_date") or "").strip() or None),
        "bill_billing_cycle_month": (str(bill_source.get("bill_billing_cycle_month") or bill_source.get("billing_cycle_month") or "").strip()[:7] or None),
        "bill_billing_cycle": normalize_billing_cycle(
            bill_source.get("bill_billing_cycle") or bill_source.get("billing_cycle")
        ),
        "bill_is_recurring": bool(
            bill_source.get("bill_is_recurring") if bill_source.get("bill_is_recurring") is not None else bill_source.get("is_recurring")
        ) if (bill_source.get("bill_is_recurring") is not None or bill_source.get("is_recurring") is not None) else True,
        "bill_auto_pay": bool(
            bill_source.get("bill_auto_pay") if bill_source.get("bill_auto_pay") is not None else bill_source.get("auto_pay")
        ) if (bill_source.get("bill_auto_pay") is not None or bill_source.get("auto_pay") is not None) else False,
        "subtotal": float(payload.get("subtotal") or 0),
        "tax": float(payload.get("tax") or 0),
        "tip": float(payload.get("tip") or 0),
        "total": float(payload.get("total") or 0),
        "confidence": float(payload.get("confidence") or 1),
        "items": [],
    }
    sanitized["default_budget_category"] = normalize_budget_category(
        payload.get("default_budget_category"),
        default=default_budget_category_for_spending_domain(
            sanitized["default_spending_domain"],
            provider_type=sanitized.get("bill_provider_type"),
            service_types=sanitized.get("bill_service_types"),
        ),
    )
    if sanitized["transaction_type"] != "refund":
        sanitized["refund_reason"] = None
        sanitized["refund_note"] = None

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
    from src.backend.initialize_database_schema import (
        ReceiptItem,
        PriceHistory,
        TelegramReceipt,
        Purchase,
        BillMeta,
        BillAllocation,
        CashTransaction,
    )

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
    session.query(BillAllocation).filter_by(purchase_id=purchase.id).delete(synchronize_session=False)
    session.query(CashTransaction).filter_by(purchase_id=purchase.id).delete(synchronize_session=False)
    session.query(BillMeta).filter_by(purchase_id=purchase.id).delete(synchronize_session=False)
    session.query(Purchase).filter_by(id=purchase.id).delete(synchronize_session=False)
    session.flush()
    try:
        session.expunge(purchase)
    except Exception:
        pass


def _clear_purchase_detail_data(session, purchase):
    """Remove item/price rows while preserving the purchase record itself."""
    from src.backend.initialize_database_schema import (
        ReceiptItem,
        PriceHistory,
        ProductSnapshot,
    )

    receipt_items = session.query(ReceiptItem).filter_by(purchase_id=purchase.id).all()
    product_ids = {item.product_id for item in receipt_items if item.product_id}
    if product_ids:
        session.query(PriceHistory).filter(
            PriceHistory.product_id.in_(product_ids),
            PriceHistory.store_id == purchase.store_id,
            PriceHistory.date == purchase.date,
        ).delete(synchronize_session=False)

    # ProductSnapshot.receipt_item_id is a non-cascading FK. Without this
    # null-out the DELETE below blows up with "FOREIGN KEY constraint
    # failed" when any snapshot was captured for these items (e.g. an
    # "after_purchase" review snapshot). Detach snapshots first so the
    # delete can proceed; the snapshot rows themselves stay valid (only
    # the receipt_item_id pointer is cleared).
    item_ids = [it.id for it in receipt_items]
    if item_ids:
        session.query(ProductSnapshot).filter(
            ProductSnapshot.receipt_item_id.in_(item_ids)
        ).update(
            {"receipt_item_id": None},
            synchronize_session=False,
        )

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


def _create_manual_receipt_entry(
    session,
    payload: dict,
    receipt_type: str,
    user_id: int | None,
    source_label: str | None = None,
    ocr_engine: str = "manual",
):
    """Create a purchase + receipt record so budgets stay accurate without an image.

    source_label controls how _receipt_source_label() later reads this row.
    Pass None for default "manual:<user_id>", or "plaid:<account_id>" for Plaid imports.
    """
    from src.backend.active_inventory import rebuild_active_inventory
    from src.backend.contribution_scores import validate_low_workflow
    from src.backend.extract_receipt_data import _save_bill_meta
    from src.backend.initialize_database_schema import (
        Purchase,
        ReceiptItem,
        Product,
        Store,
        PriceHistory,
        TelegramReceipt,
    )
    from src.backend.normalize_product_names import canonicalize_product_identity, find_matching_product
    from src.backend.normalize_store_names import (
        canonicalize_store_name,
        find_matching_store,
        is_payment_artifact,
    )
    from src.backend.manage_product_catalog import _merge_products

    sanitized = _sanitize_receipt_payload(payload)
    raw_store_name = sanitized.get("store") or "Manual Entry"
    store_name = canonicalize_store_name(raw_store_name)
    store = find_matching_store(session, store_name)
    artifact_flag = is_payment_artifact(raw_store_name) or is_payment_artifact(store_name)
    if not store:
        store = Store(
            name=store_name,
            location=sanitized.get("store_location"),
            is_payment_artifact=artifact_flag,
        )
        session.add(store)
        session.flush()
    elif artifact_flag and not getattr(store, "is_payment_artifact", False):
        store.is_payment_artifact = True
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
        refund_reason=sanitized.get("refund_reason"),
        refund_note=sanitized.get("refund_note"),
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
        receipt_item = ReceiptItem(
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
        session.add(receipt_item)
        if product is not None:
            rt = (receipt_type or "").lower() if isinstance(receipt_type, str) else ""
            if rt in {"grocery", "retail_items", ""}:
                try:
                    session.flush()
                    upsert_inventory_for_receipt_item(session, product, receipt_item, purchase)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "inventory upsert failed for product %s: %s",
                        product.id, exc,
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
        telegram_user_id=source_label or f"manual:{user_id or 'web'}",
        message_id=None,
        image_path=None,
        status="processed",
        ocr_confidence=float(sanitized.get("confidence") or 1),
        ocr_engine=ocr_engine,
        receipt_type=receipt_type,
        raw_ocr_json=json.dumps(sanitized),
        purchase_id=purchase.id,
    )
    session.add(receipt_record)
    if receipt_type in {"utility_bill", "household_bill"}:
        _save_bill_meta(session, purchase.id, sanitized)
    session.commit()

    if purchase_domain == "grocery":
        rebuild_active_inventory(session)
        session.commit()

    if receipt_record.image_path:
        try:
            from src.backend.receipt_filename_index import append_receipt_to_index
            append_receipt_to_index(
                image_path=receipt_record.image_path,
                store=store.name,
                date=purchase.date,
                total=purchase.total_amount,
                purchase_id=purchase.id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Receipt index append failed: %s", exc)

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


def _latest_snapshot_for_receipt_item(session, receipt_item_id: int) -> dict | None:
    from src.backend.initialize_database_schema import ProductSnapshot

    snapshot = (
        session.query(ProductSnapshot)
        .filter(ProductSnapshot.receipt_item_id == receipt_item_id)
        .order_by(ProductSnapshot.created_at.desc(), ProductSnapshot.id.desc())
        .first()
    )
    if not snapshot:
        return None

    snapshot_count = (
        session.query(ProductSnapshot)
        .filter(ProductSnapshot.receipt_item_id == receipt_item_id)
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


def _compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of an uploaded file for deduplication.

    Returns empty string if hash computation fails.
    """
    import hashlib
    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        hash_value = sha256.hexdigest()
        logger.debug(f"Computed hash {hash_value} for file {file_path}")
        return hash_value
    except Exception as e:
        logger.error(f"Failed to compute file hash for {file_path}: {e}", exc_info=True)
        return ""


def _check_for_duplicate(file_hash: str, session) -> dict | None:
    """Check if this file has been processed before.

    Returns:
        - None if no duplicate found
        - Dict with existing receipt info if duplicate found (processed or failed)
    """
    if not file_hash:
        logger.debug("Skipping duplicate check: empty file_hash")
        return None

    from src.backend.initialize_database_schema import TelegramReceipt

    existing = (
        session.query(TelegramReceipt)
        .filter_by(file_hash=file_hash)
        .first()
    )

    if not existing:
        logger.debug(f"No duplicate found for hash {file_hash[:16]}...")
        return None

    logger.info(f"Duplicate found! Receipt {existing.id} with status={existing.status}")
    return {
        "receipt_id": existing.id,
        "status": existing.status,
        "purchase_id": existing.purchase_id,
        "processed_at": existing.created_at.isoformat() if existing.created_at else None,
    }


def _save_failed_receipt(image_path: str, error_message: str, receipt_type_hint: str | None,
                         user_id: int | None, file_hash: str, session) -> int:
    """Save a failed receipt record so user can retry later.

    Returns: receipt_id of the saved failed receipt
    """
    from src.backend.initialize_database_schema import TelegramReceipt

    receipt = TelegramReceipt(
        telegram_user_id=str(user_id) if user_id else "upload",
        image_path=image_path,
        status="failed",
        receipt_type=receipt_type_hint,
        file_hash=file_hash,
        error_message=error_message,
        retry_count=0,
    )
    session.add(receipt)
    session.commit()

    logger.info(f"Saved failed receipt {receipt.id} with error: {error_message}")
    return receipt.id


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
    if receipt_intent not in {"auto", "grocery", "restaurant", "general_expense", "utility_bill", "household_bill"}:
        return jsonify({"error": "receipt_intent must be auto, grocery, restaurant, general_expense, utility_bill, or household_bill"}), 400
    receipt_type_hint = None if receipt_intent == "auto" else receipt_intent
    raw_model_id = (request.form.get("model_id") or "").strip()
    model_config_id = None
    if raw_model_id:
        try:
            model_config_id = int(raw_model_id)
        except ValueError:
            return jsonify({"error": "model_id must be an integer"}), 400

    # Compute file hash for deduplication
    session = g.db_session
    file_hash = _compute_file_hash(save_path)
    logger.info(f"Computed file_hash: {file_hash[:16]}... for {save_path}")

    # Check for duplicate receipts
    duplicate_info = _check_for_duplicate(file_hash, session)
    if file_hash:
        logger.info(f"Duplicate check result: {duplicate_info}")
    if duplicate_info:
        if duplicate_info["status"] == "processed" or duplicate_info["purchase_id"]:
            logger.info(f"Duplicate receipt detected: {duplicate_info['receipt_id']}")
            return jsonify({
                "status": "duplicate",
                "message": "This receipt was already processed",
                "receipt_id": duplicate_info["receipt_id"],
                "purchase_id": duplicate_info["purchase_id"],
                "processed_at": duplicate_info["processed_at"],
            }), 200
        # If status="failed", allow retry on the same record
        elif duplicate_info["status"] == "failed":
            logger.info(f"Retrying failed receipt: {duplicate_info['receipt_id']}")

    # Route to hybrid OCR processor
    # Pass file_hash so it's saved immediately during receipt creation
    try:
        from src.backend.extract_receipt_data import process_receipt
        result = process_receipt(
            image_path=save_path,
            source="upload",
            user_id=user_id,
            receipt_type_hint=receipt_type_hint,
            model_config_id=model_config_id,
            file_hash=file_hash,
        )

        status_code = {
            "processed": 200,
            "review": 200,
            "failed": 422,
            "not_implemented": 202,
        }.get(result["status"], 200)

        # If OCR failed, save failed receipt with error message
        if result["status"] == "failed":
            error_msg = result.get("error", "Unknown OCR error")
            failed_receipt_id = _save_failed_receipt(
                image_path=save_path,
                error_message=error_msg,
                receipt_type_hint=receipt_type_hint,
                user_id=user_id,
                file_hash=file_hash,
                session=session,
            )
            result["receipt_id"] = failed_receipt_id
            result["can_retry"] = True

        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"OCR processing failed: {e}")
        error_text = str(e)
        if (
            "Failed to render PDF receipt" in error_text
            or "require 'pdftoppm' to be installed" in error_text
        ):
            return jsonify({
                "error": "Unsupported or unreadable PDF receipt",
                "message": error_text,
                "image_path": save_path,
            }), 400

        # For other exceptions, save failed receipt
        failed_receipt_id = _save_failed_receipt(
            image_path=save_path,
            error_message=error_text,
            receipt_type_hint=receipt_type_hint,
            user_id=user_id,
            file_hash=file_hash,
            session=session,
        )
        return jsonify({
            "status": "failed",
            "error": "OCR processing failed",
            "message": error_text,
            "image_path": save_path,
            "receipt_id": failed_receipt_id,
            "can_retry": True,
        }), 500


@receipts_bp.route("/<int:receipt_id>", methods=["GET"])
@require_auth
def get_receipt(receipt_id):
    """Retrieve details for a specific receipt/purchase."""
    from src.backend.initialize_database_schema import Purchase, ReceiptItem, Store, Product, TelegramReceipt, BillMeta

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
    bill_meta = session.query(BillMeta).filter_by(purchase_id=purchase.id).first() if purchase else None
    bill_payload = {}
    if bill_meta:
        editable_data.update({
            "bill_provider_name": bill_meta.provider_name,
            "bill_provider_type": bill_meta.provider_type,
            "bill_service_types": json.loads(bill_meta.service_types) if bill_meta.service_types else [],
            "bill_account_label": bill_meta.account_label,
            "bill_service_period_start": bill_meta.service_period_start.isoformat() if bill_meta.service_period_start else None,
            "bill_service_period_end": bill_meta.service_period_end.isoformat() if bill_meta.service_period_end else None,
            "bill_due_date": bill_meta.due_date.isoformat() if bill_meta.due_date else None,
            "bill_billing_cycle_month": bill_meta.billing_cycle_month,
            "bill_billing_cycle": bill_meta.billing_cycle,
            "bill_is_recurring": bool(bill_meta.is_recurring),
            "bill_provider_id": bill_meta.provider_id,
            "bill_service_line_id": bill_meta.service_line_id,
        })
        bill_payload = {
            "bill_provider_name": bill_meta.provider_name,
            "bill_provider_type": bill_meta.provider_type,
            "bill_service_types": json.loads(bill_meta.service_types) if bill_meta.service_types else [],
            "bill_account_label": bill_meta.account_label,
            "bill_service_period_start": bill_meta.service_period_start.isoformat() if bill_meta.service_period_start else None,
            "bill_service_period_end": bill_meta.service_period_end.isoformat() if bill_meta.service_period_end else None,
            "bill_due_date": bill_meta.due_date.isoformat() if bill_meta.due_date else None,
            "bill_billing_cycle_month": bill_meta.billing_cycle_month,
            "bill_billing_cycle": bill_meta.billing_cycle,
            "bill_planning_month": bill_meta.planning_month,
            "bill_is_recurring": bool(bill_meta.is_recurring),
            "bill_auto_pay": bool(bill_meta.auto_pay),
            "bill_provider_id": bill_meta.provider_id,
            "bill_service_line_id": bill_meta.service_line_id,
            "bill_payment_status": bill_meta.payment_status,
            "bill_payment_confirmed_at": bill_meta.payment_confirmed_at.isoformat() if bill_meta.payment_confirmed_at else None,
            "bill_preferred_payment_method": (
                bill_meta.service_line.preferred_payment_method
                if bill_meta.service_line and bill_meta.service_line.preferred_payment_method
                else None
            ),
        }

    # Look up attribution user names so the frontend can render badges
    # without a second /auth/users round-trip.
    from src.backend.initialize_database_schema import User as _AttrUser
    purchase_attr_ids = _attribution_user_ids(purchase)
    all_attr_ids = set(purchase_attr_ids)
    for item, _product in items:
        all_attr_ids.update(_attribution_user_ids(item))
    attr_users = {}
    if all_attr_ids:
        for u in session.query(_AttrUser).filter(_AttrUser.id.in_(all_attr_ids)).all():
            attr_users[u.id] = u.name or u.email or f"User {u.id}"

    def _names_for(ids: list[int]) -> list[str]:
        return [attr_users[i] for i in ids if i in attr_users]

    def _item_payload(item, product):
        item_ids = _attribution_user_ids(item)
        return {
            "receipt_item_id": item.id,
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
            "attribution_user_id": item.attribution_user_id,
            "attribution_user_ids": item_ids,
            "attribution_user_names": _names_for(item_ids),
            "attribution_kind": item.attribution_kind,
            "attribution_user_name": attr_users.get(item_ids[0]) if item_ids else None,
            "latest_snapshot": _latest_snapshot_for_receipt_item(session, item.id),
        }

    response_payload = {
        "id": purchase.id if purchase else receipt_record.id,
        "store": store.name if store else None,
        "total": purchase.total_amount if purchase else None,
        "date": purchase.date.strftime("%Y-%m-%d") if purchase and purchase.date else None,
        "status": receipt_record.status if receipt_record else "processed",
        "ocr_engine": receipt_record.ocr_engine if receipt_record else None,
        "confidence": receipt_record.ocr_confidence if receipt_record else None,
        "receipt_type": receipt_record.receipt_type if receipt_record else None,
        "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None) if purchase else None),
        "refund_reason": getattr(purchase, "refund_reason", None) if purchase else None,
        "refund_note": getattr(purchase, "refund_note", None) if purchase else None,
        "default_spending_domain": getattr(purchase, "default_spending_domain", None) if purchase else None,
        "default_budget_category": getattr(purchase, "default_budget_category", None) if purchase else None,
        "attribution_user_id": purchase.attribution_user_id if purchase else None,
        "attribution_user_ids": purchase_attr_ids,
        "attribution_user_names": _names_for(purchase_attr_ids),
        "attribution_kind": purchase.attribution_kind if purchase else None,
        "attribution_user_name": attr_users.get(purchase_attr_ids[0]) if purchase_attr_ids else None,
        "source": _receipt_source_label(receipt_record) if receipt_record else "upload",
        "created_at": receipt_record.created_at.isoformat() if receipt_record and receipt_record.created_at else None,
        "image_url": f"/receipts/{purchase.id if purchase else receipt_record.id}/image" if receipt_record and receipt_record.image_path else None,
        "file_type": _detect_receipt_file_type(receipt_record.image_path if receipt_record else None),
        "signed_total": signed_purchase_total(purchase) if purchase else None,
        "raw_ocr_data": raw_ocr_data,
        "editable_data": editable_data,
        "items": [
            _item_payload(item, product)
            for item, product in items
        ],
    }
    response_payload.update(bill_payload)

    return jsonify(response_payload), 200


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
    from src.backend.normalize_store_names import canonicalize_store_name

    session = g.db_session
    limit = request.args.get("limit", 50, type=int)
    store_filter = request.args.get("store", "").strip()
    status_filter = request.args.get("status", "").strip().lower()
    source_filter = request.args.get("source", "").strip().lower()
    receipt_type_filter = request.args.get("receipt_type", "").strip().lower()
    transaction_type_filter = request.args.get("transaction_type", "").strip().lower()
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
        canonical_store = canonicalize_store_name(store_filter)
        query = query.filter(func.lower(Store.name) == canonical_store.lower())
    if status_filter:
        query = query.filter(TelegramReceipt.status == status_filter)
    if receipt_type_filter:
        query = query.filter(TelegramReceipt.receipt_type == receipt_type_filter)
    if transaction_type_filter == "refund":
        query = query.filter(Purchase.transaction_type == "refund")
    elif transaction_type_filter == "purchase":
        query = query.filter(or_(Purchase.transaction_type.is_(None), Purchase.transaction_type != "refund"))
    if source_filter == "manual":
        query = query.filter(TelegramReceipt.telegram_user_id.startswith("manual:"))
    elif source_filter == "telegram":
        query = query.filter(~TelegramReceipt.telegram_user_id.startswith("upload"))
        query = query.filter(~TelegramReceipt.telegram_user_id.startswith("manual:"))
    elif source_filter == "upload":
        query = query.filter(TelegramReceipt.telegram_user_id.startswith("upload"))
    # Purchase-date range — for review-status receipts that have no
    # Purchase row yet, fall back to upload date so they don't get
    # invisibly filtered out and trap users who can't find their
    # freshly-uploaded receipt.
    if purchase_date_from:
        query = query.filter(
            or_(
                Purchase.date >= purchase_date_from,
                and_(
                    Purchase.id.is_(None),
                    TelegramReceipt.created_at >= purchase_date_from,
                ),
            )
        )
    if purchase_date_to:
        query = query.filter(
            or_(
                Purchase.date < purchase_date_to + timedelta(days=1),
                and_(
                    Purchase.id.is_(None),
                    TelegramReceipt.created_at < purchase_date_to + timedelta(days=1),
                ),
            )
        )
    if upload_date_from:
        query = query.filter(TelegramReceipt.created_at >= upload_date_from)
    if upload_date_to:
        query = query.filter(TelegramReceipt.created_at < upload_date_to + timedelta(days=1))

    # Attribution filter — apply in SQL so the 50-row display cap doesn't
    # hide matching rows past the top of the list, and so per-store /
    # per-month summaries reflect the same filtered set.
    #
    # Matches if EITHER the Purchase itself OR any of its ReceiptItems
    # carries a matching tag. Supports multi-select (comma-separated
    # tokens) with OR-union semantics across tokens.
    #
    # Token grammar: "household" | "unset" | "user:<id>"
    attribution_raw = (request.args.get("attribution", "") or "").strip().lower()
    attribution_tokens = [t.strip() for t in attribution_raw.split(",") if t.strip()]

    def _user_id_matches(col_single, col_json, target_uid: int):
        """Match if legacy single col equals uid OR json array contains uid.

        SQLite `json_each` scans the array; works whether the column is
        null, an empty array, or a populated array. `target_uid` is
        validated as int before reaching here, so safe to interpolate.
        """
        table = col_json.table.name
        col = col_json.key
        json_has = sql_text(
            f"EXISTS (SELECT 1 FROM json_each({table}.{col}) "
            f"WHERE value = {int(target_uid)})"
        )
        return or_(col_single == target_uid, json_has)

    if attribution_tokens:
        conditions = []
        for token in attribution_tokens:
            if token == "household":
                item_match = session.query(ReceiptItem.purchase_id).filter(
                    ReceiptItem.attribution_kind == "household"
                )
                conditions.append(
                    or_(
                        Purchase.attribution_kind == "household",
                        Purchase.id.in_(item_match),
                    )
                )
            elif token == "unset":
                any_tagged_item_ids = session.query(ReceiptItem.purchase_id).filter(
                    or_(
                        ReceiptItem.attribution_kind.isnot(None),
                        ReceiptItem.attribution_user_id.isnot(None),
                        and_(
                            ReceiptItem.attribution_user_ids.isnot(None),
                            ReceiptItem.attribution_user_ids != "[]",
                        ),
                    )
                )
                conditions.append(
                    and_(
                        Purchase.attribution_kind.is_(None),
                        Purchase.attribution_user_id.is_(None),
                        or_(
                            Purchase.attribution_user_ids.is_(None),
                            Purchase.attribution_user_ids == "[]",
                        ),
                        ~Purchase.id.in_(any_tagged_item_ids),
                    )
                )
            elif token.startswith("user:"):
                try:
                    uid = int(token.split(":", 1)[1])
                except (TypeError, ValueError):
                    continue
                purchase_match = _user_id_matches(
                    Purchase.attribution_user_id, Purchase.attribution_user_ids, uid
                )
                item_uid_match = _user_id_matches(
                    ReceiptItem.attribution_user_id, ReceiptItem.attribution_user_ids, uid
                )
                item_match = session.query(ReceiptItem.purchase_id).filter(item_uid_match)
                conditions.append(
                    or_(
                        purchase_match,
                        Purchase.id.in_(item_match),
                    )
                )
        if conditions:
            query = query.filter(or_(*conditions))

    records = query.order_by(TelegramReceipt.created_at.desc()).all()
    limited_records = records[:max(1, min(limit, 200))]

    # Plaid-linkage map: purchase_id -> True when ≥1 confirmed staged
    # transaction points at it. Used to render a "Plaid" badge on
    # auto-merged receipt rows so users see both sources without
    # duplicate rows.
    from src.backend.initialize_database_schema import PlaidStagedTransaction as _PST
    _purchase_ids_seen = [p.id for _r, p, _s in records if p and p.id]
    plaid_linked_purchase_ids: set[int] = set()
    if _purchase_ids_seen:
        for (pid,) in (
            session.query(_PST.confirmed_purchase_id)
            .filter(_PST.confirmed_purchase_id.in_(_purchase_ids_seen))
            .distinct()
            .all()
        ):
            if pid is not None:
                plaid_linked_purchase_ids.add(pid)

    stores = sorted({
        canonicalize_store_name(row[0])
        for row in session.query(Store.name).filter(Store.name.isnot(None)).distinct().all()
        if row[0]
    })

    store_counts = {}
    month_summary = {}
    refund_count = 0
    purchase_count = 0
    refund_total = 0.0
    for record, purchase, store in records:
        store_name = canonicalize_store_name(store.name) if store and store.name else "Unknown"
        store_counts[store_name] = store_counts.get(store_name, 0) + 1
        if purchase:
            if normalize_transaction_type(getattr(purchase, "transaction_type", None)) == "refund":
                refund_count += 1
                refund_total += abs(signed_purchase_total(purchase))
            else:
                purchase_count += 1
        if purchase and purchase.date:
            month_key = purchase.date.strftime("%Y-%m")
            month_entry = month_summary.setdefault(
                month_key,
                {"count": 0, "purchase_count": 0, "refund_count": 0, "total_amount": 0.0, "refund_total": 0.0, "receipts": []},
            )
            month_entry["count"] += 1
            signed_total = signed_purchase_total(purchase)
            month_entry["total_amount"] += signed_total
            if normalize_transaction_type(getattr(purchase, "transaction_type", None)) == "refund":
                month_entry["refund_count"] += 1
                month_entry["refund_total"] += abs(signed_total)
            else:
                month_entry["purchase_count"] += 1
            month_entry["receipts"].append({
                "receipt_id": purchase.id,
                "record_id": record.id,
                "store": store_name,
                "date": purchase.date.strftime("%Y-%m-%d"),
                "total": signed_total,
                "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None)),
                "refund_reason": getattr(purchase, "refund_reason", None),
                "refund_note": getattr(purchase, "refund_note", None),
                "source": _receipt_source_label(record),
                "linked_to_plaid": purchase.id in plaid_linked_purchase_ids,
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

    # Pre-resolve user names for the returned purchases so the list view
    # can render badges without a follow-up /auth/users round-trip.
    from src.backend.initialize_database_schema import User as _AttrUser
    attr_user_ids = sorted({
        p.attribution_user_id
        for _r, p, _s in limited_records
        if p and getattr(p, "attribution_user_id", None)
    })
    attr_user_names = {}
    if attr_user_ids:
        for u in session.query(_AttrUser).filter(_AttrUser.id.in_(attr_user_ids)).all():
            attr_user_names[u.id] = u.name or u.email or f"User {u.id}"

    return jsonify({
        "receipts": [
            {
                "id": purchase.id if purchase else record.id,
                "record_id": record.id,
                "purchase_id": purchase.id if purchase else None,
                "store": canonicalize_store_name(store.name) if store and store.name else None,
                "total": purchase.total_amount if purchase else None,
                "signed_total": signed_purchase_total(purchase) if purchase else None,
                "date": purchase.date.strftime("%Y-%m-%d") if purchase and purchase.date else None,
                "status": record.status,
                "ocr_engine": record.ocr_engine,
                "confidence": record.ocr_confidence,
                "receipt_type": record.receipt_type,
                "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None) if purchase else None),
                "refund_reason": getattr(purchase, "refund_reason", None) if purchase else None,
                "refund_note": getattr(purchase, "refund_note", None) if purchase else None,
                "attribution_user_id": getattr(purchase, "attribution_user_id", None) if purchase else None,
                "attribution_kind": getattr(purchase, "attribution_kind", None) if purchase else None,
                "attribution_user_name": attr_user_names.get(getattr(purchase, "attribution_user_id", None)) if purchase else None,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "source": _receipt_source_label(record),
                "linked_to_plaid": (purchase is not None) and (purchase.id in plaid_linked_purchase_ids),
                "image_url": f"/receipts/{purchase.id if purchase else record.id}/image" if record.image_path else None,
                "file_type": _detect_receipt_file_type(record.image_path),
                "error_message": record.error_message,
                "retry_count": record.retry_count or 0,
                "last_reprocessed_at": record.last_reprocessed_at.isoformat() if record.last_reprocessed_at else None,
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
            "transaction_types": ["purchase", "refund"],
        },
        "summary": {
            "total_receipts": len(records),
            "purchase_count": purchase_count,
            "refund_count": refund_count,
            "refund_total": round(refund_total, 2),
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
                    "purchase_count": values["purchase_count"],
                    "refund_count": values["refund_count"],
                    "total_amount": round(values["total_amount"], 2),
                    "refund_total": round(values["refund_total"], 2),
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
    if receipt_type not in {"grocery", "restaurant", "general_expense", "utility_bill", "household_bill"}:
        return jsonify({"error": "Receipt type must be grocery, restaurant, general_expense, utility_bill, or household_bill"}), 400

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

    # Tell the browser to save the file under a human-readable name.
    download_name = None
    try:
        from src.backend.receipt_filename_index import format_receipt_label
        store_name = None
        receipt_date = None
        if purchase:
            from src.backend.initialize_database_schema import Store
            if purchase.store_id:
                store = session.query(Store).filter_by(id=purchase.store_id).first()
                store_name = store.name if store else None
            receipt_date = purchase.date
        download_name = format_receipt_label(
            store=store_name,
            date=receipt_date,
            extension=image_path.suffix,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not derive download filename: %s", exc)

    if download_name:
        return send_file(image_path, download_name=download_name)
    return send_file(image_path)


@receipts_bp.route("/<int:receipt_id>/approve", methods=["POST"])
@require_write_access
def approve_receipt(receipt_id):
    """Approve a review receipt using edited or stored OCR payload."""
    from src.backend.initialize_database_schema import TelegramReceipt, Purchase
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

    receipt_type = payload.get("receipt_type") or record.receipt_type or classify_receipt_data(ocr_data)
    # Only grocery/pharmacy/restaurant genuinely need itemization —
    # everything else (utility/bill/general expense/retail/event/
    # unknown) is "a total at a merchant" and shouldn't force the user
    # to fabricate line items. Previously General Expense / Event
    # receipts (e.g. a glamping booking, concert ticket) couldn't be
    # saved without fake items.
    _ITEMLESS_TYPES = {
        "utility_bill", "household_bill", "general_expense",
        "retail_items", "event", "unknown",
    }
    requires_items = str(receipt_type or "").strip().lower() not in _ITEMLESS_TYPES
    required_fields = ("store", "date", "total") if not requires_items else ("store", "date", "items", "total")
    missing = [field for field in required_fields if not ocr_data.get(field)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    if requires_items and (not isinstance(ocr_data.get("items"), list) or not ocr_data["items"]):
        return jsonify({"error": "At least one receipt item is required"}), 400

    current_user = getattr(g, "current_user", None)
    user_id = current_user.id if current_user else None
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

    # Auto-suggest attribution from uploader+store history. High
    # confidence is silently applied right here; medium is returned
    # so the upload-review modal can pre-select it without
    # committing.
    attribution_suggestion: dict | None = None
    auto_applied = False
    saved_purchase = (
        session.query(Purchase).filter_by(id=purchase_id).first()
    )
    has_user_ids_set = (
        saved_purchase
        and saved_purchase.attribution_user_ids
        and saved_purchase.attribution_user_ids != "[]"
    )
    if (
        saved_purchase
        and not saved_purchase.attribution_user_id
        and not saved_purchase.attribution_kind
        and not has_user_ids_set
    ):
        suggestion = _suggest_attribution_for_upload(
            session,
            uploader_id=user_id,
            store_id=saved_purchase.store_id,
        )
        if suggestion and suggestion["confidence"] == "high":
            _bulk_apply_attribution(
                session,
                purchase_ids=[purchase_id],
                user_ids=suggestion["user_ids"],
                kind=suggestion["kind"],
                apply_to_items=True,
            )
            session.commit()
            auto_applied = True
            attribution_suggestion = suggestion
        elif suggestion:
            attribution_suggestion = suggestion

    return jsonify({
        "status": "processed",
        "purchase_id": purchase_id,
        "receipt_id": record.id,
        "receipt_type": receipt_type,
        "attribution_suggestion": attribution_suggestion,
        "attribution_auto_applied": auto_applied,
    }), 200


@receipts_bp.route("/bulk-update", methods=["PUT"])
@require_write_access
def bulk_update_receipts():
    """Apply receipt_type and/or default_budget_category to many
    receipts in one request.

    Body:
      {
        "ids": [int, ...],                     # purchase_ids
        "receipt_type": "grocery" | ... ,      # optional
        "default_budget_category": "grocery" | ... ,  # optional
      }

    At least one field must be provided. Per-row failures are skipped;
    the response reports how many rows succeeded.
    """
    from src.backend.initialize_database_schema import Purchase, TelegramReceipt
    from src.backend.budgeting_domains import (
        normalize_budget_category,
        derive_receipt_budget_defaults,
    )

    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"error": "ids must be a non-empty list"}), 400
    try:
        ids = sorted({int(x) for x in raw_ids})
    except (TypeError, ValueError):
        return jsonify({"error": "ids must be integers"}), 400

    receipt_type = (payload.get("receipt_type") or "").strip().lower() or None
    budget_cat_raw = (payload.get("default_budget_category") or "").strip().lower() or None
    if not receipt_type and not budget_cat_raw:
        return jsonify({"error": "Provide receipt_type or default_budget_category"}), 400

    valid_types = {
        "grocery", "restaurant", "general_expense", "retail_items",
        "household_bill", "utility_bill", "event", "unknown",
    }
    if receipt_type and receipt_type not in valid_types:
        return jsonify({"error": f"Invalid receipt_type: {receipt_type}"}), 400

    budget_cat = None
    if budget_cat_raw:
        budget_cat = normalize_budget_category(budget_cat_raw, default=None)
        if budget_cat is None:
            return jsonify({"error": f"Invalid budget category: {budget_cat_raw}"}), 400

    session = g.db_session
    purchases = session.query(Purchase).filter(Purchase.id.in_(ids)).all()
    by_id = {p.id: p for p in purchases}
    updated = 0
    skipped = []
    for pid in ids:
        purchase = by_id.get(pid)
        if not purchase:
            skipped.append({"id": pid, "reason": "not found"})
            continue
        if receipt_type:
            domain, default_cat = derive_receipt_budget_defaults(receipt_type)
            purchase.default_spending_domain = domain
            if not budget_cat:
                purchase.default_budget_category = default_cat
            tr = (
                session.query(TelegramReceipt)
                .filter_by(purchase_id=purchase.id)
                .order_by(TelegramReceipt.created_at.desc())
                .first()
            )
            if tr:
                tr.receipt_type = receipt_type
        if budget_cat:
            purchase.default_budget_category = budget_cat
        updated += 1
    session.commit()
    return jsonify({"updated": updated, "skipped": skipped}), 200


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
    bill_meta = payload.get("bill_meta") or {}
    if bill_meta and not isinstance(bill_meta, dict):
        return jsonify({"error": "bill_meta must be an object"}), 400
    merged_ocr_data = dict(ocr_data)
    if bill_meta:
        merged_ocr_data.update(bill_meta)

    sanitized = _sanitize_receipt_payload(merged_ocr_data)
    receipt_type = payload.get("receipt_type") or record.receipt_type or classify_receipt_data(sanitized)
    # Only grocery/pharmacy/restaurant genuinely need itemization —
    # everything else (utility/bill/general expense/retail/event/
    # unknown) is "a total at a merchant" and shouldn't force the user
    # to fabricate line items. Previously General Expense / Event
    # receipts (e.g. a glamping booking, concert ticket) couldn't be
    # saved without fake items.
    _ITEMLESS_TYPES = {
        "utility_bill", "household_bill", "general_expense",
        "retail_items", "event", "unknown",
    }
    # Plaid-sourced receipts only carry a total (no line items per transaction).
    # Even if the user re-classifies them to grocery / pharmacy / restaurant,
    # there is nothing to itemize — block-on-items would lock them out of
    # changing the type at all. Treat plaid origin as itemless regardless of
    # receipt_type.
    is_plaid_sourced = (record.ocr_engine or "").strip().lower() == "plaid"
    requires_items = (
        str(receipt_type or "").strip().lower() not in _ITEMLESS_TYPES
        and not is_plaid_sourced
    )
    required_fields = ("store", "date", "total") if not requires_items else ("store", "date", "items", "total")
    missing = [field for field in required_fields if not sanitized.get(field)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    if requires_items and not sanitized["items"]:
        return jsonify({"error": "At least one receipt item is required"}), 400

    current_user = getattr(g, "current_user", None)
    user_id = current_user.id if current_user else None
    purchase = session.query(Purchase).filter_by(id=record.purchase_id).first() if record.purchase_id else None

    # Snapshot per-item attribution before the clear+recreate wipes it.
    # /update deletes and rebuilds receipt_items from the sanitized payload,
    # which carries no attribution fields — without this snapshot, every
    # save-receipt-edit silently untags everything the user previously tagged.
    preserved_item_attribution: dict = {}
    if purchase:
        from src.backend.initialize_database_schema import ReceiptItem as _RI
        for it in session.query(_RI).filter_by(purchase_id=purchase.id).all():
            if it.attribution_user_id or it.attribution_user_ids or it.attribution_kind:
                slot = preserved_item_attribution.setdefault(it.product_id, [])
                slot.append({
                    "user_id": it.attribution_user_id,
                    "user_ids": it.attribution_user_ids,
                    "kind": it.attribution_kind,
                })

    if purchase:
        _clear_purchase_detail_data(session, purchase)
        session.flush()

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

    # Restore per-item attribution onto the freshly-recreated rows.
    # Match by product_id; when multiple items share a product_id, consume
    # the snapshot slots in order so each row gets back its own tag.
    if preserved_item_attribution:
        from src.backend.initialize_database_schema import ReceiptItem as _RI2
        rebuilt = (
            session.query(_RI2)
            .filter_by(purchase_id=purchase_id)
            .order_by(_RI2.id)
            .all()
        )
        for it in rebuilt:
            slot = preserved_item_attribution.get(it.product_id)
            if slot:
                saved = slot.pop(0)
                it.attribution_user_id = saved["user_id"]
                it.attribution_user_ids = saved["user_ids"]
                it.attribution_kind = saved["kind"]

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
    """Re-run OCR for an existing stored receipt and update its review payload.

    OCR is run before any destructive DB work; the existing Purchase is only
    replaced if the new pass returns valid data. If OCR fails or the data
    fails validation, the previous receipt is preserved intact.
    """
    from src.backend.initialize_database_schema import Purchase
    from src.backend.extract_receipt_data import (
        _apply_receipt_type_hint,
        _cleanup_ocr_input,
        _extract_best_receipt_candidate,
        _prepare_ocr_input,
        _resolve_receipt_type,
        _safe_float,
        _save_to_database,
        _validate_receipt_data,
    )

    session = g.db_session
    record = _resolve_receipt_record(session, receipt_id)
    if not record or not record.image_path:
        return jsonify({"error": "Receipt not found"}), 404

    current_user = getattr(g, "current_user", None)
    user_id = current_user.id if current_user else None
    payload = request.get_json(silent=True) or {}
    raw_model_id = payload.get("model_id")
    model_config_id = None
    if raw_model_id not in (None, "", 0):
        try:
            model_config_id = int(raw_model_id)
        except (TypeError, ValueError):
            return jsonify({"error": "model_id must be an integer"}), 400

    receipt_type_hint = record.receipt_type

    ocr_input_path = record.image_path
    ocr_data = None
    engine_used = None
    warnings = []
    try:
        ocr_input_path = _prepare_ocr_input(record.image_path)
        ocr_data, engine_used, _model_used, warnings = _extract_best_receipt_candidate(
            ocr_input_path=ocr_input_path,
            source_file_path=record.image_path,
            receipt_type_hint=receipt_type_hint,
            model_config_id=model_config_id,
        )
    except Exception as exc:
        logger.error("Reprocess OCR failed for receipt %s: %s", record.id, exc)
        # Update error tracking on reprocess failure
        record.retry_count = (record.retry_count or 0) + 1
        record.last_reprocessed_at = datetime.utcnow()
        record.error_message = f"OCR failed: {exc}"
        session.commit()
        return jsonify({
            "error": f"OCR failed: {exc}. Previous receipt data preserved.",
        }), 422
    finally:
        if ocr_input_path != record.image_path:
            _cleanup_ocr_input(ocr_input_path)

    ocr_data = _apply_receipt_type_hint(ocr_data or {}, receipt_type_hint)
    receipt_type = _resolve_receipt_type(ocr_data, receipt_type_hint)
    if not _validate_receipt_data(ocr_data, receipt_type=receipt_type):
        # Update error tracking on validation failure
        record.retry_count = (record.retry_count or 0) + 1
        record.last_reprocessed_at = datetime.utcnow()
        record.error_message = "OCR returned incomplete data"
        session.commit()
        return jsonify({
            "error": "OCR returned incomplete data. Previous receipt data preserved.",
            "warnings": warnings,
        }), 422

    # OCR is known-good — now safe to replace the existing Purchase.
    existing_purchase = (
        session.query(Purchase).filter_by(id=record.purchase_id).first()
        if record.purchase_id
        else None
    )

    # Snapshot user-controlled toggles on the old bill_meta so re-running
    # OCR does not wipe them (OCR never returns these).
    preserved_bill_meta = {}
    if existing_purchase:
        from src.backend.initialize_database_schema import BillMeta
        old_meta = (
            session.query(BillMeta)
            .filter_by(purchase_id=existing_purchase.id)
            .first()
        )
        if old_meta:
            preserved_bill_meta = {
                "bill_auto_pay": bool(old_meta.auto_pay),
                "_preserved_payment_status": old_meta.payment_status,
                "_preserved_payment_confirmed_at": old_meta.payment_confirmed_at,
            }

    if existing_purchase:
        _delete_purchase_data(session, existing_purchase)
        record.purchase_id = None
        session.flush()

    # Fold preserved user toggles into the OCR payload before saving.
    if "bill_auto_pay" in preserved_bill_meta:
        ocr_data["bill_auto_pay"] = preserved_bill_meta["bill_auto_pay"]

    purchase_id = _save_to_database(
        ocr_data, engine_used, record.image_path, user_id, receipt_type,
    )

    if preserved_bill_meta.get("_preserved_payment_status") in {"paid", "overdue"}:
        from src.backend.initialize_database_schema import BillMeta
        new_meta = session.query(BillMeta).filter_by(purchase_id=purchase_id).first()
        if new_meta:
            new_meta.payment_status = preserved_bill_meta["_preserved_payment_status"]
            new_meta.payment_confirmed_at = preserved_bill_meta.get(
                "_preserved_payment_confirmed_at"
            )

    record.purchase_id = purchase_id
    record.status = "processed"
    record.receipt_type = receipt_type
    record.raw_ocr_json = json.dumps(ocr_data)
    record.ocr_engine = engine_used
    record.ocr_confidence = _safe_float(ocr_data.get("confidence", 1.0))
    # Clear error on successful reprocess
    record.error_message = None
    record.retry_count = (record.retry_count or 0) + 1
    record.last_reprocessed_at = datetime.utcnow()
    session.commit()

    return jsonify({
        "status": "processed",
        "purchase_id": purchase_id,
        "receipt_id": record.id,
        "receipt_type": receipt_type,
        "warnings": warnings,
    }), 200


@receipts_bp.route("/cleanup-failed", methods=["POST"])
@require_write_access
def cleanup_failed_receipts():
    """Delete all TelegramReceipt rows that failed OCR and never produced a Purchase.

    Also removes the underlying image file from disk where possible. Returns a
    count of records deleted so the UI can report it.
    """
    from src.backend.initialize_database_schema import TelegramReceipt
    import os

    session = g.db_session
    failed_records = (
        session.query(TelegramReceipt)
        .filter(TelegramReceipt.status == "failed")
        .filter(TelegramReceipt.purchase_id.is_(None))
        .all()
    )
    deleted_paths = []
    for record in failed_records:
        if record.image_path and os.path.isfile(record.image_path):
            try:
                os.remove(record.image_path)
                deleted_paths.append(record.image_path)
            except OSError as exc:
                logger.warning("Could not remove failed receipt image %s: %s", record.image_path, exc)
        session.delete(record)
    session.commit()
    return jsonify({
        "deleted_count": len(failed_records),
        "image_files_removed": len(deleted_paths),
    }), 200


# ---------------------------------------------------------------------------
# Phase 3 — retroactive dedup scan + merge
# ---------------------------------------------------------------------------
# Users who already have duplicate receipts from before Guard B was in place
# need a way to find them and consolidate. dedup-scan walks the user's
# Purchase table and returns candidate pairs using the same merchant
# alias + amount/date tolerances as the staged-confirm auto-match. merge
# then collapses the drop into the keep: reparent nullable refs, delete
# unique-constrained sidecars on drop, delete drop Purchase.
# ---------------------------------------------------------------------------

def _merge_pick_keep_drop(a, b, a_items: int, b_items: int, a_has_image: bool, b_has_image: bool):
    """Heuristic: return (keep, drop) given two merge candidates.

    Priority: more receipt_items → has OCR image → earliest created.
    """
    if a_items != b_items:
        return (a, b) if a_items > b_items else (b, a)
    if a_has_image != b_has_image:
        return (a, b) if a_has_image else (b, a)
    # Fall back to earlier id (older row is the one the user has been
    # referencing longer; merge newer dupe into it).
    return (a, b) if a.id < b.id else (b, a)


@receipts_bp.route("/dedup-scan", methods=["GET"])
@require_auth
def dedup_scan_receipts():
    """Scan the current user's Purchases for duplicate pairs.

    Returns a list of candidate pairs {keep_id, drop_id, ...} using the
    same tolerances as the Plaid matcher (±$0.02, ±3 days, alias/token
    merchant match). Keep vs drop is suggested by `_merge_pick_keep_drop`.

    Scales to ~10k Purchases comfortably (bucket by date, compare within
    ±3-day window). Larger users can filter by date range via ?since=.
    """
    from datetime import datetime as _dt, timedelta as _td
    from sqlalchemy import func as _func
    from src.backend.initialize_database_schema import (
        DedupDismissal,
        Purchase,
        ReceiptItem,
        Store,
        TelegramReceipt,
    )
    from src.backend.plaid_receipt_matcher import (
        AMOUNT_EPSILON,
        DATE_WINDOW_DAYS,
        merchants_match,
    )

    user = getattr(g, "current_user", None)
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    user_id = user.id

    session = g.db_session

    # Optional narrowing window — default: 180 days back.
    since_raw = request.args.get("since")
    since = None
    if since_raw:
        try:
            since = _dt.fromisoformat(since_raw)
        except ValueError:
            return jsonify({"error": "since must be ISO date"}), 400
    else:
        since = _dt.utcnow() - _td(days=180)

    q = (
        session.query(Purchase, Store)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .filter(Purchase.user_id == user_id)
        .filter(Purchase.date >= since)
        .order_by(Purchase.date.asc(), Purchase.id.asc())
    )
    rows = q.all()
    if not rows:
        return jsonify({"pairs": [], "scanned": 0}), 200

    # Pre-compute item counts and image presence in bulk to avoid N+1.
    purchase_ids = [p.id for p, _ in rows]
    item_counts = dict(
        session.query(ReceiptItem.purchase_id, _func.count(ReceiptItem.id))
        .filter(ReceiptItem.purchase_id.in_(purchase_ids))
        .group_by(ReceiptItem.purchase_id)
        .all()
    )
    receipt_by_purchase: dict[int, TelegramReceipt] = {}
    for r in (
        session.query(TelegramReceipt)
        .filter(TelegramReceipt.purchase_id.in_(purchase_ids))
        .all()
    ):
        # Prefer the first (oldest) receipt record per purchase.
        if r.purchase_id not in receipt_by_purchase:
            receipt_by_purchase[r.purchase_id] = r

    # Pairs the user has explicitly marked as NOT duplicates — filter these
    # out so a false-positive (e.g. two same-day, same-amount legit charges
    # at one merchant) doesn't keep resurfacing after each scan.
    dismissed_pairs: set[tuple[int, int]] = {
        (row.purchase_id_low, row.purchase_id_high)
        for row in session.query(DedupDismissal)
        .filter(DedupDismissal.user_id == user_id)
        .all()
    }

    pairs = []
    seen_drop_ids: set[int] = set()
    # Window-compare: for each row, compare against forward rows within
    # ±DATE_WINDOW_DAYS until the date delta exceeds the window.
    for i, (p_i, s_i) in enumerate(rows):
        if p_i.id in seen_drop_ids:
            continue
        amount_i = abs(float(p_i.total_amount or 0))
        if amount_i == 0:
            continue
        for j in range(i + 1, len(rows)):
            p_j, s_j = rows[j]
            if p_j.id in seen_drop_ids:
                continue
            # Bail as soon as the date window is exceeded (rows are sorted).
            date_delta = (p_j.date - p_i.date).days
            if date_delta > DATE_WINDOW_DAYS:
                break
            amount_j = abs(float(p_j.total_amount or 0))
            if abs(amount_i - amount_j) > AMOUNT_EPSILON:
                continue
            name_i = s_i.name if s_i else None
            name_j = s_j.name if s_j else None
            if not merchants_match(name_i, name_j):
                continue
            # User has already told us this pair is NOT a duplicate.
            pair_key = (min(p_i.id, p_j.id), max(p_i.id, p_j.id))
            if pair_key in dismissed_pairs:
                continue

            items_i = int(item_counts.get(p_i.id, 0))
            items_j = int(item_counts.get(p_j.id, 0))
            rec_i = receipt_by_purchase.get(p_i.id)
            rec_j = receipt_by_purchase.get(p_j.id)
            img_i = bool(rec_i and rec_i.image_path)
            img_j = bool(rec_j and rec_j.image_path)

            keep, drop = _merge_pick_keep_drop(p_i, p_j, items_i, items_j, img_i, img_j)
            keep_store = s_i if keep is p_i else s_j
            drop_store = s_i if drop is p_i else s_j
            keep_items = items_i if keep is p_i else items_j
            drop_items = items_i if drop is p_i else items_j
            keep_has_image = img_i if keep is p_i else img_j

            pairs.append({
                "keep_id": keep.id,
                "drop_id": drop.id,
                "keep": {
                    "purchase_id": keep.id,
                    "store": keep_store.name if keep_store else None,
                    "total_amount": float(keep.total_amount or 0),
                    "date": keep.date.date().isoformat() if keep.date else None,
                    "item_count": keep_items,
                    "has_image": keep_has_image,
                },
                "drop": {
                    "purchase_id": drop.id,
                    "store": drop_store.name if drop_store else None,
                    "total_amount": float(drop.total_amount or 0),
                    "date": drop.date.date().isoformat() if drop.date else None,
                    "item_count": drop_items,
                },
            })
            # Don't flag drop again against a third row.
            seen_drop_ids.add(drop.id)
            # Also skip the window-forward comparisons from this i once
            # we've found a partner — we only want one pair per i.
            break

    return jsonify({
        "pairs": pairs,
        "scanned": len(rows),
        "since": since.isoformat() if since else None,
    }), 200


def _auto_merge_with_existing_match(session, new_purchase, user_id, *, new_image_path: str | None = None):
    """If `new_purchase` matches an existing Purchase (±$0.02/±3d/merchant
    alias), merge them and return (kept_purchase_id, True). Else return
    (new_purchase.id, False).

    Called from receipt-creation paths to auto-tie a freshly-created OCR
    purchase to an already-existing Plaid-promoted purchase (or vice
    versa). Heuristic prefers the row with more items / has-image / older
    id. The other row's nullable FKs (including
    plaid_staged_transactions.confirmed_purchase_id) reparent to the keep,
    so the staged transaction stays linked.

    `new_image_path` lets callers signal that the new purchase will get
    an image once its TelegramReceipt is linked (TelegramReceipt may not
    exist yet at this point). Treated as has_image=True for the keep/drop
    heuristic.

    Caller must call session.commit() afterwards.
    """
    from datetime import timedelta as _td
    from src.backend.initialize_database_schema import (
        Purchase,
        ReceiptItem,
        Store,
        TelegramReceipt,
    )
    from src.backend.plaid_receipt_matcher import (
        AMOUNT_EPSILON,
        DATE_WINDOW_DAYS,
        merchants_match,
    )

    if new_purchase is None or new_purchase.id is None:
        return (None, False)

    store = session.query(Store).filter_by(id=new_purchase.store_id).first() if new_purchase.store_id else None
    merchant_name = store.name if store else None
    target = abs(float(new_purchase.total_amount or 0))
    if target <= 0:
        return (new_purchase.id, False)
    if new_purchase.date is None:
        return (new_purchase.id, False)
    lo = new_purchase.date - _td(days=DATE_WINDOW_DAYS)
    hi = new_purchase.date + _td(days=DATE_WINDOW_DAYS + 1)

    rows = (
        session.query(Purchase, Store)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .filter(Purchase.user_id == user_id)
        .filter(Purchase.id != new_purchase.id)
        .filter(Purchase.date >= lo)
        .filter(Purchase.date < hi)
        .order_by(Purchase.date.desc(), Purchase.id.desc())
        .all()
    )

    chosen = None
    for p, s in rows:
        if abs((p.total_amount or 0) - target) > AMOUNT_EPSILON:
            continue
        s_name = s.name if s else None
        if not merchants_match(merchant_name, s_name):
            continue
        chosen = p
        break

    if chosen is None:
        return (new_purchase.id, False)

    new_items = session.query(ReceiptItem).filter_by(purchase_id=new_purchase.id).count()
    other_items = session.query(ReceiptItem).filter_by(purchase_id=chosen.id).count()
    new_rec = session.query(TelegramReceipt).filter_by(purchase_id=new_purchase.id).first()
    other_rec = session.query(TelegramReceipt).filter_by(purchase_id=chosen.id).first()
    new_has_image = bool((new_rec and new_rec.image_path) or new_image_path)
    other_has_image = bool(other_rec and other_rec.image_path)

    keep, drop = _merge_pick_keep_drop(
        new_purchase, chosen, new_items, other_items, new_has_image, other_has_image
    )
    _merge_purchase_pair(session, keep, drop)
    session.flush()

    # Post-merge cleanup: when the caller is about to attach an image
    # (new_image_path provided), drop any image-less TelegramReceipt rows
    # that ended up on the keep — typically the Plaid placeholder TR that
    # was reparented during the merge. Otherwise the receipts list shows
    # duplicate rows (Plaid + Upload) for the same Purchase.
    if new_image_path:
        placeholder_trs = (
            session.query(TelegramReceipt)
            .filter(TelegramReceipt.purchase_id == keep.id)
            .filter((TelegramReceipt.image_path.is_(None)) | (TelegramReceipt.image_path == ""))
            .all()
        )
        for tr in placeholder_trs:
            session.delete(tr)
        session.flush()
    return (keep.id, True)


def _merge_purchase_pair(session, keep, drop) -> None:
    """Merge `drop` into `keep`: reparent nullable FKs, move unique-
    constrained sidecars only when keep has none, delete drop Purchase.

    Caller must commit. Caller is responsible for ownership/permission
    checks; this is a pure data-plane helper.
    """
    from src.backend.initialize_database_schema import (
        BillAllocation,
        BillMeta,
        CashTransaction,
        PlaidStagedTransaction,
        ProductSnapshot,
        ReceiptItem,
        TelegramReceipt,
    )

    # --- Reparent nullable FKs drop → keep -----------------------------
    session.query(ProductSnapshot).filter_by(purchase_id=drop.id).update(
        {"purchase_id": keep.id}, synchronize_session=False
    )
    session.query(PlaidStagedTransaction).filter_by(
        confirmed_purchase_id=drop.id
    ).update({"confirmed_purchase_id": keep.id}, synchronize_session=False)
    session.query(PlaidStagedTransaction).filter_by(
        duplicate_purchase_id=drop.id
    ).update({"duplicate_purchase_id": keep.id}, synchronize_session=False)

    # --- TelegramReceipt — keep keep's receipt, delete drop's ----------
    keep_receipt = session.query(TelegramReceipt).filter_by(purchase_id=keep.id).first()
    drop_receipts = session.query(TelegramReceipt).filter_by(purchase_id=drop.id).all()
    for rec in drop_receipts:
        if keep_receipt is None:
            rec.purchase_id = keep.id
            keep_receipt = rec
        else:
            session.delete(rec)

    # --- ReceiptItem — reparent any drop items to keep -----------------
    session.query(ReceiptItem).filter_by(purchase_id=drop.id).update(
        {"purchase_id": keep.id}, synchronize_session=False
    )

    # --- BillAllocation — reparent ------------------------------------
    session.query(BillAllocation).filter_by(purchase_id=drop.id).update(
        {"purchase_id": keep.id}, synchronize_session=False
    )

    # --- BillMeta — unique per purchase; move only if keep has none ----
    keep_bm = session.query(BillMeta).filter_by(purchase_id=keep.id).first()
    drop_bm = session.query(BillMeta).filter_by(purchase_id=drop.id).first()
    if drop_bm is not None:
        if keep_bm is None:
            drop_bm.purchase_id = keep.id
        else:
            session.delete(drop_bm)

    # --- CashTransaction — unique per purchase; move if keep has none --
    keep_ct = session.query(CashTransaction).filter_by(purchase_id=keep.id).first()
    drop_ct = session.query(CashTransaction).filter_by(purchase_id=drop.id).first()
    if drop_ct is not None:
        if keep_ct is None:
            drop_ct.purchase_id = keep.id
        else:
            session.delete(drop_ct)

    session.flush()
    session.delete(drop)


@receipts_bp.route("/auto-link-plaid", methods=["POST"])
@require_write_access
def auto_link_plaid_receipts():
    """Backfill: merge any pre-existing Plaid+Upload duplicate pairs.

    Walks the user's recent Purchases (default ±180 days). For every
    candidate pair where ONE side is linked to a plaid_staged_transaction
    and the OTHER has an image-bearing TelegramReceipt (OCR upload),
    auto-merges them into one row. Only merges Plaid+OCR pairs — pure
    OCR+OCR duplicates need user judgment via the existing
    /receipts/dedup-scan + manual /receipts/merge flow.

    Idempotent: running twice returns 0 the second time.
    """
    from datetime import datetime as _dt, timedelta as _td
    from src.backend.initialize_database_schema import (
        DedupDismissal,
        PlaidStagedTransaction,
        Purchase,
        Store,
        TelegramReceipt,
    )
    from src.backend.plaid_receipt_matcher import (
        AMOUNT_EPSILON,
        DATE_WINDOW_DAYS,
        merchants_match,
    )

    user = getattr(g, "current_user", None)
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    user_id = user.id

    session = g.db_session

    since_raw = request.args.get("since")
    if since_raw:
        try:
            since = _dt.fromisoformat(since_raw)
        except ValueError:
            return jsonify({"error": "since must be ISO date"}), 400
    else:
        since = _dt.utcnow() - _td(days=180)

    rows = (
        session.query(Purchase, Store)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .filter(Purchase.user_id == user_id)
        .filter(Purchase.date >= since)
        .order_by(Purchase.date.asc(), Purchase.id.asc())
        .all()
    )
    if not rows:
        return jsonify({"merged": 0, "scanned": 0}), 200

    # Bucket by which Plaid-staged ids reference each Purchase
    purchase_ids = [p.id for p, _s in rows]
    plaid_links = {}
    if purchase_ids:
        for staged_id, purchase_id in (
            session.query(PlaidStagedTransaction.id, PlaidStagedTransaction.confirmed_purchase_id)
            .filter(PlaidStagedTransaction.confirmed_purchase_id.in_(purchase_ids))
            .all()
        ):
            plaid_links.setdefault(purchase_id, []).append(staged_id)

    # Map Purchase id -> has-image bool (OCR upload signal)
    has_image_map = {}
    if purchase_ids:
        for tr_purchase_id, image_path in (
            session.query(TelegramReceipt.purchase_id, TelegramReceipt.image_path)
            .filter(TelegramReceipt.purchase_id.in_(purchase_ids))
            .all()
        ):
            if image_path:
                has_image_map[tr_purchase_id] = True

    dismissed_pairs = set()
    for low, high in (
        session.query(DedupDismissal.purchase_id_low, DedupDismissal.purchase_id_high)
        .all()
    ):
        dismissed_pairs.add((low, high))

    merged = 0
    merged_ids = []
    consumed: set[int] = set()
    n = len(rows)
    for i in range(n):
        if rows[i][0].id in consumed:
            continue
        a_p, a_s = rows[i]
        a_name = a_s.name if a_s else None
        a_total = abs(float(a_p.total_amount or 0))
        if a_total <= 0:
            continue
        for j in range(i + 1, n):
            if rows[j][0].id in consumed:
                continue
            b_p, b_s = rows[j]
            if (b_p.date - a_p.date).days > DATE_WINDOW_DAYS:
                break
            if abs(float(b_p.total_amount or 0) - a_total) > AMOUNT_EPSILON:
                continue
            if not merchants_match(a_name, b_s.name if b_s else None):
                continue
            low, high = (a_p.id, b_p.id) if a_p.id < b_p.id else (b_p.id, a_p.id)
            if (low, high) in dismissed_pairs:
                continue

            a_has_plaid = bool(plaid_links.get(a_p.id))
            b_has_plaid = bool(plaid_links.get(b_p.id))
            a_has_image = has_image_map.get(a_p.id, False)
            b_has_image = has_image_map.get(b_p.id, False)

            # Only auto-merge when one side is Plaid-linked and the
            # other has an OCR upload image. Pure OCR+OCR or pure
            # Plaid+Plaid pairs are left alone — those need user
            # judgment via the dedup-scan UI.
            is_plaid_ocr_pair = (
                (a_has_plaid and b_has_image and not b_has_plaid)
                or (b_has_plaid and a_has_image and not a_has_plaid)
            )
            if not is_plaid_ocr_pair:
                continue

            # Keep the side with the image (OCR) — staged FK reparents
            # to it via _merge_purchase_pair.
            if a_has_image:
                keep, drop = a_p, b_p
            else:
                keep, drop = b_p, a_p

            _merge_purchase_pair(session, keep, drop)
            session.flush()

            # Drop image-less placeholder TRs left on the keep
            placeholder_trs = (
                session.query(TelegramReceipt)
                .filter(TelegramReceipt.purchase_id == keep.id)
                .filter((TelegramReceipt.image_path.is_(None)) | (TelegramReceipt.image_path == ""))
                .all()
            )
            for tr in placeholder_trs:
                session.delete(tr)
            session.flush()

            consumed.add(drop.id)
            merged += 1
            merged_ids.append({"kept_purchase_id": keep.id, "dropped_purchase_id": drop.id})
            break  # this `a` is now merged into a keep — move to next i

    if merged:
        session.commit()

    return jsonify({
        "merged": merged,
        "scanned": len(rows),
        "pairs": merged_ids,
    }), 200


@receipts_bp.route("/merge", methods=["POST"])
@require_write_access
def merge_receipts():
    """Consolidate two Purchase rows into one.

    Body: {"keep_id": int, "drop_id": int}
    Both must be owned by the current user.
    """
    from src.backend.initialize_database_schema import Purchase

    user = getattr(g, "current_user", None)
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    user_id = user.id

    payload = request.get_json(silent=True) or {}
    try:
        keep_id = int(payload.get("keep_id"))
        drop_id = int(payload.get("drop_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "keep_id and drop_id must be integers"}), 400
    if keep_id == drop_id:
        return jsonify({"error": "keep_id and drop_id must differ"}), 400

    session = g.db_session
    keep = session.query(Purchase).filter_by(id=keep_id, user_id=user_id).first()
    drop = session.query(Purchase).filter_by(id=drop_id, user_id=user_id).first()
    if not keep or not drop:
        return jsonify({"error": "Purchase not found or not owned by you"}), 404

    _merge_purchase_pair(session, keep, drop)
    session.commit()

    return jsonify({
        "kept_purchase_id": keep.id,
        "dropped_purchase_id": drop_id,
    }), 200


@receipts_bp.route("/dedup-dismiss", methods=["POST"])
@require_write_access
def dismiss_dedup_pair():
    """Persist a "these are NOT duplicates" decision for two Purchase ids.

    Body: {"keep_id": int, "drop_id": int} — the two ids from a dedup-scan
    pair. Names match merge's payload for UI symmetry; the endpoint stores
    them as an unordered pair (low < high) so a single row covers both
    directions. Future dedup-scan runs skip any pair present here.
    """
    from src.backend.initialize_database_schema import DedupDismissal, Purchase

    user = getattr(g, "current_user", None)
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    user_id = user.id

    payload = request.get_json(silent=True) or {}
    try:
        a_id = int(payload.get("keep_id"))
        b_id = int(payload.get("drop_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "keep_id and drop_id must be integers"}), 400
    if a_id == b_id:
        return jsonify({"error": "keep_id and drop_id must differ"}), 400

    session = g.db_session
    # Both must belong to the caller — prevents cross-user pair poisoning.
    owned = (
        session.query(Purchase.id)
        .filter(Purchase.user_id == user_id, Purchase.id.in_([a_id, b_id]))
        .all()
    )
    if len(owned) != 2:
        return jsonify({"error": "Purchase not found or not owned by you"}), 404

    low, high = (a_id, b_id) if a_id < b_id else (b_id, a_id)

    existing = (
        session.query(DedupDismissal)
        .filter_by(user_id=user_id, purchase_id_low=low, purchase_id_high=high)
        .first()
    )
    if existing is None:
        session.add(DedupDismissal(
            user_id=user_id,
            purchase_id_low=low,
            purchase_id_high=high,
        ))
        session.commit()
        created = True
    else:
        created = False

    return jsonify({
        "dismissed": True,
        "created": created,
        "purchase_id_low": low,
        "purchase_id_high": high,
    }), 200


def _normalize_attribution_payload(data, session, User):
    """Parse + validate an attribution request body.

    Accepts either the new `user_ids: [int]` array or the legacy
    `user_id: int` scalar. Derives `kind` when not supplied:
      0 ids + kind=null        → cleared (untagged)
      0 ids + kind=household   → household
      1 id                     → personal (auto-derives kind)
      2+ ids                   → shared   (auto-derives kind)

    Returns (ok, result). On ok=True result is a dict with keys
    `user_ids` (list[int]), `kind` (str|None). On ok=False result is
    a (json_payload, status_code) tuple.
    """
    raw_kind = (data.get("kind") or "").strip().lower() or None
    if raw_kind not in (None, "household", "personal", "shared"):
        return False, ({"error": "kind must be 'household', 'personal', 'shared', or null"}, 400)

    raw_ids = data.get("user_ids")
    if raw_ids is None and "user_id" in data:
        single = data.get("user_id")
        raw_ids = [single] if single is not None else []
    if raw_ids is None:
        raw_ids = []
    if not isinstance(raw_ids, list):
        return False, ({"error": "user_ids must be a list"}, 400)

    user_ids: list[int] = []
    for v in raw_ids:
        try:
            user_ids.append(int(v))
        except (TypeError, ValueError):
            return False, ({"error": "user_ids must contain integers"}, 400)
    # De-dupe, preserve order.
    seen = set()
    user_ids = [i for i in user_ids if not (i in seen or seen.add(i))]

    if user_ids:
        found = session.query(User.id).filter(User.id.in_(user_ids)).all()
        found_ids = {r[0] for r in found}
        missing = [i for i in user_ids if i not in found_ids]
        if missing:
            return False, ({"error": f"user_ids do not exist: {missing}"}, 404)

    # Derive kind when omitted.
    if raw_kind is None:
        if len(user_ids) == 1:
            raw_kind = "personal"
        elif len(user_ids) >= 2:
            raw_kind = "shared"
        # 0 ids stays None (cleared)

    # Consistency checks.
    if raw_kind == "household" and user_ids:
        return False, ({"error": "kind='household' must not have user_ids"}, 400)
    if raw_kind == "personal" and len(user_ids) != 1:
        return False, ({"error": "kind='personal' requires exactly one user_id"}, 400)
    if raw_kind == "shared" and len(user_ids) < 2:
        return False, ({"error": "kind='shared' requires 2+ user_ids"}, 400)

    return True, {"user_ids": user_ids, "kind": raw_kind}


@receipts_bp.route("/<int:receipt_id>/attribution", methods=["PUT"])
@require_write_access
def update_receipt_attribution(receipt_id):
    """Tag a receipt as belonging to one/multiple household users, the
    whole household, or clear the tag.

    Body:
      { "user_ids": [int], "kind": "household"|"personal"|"shared"|null,
        "apply_to_items": bool }

    Legacy `user_id: int` is still accepted for backwards compat.
    """
    from src.backend.initialize_database_schema import Purchase, ReceiptItem, User

    session = g.db_session
    purchase = session.query(Purchase).filter_by(id=receipt_id).first()
    if not purchase:
        return jsonify({"error": "Receipt not found"}), 404

    data = request.get_json(silent=True) or {}
    apply_to_items = bool(data.get("apply_to_items", False))

    ok, result = _normalize_attribution_payload(data, session, User)
    if not ok:
        payload, status = result
        return jsonify(payload), status

    user_ids = result["user_ids"]
    kind = result["kind"]
    legacy_single = user_ids[0] if len(user_ids) == 1 else None
    ids_json = _serialize_user_ids(user_ids)

    purchase.attribution_user_id = legacy_single
    purchase.attribution_user_ids = ids_json
    purchase.attribution_kind = kind

    if apply_to_items:
        session.query(ReceiptItem).filter_by(purchase_id=purchase.id).update(
            {
                "attribution_user_id": legacy_single,
                "attribution_user_ids": ids_json,
                "attribution_kind": kind,
            },
            synchronize_session=False,
        )

    session.commit()
    return jsonify({
        "purchase_id": purchase.id,
        "attribution_user_id": purchase.attribution_user_id,
        "attribution_user_ids": user_ids,
        "attribution_kind": purchase.attribution_kind,
        "applied_to_items": apply_to_items,
    }), 200


def _bulk_apply_attribution(
    session,
    *,
    purchase_ids: list[int],
    user_ids: list[int],
    kind: str | None,
    apply_to_items: bool,
) -> dict:
    """Apply the same attribution to many Purchase rows.

    Pure-DB helper, no Flask. Returns
    ``{"updated": N, "skipped": [{"purchase_id": int, "reason": str}]}``.
    The caller is responsible for committing the session.
    """
    from src.backend.initialize_database_schema import Purchase, ReceiptItem

    legacy_single = user_ids[0] if len(user_ids) == 1 else None
    ids_json = _serialize_user_ids(user_ids)

    skipped: list[dict] = []
    updated = 0
    rows = (
        session.query(Purchase)
        .filter(Purchase.id.in_(purchase_ids))
        .all()
    )
    found_ids = {r.id for r in rows}
    for missing in purchase_ids:
        if missing not in found_ids:
            skipped.append({"purchase_id": missing, "reason": "not_found"})

    for row in rows:
        row.attribution_user_id = legacy_single
        row.attribution_user_ids = ids_json
        row.attribution_kind = kind
        updated += 1

    if apply_to_items and rows:
        ids = [r.id for r in rows]
        session.query(ReceiptItem).filter(
            ReceiptItem.purchase_id.in_(ids)
        ).update(
            {
                "attribution_user_id": legacy_single,
                "attribution_user_ids": ids_json,
                "attribution_kind": kind,
            },
            synchronize_session=False,
        )

    return {"updated": updated, "skipped": skipped}


@receipts_bp.route("/bulk-attribution", methods=["POST"])
@require_write_access
def bulk_update_receipt_attribution():
    """Apply the same attribution to many Purchase rows in one call.

    Body:
      { "purchase_ids": [int],
        "user_ids": [int],
        "kind": "household"|"personal"|"shared"|null,
        "apply_to_items": bool }
    """
    from src.backend.initialize_database_schema import User

    session = g.db_session
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("purchase_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"error": "purchase_ids must be a non-empty list"}), 400
    if len(raw_ids) > 200:
        return jsonify({"error": "Too many ids; max 200 per request"}), 400
    try:
        purchase_ids = [int(x) for x in raw_ids if x is not None]
    except (TypeError, ValueError):
        return jsonify({"error": "purchase_ids must be integers"}), 400
    purchase_ids = [pid for pid in purchase_ids if pid > 0]
    if not purchase_ids:
        return jsonify({"error": "purchase_ids must contain positive integers"}), 400

    ok, result = _normalize_attribution_payload(data, session, User)
    if not ok:
        payload, status = result
        return jsonify(payload), status

    bulk = _bulk_apply_attribution(
        session,
        purchase_ids=purchase_ids,
        user_ids=result["user_ids"],
        kind=result["kind"],
        apply_to_items=bool(data.get("apply_to_items", True)),
    )
    session.commit()
    return jsonify(bulk), 200


def _compute_attribution_stats(session) -> dict:
    """Counts of tagged vs untagged Purchase rows + a few sample
    untagged ids for the dashboard banner. Pure-DB helper.

    Definition of "untagged" matches the receipts-list ``unset``
    filter token (line ~1170): the Purchase has no attribution AND
    none of its ReceiptItems carry an attribution either.
    """
    from src.backend.initialize_database_schema import Purchase, ReceiptItem
    from sqlalchemy import or_, and_

    any_tagged_item_ids = session.query(ReceiptItem.purchase_id).filter(
        or_(
            ReceiptItem.attribution_kind.isnot(None),
            ReceiptItem.attribution_user_id.isnot(None),
            and_(
                ReceiptItem.attribution_user_ids.isnot(None),
                ReceiptItem.attribution_user_ids != "[]",
            ),
        )
    )
    untagged_filter = and_(
        Purchase.attribution_kind.is_(None),
        Purchase.attribution_user_id.is_(None),
        or_(
            Purchase.attribution_user_ids.is_(None),
            Purchase.attribution_user_ids == "[]",
        ),
        ~Purchase.id.in_(any_tagged_item_ids),
    )
    untagged_count = (
        session.query(Purchase).filter(untagged_filter).count()
    )
    total = session.query(Purchase).count()
    tagged_count = total - untagged_count
    sample_rows = (
        session.query(Purchase.id)
        .filter(untagged_filter)
        .order_by(Purchase.date.desc(), Purchase.id.desc())
        .limit(5)
        .all()
    )
    return {
        "untagged_count": int(untagged_count),
        "tagged_count": int(tagged_count),
        "untagged_sample_ids": [int(r[0]) for r in sample_rows],
    }


def _suggest_attribution_for_upload(
    session,
    *,
    uploader_id: int | None,
    store_id: int | None,
) -> dict | None:
    """Suggest attribution for a new Purchase row based on the
    uploader's history at the same store.

    Returns ``{"user_ids": [...], "kind": "...", "confidence":
    "high" | "medium"}`` or ``None``. Confidence:
      * 3+ of last 5 attributed receipts share the same
        (user_ids, kind) → high
      * 2 of 5 → medium
      * less → None
    """
    from src.backend.initialize_database_schema import Purchase
    from sqlalchemy import or_

    if not uploader_id or not store_id:
        return None

    rows = (
        session.query(Purchase)
        .filter(Purchase.user_id == uploader_id)
        .filter(Purchase.store_id == store_id)
        .filter(
            or_(
                Purchase.attribution_user_id.isnot(None),
                Purchase.attribution_kind.isnot(None),
            )
        )
        .order_by(Purchase.date.desc(), Purchase.id.desc())
        .limit(10)
        .all()
    )
    if len(rows) < 2:
        return None

    last_5 = rows[:5]
    counts: dict[tuple, int] = {}
    representative: dict[tuple, dict] = {}
    for r in last_5:
        ids_raw = r.attribution_user_ids
        try:
            parsed = json.loads(ids_raw) if ids_raw else []
            if not isinstance(parsed, list):
                parsed = []
        except (TypeError, ValueError):
            parsed = []
        if not parsed and r.attribution_user_id:
            parsed = [int(r.attribution_user_id)]
        ids_tuple = tuple(sorted(int(x) for x in parsed))
        kind = r.attribution_kind
        key = (ids_tuple, kind)
        counts[key] = counts.get(key, 0) + 1
        representative.setdefault(key, {
            "user_ids": list(ids_tuple),
            "kind": kind,
        })

    if not counts:
        return None
    top_key = max(counts, key=counts.get)
    top_count = counts[top_key]
    if top_count >= 3:
        confidence = "high"
    elif top_count == 2:
        confidence = "medium"
    else:
        return None

    payload = dict(representative[top_key])
    payload["confidence"] = confidence
    return payload


@receipts_bp.route("/attribution-stats", methods=["GET"])
@require_auth
def attribution_stats():
    """Return tagged/untagged purchase counts + sample untagged ids
    for the dashboard nudge banner."""
    return jsonify(_compute_attribution_stats(g.db_session)), 200


@receipts_bp.route("/<int:receipt_id>/items/<int:item_id>/attribution", methods=["PUT"])
@require_write_access
def update_receipt_item_attribution(receipt_id, item_id):
    """Set or clear per-line-item attribution.

    Body: { "user_ids": [int], "kind": "household"|"personal"|"shared"|null }
    Legacy `user_id: int` is still accepted.
    """
    from src.backend.initialize_database_schema import ReceiptItem, User

    session = g.db_session
    item = (
        session.query(ReceiptItem)
        .filter_by(id=item_id, purchase_id=receipt_id)
        .first()
    )
    if not item:
        return jsonify({"error": "Receipt item not found"}), 404

    data = request.get_json(silent=True) or {}
    ok, result = _normalize_attribution_payload(data, session, User)
    if not ok:
        payload, status = result
        return jsonify(payload), status

    user_ids = result["user_ids"]
    kind = result["kind"]
    legacy_single = user_ids[0] if len(user_ids) == 1 else None

    item.attribution_user_id = legacy_single
    item.attribution_user_ids = _serialize_user_ids(user_ids)
    item.attribution_kind = kind
    session.commit()
    return jsonify({
        "receipt_item_id": item.id,
        "attribution_user_id": item.attribution_user_id,
        "attribution_user_ids": user_ids,
        "attribution_kind": item.attribution_kind,
    }), 200


@receipts_bp.route("/<int:receipt_id>/bill-status", methods=["PUT"])
@require_write_access
def update_receipt_bill_status(receipt_id):
    """Update the payment lifecycle status of a household or utility bill."""
    from src.backend.initialize_database_schema import Base, BillMeta
    from datetime import timezone

    session = g.db_session
    record = _resolve_receipt_record(session, receipt_id)
    if not record:
        return jsonify({"error": "Receipt not found"}), 404

    payload = request.get_json(silent=True) or {}
    new_status = (payload.get("payment_status") or "").strip().lower()
    paid_date_raw = (payload.get("paid_date") or "").strip()

    valid_statuses = {"upcoming", "overdue", "paid", "estimated", "missing", "not_yet_entered"}
    if new_status not in valid_statuses:
        return jsonify({"error": f"Invalid payment_status. Must be one of {valid_statuses}"}), 400

    paid_date_value = None
    if paid_date_raw:
        try:
            paid_date_value = datetime.strptime(paid_date_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({"error": "paid_date must be YYYY-MM-DD"}), 400

    # Locate the Purchase because BillMeta ties to purchase_id
    purchase_id = getattr(record, "purchase_id", None) or getattr(record, "id", None)
    if not purchase_id:
        return jsonify({"error": "Receipt is not yet converted to a saved purchase"}), 400

    bill_meta = session.query(BillMeta).filter_by(purchase_id=purchase_id).first()
    if not bill_meta:
        return jsonify({"error": "This purchase is not configured as a household bill"}), 400

    bill_meta.payment_status = new_status
    if new_status == "paid":
        if paid_date_value is not None:
            bill_meta.payment_confirmed_at = paid_date_value
            bill_meta.payment_confirmed_by_id = getattr(getattr(g, "current_user", None), "id", None)
        elif not bill_meta.payment_confirmed_at:
            bill_meta.payment_confirmed_at = datetime.now(timezone.utc)
            bill_meta.payment_confirmed_by_id = getattr(getattr(g, "current_user", None), "id", None)
    else:
        # If toggled out of paid, clear payment confirmation
        bill_meta.payment_confirmed_at = None
        bill_meta.payment_confirmed_by_id = None

    session.commit()
    
    return jsonify({
        "message": "Bill status updated successfully",
        "payment_status": bill_meta.payment_status,
        "payment_confirmed_at": bill_meta.payment_confirmed_at.isoformat() if bill_meta.payment_confirmed_at else None,
        "paid_date": bill_meta.payment_confirmed_at.date().isoformat() if bill_meta.payment_confirmed_at else None,
    }), 200


@receipts_bp.route("/bills/sync-autopay", methods=["POST"])
@require_write_access
def sync_autopay_bills():
    """Mark any autopay bill whose effective due date has arrived as paid."""
    from src.backend.initialize_database_schema import BillMeta, Purchase
    from datetime import timezone, date as date_cls, timedelta
    from calendar import monthrange

    def _effective_due_date(meta, purchase):
        if meta.due_date:
            return meta.due_date, "due_date"
        cycle = (meta.billing_cycle_month or "").strip()
        if cycle:
            try:
                year, month = map(int, cycle.split("-", 1))
                last_day = monthrange(year, month)[1]
                return date_cls(year, month, last_day), "billing_cycle_month_end"
            except (ValueError, TypeError):
                pass
        if purchase and purchase.date:
            statement = purchase.date.date() if hasattr(purchase.date, "date") else purchase.date
            return statement + timedelta(days=21), "statement_plus_21d"
        return None, None

    session = g.db_session
    today = date_cls.today()
    candidates = (
        session.query(BillMeta, Purchase)
        .join(Purchase, Purchase.id == BillMeta.purchase_id)
        .filter(BillMeta.auto_pay.is_(True))
        .filter(BillMeta.payment_status.in_(["upcoming", "overdue"]))
        .all()
    )
    swept = []
    current_user_id = getattr(getattr(g, "current_user", None), "id", None)
    for meta, purchase in candidates:
        effective_due, source = _effective_due_date(meta, purchase)
        if effective_due is None or effective_due > today:
            continue
        meta.payment_status = "paid"
        meta.payment_confirmed_at = datetime.combine(effective_due, datetime.min.time()).replace(tzinfo=timezone.utc)
        meta.payment_confirmed_by_id = current_user_id
        swept.append({
            "purchase_id": meta.purchase_id,
            "provider_name": meta.provider_name,
            "due_date": effective_due.isoformat(),
            "due_date_source": source,
        })
    if swept:
        session.commit()
    return jsonify({"swept_count": len(swept), "swept": swept}), 200


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


@receipts_bp.route("/bill-providers", methods=["GET"])
@require_auth
def list_bill_providers():
    """Return all known bill providers and their service lines for autocomplete lookup."""
    from src.backend.initialize_database_schema import BillProvider
    from src.backend.manage_cash_transactions import serialize_bill_provider

    session = g.db_session
    providers = session.query(BillProvider).filter_by(is_active=True).all()
    results = [serialize_bill_provider(provider) for provider in providers]
    return jsonify({"providers": results}), 200


@receipts_bp.route("/bills/projection/<string:month>", methods=["GET"])
@require_auth
def get_bill_projection(month):
    """
    Get the obligation projection slots for a specific planning month.
    Month format should be YYYY-MM.
    """
    import re
    if not re.match(r"^\d{4}-\d{2}$", month):
        return jsonify({"error": "Month must be in YYYY-MM format"}), 400

    from src.backend.generate_bill_projections import generate_monthly_obligation_slots

    try:
        session = g.db_session
        slots = generate_monthly_obligation_slots(session, month)
        return jsonify({
            "planning_month": month,
            "slots": slots
        }), 200
    except Exception as exc:
        logger.error("Failed to generate bill projections for %s: %s", month, exc)
        return jsonify({"error": "Failed to generate projections"}), 500


@receipts_bp.route("/<int:receipt_id>", methods=["DELETE"])
@require_write_access
def delete_receipt(receipt_id):
    """Delete a receipt record, its stored file, and any associated purchase data."""
    from src.backend.initialize_database_schema import (
        TelegramReceipt, Purchase, ReceiptItem, PriceHistory, Inventory, BillMeta,
        PlaidStagedTransaction,
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

            # Delete bill_meta sidecar if present (utility bills)
            session.query(BillMeta).filter_by(purchase_id=purchase.id).delete(synchronize_session=False)
            session.query(ReceiptItem).filter_by(purchase_id=purchase.id).delete(synchronize_session=False)
            session.query(TelegramReceipt).filter(TelegramReceipt.purchase_id == purchase.id).delete(synchronize_session=False)

            # Clear FKs from plaid_staged_transactions before deleting the
            # Purchase. PRAGMA foreign_keys=ON would otherwise abort the
            # delete with a FOREIGN KEY constraint violation. Reset
            # confirmed staged rows back to ready_to_import so the user can
            # re-handle them; clear duplicate_purchase_id pointers too.
            session.query(PlaidStagedTransaction).filter(
                PlaidStagedTransaction.confirmed_purchase_id == purchase.id
            ).update(
                {"confirmed_purchase_id": None, "confirmed_at": None, "status": "ready_to_import"},
                synchronize_session=False,
            )
            session.query(PlaidStagedTransaction).filter(
                PlaidStagedTransaction.duplicate_purchase_id == purchase.id
            ).update(
                {"duplicate_purchase_id": None},
                synchronize_session=False,
            )

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
