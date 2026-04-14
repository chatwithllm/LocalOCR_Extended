"""
Step 10: Integrate Ollama LLaVA Fallback
=========================================
PROMPT Reference: Phase 3, Step 10

Fallback OCR engine using self-hosted Ollama with LLaVA model.
Triggered when Gemini is rate-limited or returns errors.
No rate limits — always available as long as Ollama container is running.

Endpoint: http://ollama:11434/api/generate
Target Speed: <15 seconds per receipt
Model: configurable via OLLAMA_MODEL (default: llava:7b)
"""

import os
import json
import base64
import logging

import requests

logger = logging.getLogger(__name__)

OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llava:7b")

# Same prompt as Gemini for consistent output format
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
            "name": "Product name",
            "quantity": 1,
            "unit_price": 0.00,
            "category": "one of: dairy, produce, meat, seafood, bakery, beverages, snacks, frozen, canned, condiments, household, personal_care, restaurant, other"
        }
    ],
    "subtotal": 0.00,
    "tax": 0.00,
    "tip": 0.00,
    "total": 0.00,
    "confidence": 0.85
}

Rules:
- Extract ALL line items visible on the receipt
- Use the most specific product name visible
- For restaurant receipts, keep menu item names exact and use category = restaurant
- Capture subtotal, tax, tip, credits, and amount due when visible
- If quantity is not clear, default to 1
- Confidence should reflect receipt readability (0.0 to 1.0)
- If you cannot read a field, set it to null
- Return ONLY valid JSON
"""


# ---------------------------------------------------------------------------
# Ollama OCR Function
# ---------------------------------------------------------------------------

def _safe_float(value, default=0.0):
    """Return a float for logging even when OCR returns null/string values."""
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _looks_like_prompt_echo(result: dict) -> bool:
    """Detect when the model simply echoes the schema/template instead of reading the receipt."""
    if not isinstance(result, dict):
        return False

    store = str(result.get("store", "") or "").strip().lower()
    date = str(result.get("date", "") or "").strip().lower()
    items = result.get("items", []) or []
    first_item = items[0] if items else {}
    item_name = str((first_item or {}).get("name", "") or "").strip().lower()
    category = str((first_item or {}).get("category", "") or "").strip().lower()

    echo_hits = 0
    if store in {"store name", "unknown store"}:
        echo_hits += 1
    if date in {"yyyy-mm-dd", "2023-03-15", "2023-03-25"}:
        echo_hits += 1
    if item_name in {"product name", "unknown item"}:
        echo_hits += 1
    if category.startswith("one of:"):
        echo_hits += 1

    return echo_hits >= 2


def extract_receipt_via_ollama(
    image_path: str,
    mode_hint: str | None = None,
    *,
    model_name: str | None = None,
    base_url: str | None = None,
    include_meta: bool = False,
) -> dict:
    """Extract receipt data from an image using Ollama LLaVA.

    Args:
        image_path: Path to the receipt image file.

    Returns:
        Dictionary with extracted receipt data.

    Raises:
        Exception: On API errors or connection failures.
    """
    resolved_model = (model_name or OLLAMA_MODEL or "").strip()
    resolved_base_url = (base_url or OLLAMA_ENDPOINT or "").rstrip("/")
    # Read and encode image as base64
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = RECEIPT_EXTRACTION_PROMPT
    if mode_hint == "restaurant":
        prompt += (
            "\n\nRestaurant-specific guidance:\n"
            "- This upload is intentionally marked as a restaurant receipt.\n"
            "- Prioritize restaurant name, date/time, subtotal, tax, tip, credits, total, and amount due.\n"
            "- Preserve menu item names exactly.\n"
            "- Avoid generic grocery-style fallback names unless clearly visible."
        )

    payload = {
        "model": resolved_model,
        "prompt": prompt,
        "images": [image_base64],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
        },
    }

    logger.info(f"Sending receipt to Ollama model '{resolved_model}' for OCR...")

    response = requests.post(
        f"{resolved_base_url}/api/generate",
        json=payload,
        timeout=int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180")),
    )
    response.raise_for_status()

    response_payload = response.json()
    result_text = response_payload.get("response", "")

    # Strip markdown code fences if present
    text = result_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Ollama returned invalid JSON: {e}\nRaw: {text[:500]}")
        raise ValueError(f"Ollama OCR returned invalid JSON: {e}")

    if _looks_like_prompt_echo(result):
        logger.error("Ollama returned prompt-template echo instead of receipt data: %s", text[:500])
        raise ValueError("Ollama OCR returned template placeholder data")

    # Defaults
    result.setdefault("confidence", 0.75)
    result.setdefault("items", [])
    result.setdefault("total", 0.0)

    logger.info(
        f"Ollama OCR: {result.get('store', '?')} | "
        f"${_safe_float(result.get('total', 0)):.2f} | "
        f"{len(result.get('items', []))} items | "
        f"confidence: {_safe_float(result.get('confidence', 0)):.2f} | "
        f"model: {resolved_model}"
    )

    if include_meta:
        prompt_tokens = response_payload.get("prompt_eval_count")
        output_tokens = response_payload.get("eval_count")
        total_tokens = None
        if prompt_tokens is not None or output_tokens is not None:
            total_tokens = int(prompt_tokens or 0) + int(output_tokens or 0)
        return {
            "data": result,
            "usage": {
                "input_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "finish_reason": response_payload.get("done_reason"),
            "response_meta": {
                "total_duration": response_payload.get("total_duration"),
                "load_duration": response_payload.get("load_duration"),
            },
        }

    return result


def check_ollama_health() -> bool:
    """Check if Ollama service is running and responsive."""
    try:
        response = requests.get(f"{OLLAMA_ENDPOINT}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def is_model_available(model_name: str = None) -> bool:
    """Check if a specific model is downloaded in Ollama."""
    model_name = model_name or OLLAMA_MODEL
    try:
        response = requests.get(f"{OLLAMA_ENDPOINT}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return any(m.get("name", "") == model_name or m.get("name", "").startswith(model_name.split(":")[0])
                       for m in models)
    except requests.RequestException:
        pass
    return False


def pull_ollama_model(model_name: str = None):
    """Pull the configured Ollama model if not already downloaded."""
    model_name = model_name or OLLAMA_MODEL
    if is_model_available(model_name):
        logger.info(f"Ollama model already available: {model_name}")
        return True

    logger.info(f"Pulling Ollama model '{model_name}' (this may take several minutes)...")
    try:
        response = requests.post(
            f"{OLLAMA_ENDPOINT}/api/pull",
            json={"name": model_name},
            timeout=600,
            stream=True,
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                status = json.loads(line).get("status", "")
                if status:
                    logger.info(f"  Ollama: {status}")
        logger.info(f"Ollama model pulled successfully: {model_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to pull Ollama model '{model_name}': {e}")
        return False


# ---------------------------------------------------------------------------
# Entry point for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    healthy = check_ollama_health()
    logger.info(f"Ollama health: {'✅ OK' if healthy else '❌ FAILED'}")

    model_ready = is_model_available()
    logger.info(f"Ollama model ({OLLAMA_MODEL}): {'✅ Available' if model_ready else '❌ Not downloaded'}")

    if len(sys.argv) >= 2 and healthy and model_ready:
        result = extract_receipt_via_ollama(sys.argv[1])
        print(json.dumps(result, indent=2))
