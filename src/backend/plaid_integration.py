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
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import PlaidItem, PlaidStagedTransaction
from src.backend.plaid_transaction_mapper import annotate_all_ready_staged
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


def _plaid_transaction_to_row(txn_dict: dict) -> dict:
    """Extract the stable fields we persist for every Plaid transaction.

    Input is the serialized Plaid transaction dict (from Plaid SDK to_dict()).
    Output is a dict of fields matching PlaidStagedTransaction columns.
    """
    category_list = txn_dict.get("category") or []
    personal_finance = txn_dict.get("personal_finance_category") or {}
    primary = None
    detailed = None
    if isinstance(personal_finance, dict):
        primary = personal_finance.get("primary") or None
        detailed = personal_finance.get("detailed") or None
    if not primary and category_list:
        primary = category_list[0]
    if not detailed and len(category_list) > 1:
        detailed = " / ".join(category_list[1:])

    return {
        "plaid_transaction_id": str(txn_dict.get("transaction_id") or "").strip(),
        "plaid_account_id": str(txn_dict.get("account_id") or "").strip(),
        "amount": float(txn_dict.get("amount") or 0.0),
        "iso_currency_code": (txn_dict.get("iso_currency_code") or txn_dict.get("unofficial_currency_code") or None),
        "transaction_date": txn_dict.get("date"),  # plaid returns YYYY-MM-DD or datetime.date
        "authorized_date": txn_dict.get("authorized_date"),
        "name": txn_dict.get("name") or None,
        "merchant_name": txn_dict.get("merchant_name") or None,
        "plaid_category_primary": primary,
        "plaid_category_detailed": detailed,
        "plaid_category_json": json.dumps(category_list) if category_list else None,
        "pending": bool(txn_dict.get("pending") or False),
    }


def _coerce_date(value):
    from datetime import date as date_cls, datetime as datetime_cls
    if value is None or value == "":
        return None
    if isinstance(value, date_cls) and not isinstance(value, datetime_cls):
        return value
    if isinstance(value, datetime_cls):
        return value.date()
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def sync_plaid_item_inner(session, item: PlaidItem) -> dict:
    """Perform a /transactions/sync pass for one item. Caller handles HTTP.

    Returns a dict { added, modified, removed, pages, error } — on Plaid failure,
    updates item.last_sync_status + error fields, commits, and raises ApiException.
    """
    try:
        access_token = decrypt_api_key(item.access_token_encrypted)
    except ValueError as exc:
        item.status = "disconnected"
        item.last_sync_status = "error"
        item.last_sync_error = "Access token could not be decrypted"
        item.last_sync_at = datetime.utcnow()
        session.commit()
        raise

    client = get_client()
    cursor = item.transaction_cursor or ""
    added_count = 0
    modified_count = 0
    removed_count = 0
    pages = 0
    has_more = True

    try:
        while has_more and pages < 10:  # safety cap
            pages += 1
            sync_req = TransactionsSyncRequest(
                access_token=access_token,
                cursor=cursor or None,
                count=500,
            )
            response = client.transactions_sync(sync_req).to_dict()
            cursor = response.get("next_cursor") or cursor
            has_more = bool(response.get("has_more"))

            for added in response.get("added") or []:
                added_count += 1
                _upsert_staged(session, item, item.user_id, added)
            for modified in response.get("modified") or []:
                modified_count += 1
                _upsert_staged(session, item, item.user_id, modified)
            for removed in response.get("removed") or []:
                removed_id = str(removed.get("transaction_id") or "").strip()
                if not removed_id:
                    continue
                staged = (
                    session.query(PlaidStagedTransaction)
                    .filter_by(plaid_transaction_id=removed_id)
                    .first()
                )
                if staged and staged.status not in {"confirmed", "dismissed"}:
                    staged.status = "dismissed"
                    staged.dismissed_at = datetime.utcnow()
                    removed_count += 1
        item.transaction_cursor = cursor
        item.last_sync_at = datetime.utcnow()
        item.last_sync_status = "ok"
        item.last_sync_error = None
        if item.status == "login_required":
            item.status = "active"
        annotate_all_ready_staged(session, plaid_item_id=item.id)
        session.commit()
    except ApiException as exc:
        session.rollback()
        body = {}
        try:
            body = json.loads(getattr(exc, "body", "") or "{}")
        except (TypeError, ValueError):
            body = {}
        error_code = body.get("error_code") or "PLAID_ERROR"
        if error_code == "ITEM_LOGIN_REQUIRED":
            item.status = "login_required"
        item.last_sync_status = "error"
        item.last_sync_error = body.get("error_message") or str(exc)[:500]
        item.last_sync_at = datetime.utcnow()
        session.commit()
        raise

    return {
        "added": added_count,
        "modified": modified_count,
        "removed": removed_count,
        "pages": pages,
    }


@plaid_bp.route("/items/<int:item_id>/sync", methods=["POST"])
@require_write_access
def sync_item_transactions(item_id: int):
    """Fetch new/modified/removed transactions for a Plaid item and stage them."""
    if not is_plaid_configured():
        return jsonify({"error": "Plaid is not configured on this server."}), 503
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

    try:
        stats = sync_plaid_item_inner(session, item)
    except ValueError:
        return jsonify({"error": "Bank connection needs to be re-authenticated."}), 409
    except ApiException as exc:
        return _plaid_error_response(exc)

    return jsonify({"item": _serialize_item(item), **stats}), 200


@plaid_bp.route("/webhook", methods=["POST"])
def plaid_webhook():
    """Plaid sends webhooks for TRANSACTIONS_DEFAULT_UPDATE and friends.

    SECURITY — TODO before opening this endpoint to the public internet:
    Plaid signs each webhook with a JWT passed in the `Plaid-Verification`
    header. We must verify it against Plaid's public key
    (/webhook_verification_key/get) before trusting any field in the body.
    Without verification, anyone who guesses a real `item_id` can trigger
    syncs or flip our item to "login_required" by POSTing crafted JSON.

    Current state is intentional for sandbox testing only — sandbox webhooks
    are initiated from the Plaid dashboard against a localhost/ngrok tunnel
    and the attack surface is zero. For production this check MUST be
    implemented. Tracked as the webhook-verification TODO in the Plaid
    review notes; see plaid.com/docs/api/webhooks/webhook-verification.
    """
    payload = request.get_json(silent=True) or {}
    webhook_type = payload.get("webhook_type") or ""
    webhook_code = payload.get("webhook_code") or ""
    plaid_item_id = payload.get("item_id") or ""
    logger.info(
        "Plaid webhook received: type=%s code=%s item=%s",
        webhook_type,
        webhook_code,
        plaid_item_id,
    )

    if not plaid_item_id:
        return jsonify({"ok": True, "note": "no item_id"}), 200

    session = g.db_session
    item = session.query(PlaidItem).filter_by(plaid_item_id=plaid_item_id).first()
    if not item:
        logger.warning("Plaid webhook for unknown item_id %s — ignoring", plaid_item_id)
        return jsonify({"ok": True, "note": "unknown item"}), 200

    if webhook_code in {"SYNC_UPDATES_AVAILABLE", "DEFAULT_UPDATE", "INITIAL_UPDATE", "HISTORICAL_UPDATE"}:
        try:
            sync_plaid_item_inner(session, item)
        except ApiException as exc:
            logger.warning("Webhook-triggered Plaid sync failed for item %s: %s", plaid_item_id, exc)
        except ValueError as exc:
            logger.warning("Webhook-triggered Plaid sync decrypt failed for item %s: %s", plaid_item_id, exc)
    elif webhook_code in {"ITEM_LOGIN_REQUIRED", "PENDING_EXPIRATION", "USER_PERMISSION_REVOKED"}:
        item.status = "login_required" if webhook_code == "ITEM_LOGIN_REQUIRED" else item.status
        item.last_sync_status = "error"
        item.last_sync_error = f"Webhook: {webhook_code}"
        session.commit()

    return jsonify({"ok": True}), 200


def run_scheduled_plaid_sync() -> None:
    """Iterate active Plaid items and sync each. Called by APScheduler."""
    from src.backend.initialize_database_schema import initialize_database

    if not is_plaid_configured():
        return
    _, SessionFactory = initialize_database()
    session = SessionFactory()
    try:
        items = (
            session.query(PlaidItem)
            .filter(PlaidItem.status == "active")
            .all()
        )
        for item in items:
            try:
                sync_plaid_item_inner(session, item)
                logger.info("Scheduled Plaid sync complete for item %s", item.plaid_item_id)
            except ApiException as exc:
                logger.warning("Scheduled Plaid sync ApiException for %s: %s", item.plaid_item_id, exc)
            except ValueError as exc:
                logger.warning("Scheduled Plaid sync decrypt error for %s: %s", item.plaid_item_id, exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Scheduled Plaid sync unexpected error for %s: %s", item.plaid_item_id, exc)
    finally:
        session.close()


def _upsert_staged(session, item: PlaidItem, user_id: int, txn_dict: dict) -> None:
    """Insert or update a PlaidStagedTransaction row from a raw Plaid transaction dict."""
    row_fields = _plaid_transaction_to_row(txn_dict)
    txn_id = row_fields["plaid_transaction_id"]
    if not txn_id:
        return

    staged = (
        session.query(PlaidStagedTransaction)
        .filter_by(plaid_transaction_id=txn_id)
        .first()
    )
    raw_payload = json.dumps(txn_dict, default=str)
    txn_date = _coerce_date(row_fields["transaction_date"])
    auth_date = _coerce_date(row_fields["authorized_date"])

    if staged is None:
        staged = PlaidStagedTransaction(
            plaid_item_id=item.id,
            user_id=user_id,
            plaid_transaction_id=txn_id,
            plaid_account_id=row_fields["plaid_account_id"],
            amount=row_fields["amount"],
            iso_currency_code=row_fields["iso_currency_code"],
            transaction_date=txn_date,
            authorized_date=auth_date,
            name=row_fields["name"],
            merchant_name=row_fields["merchant_name"],
            plaid_category_primary=row_fields["plaid_category_primary"],
            plaid_category_detailed=row_fields["plaid_category_detailed"],
            plaid_category_json=row_fields["plaid_category_json"],
            pending=row_fields["pending"],
            status="skipped_pending" if row_fields["pending"] else "ready_to_import",
            raw_json=raw_payload,
        )
        session.add(staged)
    else:
        # Don't overwrite a user-confirmed or dismissed row
        if staged.status in {"confirmed", "dismissed"}:
            return
        staged.plaid_account_id = row_fields["plaid_account_id"] or staged.plaid_account_id
        staged.amount = row_fields["amount"]
        staged.iso_currency_code = row_fields["iso_currency_code"] or staged.iso_currency_code
        if txn_date:
            staged.transaction_date = txn_date
        if auth_date:
            staged.authorized_date = auth_date
        staged.name = row_fields["name"] or staged.name
        staged.merchant_name = row_fields["merchant_name"] or staged.merchant_name
        staged.plaid_category_primary = row_fields["plaid_category_primary"] or staged.plaid_category_primary
        staged.plaid_category_detailed = row_fields["plaid_category_detailed"] or staged.plaid_category_detailed
        staged.plaid_category_json = row_fields["plaid_category_json"] or staged.plaid_category_json
        staged.pending = row_fields["pending"]
        staged.raw_json = raw_payload
        # Pending flipped to posted -> switch from skipped_pending to ready_to_import
        if staged.status == "skipped_pending" and not row_fields["pending"]:
            staged.status = "ready_to_import"


def _serialize_staged(staged: PlaidStagedTransaction, item: PlaidItem | None = None) -> dict:
    return {
        "id": staged.id,
        "plaid_item_id": staged.plaid_item_id,
        "institution_name": getattr(item, "institution_name", None) if item else None,
        "plaid_transaction_id": staged.plaid_transaction_id,
        "plaid_account_id": staged.plaid_account_id,
        "amount": float(staged.amount or 0),
        "iso_currency_code": staged.iso_currency_code,
        "transaction_date": staged.transaction_date.isoformat() if staged.transaction_date else None,
        "authorized_date": staged.authorized_date.isoformat() if staged.authorized_date else None,
        "name": staged.name,
        "merchant_name": staged.merchant_name,
        "plaid_category_primary": staged.plaid_category_primary,
        "plaid_category_detailed": staged.plaid_category_detailed,
        "pending": bool(staged.pending),
        "status": staged.status,
        "suggested_receipt_type": staged.suggested_receipt_type,
        "suggested_spending_domain": staged.suggested_spending_domain,
        "suggested_budget_category": staged.suggested_budget_category,
        "duplicate_purchase_id": staged.duplicate_purchase_id,
        "confirmed_purchase_id": staged.confirmed_purchase_id,
        "created_at": staged.created_at.isoformat() if staged.created_at else None,
    }


@plaid_bp.route("/staged-transactions", methods=["GET"])
@require_auth
def list_staged_transactions():
    """List staged Plaid transactions for the current user, grouped by status."""
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    session = g.db_session
    query = (
        session.query(PlaidStagedTransaction)
        .filter_by(user_id=user_id)
        .order_by(PlaidStagedTransaction.transaction_date.desc(), PlaidStagedTransaction.id.desc())
    )
    status_filter = (request.args.get("status") or "").strip().lower()
    if status_filter in {"ready_to_import", "duplicate_flagged", "skipped_pending", "confirmed", "dismissed"}:
        query = query.filter_by(status=status_filter)
    rows = query.limit(500).all()

    items_by_id = {
        it.id: it
        for it in session.query(PlaidItem).filter_by(user_id=user_id).all()
    }
    serialized = [_serialize_staged(r, items_by_id.get(r.plaid_item_id)) for r in rows]
    counts = {
        "ready_to_import": 0,
        "duplicate_flagged": 0,
        "skipped_pending": 0,
        "confirmed": 0,
        "dismissed": 0,
    }
    for row in (
        session.query(PlaidStagedTransaction.status, PlaidStagedTransaction.id)
        .filter_by(user_id=user_id)
        .all()
    ):
        status_key = row[0]
        if status_key in counts:
            counts[status_key] += 1
    return jsonify({
        "staged_transactions": serialized,
        "counts": counts,
        "status_filter": status_filter or None,
    }), 200


@plaid_bp.route("/staged-transactions/<int:staged_id>/confirm", methods=["POST"])
@require_write_access
def confirm_staged_transaction(staged_id: int):
    """Promote a staged Plaid transaction into a Purchase + TelegramReceipt row."""
    from src.backend.handle_receipt_upload import _create_manual_receipt_entry

    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    session = g.db_session
    staged = (
        session.query(PlaidStagedTransaction)
        .filter_by(id=staged_id, user_id=user_id)
        .first()
    )
    if not staged:
        return jsonify({"error": "Staged transaction not found"}), 404
    if staged.status in {"confirmed", "dismissed"}:
        return jsonify({"error": f"Transaction is already {staged.status}"}), 409

    overrides = request.get_json(silent=True) or {}
    receipt_type = (
        overrides.get("receipt_type")
        or staged.suggested_receipt_type
        or "general_expense"
    )

    amount = float(staged.amount or 0)
    transaction_type = "refund" if amount < 0 else "purchase"
    store_name = overrides.get("store") or staged.merchant_name or staged.name or "Unknown Merchant"
    date_str = overrides.get("date")
    if not date_str and staged.transaction_date:
        date_str = staged.transaction_date.isoformat()
    if not date_str:
        return jsonify({"error": "Staged transaction has no date"}), 400

    payload = {
        "store": store_name,
        "date": date_str,
        "total": abs(amount),
        "subtotal": abs(amount),
        "tax": 0,
        "tip": 0,
        "transaction_type": transaction_type,
        "default_spending_domain": overrides.get("default_spending_domain")
            or staged.suggested_spending_domain
            or "general_expense",
        "default_budget_category": overrides.get("default_budget_category")
            or staged.suggested_budget_category
            or "other",
        "items": [],
        "confidence": 1.0,
    }
    # Household-bill specific scaffolding so downstream bill_meta creation works.
    if receipt_type in {"household_bill", "utility_bill"}:
        payload.update({
            "bill_provider_name": staged.merchant_name or staged.name,
            "bill_provider_type": "other",
            "bill_service_types": [],
            "bill_billing_cycle": "monthly",
            "bill_is_recurring": True,
            "bill_auto_pay": False,
        })

    source_label = f"plaid:{staged.plaid_account_id or 'unknown'}"
    try:
        receipt_record, purchase = _create_manual_receipt_entry(
            session,
            payload,
            receipt_type,
            user_id,
            source_label=source_label,
            ocr_engine="plaid",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Confirm Plaid transaction failed: %s", exc)
        return jsonify({"error": "Could not promote transaction to a receipt"}), 500

    staged.status = "confirmed"
    staged.confirmed_purchase_id = purchase.id
    staged.confirmed_at = datetime.utcnow()
    session.commit()

    return jsonify({
        "staged": _serialize_staged(staged),
        "purchase_id": purchase.id,
        "receipt_record_id": receipt_record.id,
    }), 200


@plaid_bp.route("/staged-transactions/<int:staged_id>/dismiss", methods=["POST"])
@require_write_access
def dismiss_staged_transaction(staged_id: int):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    session = g.db_session
    staged = (
        session.query(PlaidStagedTransaction)
        .filter_by(id=staged_id, user_id=user_id)
        .first()
    )
    if not staged:
        return jsonify({"error": "Staged transaction not found"}), 404
    if staged.status == "confirmed":
        return jsonify({"error": "Cannot dismiss a transaction already confirmed as a receipt"}), 409
    staged.status = "dismissed"
    staged.dismissed_at = datetime.utcnow()
    session.commit()
    return jsonify({"staged": _serialize_staged(staged)}), 200


@plaid_bp.route("/staged-transactions/<int:staged_id>/flag-duplicate", methods=["POST"])
@require_write_access
def flag_staged_duplicate(staged_id: int):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    session = g.db_session
    staged = (
        session.query(PlaidStagedTransaction)
        .filter_by(id=staged_id, user_id=user_id)
        .first()
    )
    if not staged:
        return jsonify({"error": "Staged transaction not found"}), 404
    if staged.status == "confirmed":
        return jsonify({"error": "Cannot flag a confirmed transaction"}), 409
    payload = request.get_json(silent=True) or {}
    dup_id = payload.get("duplicate_purchase_id")
    if dup_id is not None:
        try:
            staged.duplicate_purchase_id = int(dup_id)
        except (TypeError, ValueError):
            return jsonify({"error": "duplicate_purchase_id must be an integer"}), 400
    staged.status = "duplicate_flagged"
    session.commit()
    return jsonify({"staged": _serialize_staged(staged)}), 200


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
