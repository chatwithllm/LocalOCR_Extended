"""Provider-fanout image fetcher for proactive product image backfill.

Tries free image providers in order: Wikimedia (no key), Unsplash
(``UNSPLASH_ACCESS_KEY`` env var), Pexels (``PEXELS_API_KEY`` env var).
First success wins. Returns post-normalized JPEG bytes or None.

Free key signups:
  - Unsplash: https://unsplash.com/oauth/applications
  - Pexels:   https://www.pexels.com/api/

Wikimedia requires the courtesy User-Agent below per their API policy:
https://www.mediawiki.org/wiki/API:Etiquette
"""
from __future__ import annotations

import io
import logging
import os

import requests
from PIL import Image


logger = logging.getLogger(__name__)

USER_AGENT = (
    "LocalOCR_Extended/1.0 "
    "(https://github.com/chatwithllm/LocalOCR_Extended; image-backfill)"
)
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
WIKIMEDIA_ENDPOINT = "https://en.wikipedia.org/w/api.php"
UNSPLASH_ENDPOINT = "https://api.unsplash.com/search/photos"
PEXELS_ENDPOINT = "https://api.pexels.com/v1/search"


def _query_wikimedia(query: str, timeout: float) -> str | None:
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages",
        "piprop": "thumbnail",
        "pithumbsize": 600,
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": 1,
        "gsrnamespace": 0,
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(WIKIMEDIA_ENDPOINT, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        pages = (resp.json().get("query") or {}).get("pages") or {}
        for _pid, page in pages.items():
            thumb = (page.get("thumbnail") or {}).get("source")
            if thumb:
                return thumb
    except Exception as exc:
        logger.warning("Wikimedia query failed for %r: %s", query, exc)
    return None


def _query_unsplash(query: str, timeout: float) -> str | None:
    key = (os.getenv("UNSPLASH_ACCESS_KEY") or "").strip()
    if not key:
        return None
    headers = {
        "Authorization": f"Client-ID {key}",
        "Accept-Version": "v1",
        "User-Agent": USER_AGENT,
    }
    params = {"query": query, "per_page": 1, "orientation": "squarish"}
    try:
        resp = requests.get(UNSPLASH_ENDPOINT, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if results:
            return ((results[0].get("urls") or {}).get("regular")
                    or (results[0].get("urls") or {}).get("small"))
    except Exception as exc:
        logger.warning("Unsplash query failed for %r: %s", query, exc)
    return None


def _query_pexels(query: str, timeout: float) -> str | None:
    key = (os.getenv("PEXELS_API_KEY") or "").strip()
    if not key:
        return None
    headers = {"Authorization": key, "User-Agent": USER_AGENT}
    params = {"query": query, "per_page": 1, "size": "small"}
    try:
        resp = requests.get(PEXELS_ENDPOINT, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        photos = resp.json().get("photos") or []
        if photos:
            return ((photos[0].get("src") or {}).get("medium")
                    or (photos[0].get("src") or {}).get("small"))
    except Exception as exc:
        logger.warning("Pexels query failed for %r: %s", query, exc)
    return None


def _download_and_normalize(
    image_url: str, max_bytes: int, target_width: int, timeout: float
) -> bytes | None:
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(image_url, headers=headers, timeout=timeout, stream=True)
        resp.raise_for_status()
        ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ct not in ALLOWED_CONTENT_TYPES:
            logger.info("rejecting %s: content-type %r", image_url, ct)
            return None
        buf = bytearray()
        for chunk in resp.iter_content(chunk_size=16384):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) > max_bytes:
                logger.info("rejecting %s: exceeded max_bytes=%d", image_url, max_bytes)
                return None
        raw = bytes(buf)
        # Pillow integrity check.
        Image.open(io.BytesIO(raw)).verify()
        # Reopen for actual processing — verify() exhausts the stream.
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
        logger.warning("download/normalize failed for %s: %s", image_url, exc)
        return None


def fetch_product_image(
    product_name: str,
    category: str | None = None,
    *,
    max_bytes: int = 1_048_576,
    target_width: int = 600,
    timeout: float = 10.0,
) -> bytes | None:
    """Return JPEG bytes for the best-matching image, or None if all providers fail.

    Pure function — no DB, no FS. Caller persists the bytes wherever it likes.
    """
    name = (product_name or "").strip()
    if not name:
        return None
    query = name
    if category:
        cat = category.strip()
        if cat and cat.lower() not in {"other", "unknown"}:
            query = f"{name} {cat}"

    for provider in (_query_wikimedia, _query_unsplash, _query_pexels):
        url = provider(query, timeout)
        if not url:
            continue
        data = _download_and_normalize(url, max_bytes, target_width, timeout)
        if data:
            return data
    return None
