"""
AI model registry, per-user selection, and admin management endpoints.
"""

import os
import logging
from datetime import datetime, timezone, date, timedelta

from flask import Blueprint, jsonify, request, g
from sqlalchemy import func

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import AIModelConfig, UserAIModelAccess, User, ApiUsage
from src.backend.manage_authentication import is_admin
from src.backend.route_ai_inference import encrypt_api_key

logger = logging.getLogger(__name__)

ai_models_bp = Blueprint("ai_models", __name__, url_prefix="/api/models")
admin_ai_models_bp = Blueprint("admin_ai_models", __name__, url_prefix="/api/admin/models")

VALID_PROVIDERS = {"gemini", "openai", "openrouter", "ollama", "anthropic"}
VALID_PRICE_TIERS = {"free", "premium", "pro", "enterprise"}
VALID_CREDENTIAL_MODES = {"env", "stored_key", "no_key_required"}


def _admin_or_403():
    user = getattr(g, "current_user", None)
    if not user or not is_admin(user):
        return None, (jsonify({"error": "Admin access required"}), 403)
    return user, None


def _env_has_value(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _provider_env_available(provider: str) -> bool:
    provider_name = str(provider or "").strip().lower()
    if provider_name == "gemini":
        return _env_has_value("GEMINI_API_KEY")
    if provider_name == "openai":
        return _env_has_value("OPENAI_API_KEY")
    if provider_name == "openrouter":
        return _env_has_value("OPENROUTER_API_KEY")
    if provider_name == "anthropic":
        return _env_has_value("ANTHROPIC_API_KEY")
    if provider_name == "ollama":
        return True
    return False


def _model_has_credentials(model: AIModelConfig) -> bool:
    mode = str(model.credential_mode or "env").strip().lower()
    if mode == "no_key_required":
        return True
    if mode == "stored_key":
        return bool((model.api_key_encrypted or "").strip())
    return _provider_env_available(model.provider)


def _user_has_model_access(user, model: AIModelConfig) -> bool:
    if not user or not model:
        return False
    if is_admin(user):
        return True
    if (model.price_tier or "free").strip().lower() == "free":
        return True
    access = (
        g.db_session.query(UserAIModelAccess)
        .filter_by(user_id=user.id, model_config_id=model.id)
        .first()
    )
    if not access:
        return False
    if access.expires_at:
        now = datetime.now(timezone.utc)
        expires_at = access.expires_at
        compare_now = now.replace(tzinfo=None) if getattr(expires_at, "tzinfo", None) is None else now
        if expires_at < compare_now:
            return False
    return True


def _serialize_model(model: AIModelConfig, user) -> dict:
    unlocked = _user_has_model_access(user, model)
    credentials_available = _model_has_credentials(model)
    selectable = bool(model.is_enabled and credentials_available and unlocked)
    return {
        "id": model.id,
        "name": model.name,
        "provider": model.provider,
        "model_string": model.model_string,
        "description": model.description,
        "price_tier": model.price_tier,
        "is_enabled": bool(model.is_enabled),
        "is_visible": bool(model.is_visible),
        "supports_vision": bool(model.supports_vision),
        "supports_pdf": bool(model.supports_pdf),
        "supports_json_mode": bool(model.supports_json_mode),
        "supports_image_input": bool(model.supports_image_input),
        "unlocked": unlocked,
        "locked": not unlocked,
        "active": bool(user and user.active_ai_model_config_id == model.id),
        "credentials_available": credentials_available,
        "selectable": selectable,
        "can_unlock": bool(model.is_enabled and model.is_visible and not unlocked),
        "base_url": model.base_url,
    }


def _serialize_admin_model(model: AIModelConfig, user) -> dict:
    payload = _serialize_model(model, user)
    payload.update({
        "credential_mode": model.credential_mode,
        "sort_order": model.sort_order,
        "input_cost_per_million": model.input_cost_per_million,
        "output_cost_per_million": model.output_cost_per_million,
        "created_by_id": model.created_by_id,
        "updated_by_id": model.updated_by_id,
        "has_stored_key": bool((model.api_key_encrypted or "").strip()),
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    })
    return payload


def _normalize_bool(value, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{field_name} must be true or false")


def _normalize_nullable_text(value) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _normalize_required_text(value, *, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _apply_admin_model_payload(model: AIModelConfig, payload: dict, *, actor_id: int | None, creating: bool) -> AIModelConfig:
    name = _normalize_required_text(payload.get("name"), field_name="name")
    provider = _normalize_required_text(payload.get("provider"), field_name="provider").lower()
    model_string = _normalize_required_text(payload.get("model_string"), field_name="model_string")
    price_tier = _normalize_required_text(payload.get("price_tier") or "free", field_name="price_tier").lower()
    credential_mode = _normalize_required_text(payload.get("credential_mode") or "env", field_name="credential_mode").lower()

    if provider not in VALID_PROVIDERS:
        raise ValueError(f"provider must be one of: {', '.join(sorted(VALID_PROVIDERS))}")
    if price_tier not in VALID_PRICE_TIERS:
        raise ValueError(f"price_tier must be one of: {', '.join(sorted(VALID_PRICE_TIERS))}")
    if credential_mode not in VALID_CREDENTIAL_MODES:
        raise ValueError(
            f"credential_mode must be one of: {', '.join(sorted(VALID_CREDENTIAL_MODES))}"
        )

    # Server-side safety net for the most common mistake: an admin pastes a key
    # into the form but leaves credential_mode at the default "env". Without
    # this, the key is silently dropped and the model stays unconfigured.
    raw_api_key = payload.get("api_key")
    if (
        credential_mode == "env"
        and raw_api_key is not None
        and str(raw_api_key).strip()
    ):
        credential_mode = "stored_key"

    model.name = name
    model.provider = provider
    model.model_string = model_string
    model.description = _normalize_nullable_text(payload.get("description"))
    model.price_tier = price_tier
    model.credential_mode = credential_mode
    model.base_url = _normalize_nullable_text(payload.get("base_url"))
    raw_input_cost = payload.get("input_cost_per_million")
    raw_output_cost = payload.get("output_cost_per_million")
    model.input_cost_per_million = (
        float(raw_input_cost) if raw_input_cost not in (None, "", "null") else None
    )
    model.output_cost_per_million = (
        float(raw_output_cost) if raw_output_cost not in (None, "", "null") else None
    )
    model.is_enabled = _normalize_bool(payload.get("is_enabled", True), field_name="is_enabled")
    model.is_visible = _normalize_bool(payload.get("is_visible", True), field_name="is_visible")
    model.supports_vision = _normalize_bool(payload.get("supports_vision", True), field_name="supports_vision")
    model.supports_pdf = _normalize_bool(payload.get("supports_pdf", False), field_name="supports_pdf")
    model.supports_json_mode = _normalize_bool(payload.get("supports_json_mode", False), field_name="supports_json_mode")
    model.supports_image_input = _normalize_bool(
        payload.get("supports_image_input", True),
        field_name="supports_image_input",
    )

    raw_sort_order = payload.get("sort_order", model.sort_order if not creating else 100)
    try:
        model.sort_order = int(raw_sort_order)
    except (TypeError, ValueError) as exc:
        raise ValueError("sort_order must be an integer") from exc

    stored_api_key = payload.get("api_key")
    clear_stored_key = _normalize_bool(payload.get("clear_stored_key", False), field_name="clear_stored_key")
    if credential_mode == "stored_key":
        if stored_api_key is not None and str(stored_api_key).strip():
            try:
                model.api_key_encrypted = encrypt_api_key(str(stored_api_key).strip())
            except ValueError as exc:
                msg = str(exc)
                if "FERNET_SECRET_KEY" in msg:
                    raise ValueError(
                        "Cannot store API key: FERNET_SECRET_KEY is not set on the server. "
                        "Generate one with `python -c \"from cryptography.fernet import Fernet; "
                        "print(Fernet.generate_key().decode())\"`, add it to .env, and restart the container."
                    ) from exc
                raise
        elif creating and not (model.api_key_encrypted or "").strip():
            raise ValueError("api_key is required when credential_mode is stored_key")
        elif clear_stored_key:
            model.api_key_encrypted = None
    else:
        if clear_stored_key:
            model.api_key_encrypted = None

    if creating:
        model.created_by_id = actor_id
    model.updated_by_id = actor_id
    return model


@ai_models_bp.route("", methods=["GET"])
@require_auth
def list_models():
    """Return visible models plus current-user access state."""
    user = getattr(g, "current_user", None)
    include_hidden = request.args.get("include_hidden") == "1" and is_admin(user)
    query = g.db_session.query(AIModelConfig)
    if not include_hidden:
        query = query.filter(AIModelConfig.is_visible.is_(True))
    models = query.order_by(AIModelConfig.sort_order.asc(), AIModelConfig.name.asc()).all()
    return jsonify({
        "models": [_serialize_model(model, user) for model in models],
        "active_model_config_id": getattr(user, "active_ai_model_config_id", None),
    }), 200


@ai_models_bp.route("/select", methods=["POST"])
@require_write_access
def select_model():
    """Persist the user's active model selection after server-side validation."""
    user = getattr(g, "current_user", None)
    payload = request.get_json(silent=True) or {}
    raw_model_id = payload.get("model_id")

    if raw_model_id in (None, "", 0):
        user.active_ai_model_config_id = None
        g.db_session.commit()
        return jsonify({
            "message": "Model selection cleared",
            "active_model_config_id": None,
        }), 200

    try:
        model_id = int(raw_model_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid model_id"}), 400

    model = g.db_session.query(AIModelConfig).filter_by(id=model_id).first()
    if not model:
        return jsonify({"error": "Model not found"}), 404
    if not model.is_enabled:
        return jsonify({"error": "Selected model is disabled"}), 400
    if not model.is_visible and not is_admin(user):
        return jsonify({"error": "Selected model is not available"}), 403
    if not _user_has_model_access(user, model):
        return jsonify({"error": "Selected model is locked for this user"}), 403
    if not _model_has_credentials(model):
        return jsonify({"error": "Selected model is not configured on this server"}), 400

    user.active_ai_model_config_id = model.id
    g.db_session.commit()
    logger.info("User %s selected AI model %s (%s)", user.id, model.id, model.provider)
    return jsonify({
        "message": "Active model updated",
        "active_model_config_id": model.id,
        "model": _serialize_model(model, user),
    }), 200


@ai_models_bp.route("/unlock", methods=["POST"])
@require_write_access
def unlock_model():
    """Grant a model entitlement to the current user, or another user when the actor is an admin."""
    actor = getattr(g, "current_user", None)
    payload = request.get_json(silent=True) or {}
    raw_model_id = payload.get("model_id")
    raw_target_user_id = payload.get("target_user_id")

    try:
        model_id = int(raw_model_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid model_id"}), 400

    target_user_id = getattr(actor, "id", None)
    if raw_target_user_id not in (None, "", 0):
        if not is_admin(actor):
            return jsonify({"error": "Only admins can grant model access to other users"}), 403
        try:
            target_user_id = int(raw_target_user_id)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid target_user_id"}), 400

    model = g.db_session.query(AIModelConfig).filter_by(id=model_id).first()
    if not model:
        return jsonify({"error": "Model not found"}), 404
    if not model.is_enabled:
        return jsonify({"error": "Selected model is disabled"}), 400
    if not model.is_visible and not is_admin(actor):
        return jsonify({"error": "Selected model is not available"}), 403

    target_user = g.db_session.query(User).filter_by(id=target_user_id).first()
    if not target_user:
        return jsonify({"error": "Target user not found"}), 404

    if (model.price_tier or "free").strip().lower() == "free":
        return jsonify({
            "message": "Free models do not require unlocking",
            "model": _serialize_model(model, actor),
        }), 200

    access = (
        g.db_session.query(UserAIModelAccess)
        .filter_by(user_id=target_user.id, model_config_id=model.id)
        .first()
    )
    if not access:
        access = UserAIModelAccess(user_id=target_user.id, model_config_id=model.id)
        g.db_session.add(access)
    else:
        access.expires_at = None
        access.updated_at = datetime.now(timezone.utc)

    g.db_session.commit()
    logger.info(
        "Model %s unlocked for user %s by actor %s",
        model.id,
        target_user.id,
        getattr(actor, "id", None),
    )
    return jsonify({
        "message": "Model unlocked",
        "model": _serialize_model(model, target_user if target_user.id == actor.id else actor),
        "target_user_id": target_user.id,
    }), 200


@admin_ai_models_bp.route("", methods=["GET"])
@require_auth
def list_admin_models():
    actor, error = _admin_or_403()
    if error:
        return error
    models = (
        g.db_session.query(AIModelConfig)
        .order_by(AIModelConfig.sort_order.asc(), AIModelConfig.name.asc())
        .all()
    )
    return jsonify({
        "models": [_serialize_admin_model(model, actor) for model in models],
    }), 200


@admin_ai_models_bp.route("/usage", methods=["GET"])
@require_auth
def list_admin_model_usage():
    actor, error = _admin_or_403()
    if error:
        return error

    days = request.args.get("days", default=7, type=int) or 7
    days = max(1, min(days, 30))
    cutoff = date.today() - timedelta(days=days - 1)

    rows = (
        g.db_session.query(ApiUsage, AIModelConfig)
        .outerjoin(AIModelConfig, AIModelConfig.id == ApiUsage.model_config_id)
        .filter(ApiUsage.service_name.like("ai_model:%"), ApiUsage.date >= cutoff)
        .order_by(ApiUsage.date.desc(), ApiUsage.service_name.asc())
        .all()
    )

    by_model: dict[int, dict] = {}
    daily_rows: list[dict] = []
    for usage, model in rows:
        model_id = getattr(usage, "model_config_id", None) or getattr(model, "id", None)
        if not model_id:
            continue
        bucket = by_model.setdefault(model_id, {
            "model_config_id": model_id,
            "name": getattr(model, "name", None) or usage.service_name,
            "provider": getattr(model, "provider", None),
            "model_string": getattr(model, "model_string", None),
            "request_count": 0,
            "token_count": 0,
            "prompt_token_count": 0,
            "completion_token_count": 0,
            "estimated_cost_usd": 0.0,
            "total_latency_ms": 0,
            "last_used_at": None,
        })
        bucket["request_count"] += int(getattr(usage, "request_count", 0) or 0)
        bucket["token_count"] += int(getattr(usage, "token_count", 0) or 0)
        bucket["prompt_token_count"] += int(getattr(usage, "prompt_token_count", 0) or 0)
        bucket["completion_token_count"] += int(getattr(usage, "completion_token_count", 0) or 0)
        bucket["estimated_cost_usd"] += float(getattr(usage, "estimated_cost_usd", 0.0) or 0.0)
        bucket["total_latency_ms"] += int(getattr(usage, "total_latency_ms", 0) or 0)
        if getattr(usage, "last_used_at", None):
            previous = bucket["last_used_at"]
            bucket["last_used_at"] = (
                usage.last_used_at.isoformat()
                if not previous or usage.last_used_at.isoformat() > previous
                else previous
            )
        daily_rows.append({
            "date": usage.date.isoformat() if usage.date else None,
            "model_config_id": model_id,
            "name": bucket["name"],
            "provider": bucket["provider"],
            "request_count": int(getattr(usage, "request_count", 0) or 0),
            "token_count": int(getattr(usage, "token_count", 0) or 0),
            "prompt_token_count": int(getattr(usage, "prompt_token_count", 0) or 0),
            "completion_token_count": int(getattr(usage, "completion_token_count", 0) or 0),
            "estimated_cost_usd": round(float(getattr(usage, "estimated_cost_usd", 0.0) or 0.0), 6),
            "avg_latency_ms": round(
                (float(getattr(usage, "total_latency_ms", 0) or 0) / float(getattr(usage, "request_count", 0) or 1)),
                2,
            ),
        })

    model_rows = sorted(
        [
            {
                **payload,
                "estimated_cost_usd": round(payload["estimated_cost_usd"], 6),
                "avg_latency_ms": round(payload["total_latency_ms"] / payload["request_count"], 2)
                if payload["request_count"]
                else 0.0,
            }
            for payload in by_model.values()
        ],
        key=lambda item: (-item["request_count"], -(item["estimated_cost_usd"]), str(item["name"] or "")),
    )

    return jsonify({
        "days": days,
        "models": model_rows,
        "daily": daily_rows,
        "totals": {
            "request_count": sum(item["request_count"] for item in model_rows),
            "token_count": sum(item["token_count"] for item in model_rows),
            "estimated_cost_usd": round(sum(item["estimated_cost_usd"] for item in model_rows), 6),
        },
    }), 200


@admin_ai_models_bp.route("", methods=["POST"])
@require_write_access
def create_admin_model():
    actor, error = _admin_or_403()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        model = _apply_admin_model_payload(
            AIModelConfig(),
            payload,
            actor_id=getattr(actor, "id", None),
            creating=True,
        )
        existing = (
            g.db_session.query(AIModelConfig)
            .filter_by(provider=model.provider, model_string=model.model_string)
            .first()
        )
        if existing:
            return jsonify({"error": "A model with this provider and model string already exists"}), 409
        g.db_session.add(model)
        g.db_session.commit()
    except ValueError as exc:
        g.db_session.rollback()
        return jsonify({"error": str(exc)}), 400
    logger.info("Admin %s created AI model %s", getattr(actor, "id", None), model.id)
    return jsonify({
        "message": "AI model created",
        "model": _serialize_admin_model(model, actor),
    }), 201


@admin_ai_models_bp.route("/<int:model_id>", methods=["PATCH"])
@require_write_access
def update_admin_model(model_id: int):
    actor, error = _admin_or_403()
    if error:
        return error
    model = g.db_session.query(AIModelConfig).filter_by(id=model_id).first()
    if not model:
        return jsonify({"error": "Model not found"}), 404

    payload = request.get_json(silent=True) or {}
    incoming_provider = (
        str(payload.get("provider") or model.provider or "").strip().lower()
    )
    incoming_model_string = (
        str(payload.get("model_string") or model.model_string or "").strip()
    )
    # Pre-flight conflict check BEFORE we mutate `model`, otherwise the
    # autoflush triggered by the conflict query writes the new values and
    # SQLite raises an IntegrityError that bubbles as a 500.
    if incoming_provider and incoming_model_string:
        with g.db_session.no_autoflush:
            conflict = (
                g.db_session.query(AIModelConfig)
                .filter(
                    AIModelConfig.provider == incoming_provider,
                    AIModelConfig.model_string == incoming_model_string,
                    AIModelConfig.id != model.id,
                )
                .first()
            )
        if conflict:
            return jsonify({
                "error": (
                    f"Another row already uses provider '{incoming_provider}' + "
                    f"model '{incoming_model_string}' (id={conflict.id}). "
                    "Edit that row directly, or pick a different model string here."
                ),
            }), 409

    try:
        _apply_admin_model_payload(
            model,
            payload,
            actor_id=getattr(actor, "id", None),
            creating=False,
        )
        g.db_session.commit()
    except ValueError as exc:
        g.db_session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        g.db_session.rollback()
        logger.exception("Failed to update AI model %s: %s", model.id, exc)
        return jsonify({"error": "Could not save model. Check server logs."}), 500

    logger.info("Admin %s updated AI model %s", getattr(actor, "id", None), model.id)
    return jsonify({
        "message": "AI model updated",
        "model": _serialize_admin_model(model, actor),
    }), 200
