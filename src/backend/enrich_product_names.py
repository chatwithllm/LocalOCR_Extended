"""
Gemini-backed product name enrichment for OCR-shortened receipt items.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from google import genai
from google.genai import types

from src.backend.normalize_product_names import normalize_product_category

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

ENRICHMENT_PROMPT = """
You are cleaning up OCR-shortened product names from grocery and retail receipts.
Return ONLY valid JSON.

{
  "display_name": "Shopping-friendly product name or null",
  "brand": "Brand if recognizable, else null",
  "size": "Pack size or weight if recognizable, else null",
  "category": "one of: dairy, produce, meat, seafood, bakery, beverages, snacks, frozen, canned, condiments, household, personal_care, other",
  "confidence": 0.0
}

Rules:
- Prefer names that a household would recognize in a shopping list.
- If you can identify the likely retail item, use a specific name.
- If not, fall back to a clear generic shopping-friendly name.
- Never invent impossible details.
- Confidence is 0.0 to 1.0.

Examples:
- OCR name: Bare Chck Ch -> display_name: "Just Bare Lightly Breaded Chicken Breast Chunks", brand: "Just Bare", size: "4 lbs", category: "frozen", confidence: 0.9
- OCR name: Htgf Chk Thigh -> display_name: "Heritage Farm Chicken Thighs", brand: "Heritage Farm", size: null, category: "meat", confidence: 0.88
- OCR name: Ahoxi 200LDS -> display_name: "Laundry Detergent", brand: "Arm & Hammer", size: "200 loads", category: "household", confidence: 0.82
"""

ENRICHMENT_RETRY_SUFFIX = """
Return ONLY a single-line JSON object.
Do not use markdown.
Do not include line breaks inside string values.
"""


def should_enrich_product_name(name: str, category: str | None = None) -> bool:
    """Heuristic to decide whether a product name needs AI cleanup."""
    text = str(name or "").strip()
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text)
    lower = normalized.lower()

    if len(normalized) <= 14:
        return True
    if re.search(r"\d", normalized) and not re.search(r"\b(lb|lbs|oz|ct|pk|pack|gal|ml|l)\b", lower):
        return True
    if re.search(r"\b(chck|ygrt|psta|piza|tmato|chees|dkd|lds|pacs|qtrs|sz\d+)\b", lower):
        return True
    if sum(ch in "aeiou" for ch in lower if ch.isalpha()) <= 2:
        return True
    if normalize_product_category(category) in {"other", "snacks"} and len(normalized.split()) <= 3:
        return True
    return False


def enrich_product_with_gemini(raw_name: str, category: str | None = None) -> dict | None:
    """Return Gemini enrichment for a product name, or None if unavailable."""
    if not GEMINI_API_KEY:
        return None

    client = genai.Client(api_key=GEMINI_API_KEY)
    base_prompt = (
        f"{ENRICHMENT_PROMPT}\n\n"
        f"OCR name: {raw_name}\n"
        f"Current category: {normalize_product_category(category)}\n"
    )

    data = None
    for attempt in range(2):
        prompt = base_prompt if attempt == 0 else f"{base_prompt}\n{ENRICHMENT_RETRY_SUFFIX}"
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=384,
                response_mime_type="application/json",
            ),
        )

        text = (response.text or "").strip()
        if not text:
            continue

        try:
            data = json.loads(text)
            break
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                continue
            try:
                data = json.loads(match.group(0))
                break
            except json.JSONDecodeError:
                continue

    if data is None:
        logger.warning("Gemini product enrichment returned invalid JSON for %s", raw_name)
        return None

    confidence = float(data.get("confidence") or 0)
    if confidence < 0.6:
        return None

    return {
        "display_name": (data.get("display_name") or "").strip() or None,
        "brand": (data.get("brand") or "").strip() or None,
        "size": (data.get("size") or "").strip() or None,
        "category": normalize_product_category(data.get("category") or category),
        "confidence": confidence,
    }


def maybe_enrich_product(session, product, force: bool = False):
    """Populate product display fields using Gemini when the raw name looks poor."""
    if product is None:
        return product

    if not product.raw_name:
        product.raw_name = product.name

    if not force and product.display_name and product.enrichment_confidence and product.enrichment_confidence >= 0.6:
        return product

    source_name = product.raw_name or product.name
    if not force and not should_enrich_product_name(source_name, product.category):
        if not product.display_name:
            product.display_name = product.name
        return product

    try:
        enrichment = enrich_product_with_gemini(source_name, product.category)
    except Exception as exc:
        logger.warning("Gemini product enrichment failed for %s: %s", source_name, exc)
        enrichment = None

    if enrichment:
        product.display_name = enrichment["display_name"] or product.display_name or product.name
        product.brand = enrichment["brand"] or product.brand
        product.size = enrichment["size"] or product.size
        if enrichment["category"] and (product.category in {None, "", "other", "snacks"} or force):
            product.category = enrichment["category"]
        product.enrichment_confidence = enrichment["confidence"]
        product.enriched_at = datetime.now(timezone.utc)
    elif not product.display_name:
        product.display_name = product.name

    session.flush()
    return product


def product_needs_review(product) -> bool:
    """Return True when a product name likely needs human-readable cleanup."""
    if product is None:
        return False
    if getattr(product, "review_state", None) == "dismissed":
        return False
    if getattr(product, "review_state", None) == "resolved":
        return False

    source_name = getattr(product, "raw_name", None) or getattr(product, "name", "")
    display_name = getattr(product, "display_name", None) or getattr(product, "name", "")
    confidence = getattr(product, "enrichment_confidence", None)

    if should_enrich_product_name(source_name, getattr(product, "category", None)):
        return True
    if display_name == source_name and not confidence:
        return True
    return False
