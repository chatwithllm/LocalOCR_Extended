"""
OpenAI Vision OCR fallback for receipt extraction.

Used as the secondary OCR engine after Gemini and before Ollama.
Returns the same structured JSON schema as the other OCR providers.
"""

import os
import json
import base64
import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_OCR_MODEL = os.getenv("OPENAI_OCR_MODEL", "gpt-4.1-mini")

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


def _safe_float(value, default=0.0):
    """Return a float for logging even when OCR returns null/string values."""
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def extract_receipt_via_openai(image_path: str) -> dict:
    """Extract receipt data from an image using OpenAI vision."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured")

    client = OpenAI(api_key=OPENAI_API_KEY)

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    logger.info("Sending receipt to OpenAI Vision for OCR...")

    response = client.responses.create(
        model=OPENAI_OCR_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": RECEIPT_EXTRACTION_PROMPT},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{image_b64}",
                    },
                ],
            }
        ],
    )

    text = (response.output_text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"OpenAI returned invalid JSON: {e}\nRaw: {text[:500]}")
        raise ValueError(f"OpenAI OCR returned invalid JSON: {e}")

    result.setdefault("confidence", 0.85)
    result.setdefault("items", [])
    result.setdefault("total", 0.0)

    logger.info(
        f"OpenAI OCR: {result.get('store', '?')} | "
        f"${_safe_float(result.get('total', 0)):.2f} | "
        f"{len(result.get('items', []))} items | "
        f"confidence: {_safe_float(result.get('confidence', 0)):.2f}"
    )

    return result
