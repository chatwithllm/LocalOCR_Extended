"""
Plaid integration — Phase 1.

Endpoints for creating a Link token, exchanging a public token for an access
token, and listing / disconnecting connected items. All Plaid API calls live
server-side. Access tokens are Fernet-encrypted at rest using the same
`FERNET_SECRET_KEY` the AI-model config layer uses.

Transaction fetching is handled by a separate phase; this module only covers
the connection lifecycle.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify, g

from plaid.exceptions import ApiException
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import PlaidItem
from src.backend.plaid_client import (
    PlaidConfigurationError,
    country_codes_from_strings,
    get_client,
    get_plaid_env_name,
    is_plaid_configured,
    products_from_strings,
    redact_token,
)
from src.backend.route_ai_inference import decrypt_api_key, encrypt_api_key


logger = logging.getLogger(__name__)

plaid_bp = Blueprint("plaid", __name__, url_prefix="/plaid")

LINK_CLIENT_NAME = "LocalOCR Extended"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plaid_error_response(exc: ApiException):
    """Convert a Plaid ApiException into a sanitized client response."""
    body = {}
    try:
        body = json.loads(getattr(exc, "body", "") or "{}")
    except (TypeError, ValueError):
        body = {}
    error_code = body.get("error_code") or "PLAID_ERROR"
    display_message = (
        body.get("display_message")
        or body.get("error_message")
        or "Plaid request failed"
    )
    logger.warning("Plaid API error: %s — %s", error_code, body.get("error_message"))
    return jsonify({
        "error": display_message,
        "error_code": error_code,
    }), 502


def _serialize_item(item: PlaidItem) -> dict:
    accounts = []
    if item.accounts_json:
        try:
            accounts = json.loads(item.accounts_json) or []
        except (TypeError, ValueError):
            accounts = []
    return {
        "id": item.id,
        "institution_id": item.institution_id,
        "institution_name": item.institution_name,
        "accounts": accounts,
        "products": (item.products or "").split(",") if item.products else [],
        "status": item.status,
        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        "last_sync_status": item.last_sync_status,
        "last_sync_error": item.last_sync_error,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _current_user_id() -> int | None:
    user = getattr(g, "current_user", None)
    return int(user.id) if user else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@plaid_bp.route("/status", methods=["GET"])
@require_auth
def plaid_status():
    """Lightweight check used by the frontend to decide whether to render Plaid UI."""
    return jsonify({
        "configured": is_plaid_configured(),
        "env": get_plaid_env_name(),
    }), 200


@plaid_bp.route("/link-token", methods=["POST"])
@require_write_access
def create_link_token():
    if not is_plaid_configured():
        return jsonify({"error": "Plaid is not configured on this server."}), 503
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    payload = request.get_json(silent=True) or {}
    existing_item_id = payload.get("item_id")
    update_mode = bool(existing_item_id)

    try:
        client = get_client()
        request_obj = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=str(user_id)),
            client_name=LINK_CLIENT_NAME,
            products=products_from_strings() if not update_mode else [],
            country_codes=country_codes_from_strings(),
            language="en",
        )
        if update_mode:
            # In update mode we pass the existing item's access_token so Plaid
            # re-auths the same connection instead of starting a new one.
            session = g.db_session
            item = (
                session.query(PlaidItem)
                .filter_by(id=int(existing_item_id), user_id=user_id)
                .first()
            )
            if not item:
                return jsonify({"error": "Plaid item not found"}), 404
            access_token = decrypt_api_key(item.access_token_encrypted)
            request_obj.access_token = access_token
        response = client.link_token_create(request_obj)
        return jsonify({
            "link_token": response["link_token"],
            "expiration": response["expiration"],
            "env": get_plaid_env_name(),
            "update_mode": update_mode,
        }), 200
    except PlaidConfigurationError as exc:
        logger.error("Plaid misconfigured: %s", exc)
        return jsonify({"error": str(exc)}), 503
    except ApiException as exc:
        return _plaid_error_response(exc)


@plaid_bp.route("/exchange-public-token", methods=["POST"])
@require_write_access
def exchange_public_token():
    if not is_plaid_configured():
        return jsonify({"error": "Plaid is not configured on this server."}), 503
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    payload = request.get_json(silent=True) or {}
    public_token = (payload.get("public_token") or "").strip()
    if not public_token:
        return jsonify({"error": "public_token is required"}), 400

    metadata = payload.get("metadata") or {}
    institution = metadata.get("institution") or {}
    accounts_meta = metadata.get("accounts") or []

    session = g.db_session

    try:
        client = get_client()
        exchange_req = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_res = client.item_public_token_exchange(exchange_req)
    except ApiException as exc:
        return _plaid_error_response(exc)
    except PlaidConfigurationError as exc:
        return jsonify({"error": str(exc)}), 503

    access_token = exchange_res["access_token"]
    plaid_item_id = exchange_res["item_id"]
    logger.info(
        "Exchanged public token for user %s — item=%s access=%s",
        user_id,
        plaid_item_id,
        redact_token(access_token),
    )

    existing = session.query(PlaidItem).filter_by(plaid_item_id=plaid_item_id).first()
    if existing:
        # Same institution re-linked; refresh token + metadata.
        existing.user_id = user_id
        existing.access_token_encrypted = encrypt_api_key(access_token)
        existing.institution_id = institution.get("institution_id") or existing.institution_id
        existing.institution_name = institution.get("name") or existing.institution_name
        existing.accounts_json = json.dumps(accounts_meta) if accounts_meta else existing.accounts_json
        existing.status = "active"
        existing.last_sync_error = None
        existing.last_sync_status = None
        item_record = existing
    else:
        item_record = PlaidItem(
            user_id=user_id,
            plaid_item_id=plaid_item_id,
            institution_id=institution.get("institution_id"),
            institution_name=institution.get("name"),
            access_token_encrypted=encrypt_api_key(access_token),
            accounts_json=json.dumps(accounts_meta) if accounts_meta else None,
            products=",".join(["transactions", "liabilities"]),
            status="active",
        )
        session.add(item_record)
    session.commit()

    return jsonify({
        "item": _serialize_item(item_record),
    }), 201


@plaid_bp.route("/items", methods=["GET"])
@require_auth
def list_items():
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    session = g.db_session
    items = (
        session.query(PlaidItem)
        .filter_by(user_id=user_id)
        .order_by(PlaidItem.created_at.desc())
        .all()
    )
    return jsonify({
        "configured": is_plaid_configured(),
        "env": get_plaid_env_name(),
        "items": [_serialize_item(it) for it in items],
    }), 200


@plaid_bp.route("/items/<int:item_id>", methods=["DELETE"])
@require_write_access
def delete_item(item_id: int):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    session = g.db_session
    item = (
        session.query(PlaidItem)
        .filter_by(id=item_id, user_id=user_id)
        .first()
    )
    if not item:
        return jsonify({"error": "Plaid item not found"}), 404

    # Best-effort Plaid-side disconnect; continue locally even if it fails.
    if is_plaid_configured():
        try:
            client = get_client()
            access_token = decrypt_api_key(item.access_token_encrypted)
            client.item_remove(ItemRemoveRequest(access_token=access_token))
        except ApiException as exc:
            logger.warning(
                "Plaid item_remove failed for item %s — deleting locally anyway: %s",
                item.plaid_item_id,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Plaid disconnect error for item %s: %s", item.plaid_item_id, exc)

    session.delete(item)
    session.commit()
    return jsonify({"deleted_id": item_id}), 200
