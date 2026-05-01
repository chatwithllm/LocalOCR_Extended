"""Unit tests for the multi-provider fetch_product_image module.

Mocks both providers at the dispatcher level (no real network).
"""
from __future__ import annotations

import io

import pytest
from PIL import Image


def _make_png_bytes(width: int = 1024, height: int = 1024, color=(180, 80, 40)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def mod():
    from src.backend import fetch_product_image as m
    return m


@pytest.fixture
def both_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")


def _stub_provider(mod, name: str, bytes_or_exc):
    """Replace a provider in mod._PROVIDERS with a stub that returns bytes or raises."""
    def fn(prompt, timeout, api_key):
        if isinstance(bytes_or_exc, BaseException):
            raise bytes_or_exc
        return bytes_or_exc
    mod._PROVIDERS[name] = fn


def test_auto_uses_gemini_first_when_both_keys_set(mod, monkeypatch, both_keys):
    raw = _make_png_bytes(1024, 1024)
    _stub_provider(mod, "gemini", raw)
    called = []
    def openai_stub(*a, **kw):
        called.append(("openai",))
        return _make_png_bytes()
    monkeypatch.setitem(mod._PROVIDERS, "openai", openai_stub)

    out, used = mod.fetch_product_image("Bananas")

    assert out is not None
    assert used == "gemini"
    assert called == []  # openai never invoked


def test_auto_falls_back_to_openai_when_gemini_raises(mod, monkeypatch, both_keys):
    _stub_provider(mod, "gemini", RuntimeError("gemini quota exhausted"))
    _stub_provider(mod, "openai", _make_png_bytes(1024, 1024))

    out, used = mod.fetch_product_image("Bananas")

    assert out is not None
    assert used == "openai"


def test_auto_returns_none_when_all_providers_fail(mod, monkeypatch, both_keys):
    _stub_provider(mod, "gemini", RuntimeError("gemini fail"))
    _stub_provider(mod, "openai", RuntimeError("openai fail"))

    out, used = mod.fetch_product_image("Bananas")

    assert out is None
    assert used is None


def test_provider_gemini_only_does_not_fallback(mod, monkeypatch, both_keys):
    _stub_provider(mod, "gemini", RuntimeError("gemini fail"))
    openai_called = []
    def openai_stub(*a, **kw):
        openai_called.append(True)
        return _make_png_bytes()
    monkeypatch.setitem(mod._PROVIDERS, "openai", openai_stub)

    out, used = mod.fetch_product_image("Bananas", provider="gemini")

    assert out is None
    assert used is None
    assert openai_called == []


def test_provider_openai_only(mod, monkeypatch, both_keys):
    _stub_provider(mod, "openai", _make_png_bytes())
    gemini_called = []
    monkeypatch.setitem(
        mod._PROVIDERS, "gemini",
        lambda *a, **kw: gemini_called.append(True) or _make_png_bytes(),
    )

    out, used = mod.fetch_product_image("Bananas", provider="openai")

    assert out is not None
    assert used == "openai"
    assert gemini_called == []


def test_returns_jpeg_bytes_downscaled(mod, monkeypatch, both_keys):
    _stub_provider(mod, "gemini", _make_png_bytes(2400, 2400))

    out, used = mod.fetch_product_image("Bananas", target_width=600)

    assert out[:3] == b"\xff\xd8\xff"  # JPEG magic
    img = Image.open(io.BytesIO(out))
    assert img.width == 600
    assert used == "gemini"


def test_empty_name_returns_none(mod):
    out, used = mod.fetch_product_image("   ")
    assert out is None
    assert used is None


def test_available_providers_reflects_env(mod, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert mod.available_providers() == []

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert mod.available_providers() == ["gemini"]

    monkeypatch.setenv("OPENAI_API_KEY", "y")
    assert mod.available_providers() == ["gemini", "openai"]


def test_unknown_provider_falls_back_to_auto(mod, monkeypatch, both_keys):
    _stub_provider(mod, "gemini", _make_png_bytes())

    out, used = mod.fetch_product_image("Bananas", provider="vertex")

    assert out is not None
    assert used == "gemini"


def test_prompt_includes_name_and_category(mod, monkeypatch, both_keys):
    captured = {}
    def stub(prompt, timeout, api_key):
        captured["prompt"] = prompt
        return _make_png_bytes()
    monkeypatch.setitem(mod._PROVIDERS, "gemini", stub)

    mod.fetch_product_image("Bananas", "Produce")

    assert "Bananas" in captured["prompt"]
    assert "Produce" in captured["prompt"]


def test_prompt_omits_filler_category(mod, monkeypatch, both_keys):
    captured = {}
    def stub(prompt, timeout, api_key):
        captured["prompt"] = prompt
        return _make_png_bytes()
    monkeypatch.setitem(mod._PROVIDERS, "gemini", stub)

    mod.fetch_product_image("Bananas", "other")

    assert "Bananas" in captured["prompt"]
    assert "other" not in captured["prompt"]
