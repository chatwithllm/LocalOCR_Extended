"""Unit tests for the fetch_product_image provider fanout module.

All HTTP traffic is mocked. We test:
  - Unsplash first wins when its key is set.
  - Fallback to Pexels when Unsplash returns empty.
  - Fallback to Wikimedia when both paid APIs fail.
  - Returns None when every provider fails.
  - Provider silently skipped when its API key env var is unset.
  - Content-Type validation (rejects non-images).
  - Size cap (rejects > max_bytes).
  - Pillow downscale to target_width.
  - Required User-Agent header on outbound calls.
  - Fanout survives a provider exception.
  - _build_query strips generic noise adjectives.
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from PIL import Image


def _make_png_bytes(width: int = 800, height: int = 800, color=(180, 80, 40)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _mock_streamed_response(*, content_type: str, body: bytes, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": content_type}
    resp.raise_for_status = MagicMock()

    def _iter_content(chunk_size=16384):
        idx = 0
        while idx < len(body):
            yield body[idx : idx + chunk_size]
            idx += chunk_size

    resp.iter_content = _iter_content
    return resp


def _mock_json_response(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": "application/json"}
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


@pytest.fixture
def png_bytes() -> bytes:
    return _make_png_bytes()


def test_unsplash_first_success_when_key_set(monkeypatch, png_bytes):
    """Unsplash is tried first when UNSPLASH_ACCESS_KEY is set; Wikimedia
    is the no-key fallback at the end of the chain."""
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "test-key")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "api.unsplash.com" in url:
            return _mock_json_response(
                {"results": [{"urls": {"regular": "https://images.unsplash.com/x.jpg"}}]}
            )
        if "images.unsplash.com" in url:
            return _mock_streamed_response(content_type="image/jpeg", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    out = mod.fetch_product_image("Strawberries")
    assert isinstance(out, bytes) and out[:3] == b"\xff\xd8\xff"
    # Pexels and Wikimedia must NOT have been called.
    assert all("api.pexels.com" not in c and "wikipedia.org" not in c for c in calls)


def test_falls_back_to_pexels_when_unsplash_empty(monkeypatch, png_bytes):
    """When Unsplash returns an empty result set, fall through to Pexels."""
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "uk")
    monkeypatch.setenv("PEXELS_API_KEY", "pk")

    def fake_get(url, **kwargs):
        if "api.unsplash.com" in url:
            return _mock_json_response({"results": []})
        if "api.pexels.com" in url:
            return _mock_json_response(
                {"photos": [{"src": {"medium": "https://images.pexels.com/y.jpg"}}]}
            )
        if "images.pexels.com" in url:
            return _mock_streamed_response(content_type="image/jpeg", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    out = mod.fetch_product_image("Tomato")
    assert isinstance(out, bytes) and out[:3] == b"\xff\xd8\xff"


def test_falls_back_to_wikimedia_when_paid_apis_fail(monkeypatch, png_bytes):
    """When both paid APIs return empty, Wikimedia (no-key) is the last resort."""
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "uk")
    monkeypatch.setenv("PEXELS_API_KEY", "pk")

    def fake_get(url, **kwargs):
        if "api.unsplash.com" in url:
            return _mock_json_response({"results": []})
        if "api.pexels.com" in url:
            return _mock_json_response({"photos": []})
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/x.png"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    out = mod.fetch_product_image("Mirchi")
    assert isinstance(out, bytes)


def test_returns_none_when_all_fail(monkeypatch):
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "uk")
    monkeypatch.setenv("PEXELS_API_KEY", "pk")

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response({"query": {"pages": {}}})
        if "api.unsplash.com" in url:
            return _mock_json_response({"results": []})
        if "api.pexels.com" in url:
            return _mock_json_response({"photos": []})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_product_image("Nonexistent Product") is None


def test_skips_unsplash_when_no_key(monkeypatch, png_bytes):
    """When UNSPLASH_ACCESS_KEY is unset, Unsplash is silently skipped and
    Pexels (next in chain) is tried."""
    from src.backend import fetch_product_image as mod

    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    seen_urls = []

    def fake_get(url, **kwargs):
        seen_urls.append(url)
        if "api.pexels.com" in url:
            return _mock_json_response(
                {"photos": [{"src": {"medium": "https://images.pexels.com/z.jpg"}}]}
            )
        if "images.pexels.com" in url:
            return _mock_streamed_response(content_type="image/jpeg", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    mod.fetch_product_image("Eggs")
    assert all("api.unsplash.com" not in u for u in seen_urls)


def test_rejects_non_image_content_type(monkeypatch):
    from src.backend import fetch_product_image as mod

    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/spam.html"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="text/html", body=b"<html>not an image</html>")
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_product_image("Bread") is None


def test_rejects_oversize_response(monkeypatch):
    from src.backend import fetch_product_image as mod

    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    big_body = b"\x00" * (2 * 1024 * 1024)

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/big.png"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=big_body)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_product_image("Cheese") is None


def test_downscales_to_target_width(monkeypatch):
    from src.backend import fetch_product_image as mod

    big_png = _make_png_bytes(width=2400, height=2400)

    def fake_get(url, **kwargs):
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/big.png"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=big_png)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    out = mod.fetch_product_image("Tomatoes", target_width=600)
    assert out is not None
    img = Image.open(io.BytesIO(out))
    assert img.width == 600


def test_user_agent_header_set_for_wikimedia(monkeypatch, png_bytes):
    from src.backend import fetch_product_image as mod

    captured_headers = []

    def fake_get(url, **kwargs):
        captured_headers.append(kwargs.get("headers", {}))
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/x.png"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    mod.fetch_product_image("Onions")
    assert all("LocalOCR_Extended" in (h.get("User-Agent") or "") for h in captured_headers)


def test_fanout_survives_provider_exception(monkeypatch, png_bytes):
    """A 5xx / Timeout / ConnectionError from one provider must not break
    the chain — fanout moves on to the next provider."""
    import requests as _real_requests
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "uk")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)

    def fake_get(url, **kwargs):
        if "api.unsplash.com" in url:
            raise _real_requests.exceptions.ConnectionError("simulated network blip")
        if "wikipedia.org" in url:
            return _mock_json_response(
                {"query": {"pages": {"1": {"thumbnail": {"source": "https://up.wikimedia.org/x.png"}}}}}
            )
        if "up.wikimedia.org" in url:
            return _mock_streamed_response(content_type="image/png", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    out = mod.fetch_product_image("Resilience Test")
    assert isinstance(out, bytes) and out[:3] == b"\xff\xd8\xff"


def test_build_query_strips_generic_adjectives(monkeypatch, png_bytes):
    """_build_query removes generic adjectives so 'Organic Bananas' →
    'Bananas' for cleaner image-search results."""
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "uk")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    captured_queries = []

    def fake_get(url, **kwargs):
        if "api.unsplash.com" in url:
            captured_queries.append(kwargs.get("params", {}).get("query"))
            return _mock_json_response(
                {"results": [{"urls": {"regular": "https://images.unsplash.com/x.jpg"}}]}
            )
        if "images.unsplash.com" in url:
            return _mock_streamed_response(content_type="image/jpeg", body=png_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    mod.fetch_product_image("Organic Bananas", "Produce")
    # "organic" stripped; category "Produce" appended.
    assert captured_queries == ["Bananas Produce"]


def test_build_query_keeps_name_when_all_tokens_are_noise(monkeypatch, png_bytes):
    """If every token is in the noise list, fall back to the original name."""
    from src.backend import fetch_product_image as mod

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "uk")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    captured_queries = []

    def fake_get(url, **kwargs):
        if "api.unsplash.com" in url:
            captured_queries.append(kwargs.get("params", {}).get("query"))
            return _mock_json_response({"results": []})
        if "wikipedia.org" in url:
            return _mock_json_response({"query": {"pages": {}}})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    mod.fetch_product_image("Organic Fresh")
    # All tokens are noise → fall back to "Organic Fresh" (don't return empty).
    assert captured_queries == ["Organic Fresh"]
