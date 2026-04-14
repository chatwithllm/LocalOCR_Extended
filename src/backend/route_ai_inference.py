"""
Unified AI provider routing for receipt OCR.

Phase 1 resolves the requested or active model configuration and dispatches to
the provider-specific OCR functions while keeping the legacy env-based fallback
chain available when no model is selected.
"""

import os
import logging
import time
from pathlib import Path
from datetime import date, datetime, timezone

from flask import g

from cryptography.fernet import Fernet, InvalidToken

from src.backend.initialize_database_schema import AIModelConfig, ApiUsage

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    secret = (os.getenv("FERNET_SECRET_KEY") or "").strip()
    if not secret:
        raise ValueError("FERNET_SECRET_KEY not configured")
    return Fernet(secret.encode())


def encrypt_api_key(plaintext: str) -> str:
    cleaned = str(plaintext or "").strip()
    if not cleaned:
        raise ValueError("Stored API key is empty")
    return _get_fernet().encrypt(cleaned.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    if not (ciphertext or "").strip():
        raise ValueError("Stored API key is empty")
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (ValueError, InvalidToken) as exc:
        raise ValueError("Stored API key could not be decrypted") from exc


def _provider_env_key(provider: str) -> str | None:
    provider_name = str(provider or "").strip().lower()
    if provider_name == "gemini":
        return os.getenv("GEMINI_API_KEY")
    if provider_name == "openai":
        return os.getenv("OPENAI_API_KEY")
    if provider_name == "openrouter":
        return os.getenv("OPENROUTER_API_KEY")
    if provider_name == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    return None


def _resolve_api_key(model: AIModelConfig) -> str | None:
    mode = str(model.credential_mode or "env").strip().lower()
    if mode == "no_key_required":
        return None
    if mode == "stored_key":
        return decrypt_api_key(model.api_key_encrypted or "")
    return (_provider_env_key(model.provider) or "").strip() or None


def _normalize_usage_payload(usage: dict | None) -> dict:
    payload = usage or {}
    input_tokens = int(payload.get("input_tokens") or 0)
    output_tokens = int(payload.get("output_tokens") or 0)
    total_tokens = payload.get("total_tokens")
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": int(total_tokens or 0),
    }


def _estimate_usage_cost(model: AIModelConfig, usage: dict) -> float:
    input_rate = float(getattr(model, "input_cost_per_million", 0.0) or 0.0)
    output_rate = float(getattr(model, "output_cost_per_million", 0.0) or 0.0)
    return (
        (float(usage["input_tokens"]) / 1_000_000.0) * input_rate
        + (float(usage["output_tokens"]) / 1_000_000.0) * output_rate
    )


def _track_model_usage(model: AIModelConfig, normalized_result: dict) -> None:
    session = getattr(g, "db_session", None)
    if session is None:
        return

    usage = _normalize_usage_payload(normalized_result.get("usage"))
    service_name = f"ai_model:{int(model.id)}"
    today = date.today()
    row = session.query(ApiUsage).filter_by(service_name=service_name, date=today).first()
    if not row:
        row = ApiUsage(
            service_name=service_name,
            date=today,
            model_config_id=model.id,
            request_count=0,
            token_count=0,
            prompt_token_count=0,
            completion_token_count=0,
            estimated_cost_usd=0.0,
            total_latency_ms=0,
        )
        session.add(row)

    row.model_config_id = model.id
    row.request_count += 1
    row.token_count += usage["total_tokens"]
    row.prompt_token_count += usage["input_tokens"]
    row.completion_token_count += usage["output_tokens"]
    row.total_latency_ms += int(normalized_result.get("latency_ms") or 0)
    row.estimated_cost_usd += _estimate_usage_cost(model, usage)
    row.last_used_at = datetime.now(timezone.utc)
    session.commit()


def resolve_ai_model_selection(session, *, requested_model_id: int | None = None, user=None) -> tuple[AIModelConfig | None, list[str]]:
    """Resolve the active AI model for the current request and return warnings when auto-falling back."""
    warnings: list[str] = []
    model = None

    if requested_model_id:
        model = session.query(AIModelConfig).filter_by(id=requested_model_id).first()
        if not model:
            raise ValueError("Requested model was not found")
        if not model.is_enabled:
            raise ValueError("Requested model is disabled")
        return model, warnings

    active_model_id = getattr(user, "active_ai_model_config_id", None)
    if not active_model_id:
        return None, warnings

    model = session.query(AIModelConfig).filter_by(id=active_model_id).first()
    if model and model.is_enabled:
        return model, warnings

    if user and active_model_id:
        disabled_model_id = active_model_id
        user.active_ai_model_config_id = None
        session.commit()
        warnings.append("Your selected model is no longer available. Falling back to the default OCR provider.")
        logger.warning(
            "Disabled AI model fallback applied",
            extra={"user_id": getattr(user, "id", None), "model_config_id": disabled_model_id},
        )
    return None, warnings


def route_receipt_inference(
    *,
    image_path: str,
    source_file_path: str,
    mode_hint: str | None = None,
    model: AIModelConfig,
) -> dict:
    """Route receipt OCR to the selected provider and return a normalized result."""
    started_at = time.perf_counter()
    provider = str(model.provider or "").strip().lower()
    model_string = (model.model_string or "").strip()
    api_key = _resolve_api_key(model)
    source_suffix = Path(source_file_path or image_path).suffix.lower()
    is_pdf = source_suffix == ".pdf"

    if is_pdf and not model.supports_pdf:
        raise ValueError(f"Selected model '{model.name}' does not support PDF receipts")
    if not is_pdf and not model.supports_image_input:
        raise ValueError(f"Selected model '{model.name}' does not support image receipts")

    if provider == "gemini":
        from src.backend.call_gemini_vision_api import extract_receipt_via_gemini

        provider_result = extract_receipt_via_gemini(
            image_path,
            source_file_path=source_file_path,
            mode_hint=mode_hint,
            api_key=api_key,
            model_name=model_string,
            include_meta=True,
        )
    elif provider == "openai":
        from src.backend.call_openai_vision_api import extract_receipt_via_openai

        provider_result = extract_receipt_via_openai(
            image_path,
            mode_hint=mode_hint,
            api_key=api_key,
            model_name=model_string,
            base_url=model.base_url,
            include_meta=True,
        )
    elif provider == "openrouter":
        from src.backend.call_openai_vision_api import extract_receipt_via_openai

        extra_headers = {}
        referer = (os.getenv("OPENROUTER_HTTP_REFERER") or "").strip()
        title = (os.getenv("OPENROUTER_X_TITLE") or "LocalOCR Extended").strip()
        if referer:
            extra_headers["HTTP-Referer"] = referer
        if title:
            extra_headers["X-Title"] = title
        provider_result = extract_receipt_via_openai(
            image_path,
            mode_hint=mode_hint,
            api_key=api_key,
            model_name=model_string,
            base_url=(model.base_url or "https://openrouter.ai/api/v1"),
            extra_headers=extra_headers or None,
            include_meta=True,
        )
    elif provider == "ollama":
        from src.backend.call_ollama_vision_api import extract_receipt_via_ollama

        provider_result = extract_receipt_via_ollama(
            image_path,
            mode_hint=mode_hint,
            model_name=model_string,
            base_url=model.base_url,
            include_meta=True,
        )
    elif provider == "anthropic":
        from src.backend.call_anthropic_vision_api import extract_receipt_via_anthropic

        provider_result = extract_receipt_via_anthropic(
            image_path,
            mode_hint=mode_hint,
            api_key=api_key,
            model_name=model_string,
            include_meta=True,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    normalized_result = {
        "provider": provider,
        "model_string": model_string,
        "data": provider_result.get("data"),
        "usage": provider_result.get("usage"),
        "finish_reason": provider_result.get("finish_reason"),
        "response_meta": provider_result.get("response_meta") or {},
        "latency_ms": int((time.perf_counter() - started_at) * 1000),
    }
    _track_model_usage(model, normalized_result)
    return normalized_result
