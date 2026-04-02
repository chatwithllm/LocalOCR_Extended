"""
Step 11: Implement Hybrid OCR Processor
========================================
PROMPT Reference: Phase 3, Step 11

Orchestrates the Gemini → Ollama fallback logic for receipt processing.
Validates OCR output, auto-updates inventory on success, and ensures
Telegram users always receive feedback (when triggered via Telegram).

Fallback chain: Gemini → Ollama → Manual Review
Confidence threshold: ≥0.40 (aligned with scaled confidence formulas)
"""

import logging
import os
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from flask import g

from src.backend.active_inventory import rebuild_active_inventory
from src.backend.enrich_product_names import should_enrich_product_name
from src.backend.normalize_product_names import (
    canonicalize_product_identity,
    find_matching_product,
)
from src.backend.contribution_scores import validate_low_workflow
from src.backend.normalize_store_names import canonicalize_store_name, find_matching_store

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.80  # Flag for manual review below this
MIN_CONFIDENCE = 0.40        # Reject entirely below this

NON_PRODUCT_PATTERNS = (
    "discount",
    "coupon",
    "savings",
    "instant savings",
    "store savings",
    "digital coupon",
    "manufacturer coupon",
    "promo",
    "promotion",
    "member savings",
)


def _safe_float(value, default=0.0):
    """Return a float for persistence/logging even when OCR returns null/string values."""
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _is_non_product_line(item_data: dict) -> bool:
    """Return True for discounts, coupons, and other non-merchandise lines."""
    name = str(item_data.get("name", "") or "").strip().lower()
    if not name:
        return True

    if any(token in name for token in NON_PRODUCT_PATTERNS):
        return True

    if name.endswith(" savings") or name.startswith("savings "):
        return True

    category = str(item_data.get("category", "") or "").strip().lower()
    if category in {"discount", "coupon", "promotion"}:
        return True

    unit_price = _safe_float(item_data.get("unit_price", 0.0), 0.0)
    quantity = _safe_float(item_data.get("quantity", 1), 1.0)
    if unit_price < 0 or quantity < 0:
        return True

    return False


# ---------------------------------------------------------------------------
# Hybrid OCR Processor
# ---------------------------------------------------------------------------

def process_receipt(image_path: str, source: str = "upload",
                    chat_id: str = None, user_id: int = None,
                    receipt_record_id: int | None = None) -> dict:
    """Process a receipt image through the hybrid OCR pipeline.

    Args:
        image_path: Path to the receipt image file.
        source: Origin of the receipt — "telegram" or "upload"
        chat_id: Telegram chat ID (only set when source="telegram")
        user_id: ID of the user who uploaded (for audit trail)

    Returns:
        Dictionary with processed receipt data and status.
    """
    result = {
        "status": "pending",
        "image_path": image_path,
        "source": source,
        "ocr_engine": None,
        "data": None,
        "confidence": 0.0,
        "error": None,
    }

    ocr_data = None
    engine_used = None
    ocr_input_path = image_path

    try:
        ocr_input_path = _prepare_ocr_input(image_path)

        # --- Step 1: Try Gemini ---
        try:
            from src.backend.call_gemini_vision_api import extract_receipt_via_gemini
            ocr_data = extract_receipt_via_gemini(ocr_input_path, source_file_path=image_path)
            engine_used = "gemini"
            logger.info("Gemini OCR succeeded.")
        except Exception as e:
            logger.warning(f"Gemini OCR failed: {e}. Falling back to OpenAI.")

            # --- Step 2: Fallback to OpenAI ---
            try:
                from src.backend.call_openai_vision_api import extract_receipt_via_openai
                ocr_data = extract_receipt_via_openai(ocr_input_path)
                engine_used = "openai"
                logger.info("OpenAI OCR fallback succeeded.")
            except Exception as e2:
                logger.warning(f"OpenAI OCR failed: {e2}. Falling back to Ollama.")

                # --- Step 3: Fallback to Ollama ---
                try:
                    from src.backend.call_ollama_vision_api import extract_receipt_via_ollama
                    ocr_data = extract_receipt_via_ollama(ocr_input_path)
                    engine_used = "ollama"
                    logger.info("Ollama OCR fallback succeeded.")
                except Exception as e3:
                    logger.error(f"All OCR engines failed. Gemini: {e}; OpenAI: {e2}; Ollama: {e3}")
                    result["status"] = "failed"
                    result["error"] = f"All OCR engines failed. Gemini: {e}; OpenAI: {e2}; Ollama: {e3}"

                    if source == "telegram" and chat_id:
                        _send_telegram_error(chat_id)

                _save_receipt_record(
                    image_path, None, None, "failed", 0.0,
                    _get_receipt_actor_id(source, chat_id, user_id),
                    receipt_record_id=receipt_record_id,
                    receipt_type=result.get("receipt_type"),
                    raw_ocr_data=None,
                )
                return result
    finally:
        if ocr_input_path != image_path:
            _cleanup_ocr_input(ocr_input_path)

    # --- Step 3: Validate & Route ---
    if ocr_data:
        result["data"] = ocr_data
        result["ocr_engine"] = engine_used
        result["confidence"] = _safe_float(ocr_data.get("confidence", 0.0))
        result["receipt_type"] = classify_receipt_data(ocr_data)

        is_valid = _validate_receipt_data(ocr_data)

        if is_valid and result["confidence"] >= CONFIDENCE_THRESHOLD:
            # High confidence — auto-process
            result["status"] = "processed"
            purchase_id = _save_to_database(
                ocr_data, engine_used, image_path, user_id, result["receipt_type"]
            )
            result["purchase_id"] = purchase_id
            _save_receipt_record(
                image_path, engine_used, purchase_id, "processed",
                result["confidence"], _get_receipt_actor_id(source, chat_id, user_id),
                receipt_record_id=receipt_record_id,
                receipt_type=result["receipt_type"],
                raw_ocr_data=ocr_data,
            )

            if source == "telegram" and chat_id:
                _send_telegram_success(chat_id, ocr_data)

        elif is_valid and result["confidence"] >= MIN_CONFIDENCE:
            # Medium confidence — save but flag for review
            result["status"] = "review"
            purchase_id = _save_to_database(
                ocr_data, engine_used, image_path, user_id, result["receipt_type"]
            )
            result["purchase_id"] = purchase_id
            _save_receipt_record(
                image_path, engine_used, purchase_id, "review",
                result["confidence"], _get_receipt_actor_id(source, chat_id, user_id),
                receipt_record_id=receipt_record_id,
                receipt_type=result["receipt_type"],
                raw_ocr_data=ocr_data,
            )

            if source == "telegram" and chat_id:
                _send_telegram_warning(chat_id)

        else:
            # Low confidence or invalid — manual review
            result["status"] = "review"
            _save_receipt_record(
                image_path, engine_used, None, "review",
                result["confidence"], _get_receipt_actor_id(source, chat_id, user_id),
                receipt_record_id=receipt_record_id,
                receipt_type=result["receipt_type"],
                raw_ocr_data=ocr_data,
            )

            if source == "telegram" and chat_id:
                _send_telegram_warning(chat_id)

    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_receipt_data(data: dict) -> bool:
    """Validate that OCR output contains all required fields."""
    required_fields = ["store", "date", "items", "total"]
    for field in required_fields:
        if field not in data or data[field] is None:
            logger.warning(f"Validation failed: missing field '{field}'")
            return False

    if not isinstance(data["items"], list) or len(data["items"]) == 0:
        logger.warning("Validation failed: items must be a non-empty list")
        return False

    # Validate each item has at least name and unit_price
    for i, item in enumerate(data["items"]):
        if not item.get("name"):
            logger.warning(f"Validation: item {i} missing 'name'")
            return False
        if item.get("unit_price") is None:
            logger.warning(f"Validation: item {i} missing 'unit_price'")
            # Don't fail — some items might be discounts at $0.00

    return True


def classify_receipt_data(data: dict) -> str:
    """Classify receipt into grocery, retail_items, restaurant, or unknown."""
    store = str(data.get("store", "")).lower()
    items = data.get("items", []) or []
    item_names = " ".join(str(item.get("name", "")).lower() for item in items)
    categories = [str(item.get("category", "")).lower() for item in items if item.get("category")]
    category_set = set(categories)

    grocery_store_keywords = {
        "kroger", "walmart", "aldi", "meijer", "costco", "safeway",
        "whole foods", "trader joe", "publix", "target", "sam's club"
    }
    restaurant_store_keywords = {
        "mcdonald", "burger king", "taco bell", "chipotle", "starbucks",
        "subway", "pizza", "restaurant", "cafe", "bar", "grill"
    }
    retail_store_keywords = {
        "best buy", "home depot", "lowe", "ikea", "walgreens", "cvs",
        "macys", "kohls", "tj maxx", "marshall", "office depot"
    }
    grocery_categories = {
        "dairy", "produce", "meat", "seafood", "bakery", "beverages",
        "snacks", "frozen", "canned", "condiments", "household", "personal_care"
    }
    retail_categories = {"electronics", "apparel", "hardware", "office", "pharmacy", "home"}
    restaurant_terms = {
        "burger", "fries", "drink", "combo", "sandwich", "pizza", "salad",
        "soda", "coffee", "latte", "tip", "gratuity", "server", "table"
    }

    if any(keyword in store for keyword in grocery_store_keywords) or category_set.intersection(grocery_categories):
        return "grocery"
    if any(keyword in store for keyword in retail_store_keywords) or category_set.intersection(retail_categories):
        return "retail_items"
    if any(keyword in store for keyword in restaurant_store_keywords) or any(term in item_names for term in restaurant_terms):
        return "restaurant"

    if items:
        food_like_hits = sum(
            1 for item in items
            if str(item.get("category", "")).lower() in grocery_categories
            or any(term in str(item.get("name", "")).lower() for term in ("milk", "bread", "eggs", "cheese", "apple", "banana"))
        )
        if food_like_hits >= max(1, len(items) // 2):
            return "grocery"

    return "unknown"


def _prepare_ocr_input(file_path: str) -> str:
    """Render PDFs to a temporary PNG so the OCR engines can process them."""
    if Path(file_path).suffix.lower() != ".pdf":
        return file_path

    output_dir = tempfile.mkdtemp(prefix="receipt-pdf-")
    output_prefix = os.path.join(output_dir, "page")

    try:
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-f", "1",
                "-singlefile",
                file_path,
                output_prefix,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        _cleanup_temp_dir(output_dir)
        raise RuntimeError("PDF receipts require 'pdftoppm' to be installed on the server.") from exc
    except subprocess.CalledProcessError as exc:
        _cleanup_temp_dir(output_dir)
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"Failed to render PDF receipt: {stderr or exc}") from exc

    rendered_path = f"{output_prefix}.png"
    if not os.path.exists(rendered_path):
        _cleanup_temp_dir(output_dir)
        raise RuntimeError("Failed to render PDF receipt: no PNG output was produced.")

    logger.info("Rendered PDF receipt for OCR: %s -> %s", file_path, rendered_path)
    return rendered_path


def _cleanup_ocr_input(ocr_input_path: str):
    """Remove temporary OCR artifacts created from PDF receipts."""
    try:
        temp_dir = Path(ocr_input_path).parent
        if temp_dir.name.startswith("receipt-pdf-") and temp_dir.is_dir():
            _cleanup_temp_dir(temp_dir)
    except Exception as exc:
        logger.warning("Failed to clean temporary OCR input %s: %s", ocr_input_path, exc)


def _cleanup_temp_dir(temp_dir: str | Path):
    """Best-effort removal for temporary OCR directories."""
    path = Path(temp_dir)
    if not path.exists():
        return
    for child in path.iterdir():
        child.unlink(missing_ok=True)
    path.rmdir()


# ---------------------------------------------------------------------------
# Database Persistence
# ---------------------------------------------------------------------------

def _save_to_database(ocr_data: dict, engine: str, image_path: str,
                       user_id: int = None, receipt_type: str = "grocery") -> int:
    """Save validated OCR data to purchases, receipt_items, and price_history."""
    try:
        from src.backend.initialize_database_schema import (
            Purchase, ReceiptItem, Product, Store, PriceHistory
        )
        session = g.db_session

        # Find or create store
        store_name = canonicalize_store_name(ocr_data.get("store", "Unknown Store"))
        store = find_matching_store(session, store_name)
        if not store:
            store = Store(
                name=store_name,
                location=ocr_data.get("store_location"),
            )
            session.add(store)
            session.flush()

        # Create purchase record
        purchase_date = ocr_data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        purchase = Purchase(
            store_id=store.id,
            total_amount=_safe_float(ocr_data.get("total", 0.0)),
            date=datetime.strptime(str(purchase_date), "%Y-%m-%d"),
            user_id=user_id,
        )
        session.add(purchase)
        session.flush()

        # Process each item
        persisted_items = []
        for item_data in ocr_data.get("items", []):
            if _is_non_product_line(item_data):
                logger.info("Skipping non-product receipt line: %s", item_data.get("name"))
                continue

            product_name, category = canonicalize_product_identity(
                item_data.get("name", "Unknown Item"),
                item_data.get("category", "other"),
            )
            quantity = _safe_float(item_data.get("quantity", 1), 1.0)
            unit_price = _safe_float(item_data.get("unit_price", 0.0), 0.0)

            # Find or create product
            product = find_matching_product(session, product_name, category)
            if not product:
                product = Product(
                    name=product_name,
                    raw_name=item_data.get("name", product_name),
                    display_name=product_name,
                    review_state="pending" if should_enrich_product_name(item_data.get("name", product_name), category) else "resolved",
                    category=category,
                )
                session.add(product)
                session.flush()

            # Create receipt item
            receipt_item = ReceiptItem(
                purchase_id=purchase.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=unit_price,
                extracted_by=engine,
            )
            session.add(receipt_item)

            # Update price history
            ph = PriceHistory(
                product_id=product.id,
                store_id=store.id,
                price=unit_price,
                date=purchase.date,
            )
            session.add(ph)
            persisted_items.append(item_data)
            session.flush()
            validate_low_workflow(
                session,
                product_id=product.id,
                purchase_id=purchase.id,
                product_name=product.display_name or product.name,
            )

            session.commit()

        logger.info(
            f"Saved receipt: {store_name} | ${_safe_float(ocr_data.get('total', 0)):.2f} | "
            f"{len(ocr_data.get('items', []))} items | purchase_id={purchase.id}"
        )

        if receipt_type in {"grocery", "retail_items"}:
            rebuild_active_inventory(session)
            session.commit()
            _publish_inventory_updates(session, persisted_items)

        return purchase.id

    except Exception as e:
        logger.error(f"Failed to save receipt to database: {e}")
        session.rollback()
        raise


def _publish_inventory_updates(session, items):
    """Publish MQTT events for all updated products."""
    try:
        from src.backend.publish_mqtt_events import publish_inventory_update
        from src.backend.initialize_database_schema import Product, Inventory

        for item_data in items:
            product = session.query(Product).filter_by(
                name=item_data.get("name", "")
            ).first()
            if product:
                inv = session.query(Inventory).filter_by(
                    product_id=product.id
                ).first()
                if inv:
                    publish_inventory_update(
                        product_id=product.id,
                        name=product.name,
                        quantity=inv.quantity,
                        location=inv.location or "Pantry",
                        updated_by="system",
                    )
    except Exception as e:
        logger.warning(f"Failed to publish MQTT updates: {e}")


def _save_receipt_record(
    image_path,
    engine,
    purchase_id,
    status,
    confidence,
    user_id,
    receipt_record_id: int | None = None,
    receipt_type: str | None = None,
    raw_ocr_data: dict | None = None,
):
    """Save a minimal receipt record for failed/review items."""
    try:
        from src.backend.initialize_database_schema import TelegramReceipt
        session = g.db_session

        record = None
        if receipt_record_id is not None:
            record = session.query(TelegramReceipt).filter_by(id=receipt_record_id).first()

        if not record:
            record = TelegramReceipt(
                telegram_user_id=str(user_id or "unknown"),
                image_path=image_path,
            )
            session.add(record)
        elif not record.telegram_user_id:
            record.telegram_user_id = str(user_id or "unknown")

        if not record.telegram_user_id:
            record.telegram_user_id = str(user_id or "unknown")
        record.image_path = image_path
        record.status = status
        record.ocr_confidence = confidence
        record.ocr_engine = engine
        record.receipt_type = receipt_type
        record.raw_ocr_json = json.dumps(raw_ocr_data) if raw_ocr_data is not None else record.raw_ocr_json
        record.purchase_id = purchase_id
        session.commit()
    except Exception as e:
        logger.warning(f"Failed to save receipt record: {e}")


def _get_receipt_actor_id(source: str, chat_id: str | None, user_id: int | None) -> str:
    """Build a stable actor/source identifier for receipt history records."""
    if source == "telegram" and chat_id:
        return str(chat_id)
    if user_id is not None:
        return f"{source}:{user_id}"
    return source


# ---------------------------------------------------------------------------
# Telegram Feedback
# ---------------------------------------------------------------------------

def _send_telegram_success(chat_id: str, data: dict):
    """Send success confirmation to Telegram user."""
    try:
        from src.backend.handle_telegram_messages import send_telegram_message
        item_count = len(data.get("items", []))
        store = data.get("store", "Unknown")
        total = _safe_float(data.get("total", 0), 0.0)
        receipt_type = classify_receipt_data(data)
        inventory_note = (
            "Added to inventory."
            if receipt_type in {"grocery", "retail_items"}
            else "Saved for reference only."
        )
        msg = (
            f"✅ Processed: ${total:.2f} at {store} | {item_count} items\n"
            f"Detected type: {receipt_type.replace('_', ' ')}\n"
            f"{inventory_note}"
        )
        send_telegram_message(chat_id, msg)
    except Exception as e:
        logger.warning(f"Failed to send Telegram success: {e}")


def _send_telegram_warning(chat_id: str):
    """Send low-confidence warning to Telegram user."""
    try:
        from src.backend.handle_telegram_messages import send_telegram_message
        send_telegram_message(chat_id, "⚠️ Low confidence — please review in Home Assistant")
    except Exception as e:
        logger.warning(f"Failed to send Telegram warning: {e}")


def _send_telegram_error(chat_id: str):
    """Send failure error to Telegram user."""
    try:
        from src.backend.handle_telegram_messages import send_telegram_message
        send_telegram_message(chat_id, "❌ Could not process receipt. Saved for manual review.")
    except Exception as e:
        logger.warning(f"Failed to send Telegram error: {e}")
