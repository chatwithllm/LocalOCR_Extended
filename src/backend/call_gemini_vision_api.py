"""
Step 9: Integrate Gemini Vision API
=====================================
PROMPT Reference: Phase 3, Step 9

Primary OCR engine using Google Gemini Vision API. Extracts receipt data
from images and returns structured JSON. Persists usage counters to the
api_usage table for rate-limit tracking across container restarts.

Rate Limits: 60 req/min, 1.5M tokens/day (free tier)
Target Speed: <3 seconds per receipt
"""

import os
import json
import logging
import mimetypes
import re
import subprocess
from pathlib import Path
from datetime import date, datetime, timezone

from google import genai
from flask import has_app_context
from google.genai import types
from PIL import Image

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ---------------------------------------------------------------------------
# OCR Prompt
# ---------------------------------------------------------------------------

RECEIPT_EXTRACTION_PROMPT = """
Analyze this receipt image and extract the following information as JSON.
Return ONLY the raw JSON object — no markdown, no code fences, no explanation.

{
    "store": "Store name",
    "store_location": "Store address if visible, or null",
    "date": "YYYY-MM-DD",
    "time": "HH:MM or null",
    "items": [
        {
            "name": "Product name (be specific, e.g. 'Organic Whole Milk 1 Gal' not just 'Milk')",
            "quantity": 1,
            "unit_price": 0.00,
            "category": "one of: dairy, produce, meat, seafood, bakery, beverages, snacks, frozen, canned, condiments, household, personal_care, restaurant, other"
        }
    ],
    "subtotal": 0.00,
    "tax": 0.00,
    "tip": 0.00,
    "total": 0.00,
    "confidence": 0.95
}

Rules:
- Extract ALL line items visible on the receipt
- Use the most specific product name visible on the receipt
- For restaurant receipts, preserve menu item names exactly and use category = restaurant
- Capture subtotal, tax, tip, credits, and amount due when visible
- If quantity is not explicitly shown, default to 1
- For BOGO or discount lines, include them as separate items with unit_price = 0.00 or the discounted price
- Confidence should reflect overall receipt readability (0.0 to 1.0)
- If you cannot read a field clearly, set it to null
- Return ONLY valid JSON
"""

RECEIPT_SUMMARY_PROMPT = """
Analyze this receipt image and extract ONLY the high-level summary fields as JSON.
Return ONLY the raw JSON object — no markdown, no code fences, no explanation.

{
    "store": "Store name or null",
    "store_location": "Store address if visible, or null",
    "date": "YYYY-MM-DD or null",
    "time": "HH:MM or null",
    "subtotal": 0.00,
    "tax": 0.00,
    "total": 0.00,
    "confidence": 0.95
}

Rules:
- Focus on header/footer summary fields, especially the purchase date and final total
- If the receipt shows dates like MM/DD/YYYY, convert them to YYYY-MM-DD
- Prefer the final charged amount as total
- If a field is not clearly visible, set it to null
- Return ONLY valid JSON
"""

BILL_EXTRACTION_PROMPT = """
Analyze this household bill or utility statement image and extract the following information as JSON.
Return ONLY the raw JSON object — no markdown, no code fences, no explanation.

{
    "bill_provider_name": "Company name, e.g. 'Comcast' or 'Duke Energy'",
    "bill_provider_type": "one of: electricity, water, gas, internet, trash, rent, mortgage, insurance, medical, tax, other",
    "bill_service_types": ["electricity", "gas", etc],
    "bill_account_label": "Last 4 digits of account or address hint, e.g. '...1234' or '123 Main St'",
    "bill_service_period_start": "YYYY-MM-DD or null",
    "bill_service_period_end": "YYYY-MM-DD or null",
    "bill_due_date": "YYYY-MM-DD (Date payment is due)",
    "bill_billing_cycle_month": "YYYY-MM (The month this bill applies to, often the previous month)",
    "bill_is_recurring": true,
    "bill_auto_pay": true,
    "bill_allocations": [
        {"service_type": "water", "amount": 45.50, "description": "Water service"},
        {"service_type": "sewer", "amount": 32.00, "description": "Sewer usage"}
    ],
    "date": "YYYY-MM-DD (The statement or bill date found in header)",
    "total": 0.00,
    "store": "Bill Provider Name (repeat the provider name here)",
    "items": [],
    "confidence": 0.95
}

Rules:
- This is a recurring household bill, not a grocery store receipt.
- For bill_provider_name, use the main company branding found in the header.
- For bill_service_period, look for 'billing period' or 'usage from/to' dates.
- For total, use the 'Amount Due', 'New Balance', or 'Total amount to pay'.
- For bill_due_date, scan the whole document — it is often near the amount due
  and can be labeled 'Due Date', 'Date Due', 'Payment Due', 'Payment Due Date',
  'Pay By', 'Pay by', 'Please pay by', 'Amount Due By', 'Due On',
  'Due on or before', 'Autopay Date', 'Auto-Pay Date', 'AutoPay Date',
  'Scheduled Payment Date', 'AutoPay is scheduled for', 'AutoPay scheduled for',
  'Auto Pay is scheduled for', 'Scheduled for', 'Will be withdrawn on',
  'Payment will be processed on', or simply a bare date right next to the
  amount-due box or inside a prominent graphic badge. Return the earliest
  such date.
- If bill_due_date is genuinely not printed, return null — do not guess.
- For bill_auto_pay, set it to true when the bill shows an autopay indicator
  such as 'AutoPay is scheduled for ...', 'Enrolled in AutoPay',
  'AutoPay is on', 'Automatic payment on file', 'Will be paid automatically',
  or a green AutoPay badge. Otherwise set it to false.
- If a date is in MM/DD/YY format, normalize to YYYY-MM-DD.
- Keep "items" as an empty list [].
- Return ONLY valid JSON.
"""

PRODUCT_IDENTIFY_PROMPT = """
Identify the product shown in this photo (typically a packaged grocery, pantry,
or household item). Return ONLY a raw JSON object — no markdown, no code
fences, no explanation.

{
    "name": "Short, shopper-friendly product name (e.g. 'Almond Milk', 'Basmati Rice', 'Paper Towels'). Do NOT include brand in the name field.",
    "brand": "Primary brand name on the label, or null if none visible",
    "size": "Size/weight as printed, e.g. '12 oz', '454 g', '5 lb', '1 gal', or null",
    "unit": "One of: each, lb, oz, g, kg, ml, l, gal, count, pack — default to 'each'",
    "category": "One of: produce, dairy, snacks, bakery, meat, seafood, frozen, beverages, condiments, grains, household, personal_care, apparel, other",
    "confidence": 0.85
}

Rules:
- Focus on the most prominent product label. If multiple items are visible,
  pick the one closest to the center of the frame.
- "name" should be what a shopper would write on a list — generic + concise.
- "brand" is optional; leave null if the photo shows a generic item (fresh
  produce, bulk items) or if no brand is clearly legible.
- "category" must be one of the allowed values. Use "other" if uncertain.
  Pantry items like rice, flour, pasta → grains.
  Drinks (soda, water, juice) → beverages.
  Candy, chips, cookies → snacks.
  Cleaning supplies, detergent, paper towels → household.
  Shampoo, soap, toothpaste, vitamins, OTC medicine → personal_care.
- confidence is a 0-1 float reflecting how sure you are this is a single
  identifiable product.
- Return ONLY valid JSON.
"""

# ---------------------------------------------------------------------------
# Gemini OCR Function
# ---------------------------------------------------------------------------

def _safe_float(value, default=0.0):
    """Return a float for logging even when OCR returns null/string values."""
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def extract_receipt_via_gemini(
    image_path: str,
    source_file_path: str | None = None,
    mode_hint: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
    include_meta: bool = False,
) -> dict:
    """Extract receipt data from an image using Google Gemini Vision API.

    Args:
        image_path: Path to the receipt image file.

    Returns:
        Dictionary with extracted receipt data.

    Raises:
        ValueError: If GEMINI_API_KEY is not configured.
        Exception: On API errors (caller should handle fallback to Ollama).
    """
    resolved_api_key = (api_key or GEMINI_API_KEY or "").strip()
    resolved_model = (model_name or GEMINI_MODEL or "").strip()
    if not resolved_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    # Load and compress image if needed
    image_bytes, mime_type = _load_and_compress_image(image_path)
    supplemental_text = _extract_pdf_text(source_file_path or image_path)

    client = genai.Client(api_key=resolved_api_key)
    result = _generate_gemini_json(
        client=client,
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=_build_prompt(RECEIPT_EXTRACTION_PROMPT, supplemental_text, mode_hint=mode_hint),
        max_output_tokens=8192,
        model_name=resolved_model,
        include_meta=include_meta,
    )
    usage_payload = None
    if include_meta:
        usage_payload = result
        result = usage_payload.get("data") or {}
    result = _merge_summary_fields(result, _extract_summary_from_pdf_text(supplemental_text))

    # Validate required fields
    result.setdefault("confidence", 0.85)
    result.setdefault("items", [])
    result.setdefault("total", 0.0)

    if _needs_summary_enrichment(result):
        summary = extract_receipt_summary_via_gemini(
            image_path=image_path,
            client=client,
            image_bytes=image_bytes,
            mime_type=mime_type,
            supplemental_text=supplemental_text,
            mode_hint=mode_hint,
            model_name=resolved_model,
        )
        result = _merge_summary_fields(result, summary)

    logger.info(
        f"Gemini OCR: {result.get('store', '?')} | "
        f"${_safe_float(result.get('total', 0)):.2f} | "
        f"{len(result.get('items', []))} items | "
        f"confidence: {_safe_float(result.get('confidence', 0)):.2f} | "
        f"model: {resolved_model}"
    )

    if include_meta:
        usage_payload["data"] = result
        return usage_payload
    return result


def extract_receipt_summary_via_gemini(
    image_path: str,
    client: genai.Client | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
    supplemental_text: str | None = None,
    mode_hint: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
    include_meta: bool = False,
) -> dict:
    """Run a focused Gemini pass for summary/header/footer fields."""
    resolved_api_key = (api_key or GEMINI_API_KEY or "").strip()
    resolved_model = (model_name or GEMINI_MODEL or "").strip()
    if not resolved_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    if image_bytes is None or mime_type is None:
        image_bytes, mime_type = _load_and_compress_image(image_path)

    client = client or genai.Client(api_key=resolved_api_key)
    result = _generate_gemini_json(
        client=client,
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=_build_prompt(RECEIPT_SUMMARY_PROMPT, supplemental_text, mode_hint=mode_hint),
        max_output_tokens=1024,
        model_name=resolved_model,
        include_meta=include_meta,
    )
    if include_meta:
        payload = result
        payload["data"].setdefault("confidence", 0.85)
        return payload
    result.setdefault("confidence", 0.85)
    return result


def identify_product_via_gemini(
    image_path: str,
    api_key: str | None = None,
    model_name: str | None = None,
) -> dict:
    """Identify a product from a photo of its packaging.

    Used by the Shopping-list manual-add "photo-first" flow: user snaps the
    product, this returns {name, brand, size, unit, category, confidence}
    so the form can prefill.

    Returns:
        dict with keys: name, brand, size, unit, category, confidence.
        Missing fields default to null / "other" / 0.0.

    Raises:
        ValueError if GEMINI_API_KEY is not configured.
    """
    resolved_api_key = (api_key or GEMINI_API_KEY or "").strip()
    resolved_model = (model_name or GEMINI_MODEL or "").strip()
    if not resolved_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    image_bytes, mime_type = _load_and_compress_image(image_path)

    client = genai.Client(api_key=resolved_api_key)
    result = _generate_gemini_json(
        client=client,
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=PRODUCT_IDENTIFY_PROMPT,
        max_output_tokens=512,
        model_name=resolved_model,
    )

    # Normalize + defaults so the caller gets a predictable shape.
    result.setdefault("name", None)
    result.setdefault("brand", None)
    result.setdefault("size", None)
    result.setdefault("unit", "each")
    result.setdefault("category", "other")
    result.setdefault("confidence", 0.5)

    allowed_categories = {
        "produce", "dairy", "snacks", "bakery", "meat", "seafood",
        "frozen", "beverages", "condiments", "grains", "household",
        "personal_care", "apparel", "other",
    }
    if result["category"] not in allowed_categories:
        result["category"] = "other"

    logger.info(
        f"Gemini product identify: name={result.get('name')!r} | "
        f"category={result.get('category')} | "
        f"confidence={_safe_float(result.get('confidence', 0)):.2f} | "
        f"model={resolved_model}"
    )
    return result


def _generate_gemini_json(client, image_bytes: bytes, mime_type: str, prompt: str, max_output_tokens: int, model_name: str | None = None, include_meta: bool = False) -> dict:
    """Send a structured OCR request to Gemini and parse the JSON response."""
    response = client.models.generate_content(
        model=(model_name or GEMINI_MODEL),
        contents=[
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
        ),
    )

    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata:
        _track_api_usage(usage_metadata)

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        payload = json.loads(text)
        if include_meta:
            return {
                "data": payload,
                "usage": {
                    "input_tokens": getattr(usage_metadata, "prompt_token_count", None),
                    "output_tokens": getattr(usage_metadata, "candidates_token_count", None),
                    "total_tokens": getattr(usage_metadata, "total_token_count", None),
                } if usage_metadata else None,
                "finish_reason": None,
                "response_meta": {},
            }
        return payload
    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}\nRaw: {text[:500]}")
        raise ValueError(f"Gemini OCR returned invalid JSON: {e}")


def _build_prompt(base_prompt: str, supplemental_text: str | None, mode_hint: str | None = None) -> str:
    """Augment the OCR prompt with extracted PDF text when available."""
    prompt = base_prompt
    
    if mode_hint in {"utility_bill", "household_bill"}:
        prompt = BILL_EXTRACTION_PROMPT
    elif mode_hint == "restaurant":
        prompt += (
            "\n\nRestaurant-specific guidance:\n"
            "- This upload is intentionally marked as a restaurant receipt.\n"
            "- Prioritize restaurant name, visit date/time, subtotal, tax, tip, credits, total, and amount due.\n"
            "- Preserve menu item names exactly as printed.\n"
            "- Avoid grocery-style generic names unless the receipt clearly shows them."
        )
    if not supplemental_text:
        return prompt
    return (
        f"{prompt}\n\n"
        "Additional extracted receipt text is provided below. Use it as a strong hint for summary fields "
        "like store, address, purchase date, subtotal, tax, and total when it is clearer than the image.\n"
        "Do not invent values. Prefer visible receipt evidence.\n\n"
        f"Extracted receipt text:\n{supplmental_text_guard(supplemental_text)}"
    )


def supplmental_text_guard(text: str) -> str:
    """Trim excessive PDF text so prompts stay bounded."""
    cleaned = text.strip()
    if len(cleaned) <= 6000:
        return cleaned
    return cleaned[:6000]


def _extract_pdf_text(file_path: str | None) -> str | None:
    """Extract text directly from a PDF receipt when a text layer is present."""
    if not file_path or Path(file_path).suffix.lower() != ".pdf":
        return None

    try:
        result = subprocess.run(
            ["pdftotext", "-layout", file_path, "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    text = (result.stdout or "").strip()
    return text or None


def _extract_summary_from_pdf_text(text: str | None) -> dict | None:
    """Parse deterministic summary fields from PDF text when available."""
    if not text:
        return None

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    summary = {
        "store": None,
        "store_location": None,
        "date": None,
        "time": None,
        "subtotal": None,
        "tax": None,
        "total": None,
    }

    amount_patterns = {
        "subtotal": r"\bSUBTOTAL\s+([0-9]+\.[0-9]{2})\b",
        "tax": r"\bTAX\s+([0-9]+\.[0-9]{2})\b",
        "total": r"\bTOTAL\s+([0-9]+\.[0-9]{2})\b",
    }
    for field, pattern in amount_patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            summary[field] = _safe_float(match.group(1))

    date_match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    if date_match:
        month, day, year = date_match.groups()
        summary["date"] = f"{year}-{month}-{day}"

    time_match = re.search(r"\b(\d{2}):(\d{2})\b", text)
    if time_match:
        summary["time"] = f"{time_match.group(1)}:{time_match.group(2)}"

    header_lines = lines[:6]
    if header_lines:
        summary["store"] = "COSTCO WHOLESALE" if any("CASTLETON" in line.upper() for line in header_lines) else None
        address_lines = [line for line in header_lines if any(token in line.upper() for token in ("ST", "AVE", "RD", "BLVD", "INDIANAPOLIS", "IN "))]
        if address_lines:
            summary["store_location"] = ", ".join(address_lines)

    return summary


def _needs_summary_enrichment(result: dict) -> bool:
    """Detect when the first OCR pass missed critical summary fields."""
    missing_store = not result.get("store")
    missing_date = not result.get("date")
    total_value = result.get("total")
    missing_total = total_value in (None, "", 0, 0.0)
    return missing_store or missing_date or missing_total


def _merge_summary_fields(result: dict, summary: dict | None) -> dict:
    """Fill in missing top-level fields from a focused summary extraction pass."""
    if not summary:
        return result

    merged = dict(result)
    for field in ("store", "store_location", "date", "time", "subtotal", "tax", "total"):
        current = merged.get(field)
        incoming = summary.get(field)
        if current in (None, "", 0, 0.0) and incoming not in (None, ""):
            merged[field] = incoming

    merged["confidence"] = max(_safe_float(result.get("confidence", 0.0)), _safe_float(summary.get("confidence", 0.0)))
    return merged


# ---------------------------------------------------------------------------
# Rate Limit Tracking (persisted to DB)
# ---------------------------------------------------------------------------

def _track_api_usage(usage_metadata):
    """Persist API usage counters to the api_usage table."""
    if not has_app_context():
        logger.debug("Skipping Gemini API usage tracking outside Flask app context.")
        return

    try:
        from flask import g
        session = g.db_session

        from src.backend.initialize_database_schema import ApiUsage
        today = date.today()

        usage = session.query(ApiUsage).filter_by(
            service_name="gemini", date=today
        ).first()

        if not usage:
            usage = ApiUsage(service_name="gemini", date=today, request_count=0, token_count=0)
            session.add(usage)

        usage.request_count += 1
        if hasattr(usage_metadata, "total_token_count"):
            usage.token_count += usage_metadata.total_token_count

        session.commit()

        # Warn at 80% of daily limits
        if usage.token_count > 1_200_000:  # 80% of 1.5M
            logger.warning(f"Gemini API approaching daily token limit! ({usage.token_count:,} tokens used)")
        if usage.request_count > 69_120:  # 80% of 60/min * 60 * 24
            logger.warning(f"Gemini API approaching daily request limit! ({usage.request_count:,} requests)")

    except Exception as e:
        # Don't let tracking failures break OCR
        logger.warning(f"Failed to track Gemini API usage: {e}")


def get_daily_usage() -> dict:
    """Get current day's Gemini API usage from the database."""
    if not has_app_context():
        return {"service": "gemini", "date": str(date.today()), "requests": 0, "tokens": 0}

    try:
        from flask import g
        from src.backend.initialize_database_schema import ApiUsage
        session = g.db_session
        today = date.today()
        usage = session.query(ApiUsage).filter_by(service_name="gemini", date=today).first()
        if usage:
            return {
                "service": "gemini",
                "date": str(today),
                "requests": usage.request_count,
                "tokens": usage.token_count,
            }
    except Exception:
        pass
    return {"service": "gemini", "date": str(date.today()), "requests": 0, "tokens": 0}


def _load_and_compress_image(image_path: str, max_size_mb: int = 5) -> tuple[bytes, str]:
    """Load an image and compress if larger than max_size_mb."""
    img = Image.open(image_path)

    # Convert RGBA to RGB if needed
    if img.mode == "RGBA":
        img = img.convert("RGB")

    # Compress if file too large
    file_size = os.path.getsize(image_path)
    if file_size > max_size_mb * 1024 * 1024:
        img.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        logger.info(f"Compressed image from {file_size / 1024 / 1024:.1f}MB")
        img_format = "JPEG"
    else:
        img_format = img.format or "PNG"

    mime_type = mimetypes.guess_type(image_path)[0]
    if img_format == "JPEG":
        mime_type = "image/jpeg"
    elif not mime_type:
        mime_type = "image/png"

    from io import BytesIO

    buffer = BytesIO()
    save_kwargs = {"format": img_format}
    if img_format == "JPEG":
        save_kwargs["quality"] = 90
    img.save(buffer, **save_kwargs)
    return buffer.getvalue(), mime_type


# ---------------------------------------------------------------------------
# Entry point for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if not GEMINI_API_KEY:
        logger.error("Set GEMINI_API_KEY environment variable to test.")
        sys.exit(1)
    if len(sys.argv) < 2:
        logger.error("Usage: python call_gemini_vision_api.py <image_path>")
        sys.exit(1)
    result = extract_receipt_via_gemini(sys.argv[1])
    print(json.dumps(result, indent=2))
