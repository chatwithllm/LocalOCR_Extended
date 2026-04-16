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
from typing import Any

from flask import g
from PIL import Image, ImageOps

from src.backend.active_inventory import rebuild_active_inventory
from src.backend.enrich_product_names import should_enrich_product_name
from src.backend.normalize_product_names import (
    canonicalize_product_identity,
    find_matching_product,
)
from src.backend.manage_product_catalog import _merge_products
from src.backend.contribution_scores import validate_low_workflow
from src.backend.budgeting_domains import (
    default_budget_category_for_spending_domain,
    derive_receipt_budget_defaults,
    normalize_budget_category,
    normalize_spending_domain,
    normalize_utility_service_types,
)
from src.backend.budgeting_rollups import normalize_transaction_type
from src.backend.bill_cadence import normalize_billing_cycle
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

PLACEHOLDER_TEXT_VALUES = {
    "",
    "store name",
    "product name",
    "unknown store",
    "unknown item",
    "yyyy-mm-dd",
    "hh:mm",
    "null",
}


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


def _is_placeholder_text(value: object) -> bool:
    """Return True for OCR scaffolding values that should not be treated as real data."""
    normalized = str(value or "").strip().lower()
    return normalized in PLACEHOLDER_TEXT_VALUES


def _is_valid_receipt_date(value: object) -> bool:
    """Validate receipt dates while tolerating OCR failures without crashing persistence."""
    if _is_placeholder_text(value):
        return False
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Hybrid OCR Processor
# ---------------------------------------------------------------------------

def process_receipt(image_path: str, source: str = "upload",
                    chat_id: str = None, user_id: int = None,
                    receipt_record_id: int | None = None,
                    receipt_type_hint: str | None = None,
                    model_config_id: int | None = None) -> dict:
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
        "warnings": [],
    }

    ocr_data = None
    engine_used = None
    model_used = None
    ocr_input_path = image_path

    try:
        ocr_input_path = _prepare_ocr_input(image_path)
        try:
            ocr_data, engine_used, model_used, warnings = _extract_best_receipt_candidate(
                ocr_input_path=ocr_input_path,
                source_file_path=image_path,
                receipt_type_hint=receipt_type_hint,
                model_config_id=model_config_id,
            )
            result["warnings"] = warnings or []
        except Exception as exc:
            logger.error("All OCR engines failed: %s", exc)
            result["status"] = "failed"
            result["error"] = str(exc)

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
        ocr_data = _apply_receipt_type_hint(ocr_data, receipt_type_hint)
        result["data"] = ocr_data
        result["ocr_engine"] = engine_used
        result["model_used"] = model_used
        result["confidence"] = _safe_float(ocr_data.get("confidence", 0.0))
        result["receipt_type"] = _resolve_receipt_type(ocr_data, receipt_type_hint)

        is_valid = _validate_receipt_data(ocr_data, receipt_type=result["receipt_type"])

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


def _extract_best_receipt_candidate(
    ocr_input_path: str,
    source_file_path: str,
    receipt_type_hint: str | None = None,
    model_config_id: int | None = None,
) -> tuple[dict, str, str | None, list[str]]:
    """Run OCR, optionally trying multiple rotated restaurant candidates and selecting the best one."""
    mode_hint = _normalize_receipt_type_hint(receipt_type_hint)
    ocr_data, engine_used, model_used, warnings = _run_ocr_with_fallback(
        image_path=ocr_input_path,
        source_file_path=source_file_path,
        mode_hint=mode_hint,
        model_config_id=model_config_id,
    )

    if not _should_run_restaurant_candidate_assist(ocr_data, mode_hint):
        return ocr_data, engine_used, model_used, warnings

    candidate_specs = [{"label": "base", "rotation": 0, "path": ocr_input_path}]
    candidate_specs.extend(_build_rotated_restaurant_candidates(ocr_input_path))

    best_data = ocr_data
    best_engine = engine_used
    best_model = model_used
    best_score = _score_restaurant_candidate(ocr_data)
    best_label = "base"

    for candidate in candidate_specs[1:]:
        try:
            candidate_data, candidate_engine, candidate_model, _candidate_warnings = _run_ocr_with_fallback(
                image_path=candidate["path"],
                source_file_path=source_file_path,
                mode_hint="restaurant",
                model_config_id=model_config_id,
            )
        except Exception as exc:
            logger.info("Restaurant OCR candidate %s failed: %s", candidate["label"], exc)
            continue

        candidate_score = _score_restaurant_candidate(candidate_data)
        logger.info(
            "Restaurant OCR candidate %s scored %.2f (%s, total=%s, items=%s)",
            candidate["label"],
            candidate_score,
            classify_receipt_data(candidate_data),
            candidate_data.get("total"),
            len(candidate_data.get("items", []) or []),
        )
        if candidate_score > best_score:
            best_data = candidate_data
            best_engine = candidate_engine
            best_model = candidate_model
            best_score = candidate_score
            best_label = candidate["label"]

    if best_label != "base":
        logger.info(
            "Restaurant OCR assist selected candidate %s over base result (score %.2f).",
            best_label,
            best_score,
        )

    for candidate in candidate_specs[1:]:
        _cleanup_ocr_input(candidate["path"])

    return best_data, best_engine, best_model, warnings


def _run_ocr_with_fallback(
    image_path: str,
    source_file_path: str,
    mode_hint: str | None = None,
    model_config_id: int | None = None,
) -> tuple[dict, str, str | None, list[str]]:
    """Run the OCR provider chain and return the first successful result."""
    from src.backend.route_ai_inference import resolve_ai_model_selection, route_receipt_inference

    errors: list[str] = []
    warnings: list[str] = []
    session = getattr(g, "db_session", None)
    current_user = getattr(g, "current_user", None)

    if session is not None:
        selected_model, warnings = resolve_ai_model_selection(
            session,
            requested_model_id=model_config_id,
            user=current_user,
        )
        if selected_model:
            routed = route_receipt_inference(
                image_path=image_path,
                source_file_path=source_file_path,
                mode_hint=mode_hint,
                model=selected_model,
            )
            logger.info(
                "Selected OCR provider succeeded: %s (%s)",
                routed["provider"],
                routed["model_string"],
            )
            return routed["data"], routed["provider"], routed["model_string"], warnings

    try:
        from src.backend.call_gemini_vision_api import extract_receipt_via_gemini

        data = extract_receipt_via_gemini(
            image_path,
            source_file_path=source_file_path,
            mode_hint=mode_hint,
        )
        logger.info("Gemini OCR succeeded.")
        return data, "gemini", None, warnings
    except Exception as exc:
        errors.append(f"Gemini: {exc}")
        logger.warning("Gemini OCR failed: %s. Falling back to OpenAI.", exc)

    try:
        from src.backend.call_openai_vision_api import extract_receipt_via_openai

        data = extract_receipt_via_openai(image_path, mode_hint=mode_hint)
        logger.info("OpenAI OCR fallback succeeded.")
        return data, "openai", None, warnings
    except Exception as exc:
        errors.append(f"OpenAI: {exc}")
        logger.warning("OpenAI OCR failed: %s. Falling back to Ollama.", exc)

    try:
        from src.backend.call_ollama_vision_api import extract_receipt_via_ollama

        data = extract_receipt_via_ollama(image_path, mode_hint=mode_hint)
        logger.info("Ollama OCR fallback succeeded.")
        return data, "ollama", None, warnings
    except Exception as exc:
        errors.append(f"Ollama: {exc}")
        raise RuntimeError("; ".join(errors)) from exc


def _should_run_restaurant_candidate_assist(ocr_data: dict, receipt_type_hint: str | None) -> bool:
    """Decide whether restaurant-specific multi-pass OCR is worth the extra work."""
    if receipt_type_hint == "restaurant":
        return True
    if classify_receipt_data(ocr_data) != "restaurant":
        return False
    return _score_restaurant_candidate(ocr_data) < 70


def _build_rotated_restaurant_candidates(image_path: str) -> list[dict[str, Any]]:
    """Generate rotated OCR candidates for hard restaurant photos."""
    candidates: list[dict[str, Any]] = []
    source_path = Path(image_path)
    if source_path.suffix.lower() == ".pdf":
        return candidates

    try:
        with Image.open(source_path) as image:
            normalized = ImageOps.exif_transpose(image)
            for degrees in (90, 180, 270):
                output_dir = tempfile.mkdtemp(prefix=f"receipt-restaurant-{degrees}-")
                rotated_path = Path(output_dir) / source_path.name
                normalized.rotate(degrees, expand=True).save(rotated_path)
                candidates.append(
                    {
                        "label": f"rotate-{degrees}",
                        "rotation": degrees,
                        "path": str(rotated_path),
                    }
                )
    except Exception as exc:
        logger.warning("Failed to create restaurant OCR candidates for %s: %s", image_path, exc)
    return candidates


def _score_restaurant_candidate(data: dict) -> float:
    """Heuristic score for restaurant OCR candidates so the editor starts with the best draft."""
    if not isinstance(data, dict):
        return -100.0

    score = 0.0
    receipt_type = classify_receipt_data(data)
    if receipt_type == "restaurant":
        score += 35

    confidence = _safe_float(data.get("confidence", 0.0), 0.0)
    score += min(confidence, 1.0) * 12

    total = _safe_float(data.get("total", 0.0), 0.0)
    subtotal = _safe_float(data.get("subtotal", 0.0), 0.0)
    tax = _safe_float(data.get("tax", 0.0), 0.0)
    tip = _safe_float(data.get("tip", 0.0), 0.0)

    if total > 0:
        score += 18
    if subtotal > 0:
        score += 8
    if tax > 0:
        score += 5
    if tip > 0:
        score += 4
    if total > 0 and subtotal > 0 and total >= subtotal:
        score += 5

    store = str(data.get("store", "") or "").strip()
    store_lower = store.lower()
    if store and store_lower not in {"unknown", "unknown store", "store name", "restaurant"}:
        score += 12
    if any(term in store_lower for term in ("restaurant", "cafe", "grill", "kitchen", "toast", "biryani", "kabob", "kebab")):
        score += 4

    if data.get("date"):
        score += 8
    if data.get("time"):
        score += 4

    items = data.get("items", []) or []
    meaningful_items = 0
    for item in items:
        name = str((item or {}).get("name", "") or "").strip()
        lower_name = name.lower()
        if not name:
            score -= 4
            continue
        if lower_name in {"product name", "item", "food", "bread"}:
            score -= 5
            continue
        if any(token in lower_name for token in ("subtotal", "tax", "tip", "amount due", "credit")):
            score -= 3
            continue
        meaningful_items += 1
        score += 2
        if str((item or {}).get("category", "") or "").lower() == "restaurant":
            score += 2

    score += min(meaningful_items, 6) * 2

    item_blob = " ".join(str((item or {}).get("name", "") or "").lower() for item in items)
    restaurant_terms = (
        "combo", "burger", "fries", "wrap", "rice", "naan", "biryani",
        "kebab", "kabob", "tikka", "chai", "tea", "coffee", "soda",
        "dessert", "pani puri", "haleem", "idli", "dosa", "vada",
    )
    term_hits = sum(1 for term in restaurant_terms if term in item_blob)
    score += min(term_hits, 6) * 2

    if meaningful_items == 0:
        score -= 15

    return score


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_receipt_data(data: dict, receipt_type: str | None = None) -> bool:
    """Validate that OCR output contains all required fields."""
    required_fields = ["store", "date", "total"]
    # For non-bill receipts, items are required
    if receipt_type not in {"utility_bill", "household_bill"}:
        required_fields.append("items")

    for field in required_fields:
        if field not in data or data[field] is None:
            logger.warning(f"Validation failed: missing field '{field}'")
            return False

    if _is_placeholder_text(data.get("store")):
        logger.warning("Validation failed: OCR returned a placeholder store name")
        return False

    if not _is_valid_receipt_date(data.get("date")):
        logger.warning("Validation failed: OCR returned an invalid receipt date: %s", data.get("date"))
        return False

    if receipt_type in {"utility_bill", "household_bill"}:
        return True

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
    """Classify receipt into grocery, restaurant, general_expense, or unknown."""
    store = str(data.get("store", "")).lower()
    items = data.get("items", []) or []
    item_names = " ".join(str(item.get("name", "")).lower() for item in items)
    categories = [str(item.get("category", "")).lower() for item in items if item.get("category")]
    category_set = set(categories)
    store_location = str(data.get("store_location", "")).lower()

    grocery_store_keywords = {
        "kroger", "walmart", "aldi", "meijer", "costco", "safeway",
        "whole foods", "trader joe", "publix", "target", "sam's club"
    }
    restaurant_store_keywords = {
        "mcdonald", "burger king", "taco bell", "chipotle", "starbucks",
        "subway", "pizza", "restaurant", "cafe", "bar", "grill",
        "desi", "biryani", "kabob", "kebab", "chowrastha", "toast"
    }
    retail_store_keywords = {
        "best buy", "home depot", "lowe", "ikea", "walgreens", "cvs",
        "macys", "kohls", "tj maxx", "marshall", "office depot", "claire", "ulta",
        "sephora", "great clips", "supercuts", "sport clips", "pearle vision"
    }
    grocery_categories = {
        "dairy", "produce", "meat", "seafood", "bakery", "beverages",
        "snacks", "frozen", "canned", "condiments", "household", "personal_care"
    }
    retail_categories = {"electronics", "apparel", "hardware", "office", "pharmacy", "home"}
    expense_terms = {
        "ear piercing", "piercing", "service", "fee", "fees", "gift", "accessory",
        "beauty", "salon", "spa", "membership", "repair", "repair service"
    }
    restaurant_terms = {
        "burger", "fries", "drink", "combo", "sandwich", "pizza", "salad",
        "soda", "coffee", "latte", "tip", "gratuity", "server", "table",
        "guest count", "ordered", "amount due", "credit", "pani puri",
        "haleem", "idli", "vada", "kebab", "toasttab", "toast"
    }

    restaurant_signal_count = sum(
        1 for term in restaurant_terms
        if term in item_names or term in store or term in store_location
    )

    if "restaurant" in category_set or restaurant_signal_count >= 2:
        return "restaurant"
    if any(keyword in store for keyword in grocery_store_keywords) or category_set.intersection(grocery_categories):
        return "grocery"
    if any(keyword in store for keyword in retail_store_keywords) or category_set.intersection(retail_categories):
        return "general_expense"
    if any(term in item_names for term in expense_terms) or any(term in store for term in expense_terms):
        return "general_expense"
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


def _normalize_receipt_type_hint(receipt_type_hint: str | None) -> str | None:
    hint = str(receipt_type_hint or "").strip().lower()
    valid_hints = {"grocery", "restaurant", "general_expense", "retail_items", "utility_bill", "household_bill"}
    return hint if hint in valid_hints else None


def _apply_receipt_type_hint(data: dict, receipt_type_hint: str | None) -> dict:
    """Apply upload-time intent so OCR output starts closer to the right domain."""
    hint = _normalize_receipt_type_hint(receipt_type_hint)
    if not hint:
        return data

    hinted = dict(data or {})
    items = []
    for item in hinted.get("items", []) or []:
        normalized_item = dict(item or {})
        if hint == "restaurant":
            normalized_item["category"] = "restaurant"
        elif hint == "general_expense":
            normalized_item["category"] = "general_expense"
        items.append(normalized_item)
    hinted["items"] = items
    return hinted


def _resolve_receipt_type(data: dict, receipt_type_hint: str | None) -> str:
    """Choose the final receipt type, respecting explicit user intent first."""
    hint = _normalize_receipt_type_hint(receipt_type_hint)
    if hint:
        return hint
    return classify_receipt_data(data)


def _prepare_ocr_input(file_path: str) -> str:
    """Render PDFs to a temporary PNG so the OCR engines can process them."""
    source_path = Path(file_path)
    if source_path.suffix.lower() != ".pdf":
        try:
            with Image.open(source_path) as image:
                normalized = ImageOps.exif_transpose(image)
                width, height = normalized.size
                if width <= height:
                    return file_path

                output_dir = tempfile.mkdtemp(prefix="receipt-image-")
                rotated_path = Path(output_dir) / source_path.name
                normalized.rotate(90, expand=True).save(rotated_path)
                logger.info("Rotated landscape receipt for OCR: %s -> %s", file_path, rotated_path)
                return str(rotated_path)
        except Exception as exc:
            logger.warning("Failed to normalize receipt image orientation for %s: %s", file_path, exc)
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
        if temp_dir.name.startswith(("receipt-pdf-", "receipt-image-")) and temp_dir.is_dir():
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
                       user_id: int = None, receipt_type: str = "grocery",
                       existing_purchase=None) -> int:
    """Save validated OCR data to purchases, receipt_items, and price_history."""
    session = None
    try:
        from src.backend.initialize_database_schema import (
            Purchase, ReceiptItem, Product, Store, PriceHistory
        )
        from src.backend.bill_planning import derive_planning_month
        session = g.db_session

        purchase_domain, purchase_budget_category = derive_receipt_budget_defaults(
            "general_expense" if receipt_type in {"general_expense", "retail_items"} else receipt_type,
            provider_type=ocr_data.get("bill_provider_type"),
            service_types=ocr_data.get("bill_service_types"),
        )

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

        purchase_date = _normalize_purchase_date(ocr_data.get("date"))
        purchase = existing_purchase or Purchase()
        purchase.store_id = store.id
        purchase.total_amount = _safe_float(ocr_data.get("total", 0.0))
        purchase.date = datetime.strptime(str(purchase_date), "%Y-%m-%d")
        purchase.domain = purchase_domain
        purchase.transaction_type = normalize_transaction_type(ocr_data.get("transaction_type"), default="purchase")
        purchase.refund_reason = (
            str(ocr_data.get("refund_reason", "") or "").strip().lower() or None
        ) if purchase.transaction_type == "refund" else None
        purchase.refund_note = (
            str(ocr_data.get("refund_note", "") or "").strip() or None
        ) if purchase.transaction_type == "refund" else None
        purchase.default_spending_domain = normalize_spending_domain(
            ocr_data.get("default_spending_domain"),
            default=purchase_domain,
        )
        purchase.default_budget_category = normalize_budget_category(
            ocr_data.get("default_budget_category"),
            default=purchase_budget_category,
        )
        purchase.user_id = user_id
        if existing_purchase is None:
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
            unit = (str(item_data.get("unit", "each") or "each").strip().lower() or "each")
            size_label = (str(item_data.get("size_label", "") or "").strip() or None)
            item_spending_domain = normalize_spending_domain(
                item_data.get("spending_domain"),
                default="",
            ) or None
            item_budget_category = normalize_budget_category(
                item_data.get("budget_category"),
                default="",
            ) or None
            if item_budget_category and not item_spending_domain:
                item_spending_domain = purchase.default_spending_domain
            if item_spending_domain and not item_budget_category:
                item_budget_category = default_budget_category_for_spending_domain(item_spending_domain)

            # Preserve the existing linked product on receipt edits when available.
            product = None
            incoming_product_id = item_data.get("product_id")
            if incoming_product_id not in (None, "", 0, "0"):
                try:
                    product = session.query(Product).filter_by(id=int(incoming_product_id)).first()
                except (TypeError, ValueError):
                    product = None

            # Find or create product
            matched_product = find_matching_product(session, product_name, category)
            if product and matched_product and matched_product.id != product.id:
                product = _merge_products(session, product, matched_product)
                session.flush()
            elif not product:
                product = matched_product
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
                unit=unit,
                size_label=size_label,
                spending_domain=item_spending_domain,
                budget_category=item_budget_category,
                extracted_by=engine,
            )
            session.add(receipt_item)

            # Update price history
            if purchase.transaction_type != "refund":
                ph = PriceHistory(
                    product_id=product.id,
                    store_id=store.id,
                    price=unit_price,
                    date=purchase.date,
                )
                session.add(ph)
            persisted_items.append(item_data)
            session.flush()
            if purchase_domain == "grocery" and purchase.transaction_type != "refund":
                validate_low_workflow(
                    session,
                    product_id=product.id,
                    purchase_id=purchase.id,
                    product_name=product.display_name or product.name,
                )

        logger.info(
            f"Saved receipt: {store_name} | ${_safe_float(ocr_data.get('total', 0)):.2f} | "
            f"{len(ocr_data.get('items', []))} items | purchase_id={purchase.id}"
        )

        if str(receipt_type or "").strip().lower() in {"utility_bill", "household_bill"}:
            _save_bill_meta(session, purchase.id, ocr_data, purchase_date=purchase.date)

        if receipt_type == "grocery":
            rebuild_active_inventory(session)
            if purchase.transaction_type != "refund":
                _publish_inventory_updates(session, persisted_items)

        session.commit()

        # Best-effort: append a human-readable line to <receipts_root>/_index.txt
        # so an operator SSH-ing in can grep store + date without touching the DB.
        try:
            from src.backend.receipt_filename_index import append_receipt_to_index
            append_receipt_to_index(
                image_path=image_path,
                store=store_name,
                date=ocr_data.get("date"),
                total=ocr_data.get("total"),
                purchase_id=purchase.id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Receipt index append failed: %s", exc)

        return purchase.id

    except Exception as e:
        logger.error(f"Failed to save receipt to database: {e}")
        session.rollback()
        raise


def _normalize_purchase_date(value: object) -> str:
    """Return a safe YYYY-MM-DD value so OCR placeholders cannot crash receipt persistence."""
    if _is_valid_receipt_date(value):
        return str(value)
    fallback = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.warning("Falling back to current date because OCR returned invalid date: %s", value)
    return fallback


def _safe_date_parse(value: str | None):
    """Try to parse a YYYY-MM-DD string for household bill metadata."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _save_bill_meta(session, purchase_id: int, ocr_data: dict, purchase_date=None) -> None:
    """Create or update the bill-meta sidecar for household bill receipts."""
    try:
        from src.backend.initialize_database_schema import BillMeta, BillProvider, BillServiceLine
        from src.backend.bill_planning import derive_planning_month

        provider_name = str(ocr_data.get("bill_provider_name") or ocr_data.get("store") or "").strip() or None
        provider_type = str(ocr_data.get("bill_provider_type") or "").strip().lower() or None
        service_types = normalize_utility_service_types(
            ocr_data.get("bill_service_types"),
            provider_type=provider_type,
        )

        existing = session.query(BillMeta).filter_by(purchase_id=purchase_id).first()
        meta = existing or BillMeta(purchase_id=purchase_id)
        if existing is None:
            session.add(meta)

        meta.provider_name = provider_name
        meta.provider_type = provider_type
        meta.service_types = json.dumps(service_types) if service_types else None
        meta.account_label = (
            str(ocr_data.get("bill_account_label") or "").strip() or None
        )
        meta.service_period_start = _safe_date_parse(ocr_data.get("bill_service_period_start"))
        meta.service_period_end = _safe_date_parse(ocr_data.get("bill_service_period_end"))
        meta.due_date = _safe_date_parse(ocr_data.get("bill_due_date"))
        meta.billing_cycle_month = (
            str(ocr_data.get("bill_billing_cycle_month") or "").strip()[:7] or None
        )
        if meta.due_date is None and meta.billing_cycle_month:
            from calendar import monthrange
            from datetime import date as _date_cls
            try:
                _year, _mon = map(int, meta.billing_cycle_month.split("-", 1))
                meta.due_date = _date_cls(_year, _mon, monthrange(_year, _mon)[1])
            except (ValueError, TypeError):
                pass
        meta.billing_cycle = normalize_billing_cycle(ocr_data.get("bill_billing_cycle"))
        is_recurring_raw = ocr_data.get("bill_is_recurring")
        meta.is_recurring = bool(is_recurring_raw) if is_recurring_raw is not None else True
        auto_pay_raw = ocr_data.get("bill_auto_pay")
        if auto_pay_raw is not None:
            meta.auto_pay = bool(auto_pay_raw)

        # Derive planning month deterministic fallbacks
        receipt_date_str = purchase_date.strftime("%Y-%m-%d") if purchase_date else None
        meta.planning_month = derive_planning_month(
            due_date=meta.due_date.strftime("%Y-%m-%d") if meta.due_date else None,
            service_period_end=meta.service_period_end.strftime("%Y-%m-%d") if meta.service_period_end else None,
            receipt_date=receipt_date_str,
            billing_cycle_month=meta.billing_cycle_month,
        )

        provider = None
        if provider_name:
            provider_key = provider_name.strip().lower()
            provider = session.query(BillProvider).filter_by(normalized_key=provider_key).first()
            if not provider:
                provider = BillProvider(
                    canonical_name=provider_name,
                    normalized_key=provider_key,
                    provider_type_hint=provider_type,
                )
                session.add(provider)
                session.flush()
            elif provider_type and not provider.provider_type_hint:
                provider.provider_type_hint = provider_type

        service_line = None
        if provider:
            service_line_key = f"{provider.normalized_key}::{provider_type or 'other'}::{meta.account_label or 'default'}"
            service_line = session.query(BillServiceLine).filter_by(normalized_key=service_line_key).first()
            if not service_line:
                service_line = BillServiceLine(
                    provider_id=provider.id,
                    service_type=service_types[0] if service_types else provider_type,
                    account_label=meta.account_label,
                    normalized_key=service_line_key,
                )
                session.add(service_line)
                session.flush()

        meta.provider_id = provider.id if provider else None
        meta.service_line_id = service_line.id if service_line else None

        # Phase 7: Handle multi-service allocations
        allocations_raw = ocr_data.get("bill_allocations")
        if isinstance(allocations_raw, list) and allocations_raw:
            from src.backend.initialize_database_schema import BillAllocation
            # Clear existing allocations for this purchase if updating
            session.query(BillAllocation).filter_by(purchase_id=purchase_id).delete()
            
            for alloc_data in allocations_raw:
                s_type = str(alloc_data.get("service_type") or "").strip().lower()
                amt = _safe_float(alloc_data.get("amount"), 0.0)
                if not s_type or amt <= 0:
                    continue
                
                # Find or create service line for this allocation
                a_service_line_key = f"{provider.normalized_key if provider else 'unknown'}::{s_type}::{meta.account_label or 'default'}"
                a_service_line = session.query(BillServiceLine).filter_by(normalized_key=a_service_line_key).first()
                if not a_service_line and provider:
                    a_service_line = BillServiceLine(
                        provider_id=provider.id,
                        service_type=s_type,
                        account_label=meta.account_label,
                        normalized_key=a_service_line_key,
                    )
                    session.add(a_service_line)
                    session.flush()
                
                if a_service_line:
                    session.add(BillAllocation(
                        purchase_id=purchase_id,
                        service_line_id=a_service_line.id,
                        amount=amt,
                        description=alloc_data.get("description")
                    ))

        session.flush()
        logger.info("Saved bill_meta for purchase_id=%s provider=%s", purchase_id, meta.provider_name)
    except Exception as exc:
        logger.warning("Failed to save bill_meta for purchase_id=%s: %s", purchase_id, exc)


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
    error_message: str | None = None,
    retry_count: int | None = None,
    last_reprocessed_at=None,
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
        # Update error tracking fields
        if error_message is not None:
            record.error_message = error_message
        if retry_count is not None:
            record.retry_count = retry_count
        if last_reprocessed_at is not None:
            record.last_reprocessed_at = last_reprocessed_at
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
            if receipt_type == "grocery"
            else "Saved for expense/reference tracking only."
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
    """Send failure error to Telegram user."""
    try:
        from src.backend.handle_telegram_messages import send_telegram_message
        send_telegram_message(chat_id, "❌ Could not process receipt. Saved for manual review.")
    except Exception as e:
        logger.warning(f"Failed to send Telegram error: {e}")
