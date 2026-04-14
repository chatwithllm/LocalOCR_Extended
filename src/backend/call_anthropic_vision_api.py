"""
Anthropic vision OCR support for receipt extraction.

Phase 1 keeps this aligned with the existing structured JSON contract used by
the other OCR providers so the extraction pipeline can treat it uniformly.
"""

import os
import json
import base64
import logging

from anthropic import Anthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_OCR_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

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
- Confidence should reflect overall receipt readability (0.0 to 1.0)
- If you cannot read a field clearly, set it to null
- Return ONLY valid JSON
"""


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def extract_receipt_via_anthropic(
    image_path: str,
    mode_hint: str | None = None,
    *,
    api_key: str | None = None,
    model_name: str | None = None,
    include_meta: bool = False,
) -> dict:
    """Extract receipt data from an image using Anthropic vision."""
    resolved_api_key = (api_key or ANTHROPIC_API_KEY or "").strip()
    resolved_model = (model_name or ANTHROPIC_OCR_MODEL or "").strip()
    if not resolved_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    with open(image_path, "rb") as handle:
        image_bytes = handle.read()

    prompt = RECEIPT_EXTRACTION_PROMPT
    if mode_hint == "restaurant":
        prompt += (
            "\n\nRestaurant-specific guidance:\n"
            "- This upload is intentionally marked as a restaurant receipt.\n"
            "- Prioritize restaurant name, date/time, subtotal, tax, tip, credits, total, and amount due.\n"
            "- Preserve menu item names exactly.\n"
            "- Avoid grocery-style fallback names unless the receipt clearly shows them."
        )

    client = Anthropic(api_key=resolved_api_key)
    media_type = "image/png"
    lower_path = image_path.lower()
    if lower_path.endswith(".jpg") or lower_path.endswith(".jpeg"):
        media_type = "image/jpeg"
    elif lower_path.endswith(".webp"):
        media_type = "image/webp"

    response = client.messages.create(
        model=resolved_model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image_bytes).decode("utf-8"),
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    text_parts = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    text = "\n".join(text_parts).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Anthropic returned invalid JSON: %s\nRaw: %s", exc, text[:500])
        raise ValueError(f"Anthropic OCR returned invalid JSON: {exc}") from exc

    result.setdefault("confidence", 0.85)
    result.setdefault("items", [])
    result.setdefault("total", 0.0)

    logger.info(
        "Anthropic OCR: %s | $%.2f | %s items | confidence: %.2f | model: %s",
        result.get("store", "?"),
        _safe_float(result.get("total", 0)),
        len(result.get("items", []) or []),
        _safe_float(result.get("confidence", 0)),
        resolved_model,
    )
    if include_meta:
        usage = getattr(response, "usage", None)
        stop_reason = getattr(response, "stop_reason", None)
        return {
            "data": result,
            "usage": {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "total_tokens": (
                    (getattr(usage, "input_tokens", 0) or 0)
                    + (getattr(usage, "output_tokens", 0) or 0)
                ) if usage else None,
            } if usage else None,
            "finish_reason": stop_reason,
            "response_meta": {
                "response_id": getattr(response, "id", None),
            },
        }

    return result
