"""OpenAI image generation for proactive product image backfill.

Calls ``gpt-image-1`` to synthesize a clean studio product photo from the
product name. Returns post-normalized JPEG bytes or None.

Requires ``OPENAI_API_KEY`` env var (or the ``api_key`` kwarg).
"""
from __future__ import annotations

import base64
import io
import logging
import os

import openai
from PIL import Image


logger = logging.getLogger(__name__)


def fetch_product_image(
    product_name: str,
    category: str | None = None,
    *,
    target_width: int = 600,
    timeout: float = 60.0,
    api_key: str | None = None,
) -> bytes | None:
    """Return JPEG bytes for a synthesized product photo, or None on failure.

    Pure function — no DB, no FS. Caller persists the bytes wherever it likes.
    """
    key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.warning("OPENAI_API_KEY not set; skipping image generation")
        return None

    name = (product_name or "").strip()
    if not name:
        return None

    cat_suffix = ""
    if category and category.strip().lower() not in {"", "other", "unknown"}:
        cat_suffix = f", {category.strip()}"
    prompt = (
        f"A clean studio product photograph of {name}{cat_suffix}, "
        "white background, centered, no text, no watermark, no people, photorealistic."
    )

    try:
        client = openai.OpenAI(api_key=key, timeout=timeout)
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            quality="low",
            n=1,
            response_format="b64_json",
        )
        raw = base64.b64decode(resp.data[0].b64_json)
    except (openai.APIError, openai.APITimeoutError, Exception) as exc:
        logger.warning("Image generation failed for %r: %s", name, exc)
        return None

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
        logger.warning("Image normalize failed for %r: %s", name, exc)
        return None
