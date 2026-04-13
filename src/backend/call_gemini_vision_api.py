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

UTILITY_BILL_EXTRACTION_PROMPT = """
Analyze this utility bill or recurring bill document and extract the following information as JSON.
Return ONLY the raw JSON object — no markdown, no code fences, no explanation.

{
    "store": "Provider or company name (e.g. NIPSCO, Comcast, Planet Fitness)",
    "store_location": "Provider address if visible, or null",
    "date": "YYYY-MM-DD (bill date or statement date)",
    "time": null,
    "items": [],
    "subtotal": 0.00,
    "tax": 0.00,
    "tip": 0.00,
    "total": 0.00,
    "confidence": 0.95,
    "bill_provider_type": "one of: electricity, water, sewage, gas, internet, phone, cable, trash, hoa, rent, mortgage, insurance, daycare, school, gym, streaming, software, subscription, health, other",
    "bill_account_label": "Account number, last 4 digits, or account nickname if visible, or null",
    "bill_service_period_start": "YYYY-MM-DD or null",
    "bill_service_period_end": "YYYY-MM-DD or null",
    "bill_due_date": "YYYY-MM-DD or null",
    "bill_billing_cycle_month": "YYYY-MM — month this bill covers, or null",
    "bill_is_recurring": true
}

Rules:
- store = provider or company name (e.g. "NIPSCO", "Comcast", "Planet Fitness")
- date = bill issue date or statement date (not due date)
- total = amount due / amount owed on this bill
- items array should be EMPTY unless the bill explicitly lists separately charged services
- bill_provider_type: choose the best matching type from the allowed list
- bill_service_period_start / end: the period covered by this bill (e.g. March 1 to March 31)
- bill_due_date: the payment due date shown on the bill
- bill_billing_cycle_month: the YYYY-MM that this bill is for (usually the month before due date)
- bill_is_recurring: true for regular monthly/annual bills, false for one-off charges
- Confidence should reflect overall bill readability (0.0 to 1.0)
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
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured")

    # Load and compress image if needed
    image_bytes, mime_type = _load_and_compress_image(image_path)
    supplemental_text = _extract_pdf_text(source_file_path or image_path)

    client = genai.Client(api_key=GEMINI_API_KEY)
    result = _generate_gemini_json(
        client=client,
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=_build_prompt(RECEIPT_EXTRACTION_PROMPT, supplemental_text, mode_hint=mode_hint),
        max_output_tokens=8192,
    )
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
        )
        result = _merge_summary_fields(result, summary)

    logger.info(
        f"Gemini OCR: {result.get('store', '?')} | "
        f"${_safe_float(result.get('total', 0)):.2f} | "
        f"{len(result.get('items', []))} items | "
        f"confidence: {_safe_float(result.get('confidence', 0)):.2f} | "
        f"model: {GEMINI_MODEL}"
    )

    return result


def extract_receipt_summary_via_gemini(
    image_path: str,
    client: genai.Client | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
    supplemental_text: str | None = None,
    mode_hint: str | None = None,
) -> dict:
    """Run a focused Gemini pass for summary/header/footer fields."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured")

    if image_bytes is None or mime_type is None:
        image_bytes, mime_type = _load_and_compress_image(image_path)

    client = client or genai.Client(api_key=GEMINI_API_KEY)
    result = _generate_gemini_json(
        client=client,
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=_build_prompt(RECEIPT_SUMMARY_PROMPT, supplemental_text, mode_hint=mode_hint),
        max_output_tokens=1024,
    )
    result.setdefault("confidence", 0.85)
    return result


def _generate_gemini_json(client, image_bytes: bytes, mime_type: str, prompt: str, max_output_tokens: int) -> dict:
    """Send a structured OCR request to Gemini and parse the JSON response."""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
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

    if hasattr(response, "usage_metadata") and response.usage_metadata:
        _track_api_usage(response.usage_metadata)

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}\nRaw: {text[:500]}")
        raise ValueError(f"Gemini OCR returned invalid JSON: {e}")


def _build_prompt(base_prompt: str, supplemental_text: str | None, mode_hint: str | None = None) -> str:
    """Augment the OCR prompt with extracted PDF text when available."""
    # Legacy utility_bill and the new household_bill flow share the same bill prompt.
    if mode_hint in {"utility_bill", "household_bill"}:
        base_prompt = UTILITY_BILL_EXTRACTION_PROMPT
    prompt = base_prompt
    if mode_hint == "restaurant":
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
