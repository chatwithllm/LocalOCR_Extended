"""Multi-provider image generation for proactive product image backfill.

Pluggable providers: ``gemini`` (free tier via Gemini Flash Image) and
``openai`` (gpt-image-1, paid). With provider="auto" the dispatcher tries
the user's preferred order and falls back on any failure (404, 429, etc).

Returns ``(jpeg_bytes, provider_used)`` or ``(None, None)`` on total failure.
Caller persists bytes wherever; this module does no DB / FS work.

Env vars:
  GEMINI_API_KEY  — Gemini Flash Image (free tier, shares OCR quota)
  OPENAI_API_KEY  — gpt-image-1 (paid, ~$0.011/image low quality)
"""
from __future__ import annotations

import base64
import io
import logging
import os
from typing import Callable

from PIL import Image


logger = logging.getLogger(__name__)


GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"
OPENAI_IMAGE_MODEL = "gpt-image-1"

# Provider preference when caller passes provider="auto"
DEFAULT_PROVIDER_CHAIN = ("gemini", "openai")

# Single source of truth for which model string each provider uses —
# stamped onto ProductSnapshot.notes by the backfill writers so history
# views can show "what model produced this image" without re-deriving.
PROVIDER_MODELS = {
    "gemini": GEMINI_IMAGE_MODEL,
    "openai": OPENAI_IMAGE_MODEL,
}


def model_for_provider(provider: str | None) -> str | None:
    if not provider:
        return None
    return PROVIDER_MODELS.get(provider.lower())


def _build_prompt(name: str, category: str | None) -> str:
    cat_suffix = ""
    if category and category.strip().lower() not in {"", "other", "unknown"}:
        cat_suffix = f", {category.strip()}"
    return (
        f"A clean studio product photograph of {name}{cat_suffix}, "
        "white background, centered, no text, no watermark, no people, photorealistic."
    )


def _generate_via_gemini(prompt: str, timeout: float, api_key: str | None) -> bytes:
    """Return raw image bytes from Gemini Flash Image. Raises on failure."""
    key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )
    for part in (resp.candidates[0].content.parts or []):
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            return inline.data
    raise RuntimeError("Gemini returned no inline image data")


def _generate_via_openai(prompt: str, timeout: float, api_key: str | None) -> bytes:
    """Return raw image bytes from OpenAI gpt-image-1. Raises on failure."""
    key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    import openai

    client = openai.OpenAI(api_key=key, timeout=timeout)
    resp = client.images.generate(
        model=OPENAI_IMAGE_MODEL,
        prompt=prompt,
        size="1024x1024",
        quality="low",
        n=1,
    )
    return base64.b64decode(resp.data[0].b64_json)


_PROVIDERS: dict[str, Callable[[str, float, str | None], bytes]] = {
    "gemini": _generate_via_gemini,
    "openai": _generate_via_openai,
}


def available_providers() -> list[str]:
    """Return providers whose env keys are set, in preference order."""
    out = []
    if (os.getenv("GEMINI_API_KEY") or "").strip():
        out.append("gemini")
    if (os.getenv("OPENAI_API_KEY") or "").strip():
        out.append("openai")
    return out


def _normalize_jpeg(raw: bytes, target_width: int) -> bytes | None:
    try:
        img = Image.open(io.BytesIO(raw))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        if img.width > target_width:
            new_h = int(img.height * (target_width / img.width))
            img = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=82, optimize=True)
        return out.getvalue()
    except Exception as exc:
        logger.warning("Image normalize failed: %s", exc)
        return None


def fetch_product_image(
    product_name: str,
    category: str | None = None,
    *,
    provider: str = "auto",
    target_width: int = 600,
    timeout: float = 60.0,
    gemini_api_key: str | None = None,
    openai_api_key: str | None = None,
) -> tuple[bytes | None, str | None]:
    """Generate a product photo via the chosen provider (or fallback chain).

    provider:
      - ``"auto"``  — try gemini, then openai. First success wins.
      - ``"gemini"`` — only Gemini. No fallback.
      - ``"openai"`` — only OpenAI. No fallback.

    Returns ``(jpeg_bytes, provider_used)`` or ``(None, None)``.
    """
    name = (product_name or "").strip()
    if not name:
        return (None, None)

    if provider == "auto":
        chain = list(DEFAULT_PROVIDER_CHAIN)
    elif provider in _PROVIDERS:
        chain = [provider]
    else:
        logger.warning("Unknown provider %r; treating as 'auto'", provider)
        chain = list(DEFAULT_PROVIDER_CHAIN)

    prompt = _build_prompt(name, category)

    for prov in chain:
        fn = _PROVIDERS[prov]
        kwargs = {
            "gemini": gemini_api_key,
            "openai": openai_api_key,
        }
        try:
            raw = fn(prompt, timeout, kwargs[prov])
        except Exception as exc:
            logger.warning("Provider %s failed for %r: %s", prov, name, exc)
            continue
        jpeg = _normalize_jpeg(raw, target_width)
        if jpeg:
            return (jpeg, prov)
        logger.warning("Provider %s returned bytes but normalize failed for %r", prov, name)
    return (None, None)
