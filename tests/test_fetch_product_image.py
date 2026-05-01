"""Unit tests for the fetch_product_image OpenAI image-generation module.

All OpenAI calls are mocked. We test:
  - Returns JPEG bytes (downscaled to target_width) on success.
  - Returns None when OPENAI_API_KEY is unset (no client created).
  - Returns None on openai.APIError.
  - Prompt includes product name and category.
  - Downscales oversized images to target_width.
"""
from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock

import pytest
from PIL import Image


def _make_png_bytes(width: int = 1024, height: int = 1024, color=(180, 80, 40)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _make_b64_png(width: int = 1024, height: int = 1024) -> str:
    return base64.b64encode(_make_png_bytes(width, height)).decode()


def _mock_openai_client(b64: str) -> MagicMock:
    client = MagicMock()
    client.images.generate.return_value = MagicMock(
        data=[MagicMock(b64_json=b64)]
    )
    return client


def test_returns_jpeg_bytes_on_success(monkeypatch):
    from src.backend import fetch_product_image as mod

    client = _mock_openai_client(_make_b64_png(1024, 1024))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mod.openai, "OpenAI", lambda **kw: client)

    out = mod.fetch_product_image("Bananas")

    assert out is not None
    assert out[:3] == b"\xff\xd8\xff"  # JPEG magic bytes
    img = Image.open(io.BytesIO(out))
    assert img.width == 600


def test_returns_none_when_no_api_key(monkeypatch):
    from src.backend import fetch_product_image as mod

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr(mod.openai, "OpenAI", lambda **kw: calls.append(kw) or MagicMock())

    out = mod.fetch_product_image("Bananas")

    assert out is None
    assert calls == []


def test_returns_none_on_api_error(monkeypatch):
    from src.backend import fetch_product_image as mod

    client = MagicMock()
    client.images.generate.side_effect = mod.openai.APIError(
        message="quota exceeded", request=MagicMock(), body=None
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mod.openai, "OpenAI", lambda **kw: client)

    assert mod.fetch_product_image("Tomatoes") is None


def test_prompt_includes_product_name_and_category(monkeypatch):
    from src.backend import fetch_product_image as mod

    client = _mock_openai_client(_make_b64_png())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mod.openai, "OpenAI", lambda **kw: client)

    mod.fetch_product_image("Bananas", "Produce")

    call_kwargs = client.images.generate.call_args.kwargs
    prompt = call_kwargs["prompt"]
    assert "Bananas" in prompt
    assert "Produce" in prompt


def test_downscales_to_target_width(monkeypatch):
    from src.backend import fetch_product_image as mod

    client = _mock_openai_client(_make_b64_png(2400, 2400))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mod.openai, "OpenAI", lambda **kw: client)

    out = mod.fetch_product_image("Tomatoes", target_width=600)

    assert out is not None
    img = Image.open(io.BytesIO(out))
    assert img.width == 600
