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
import os
from datetime import datetime

from flask import Blueprint, request, jsonify, g
from sqlalchemy import or_, false as sa_false

from plaid.exceptions import ApiException
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import (
    PlaidAccount,
    PlaidItem,
    PlaidStagedTransaction,
    Purchase,
    Store,
    TelegramReceipt,
)
from src.backend.plaid_transaction_mapper import annotate_all_ready_staged, map_plaid_transaction
from src.backend.plaid_receipt_matcher import (
    DATE_WINDOW_DAYS,
    find_matching_purchase,
    merchants_match,
)
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


def _iso_utc(dt) -> str | None:
    """Serialize a naive-UTC datetime as an ISO string the browser can
    parse as UTC. Without the 'Z' suffix, `new Date(iso)` in the browser
    interprets the string as local time, shifting displayed timestamps
    by the user's offset.
    """
    if dt is None:
        return None
    iso = dt.isoformat()
    if iso.endswith("Z") or "+" in iso[10:] or (len(iso) > 19 and iso[-6:-3].startswith("-") and iso[-3] == ":"):
        return iso
    return iso + "Z"


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
        "nickname": item.nickname,
        "accounts": accounts,
        "products": (item.products or "").split(",") if item.products else [],
        "status": item.status,
        "last_sync_at": _iso_utc(item.last_sync_at),
        "last_sync_status": item.last_sync_status,
        "last_sync_error": item.last_sync_error,
        "shared_with_user_ids": _parse_shared_user_ids(getattr(item, "shared_with_user_ids", None)),
        "owner_user_id": item.user_id,
        "created_at": _iso_utc(item.created_at),
    }


def _current_user_id() -> int | None:
    user = getattr(g, "current_user", None)
    return int(user.id) if user else None


def _current_user_is_admin() -> bool:
    user = getattr(g, "current_user", None)
    return bool(user and getattr(user, "role", None) == "admin")


def _parse_shared_user_ids(raw) -> list[int]:
    """Decode plaid_items.shared_with_user_ids (JSON array of user ids)."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [int(x) for x in parsed if x is not None]
    except (TypeError, ValueError):
        pass
    return []


def _fetch_visible_staged(session, staged_id: int, user_id: int):
    """Load a PlaidStagedTransaction the current user is allowed to see
    (own or shared-via PlaidItem). Returns the row or None if the user
    can't touch it. Admins see every row.
    """
    visible_ids = _visible_plaid_item_ids(session, user_id)
    q = session.query(PlaidStagedTransaction).filter_by(id=staged_id)
    if visible_ids is not None:
        if not visible_ids:
            return None
        q = q.filter(PlaidStagedTransaction.plaid_item_id.in_(visible_ids))
    return q.first()


def _visible_plaid_item_ids(session, user_id: int) -> list[int] | None:
    """Return the list of plaid_items.id values visible to `user_id`.

    Returns `None` when the caller is an admin — callers should interpret
    that as "no restriction, see every item" and skip filtering. Otherwise
    returns a concrete list (possibly empty) of ids combining:
      * items the user personally linked (plaid_items.user_id == me), and
      * items shared with them via shared_with_user_ids.
    """
    if _current_user_is_admin():
        return None
    own_ids = {
        row[0]
        for row in session.query(PlaidItem.id)
        .filter(PlaidItem.user_id == user_id)
        .all()
    }
    shared_ids: set[int] = set()
    # SQLite doesn't have great JSON containment operators in older
    # versions, so scan the small plaid_items table in-Python. The
    # total row count is tiny (one per link), so this is cheap.
    for row_id, raw in session.query(
        PlaidItem.id, PlaidItem.shared_with_user_ids
    ).all():
        if user_id in _parse_shared_user_ids(raw):
            shared_ids.add(int(row_id))
    return list(own_ids | shared_ids)


def _upsert_plaid_accounts_from_metadata(session, item: PlaidItem, accounts_meta: list) -> None:
    """Ensure a plaid_accounts row exists for each sub-account in accounts_meta.

    Called from the Link exchange path so GET /plaid/accounts returns rows
    immediately after linking, before any balance refresh. Does not touch
    balance_cents / balance_updated_at — those stay NULL until the first
    explicit refresh-balances call.

    Idempotent on (plaid_item_id, plaid_account_id) via the migration's
    unique constraint.
    """
    if not accounts_meta:
        return
    for acct in accounts_meta:
        if not isinstance(acct, dict):
            continue
        # Plaid Link's onSuccess metadata.accounts[] uses "id"; the
        # Transactions / Balance API response uses "account_id". Accept
        # both so this helper works from either callsite.
        plaid_account_id = (
            acct.get("account_id")
            or acct.get("plaid_account_id")
            or acct.get("id")
            or ""
        ).strip()
        if not plaid_account_id:
            continue
        existing = (
            session.query(PlaidAccount)
            .filter_by(plaid_item_id=item.id, plaid_account_id=plaid_account_id)
            .first()
        )
        name = acct.get("name") or acct.get("official_name")
        mask = acct.get("mask")
        acct_type = acct.get("type")
        acct_subtype = acct.get("subtype")
        if existing:
            # Refresh metadata only; leave balance columns alone.
            existing.account_name = name or existing.account_name
            existing.account_mask = mask or existing.account_mask
            existing.account_type = acct_type or existing.account_type
            existing.account_subtype = acct_subtype or existing.account_subtype
        else:
            session.add(
                PlaidAccount(
                    plaid_item_id=item.id,
                    user_id=item.user_id,
                    plaid_account_id=plaid_account_id,
                    account_name=name,
                    account_mask=mask,
                    account_type=acct_type,
                    account_subtype=acct_subtype,
                )
            )


def _serialize_plaid_account(acct: PlaidAccount) -> dict:
    return {
        "id": acct.id,
        "plaid_item_id": acct.plaid_item_id,
        "plaid_account_id": acct.plaid_account_id,
        "name": acct.account_name,
        "mask": acct.account_mask,
        "type": acct.account_type,
        "subtype": acct.account_subtype,
        "balance_cents": acct.balance_cents,
        "credit_limit_cents": acct.credit_limit_cents,
        "available_credit_cents": acct.available_credit_cents,
        "balance_currency": acct.balance_iso_currency_code,
        "balance_updated_at": _iso_utc(acct.balance_updated_at),
    }


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
    session.flush()  # ensure item_record.id is populated before upserting accounts
    _upsert_plaid_accounts_from_metadata(session, item_record, accounts_meta)
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
    visible_ids = _visible_plaid_item_ids(session, user_id)
    q = session.query(PlaidItem).order_by(PlaidItem.created_at.desc())
    if visible_ids is not None:
        q = q.filter(PlaidItem.id.in_(visible_ids)) if visible_ids else q.filter(sa_false())
    items = q.all()

    # Lazy auto-sync: if an item the caller can see hasn't been synced
    # within the configured window, sync it once before returning. Costs
    # one Plaid /transactions/sync call per stale item per window, shared
    # across the household (any member's page view triggers it).
    _auto_sync_stale_items(session, items)

    return jsonify({
        "configured": is_plaid_configured(),
        "env": get_plaid_env_name(),
        "items": [_serialize_item(it) for it in items],
        "auto_sync_hours": _auto_sync_window_hours(),
    }), 200


def _auto_sync_window_hours() -> int:
    """Hours between allowed auto-syncs. Override via env; default 24."""
    raw = os.getenv("PLAID_AUTO_SYNC_HOURS", "24").strip()
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 24


def _auto_sync_stale_items(session, items: list) -> None:
    """For each item in `items`, trigger a sync if last_sync_at is older
    than the configured auto-sync window. Silent on failure (logs only)
    so a single broken bank doesn't blow up the page load for the user.
    """
    from datetime import datetime as _dt, timedelta as _td
    if not is_plaid_configured():
        return
    window = _td(hours=_auto_sync_window_hours())
    now = _dt.utcnow()
    for item in items:
        if item.status != "active":
            continue
        if item.last_sync_at and (now - item.last_sync_at) < window:
            continue
        try:
            sync_plaid_item_inner(session, item)
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "Auto-sync skipped for item %s: %s", item.plaid_item_id, exc
            )


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
            # Plaid's SDK requires cursor to be a string. For the first sync
            # (no prior cursor), the correct value per Plaid docs is "".
            sync_req = TransactionsSyncRequest(
                access_token=access_token,
                cursor=cursor,
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
        # Friendly message for the user. Order matters:
        #   1. Structured Plaid error_message (best — they wrote it for humans)
        #   2. Transient gateway errors (503/504/upstream/connection refused)
        #      → "Plaid temporarily unavailable" (actionable: just wait)
        #   3. Fallback: first 200 chars of the exception, stripped
        friendly: str | None = body.get("error_message") or None
        if not friendly:
            status = int(getattr(exc, "status", 0) or 0)
            raw = str(exc)
            transient_markers = (
                "Service Unavailable",
                "Gateway Timeout",
                "upstream connect error",
                "Connection refused",
                "connect failure",
                "EOF",
            )
            if status in (502, 503, 504) or any(m in raw for m in transient_markers):
                friendly = (
                    "Plaid is temporarily unavailable. Will retry on next "
                    "auto-sync — no action needed."
                )
            else:
                # Trim the usual HTTPHeaderDict(...) noise so the chip stays
                # readable. Keep the first line only, cap at 200 chars.
                first_line = raw.splitlines()[0] if raw else ""
                friendly = (first_line or raw)[:200]
        item.last_sync_error = friendly
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
    """Fetch new/modified/removed transactions for a Plaid item and stage them.

    Manual sync is admin-only — Plaid bills each /transactions/sync call,
    so we gate the big red button behind elevated access. Non-admin users
    still get fresh data via the lazy auto-sync path in list_items().
    """
    if not is_plaid_configured():
        return jsonify({"error": "Plaid is not configured on this server."}), 503
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    if not _current_user_is_admin():
        return jsonify({
            "error": "Manual sync is admin-only. Data refreshes automatically on a schedule.",
        }), 403

    session = g.db_session
    # Admins can sync any item (not just their own) so they can maintain
    # household banks linked under other users.
    item = session.query(PlaidItem).filter_by(id=item_id).first()
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
    visible_ids = _visible_plaid_item_ids(session, user_id)
    query = session.query(PlaidStagedTransaction).order_by(
        PlaidStagedTransaction.transaction_date.desc(),
        PlaidStagedTransaction.id.desc(),
    )
    if visible_ids is not None:
        query = (
            query.filter(PlaidStagedTransaction.plaid_item_id.in_(visible_ids))
            if visible_ids
            else query.filter(sa_false())
        )
    status_filter = (request.args.get("status") or "").strip().lower()
    if status_filter in {"ready_to_import", "duplicate_flagged", "skipped_pending", "confirmed", "dismissed"}:
        query = query.filter_by(status=status_filter)
    account_id = (request.args.get("account_id") or "").strip() or None
    if account_id:
        query = query.filter(PlaidStagedTransaction.plaid_account_id == account_id)
    rows = query.limit(500).all()

    # Item lookup covers both owned + shared items so serialized rows
    # get nickname / institution when available.
    items_q = session.query(PlaidItem)
    if visible_ids is not None:
        items_q = items_q.filter(PlaidItem.id.in_(visible_ids)) if visible_ids else items_q.filter(sa_false())
    items_by_id = {it.id: it for it in items_q.all()}
    serialized = [_serialize_staged(r, items_by_id.get(r.plaid_item_id)) for r in rows]
    counts = {
        "ready_to_import": 0,
        "duplicate_flagged": 0,
        "skipped_pending": 0,
        "confirmed": 0,
        "dismissed": 0,
    }
    counts_q = session.query(PlaidStagedTransaction.status, PlaidStagedTransaction.id)
    if visible_ids is not None:
        counts_q = (
            counts_q.filter(PlaidStagedTransaction.plaid_item_id.in_(visible_ids))
            if visible_ids
            else counts_q.filter(sa_false())
        )
    for row in counts_q.all():
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
    staged = _fetch_visible_staged(session, staged_id, user_id)
    if not staged:
        return jsonify({"error": "Staged transaction not found"}), 404
    if staged.status in {"confirmed", "dismissed"}:
        return jsonify({"error": f"Transaction is already {staged.status}"}), 409

    overrides = request.get_json(silent=True) or {}
    force = bool(overrides.get("force"))

    # --- Guard A: block transfers / CC payments / income ----------------
    # The mapper's skip flag fires on TRANSFER_IN/OUT, INCOME, Transfer,
    # Deposit. These are not real expenses and should never land in the
    # receipt list unless the user explicitly overrides.
    mapped_hint = map_plaid_transaction(staged)
    if mapped_hint.get("skip") and not force:
        return jsonify({
            "error": (
                "This transaction looks like a transfer, credit-card payment, "
                "deposit, or income — not a purchase. Pass force=true to "
                "import anyway."
            ),
            "reason": "skipped_category",
            "category": staged.plaid_category_primary,
        }), 422

    # --- Guard B: auto-match against an existing receipt ---------------
    # If the user already has a Purchase within ±3 days, same amount, and
    # a matching merchant (alias-aware), link to it instead of creating
    # a dupe. The staged row is still marked confirmed; no new
    # TelegramReceipt/Purchase is created.
    amount = float(staged.amount or 0)
    if not force:
        existing = find_matching_purchase(
            session,
            user_id,
            amount,
            staged.transaction_date,
            staged.merchant_name or staged.name,
        )
        if existing is not None:
            staged.status = "confirmed"
            staged.confirmed_purchase_id = existing.id
            staged.confirmed_at = datetime.utcnow()
            session.commit()
            return jsonify({
                "staged": _serialize_staged(staged),
                "purchase_id": existing.id,
                "receipt_record_id": None,
                "matched_existing": True,
            }), 200

    receipt_type = (
        overrides.get("receipt_type")
        or staged.suggested_receipt_type
        or "general_expense"
    )
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


@plaid_bp.route("/staged-transactions/bulk-confirm", methods=["POST"])
@require_write_access
def bulk_confirm_staged_transactions():
    """Confirm many staged transactions in one request.

    Body:
      {"ids": [1, 2, 3]}        # confirm this exact set
      {"all_ready": true}       # confirm every status='ready_to_import' row
                                 for the current user (up to `max` rows)
      {"max": 200}               # optional cap, default 500, hard max 2000
    Per-row failures are collected and reported back; successes are committed
    row-by-row so a single bad row can't roll back the rest.
    """
    from src.backend.handle_receipt_upload import _create_manual_receipt_entry

    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids") or []
    all_ready = bool(payload.get("all_ready"))
    try:
        cap = int(payload.get("max") or 500)
    except (TypeError, ValueError):
        cap = 500
    cap = max(1, min(cap, 2000))

    session = g.db_session
    # Match the visibility rule used by the list endpoint: admin sees
    # everything, non-admin sees own + shared. Previously this query
    # filtered strictly by user_id, which returned 0 rows for admins
    # trying to confirm transactions on banks linked under other users
    # (e.g. a joint BOA that the admin manages but whose PlaidItem is
    # owned by a spouse).
    visible_ids = _visible_plaid_item_ids(session, user_id)
    q = session.query(PlaidStagedTransaction).filter(
        PlaidStagedTransaction.status == "ready_to_import"
    )
    if visible_ids is not None:
        q = (
            q.filter(PlaidStagedTransaction.plaid_item_id.in_(visible_ids))
            if visible_ids
            else q.filter(sa_false())
        )
    if not all_ready:
        if not isinstance(ids, list) or not ids:
            return jsonify({"error": "Provide ids=[...] or all_ready=true"}), 400
        try:
            id_set = {int(x) for x in ids}
        except (TypeError, ValueError):
            return jsonify({"error": "ids must be a list of integers"}), 400
        q = q.filter(PlaidStagedTransaction.id.in_(id_set))
    staged_rows = q.order_by(PlaidStagedTransaction.id.asc()).limit(cap).all()

    force = bool(payload.get("force"))
    confirmed = 0
    matched = 0
    skipped = []
    failed = []
    for staged in staged_rows:
        try:
            amount = float(staged.amount or 0)
            date_str = staged.transaction_date.isoformat() if staged.transaction_date else None
            if not date_str:
                failed.append({"id": staged.id, "error": "missing date"})
                continue

            # --- Guard A: skip transfers/CC payments/income ---------
            mapped_hint = map_plaid_transaction(staged)
            if mapped_hint.get("skip") and not force:
                skipped.append({
                    "id": staged.id,
                    "reason": "skipped_category",
                    "category": staged.plaid_category_primary,
                })
                continue

            # --- Guard B: auto-match against an existing receipt ----
            if not force:
                existing = find_matching_purchase(
                    session,
                    user_id,
                    amount,
                    staged.transaction_date,
                    staged.merchant_name or staged.name,
                )
                if existing is not None:
                    staged.status = "confirmed"
                    staged.confirmed_purchase_id = existing.id
                    staged.confirmed_at = datetime.utcnow()
                    session.commit()
                    matched += 1
                    continue

            receipt_type = staged.suggested_receipt_type or "general_expense"
            store_name = staged.merchant_name or staged.name or "Unknown Merchant"
            body = {
                "store": store_name,
                "date": date_str,
                "total": abs(amount),
                "subtotal": abs(amount),
                "tax": 0,
                "tip": 0,
                "transaction_type": "refund" if amount < 0 else "purchase",
                "default_spending_domain": staged.suggested_spending_domain or "general_expense",
                "default_budget_category": staged.suggested_budget_category or "other",
                "items": [],
                "confidence": 1.0,
            }
            if receipt_type in {"household_bill", "utility_bill"}:
                body.update({
                    "bill_provider_name": staged.merchant_name or staged.name,
                    "bill_provider_type": "other",
                    "bill_service_types": [],
                    "bill_billing_cycle": "monthly",
                    "bill_is_recurring": True,
                    "bill_auto_pay": False,
                })
            source_label = f"plaid:{staged.plaid_account_id or 'unknown'}"
            _, purchase = _create_manual_receipt_entry(
                session,
                body,
                receipt_type,
                user_id,
                source_label=source_label,
                ocr_engine="plaid",
            )
            staged.status = "confirmed"
            staged.confirmed_purchase_id = purchase.id
            staged.confirmed_at = datetime.utcnow()
            session.commit()
            confirmed += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("bulk confirm failed for staged=%s: %s", staged.id, exc)
            session.rollback()
            failed.append({"id": staged.id, "error": str(exc)[:200]})

    return jsonify({
        "confirmed": confirmed,
        "matched_existing": matched,
        "skipped": skipped,
        "attempted": len(staged_rows),
        "failed": failed,
    }), 200


@plaid_bp.route("/staged-transactions/<int:staged_id>/dismiss", methods=["POST"])
@require_write_access
def dismiss_staged_transaction(staged_id: int):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    session = g.db_session
    staged = _fetch_visible_staged(session, staged_id, user_id)
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
    staged = _fetch_visible_staged(session, staged_id, user_id)
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


# ---------------------------------------------------------------------------
# Phase 2 — manual link + attach-upload for staged transactions
# ---------------------------------------------------------------------------
# If Guard B's fuzzy matcher misses, the user has two escape hatches:
#   1. Link the staged row to an existing receipt they already uploaded.
#   2. Attach a new photo/PDF of the receipt — we run OCR and link the
#      resulting Purchase.
# Both write staged.confirmed_purchase_id + status='confirmed' without
# creating a duplicate Purchase from Plaid data.
# ---------------------------------------------------------------------------

def _staged_for_current_user(staged_id: int) -> tuple[PlaidStagedTransaction | None, object]:
    """Return (staged_row, error_response) for the current user's staged tx."""
    user_id = _current_user_id()
    if user_id is None:
        return None, (jsonify({"error": "Authenticated user required"}), 401)
    session = g.db_session
    staged = _fetch_visible_staged(session, staged_id, user_id)
    if not staged:
        return None, (jsonify({"error": "Staged transaction not found"}), 404)
    return staged, None


@plaid_bp.route(
    "/staged-transactions/<int:staged_id>/match-candidates",
    methods=["GET"],
)
@require_auth
def staged_match_candidates(staged_id: int):
    """Return up to 20 Purchase rows that could plausibly be this staged tx.

    Ranking is deliberately simple — merchant-match first (alias or token),
    then amount closeness, then date closeness. The UI lets the user pick.
    We include a widened date window (±14 days, not ±3) and a wider amount
    tolerance ($5 or 20%) because this is a *human picker*, not an
    auto-match — we'd rather offer too many than too few.
    """
    from datetime import timedelta

    staged, err = _staged_for_current_user(staged_id)
    if err:
        return err
    session = g.db_session
    user_id = staged.user_id

    amount = abs(float(staged.amount or 0))
    date = staged.transaction_date
    if date is None:
        return jsonify({"candidates": []}), 200

    lo = date - timedelta(days=14)
    hi = date + timedelta(days=15)
    dollar_tol = max(5.0, amount * 0.20)

    rows = (
        session.query(Purchase, Store)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .filter(Purchase.user_id == user_id)
        .filter(Purchase.date >= lo)
        .filter(Purchase.date < hi)
        .order_by(Purchase.date.desc(), Purchase.id.desc())
        .limit(200)  # prune heavy users before we score in Python
        .all()
    )

    staged_merchant = staged.merchant_name or staged.name

    scored = []
    for purchase, store in rows:
        p_amount = abs(float(purchase.total_amount or 0))
        amount_delta = abs(p_amount - amount)
        if amount_delta > dollar_tol:
            continue
        date_delta_days = abs((purchase.date.date() - date).days) if purchase.date else 99
        store_name = store.name if store is not None else None
        merchant_hit = merchants_match(staged_merchant, store_name)

        # Rank: merchant-match first, then amount closeness, then date.
        # Lower score = better.
        score = (
            0 if merchant_hit else 1,
            round(amount_delta, 2),
            date_delta_days,
        )
        scored.append((score, purchase, store))

    scored.sort(key=lambda t: t[0])
    top = scored[:20]

    return jsonify({
        "candidates": [
            {
                "purchase_id": purchase.id,
                "store": (store.name if store is not None else None),
                "total_amount": float(purchase.total_amount or 0),
                "date": purchase.date.date().isoformat() if purchase.date else None,
                "merchant_match": bool(score[0] == 0),
                "amount_delta": score[1],
                "date_delta_days": score[2],
            }
            for score, purchase, store in top
        ],
        "staged": {
            "amount": amount,
            "date": date.isoformat() if hasattr(date, "isoformat") else None,
            "merchant": staged_merchant,
        },
    }), 200


@plaid_bp.route(
    "/staged-transactions/<int:staged_id>/link-receipt",
    methods=["POST"],
)
@require_write_access
def link_staged_to_receipt(staged_id: int):
    """Link a staged transaction to an existing Purchase the user already owns.

    Body: {"purchase_id": int}  or  {"receipt_id": int}
    (receipt_id is a TelegramReceipt.id — we resolve it to its purchase.)
    """
    staged, err = _staged_for_current_user(staged_id)
    if err:
        return err
    if staged.status in {"confirmed", "dismissed"}:
        return jsonify({"error": f"Transaction is already {staged.status}"}), 409

    payload = request.get_json(silent=True) or {}
    purchase_id = payload.get("purchase_id")
    receipt_id = payload.get("receipt_id")
    if purchase_id is None and receipt_id is None:
        return jsonify({"error": "Provide purchase_id or receipt_id"}), 400

    session = g.db_session
    purchase = None
    if purchase_id is not None:
        try:
            purchase_id = int(purchase_id)
        except (TypeError, ValueError):
            return jsonify({"error": "purchase_id must be an integer"}), 400
        purchase = (
            session.query(Purchase)
            .filter_by(id=purchase_id, user_id=staged.user_id)
            .first()
        )
    elif receipt_id is not None:
        try:
            receipt_id = int(receipt_id)
        except (TypeError, ValueError):
            return jsonify({"error": "receipt_id must be an integer"}), 400
        receipt = (
            session.query(TelegramReceipt)
            .filter_by(id=receipt_id, user_id=staged.user_id)
            .first()
        )
        if receipt and receipt.purchase_id:
            purchase = (
                session.query(Purchase)
                .filter_by(id=receipt.purchase_id, user_id=staged.user_id)
                .first()
            )

    if purchase is None:
        return jsonify({"error": "Receipt not found or not owned by you"}), 404

    staged.status = "confirmed"
    staged.confirmed_purchase_id = purchase.id
    staged.confirmed_at = datetime.utcnow()
    session.commit()

    return jsonify({
        "staged": _serialize_staged(staged),
        "purchase_id": purchase.id,
        "matched_existing": True,
    }), 200


@plaid_bp.route(
    "/staged-transactions/<int:staged_id>/attach-upload",
    methods=["POST"],
)
@require_write_access
def attach_upload_to_staged(staged_id: int):
    """Upload a receipt image and link the resulting Purchase to this staged tx.

    Accepts the same multipart 'image' field as /receipts/upload. We route
    through the same OCR pipeline; on success we set staged.confirmed_purchase_id
    to the new Purchase.id and mark the staged row confirmed.
    """
    from src.backend.extract_receipt_data import process_receipt
    from src.backend.handle_receipt_upload import (
        ALLOWED_EXTENSIONS,
        _compute_file_hash,
        _get_receipts_root,
        _save_failed_receipt,
    )
    import os
    from datetime import datetime as _dt
    from uuid import uuid4

    staged, err = _staged_for_current_user(staged_id)
    if err:
        return err
    if staged.status in {"confirmed", "dismissed"}:
        return jsonify({"error": f"Transaction is already {staged.status}"}), 409

    if "image" not in request.files:
        return jsonify({"error": "No receipt file provided. Use 'image' field."}), 400
    image_file = request.files["image"]
    if not image_file.filename:
        return jsonify({"error": "Empty filename"}), 400
    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type: {ext}",
            "allowed": list(ALLOWED_EXTENSIONS),
        }), 400

    timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{uuid4().hex[:8]}{ext}"
    year_month = _dt.now().strftime("%Y/%m")
    save_dir = os.path.join(_get_receipts_root(), year_month)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    try:
        image_file.save(save_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("attach-upload save failed: %s", exc)
        return jsonify({"error": "Failed to save receipt file"}), 500

    session = g.db_session
    file_hash = _compute_file_hash(save_path)
    receipt_type_hint = staged.suggested_receipt_type or None

    try:
        result = process_receipt(
            image_path=save_path,
            source=f"plaid-attach:{staged_id}",
            user_id=staged.user_id,
            receipt_type_hint=receipt_type_hint,
            file_hash=file_hash,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("attach-upload OCR failed: %s", exc)
        failed_id = _save_failed_receipt(
            image_path=save_path,
            error_message=str(exc)[:500],
            receipt_type_hint=receipt_type_hint,
            user_id=staged.user_id,
            file_hash=file_hash,
            session=session,
        )
        return jsonify({
            "status": "failed",
            "error": "OCR processing failed",
            "receipt_id": failed_id,
            "can_retry": True,
        }), 500

    purchase_id = result.get("purchase_id")
    if not purchase_id:
        # OCR completed but didn't produce a Purchase (e.g. 'review' status
        # without a finalized row, or 'failed'). Leave staged alone so the
        # user can retry — the receipt row will exist for manual review.
        return jsonify({
            "status": result.get("status", "unknown"),
            "receipt_id": result.get("receipt_id"),
            "error": result.get("error"),
            "message": (
                "Receipt saved but not yet linked — review it in Receipts, "
                "then come back and use Link existing."
            ),
        }), 202

    staged.status = "confirmed"
    staged.confirmed_purchase_id = purchase_id
    staged.confirmed_at = datetime.utcnow()
    session.commit()

    return jsonify({
        "staged": _serialize_staged(staged),
        "purchase_id": purchase_id,
        "receipt_id": result.get("receipt_id"),
        "status": result.get("status"),
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

    # Clean up dependent plaid_accounts rows before deleting the parent item
    # (no cascade configured on the FK).
    session.query(PlaidAccount).filter_by(plaid_item_id=item.id).delete(
        synchronize_session=False
    )
    session.delete(item)
    session.commit()
    return jsonify({"deleted_id": item_id}), 200


# ---------------------------------------------------------------------------
# Accounts Dashboard routes (Phase 1b — read-only views + rename + balance
# refresh). All strictly scoped by current_user.id. No admin bypass.
# ---------------------------------------------------------------------------

# Server-side throttle: one balance refresh per user every N seconds. We check
# max(plaid_accounts.balance_updated_at) for the user; if it's within the
# window we 429. This protects the Plaid billing quota and matches the spec.
BALANCE_REFRESH_TTL_SECONDS = 5 * 60


@plaid_bp.route("/items/<int:item_id>", methods=["PATCH"])
@require_write_access
def patch_item(item_id: int):
    """Edit a linked Plaid item: nickname and/or shared_with_user_ids.

    Nickname: any authenticated user who owns or is shared on the item
    can rename it.

    shared_with_user_ids: admin-only — non-admins can't grant/revoke
    access because it's a permission change on other household members.
    """
    from src.backend.initialize_database_schema import User

    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    payload = request.get_json(silent=True) or {}
    allowed_keys = {"nickname", "shared_with_user_ids"}
    unknown = set(payload.keys()) - allowed_keys
    if unknown:
        return jsonify({"error": f"Unknown fields: {sorted(unknown)}"}), 400
    if not payload:
        return jsonify({"error": "No fields to update"}), 400

    session = g.db_session
    item = session.query(PlaidItem).filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Plaid item not found"}), 404
    # Authorization: admin always; otherwise linker only (renaming
    # someone else's shared bank would be surprising).
    if not _current_user_is_admin() and item.user_id != user_id:
        return jsonify({"error": "Not authorized to edit this item"}), 403

    if "nickname" in payload:
        raw = payload.get("nickname")
        if raw is None:
            item.nickname = None
        else:
            nick = str(raw).strip() or None
            if nick is not None and len(nick) > 64:
                return jsonify({"error": "Nickname must be 64 characters or fewer"}), 400
            item.nickname = nick

    if "shared_with_user_ids" in payload:
        if not _current_user_is_admin():
            return jsonify({"error": "Admin access required to change sharing"}), 403
        raw_list = payload.get("shared_with_user_ids")
        if raw_list is None:
            item.shared_with_user_ids = None
        else:
            if not isinstance(raw_list, list):
                return jsonify({"error": "shared_with_user_ids must be a list"}), 400
            cleaned: list[int] = []
            seen: set[int] = set()
            for v in raw_list:
                try:
                    uid = int(v)
                except (TypeError, ValueError):
                    return jsonify({"error": "shared_with_user_ids must contain integers"}), 400
                if uid in seen or uid == item.user_id:
                    # Owner is always implicit; don't duplicate.
                    continue
                seen.add(uid)
                cleaned.append(uid)
            if cleaned:
                found = {
                    r[0]
                    for r in session.query(User.id).filter(User.id.in_(cleaned)).all()
                }
                missing = [i for i in cleaned if i not in found]
                if missing:
                    return jsonify({"error": f"Unknown user ids: {missing}"}), 400
            item.shared_with_user_ids = json.dumps(cleaned) if cleaned else None

    session.commit()
    return jsonify({
        "id": item.id,
        "nickname": item.nickname,
        "shared_with_user_ids": _parse_shared_user_ids(item.shared_with_user_ids),
        "owner_user_id": item.user_id,
    }), 200


@plaid_bp.route("/accounts", methods=["GET"])
@require_auth
def list_accounts():
    """List the current user's Plaid sub-accounts with cached balances.

    Does NOT call Plaid. Use POST /plaid/accounts/refresh-balances to
    refresh balance_cents / balance_updated_at.
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    session = g.db_session
    visible_ids = _visible_plaid_item_ids(session, user_id)
    q = session.query(PlaidAccount).order_by(
        PlaidAccount.plaid_item_id.asc(), PlaidAccount.id.asc()
    )
    if visible_ids is not None:
        q = q.filter(PlaidAccount.plaid_item_id.in_(visible_ids)) if visible_ids else q.filter(sa_false())
    accounts = q.all()
    return jsonify({
        "accounts": [_serialize_plaid_account(a) for a in accounts],
    }), 200


@plaid_bp.route("/accounts/refresh-balances", methods=["POST"])
@require_write_access
def refresh_balances():
    """Refresh balances for all of the current user's linked items.

    Throttled: 429 if any of the user's accounts were refreshed in the last
    5 minutes. On success, per-account balance_cents and balance_updated_at
    are updated; the response mirrors GET /plaid/accounts shape.
    """
    if not is_plaid_configured():
        return jsonify({"error": "Plaid is not configured on this server."}), 503
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    session = g.db_session
    now = datetime.utcnow()

    # Throttle check — look at the most recent balance update across this
    # user's accounts.
    latest = (
        session.query(PlaidAccount.balance_updated_at)
        .filter(PlaidAccount.user_id == user_id)
        .filter(PlaidAccount.balance_updated_at.isnot(None))
        .order_by(PlaidAccount.balance_updated_at.desc())
        .first()
    )
    if latest and latest[0] is not None:
        elapsed = (now - latest[0]).total_seconds()
        if elapsed < BALANCE_REFRESH_TTL_SECONDS:
            retry_after = int(BALANCE_REFRESH_TTL_SECONDS - elapsed) + 1
            return (
                jsonify({
                    "error": "Balances were refreshed recently.",
                    "retry_after_seconds": retry_after,
                }),
                429,
                {"Retry-After": str(retry_after)},
            )

    items = session.query(PlaidItem).filter_by(user_id=user_id, status="active").all()
    if not items:
        return jsonify({"accounts": [], "refreshed_items": 0}), 200

    client = get_client()
    refreshed_items = 0
    for item in items:
        try:
            access_token = decrypt_api_key(item.access_token_encrypted)
            bal_req = AccountsBalanceGetRequest(access_token=access_token)
            bal_res = client.accounts_balance_get(bal_req)
        except ApiException as exc:
            logger.warning(
                "Balance refresh failed for item %s: %s", item.plaid_item_id, exc
            )
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Balance refresh unexpected error item %s: %s", item.plaid_item_id, exc
            )
            continue

        for plaid_acct in bal_res.get("accounts") or []:
            plaid_acct_id = str(plaid_acct.get("account_id") or "").strip()
            if not plaid_acct_id:
                continue
            balances = plaid_acct.get("balances") or {}
            current = balances.get("current")
            limit = balances.get("limit")
            available = balances.get("available")
            currency = balances.get("iso_currency_code") or "USD"

            def _to_cents(v):
                if v is None:
                    return None
                try:
                    return int(round(float(v) * 100))
                except (TypeError, ValueError):
                    return None

            balance_cents = _to_cents(current)
            credit_limit_cents = _to_cents(limit)
            available_credit_cents = _to_cents(available)

            row = (
                session.query(PlaidAccount)
                .filter_by(plaid_item_id=item.id, plaid_account_id=plaid_acct_id)
                .first()
            )
            if row is None:
                # Plaid returned an account we don't have a row for yet —
                # lazily create it (e.g., account added at the institution
                # after the original link).
                row = PlaidAccount(
                    plaid_item_id=item.id,
                    user_id=user_id,
                    plaid_account_id=plaid_acct_id,
                    account_name=plaid_acct.get("name") or plaid_acct.get("official_name"),
                    account_mask=plaid_acct.get("mask"),
                    account_type=str(plaid_acct.get("type")) if plaid_acct.get("type") else None,
                    account_subtype=(
                        str(plaid_acct.get("subtype")) if plaid_acct.get("subtype") else None
                    ),
                )
                session.add(row)
            row.balance_cents = balance_cents
            row.credit_limit_cents = credit_limit_cents
            row.available_credit_cents = available_credit_cents
            row.balance_iso_currency_code = currency
            row.balance_updated_at = now
        refreshed_items += 1

    session.commit()

    accounts = (
        session.query(PlaidAccount)
        .filter_by(user_id=user_id)
        .order_by(PlaidAccount.plaid_item_id.asc(), PlaidAccount.id.asc())
        .all()
    )
    return jsonify({
        "accounts": [_serialize_plaid_account(a) for a in accounts],
        "refreshed_items": refreshed_items,
    }), 200


@plaid_bp.route("/cards-overview", methods=["GET"])
@require_auth
def cards_overview():
    """Card-usage view: balance, credit limit, utilization %, MTD spend per card.

    Read-only. No throttle. Sources data exclusively from the
    `plaid_accounts` cache and `plaid_staged_transactions`. Use
    `POST /plaid/accounts/refresh-balances` to refresh balances first.

    Includes accounts where `account_type` is `credit` or `loan`. Depository
    and investment accounts are excluded.
    """
    from datetime import timezone
    from sqlalchemy import case, func

    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    session = g.db_session
    visible_ids = _visible_plaid_item_ids(session, user_id)

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    accounts_q = session.query(PlaidAccount).filter(
        PlaidAccount.account_type.in_(("credit", "loan")),
    )
    if visible_ids is not None:
        accounts_q = (
            accounts_q.filter(PlaidAccount.plaid_item_id.in_(visible_ids))
            if visible_ids
            else accounts_q.filter(sa_false())
        )
    accounts = accounts_q.all()

    # MTD spend per plaid_account_id
    spend_q = (
        session.query(
            PlaidStagedTransaction.plaid_account_id,
            func.sum(PlaidStagedTransaction.amount).label("net_amount"),
            func.sum(case((PlaidStagedTransaction.amount > 0, 1), else_=0)).label("debit_count"),
        )
        .filter(PlaidStagedTransaction.transaction_date >= month_start.date())
        .filter(PlaidStagedTransaction.status != "dismissed")
    )
    if visible_ids is not None:
        spend_q = (
            spend_q.filter(PlaidStagedTransaction.plaid_item_id.in_(visible_ids))
            if visible_ids
            else spend_q.filter(sa_false())
        )
    spend_rows = spend_q.group_by(PlaidStagedTransaction.plaid_account_id).all()
    spend_map = {
        r.plaid_account_id: {
            "spend_mtd_cents": int(round(float(r.net_amount or 0) * 100)),
            "txn_count_mtd": int(r.debit_count or 0),
        }
        for r in spend_rows
    }

    credit_rows = []
    loan_rows = []
    for a in accounts:
        base = _serialize_plaid_account(a)
        bucket = spend_map.get(a.plaid_account_id, {"spend_mtd_cents": 0, "txn_count_mtd": 0})
        base["spend_mtd_cents"] = bucket["spend_mtd_cents"]
        base["txn_count_mtd"] = bucket["txn_count_mtd"]

        limit = a.credit_limit_cents
        balance = a.balance_cents
        if a.account_type == "credit" and limit and limit > 0 and balance is not None:
            base["utilization_pct"] = round(balance / limit * 100, 2)
        else:
            base["utilization_pct"] = None

        if a.account_type == "credit":
            credit_rows.append(base)
        else:
            loan_rows.append(base)

    credit_rows.sort(key=lambda r: r["utilization_pct"] if r["utilization_pct"] is not None else -1, reverse=True)
    loan_rows.sort(key=lambda r: r["balance_cents"] or 0, reverse=True)

    groups = []
    if credit_rows:
        groups.append({"type": "credit_card", "label": "Credit Cards", "accounts": credit_rows})
    if loan_rows:
        groups.append({"type": "loan", "label": "Loans", "accounts": loan_rows})

    # Totals — USD only, only accounts with non-null limit contribute to limit/util
    usd_credit = [r for r in credit_rows if (r["balance_currency"] or "USD") == "USD"]
    usd_loan = [r for r in loan_rows if (r["balance_currency"] or "USD") == "USD"]

    credit_balance_cents = sum((r["balance_cents"] or 0) for r in usd_credit)
    credit_limit_cents = sum((r["credit_limit_cents"] or 0) for r in usd_credit if r["credit_limit_cents"])
    credit_spend_mtd_cents = sum((r["spend_mtd_cents"] or 0) for r in usd_credit)
    loan_balance_cents = sum((r["balance_cents"] or 0) for r in usd_loan)

    overall_util = None
    if credit_limit_cents > 0:
        overall_util = round(credit_balance_cents / credit_limit_cents * 100, 2)

    return jsonify({
        "as_of": now.replace(tzinfo=None).isoformat() + "Z",
        "month_start": month_start.date().isoformat(),
        "groups": groups,
        "totals": {
            "credit_balance_cents": credit_balance_cents,
            "credit_limit_cents": credit_limit_cents,
            "overall_utilization_pct": overall_util,
            "credit_spend_mtd_cents": credit_spend_mtd_cents,
            "loan_balance_cents": loan_balance_cents,
        },
    }), 200


@plaid_bp.route("/transaction-breakdown", methods=["GET"])
@require_auth
def transaction_breakdown():
    """Per-account transaction counts grouped by category class.

    Source: plaid_staged_transactions (every Plaid-imported row, covers
    both confirmed and pending-review states so the breakdown matches
    what users actually see in the Accounts page).

    Query params:
      start, end  — ISO dates (inclusive) bounding transaction_date.
                    Omit for "all time".

    Response:
      {
        "accounts": [
          {
            "plaid_account_id": "...",
            "name": "BOA Balance Rewards",
            "mask": "4605",
            "counts": {"purchase": 42, "autopay": 8, "interest": 3, "refund": 1},
            "total": 54
          }, ...
        ]
      }
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    start_raw = (request.args.get("start") or "").strip() or None
    end_raw = (request.args.get("end") or "").strip() or None

    session = g.db_session
    visible_ids = _visible_plaid_item_ids(session, user_id)
    q = session.query(PlaidStagedTransaction)
    if visible_ids is not None:
        q = (
            q.filter(PlaidStagedTransaction.plaid_item_id.in_(visible_ids))
            if visible_ids
            else q.filter(sa_false())
        )
    if start_raw:
        q = q.filter(PlaidStagedTransaction.transaction_date >= start_raw)
    if end_raw:
        q = q.filter(PlaidStagedTransaction.transaction_date <= end_raw)

    AUTOPAY_CATS = {"LOAN_PAYMENTS", "TRANSFER_OUT", "RENT_AND_UTILITIES"}
    INTEREST_CATS = {"BANK_FEES"}

    # Pull accounts + items scoped by visibility so shared users see
    # nickname / name metadata for the banks they have access to.
    acct_q = session.query(PlaidAccount)
    item_q = session.query(PlaidItem)
    if visible_ids is not None:
        if visible_ids:
            acct_q = acct_q.filter(PlaidAccount.plaid_item_id.in_(visible_ids))
            item_q = item_q.filter(PlaidItem.id.in_(visible_ids))
        else:
            acct_q = acct_q.filter(sa_false())
            item_q = item_q.filter(sa_false())
    acct_rows = acct_q.all()
    item_nicknames = {
        it.id: it.nickname
        for it in item_q.all()
    }
    def _clean_name(name: str, mask: str) -> str:
        """Strip the trailing mask if Plaid's account_name already ends
        with those digits (e.g. "BOA Beginning Balance 4517" — we'd
        append ····4517 and show the mask twice)."""
        n = (name or "Account").strip()
        m = (mask or "").strip()
        if m and n.endswith(m):
            # Drop the trailing mask + any preceding whitespace/dash/dot.
            return n[: -len(m)].rstrip(" -·.").strip() or "Account"
        return n

    acct_meta = {
        a.plaid_account_id: (
            item_nicknames.get(a.plaid_item_id),
            _clean_name(a.account_name, a.account_mask),
            a.account_mask or "",
        )
        for a in acct_rows
    }
    by_account: dict[str, dict[str, int]] = {}
    for tx in q.all():
        if not tx.plaid_account_id:
            continue
        cat = (tx.plaid_category_primary or "").upper()
        if (tx.amount or 0) < 0:
            bucket = "refund"
        elif cat in AUTOPAY_CATS:
            bucket = "autopay"
        elif cat in INTEREST_CATS:
            bucket = "interest"
        else:
            bucket = "purchase"
        slot = by_account.setdefault(
            tx.plaid_account_id,
            {"purchase": 0, "autopay": 0, "interest": 0, "refund": 0},
        )
        slot[bucket] += 1

    accounts = []
    for plaid_account_id, counts in by_account.items():
        nickname, name, mask = acct_meta.get(
            plaid_account_id, (None, "Account", "")
        )
        total = sum(counts.values())
        accounts.append({
            "plaid_account_id": plaid_account_id,
            "nickname": nickname,
            "name": name,
            "mask": mask,
            "counts": counts,
            "total": total,
        })
    accounts.sort(key=lambda a: a["total"], reverse=True)
    return jsonify({"accounts": accounts}), 200


@plaid_bp.route("/transactions", methods=["GET"])
@require_auth
def list_plaid_transactions():
    """Paginated list of confirmed Plaid-sourced purchases for the current user.

    Source of truth is the `purchases` table, filtered to rows with
    plaid_transaction_id IS NOT NULL. Never reads plaid_staged_transactions
    (that is the Review queue; this endpoint is for the Accounts dashboard
    history view).

    Query params:
      account_id  — optional Plaid account_id (string); matches via the
                    linked PlaidStagedTransaction sibling row.
      start, end  — ISO-8601 dates (inclusive) bounding Purchase.date.
      category    — matches Purchase.default_budget_category.
      merchant    — case-insensitive substring match on the sibling
                    PlaidStagedTransaction.merchant_name.
      limit, offset — pagination (limit default 100, max 500).
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401

    account_id = (request.args.get("account_id") or "").strip() or None
    start_raw = (request.args.get("start") or "").strip() or None
    end_raw = (request.args.get("end") or "").strip() or None
    category = (request.args.get("category") or "").strip() or None
    merchant = (request.args.get("merchant") or "").strip() or None
    kind = (request.args.get("kind") or "").strip().lower() or None
    try:
        limit = int(request.args.get("limit") or 100)
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = int(request.args.get("offset") or 0)
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    session = g.db_session
    visible_ids = _visible_plaid_item_ids(session, user_id)
    q = (
        session.query(Purchase, PlaidStagedTransaction)
        .outerjoin(
            PlaidStagedTransaction,
            PlaidStagedTransaction.confirmed_purchase_id == Purchase.id,
        )
        .filter(PlaidStagedTransaction.id.isnot(None))
    )
    # Visibility: admin sees every Plaid purchase; others see only those
    # whose PlaidItem is owned-by or shared-with them.
    if visible_ids is not None:
        q = (
            q.filter(PlaidStagedTransaction.plaid_item_id.in_(visible_ids))
            if visible_ids
            else q.filter(sa_false())
        )
    if start_raw:
        q = q.filter(Purchase.date >= start_raw)
    if end_raw:
        q = q.filter(Purchase.date <= end_raw + " 23:59:59")
    if category:
        q = q.filter(Purchase.default_budget_category == category)
    if account_id:
        q = q.filter(PlaidStagedTransaction.plaid_account_id == account_id)
    if merchant:
        q = q.filter(PlaidStagedTransaction.merchant_name.ilike(f"%{merchant}%"))
    # Tab split: spending vs transfers & bills. Applied server-side so
    # the count / pagination reflect the visible bucket honestly (the
    # client-side-only filter was confusing when a full page fell into
    # the other bucket).
    TRANSFER_CATS = {
        "LOAN_PAYMENTS", "TRANSFER_IN", "TRANSFER_OUT",
        "BANK_FEES", "RENT_AND_UTILITIES", "GOVERNMENT_AND_NON_PROFIT",
    }
    if kind == "transfers":
        q = q.filter(PlaidStagedTransaction.plaid_category_primary.in_(TRANSFER_CATS))
    elif kind == "spending":
        q = q.filter(
            or_(
                PlaidStagedTransaction.plaid_category_primary.is_(None),
                ~PlaidStagedTransaction.plaid_category_primary.in_(TRANSFER_CATS),
            )
        )

    total = q.count()
    rows = (
        q.order_by(Purchase.date.desc(), Purchase.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    transactions = []
    for purchase, staged in rows:
        transactions.append({
            "purchase_id": purchase.id,
            "date": purchase.date.isoformat() if purchase.date else None,
            "amount": purchase.total_amount,
            "merchant": (staged.merchant_name or staged.name) if staged else None,
            "plaid_account_id": staged.plaid_account_id if staged else None,
            "plaid_category_primary": staged.plaid_category_primary if staged else None,
            "plaid_category_detailed": staged.plaid_category_detailed if staged else None,
            "budget_category": purchase.default_budget_category,
            "spending_domain": purchase.default_spending_domain,
            "transaction_type": purchase.transaction_type,
        })
    return jsonify({
        "transactions": transactions,
        "total": total,
        "limit": limit,
        "offset": offset,
    }), 200


@plaid_bp.route("/spending-trends", methods=["GET"])
@require_auth
def spending_trends():
    """Monthly spending totals by category for the current user.

    Returns the last N months (default 12, max 24) of Plaid-sourced
    confirmed purchases, aggregated by (month, default_budget_category).

    Receipt-sourced purchases and Plaid-sourced purchases are NOT merged
    here — Panel 3's UI decides whether to stack or split them (see
    spec Section 4.10 on taxonomy mismatch).
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    try:
        months = int(request.args.get("months") or 12)
    except (TypeError, ValueError):
        months = 12
    months = max(1, min(months, 24))

    session = g.db_session
    # Visibility: admin sees everyone's Plaid purchases; non-admin sees
    # those tied to items they own or were shared. Build the id list as
    # a comma-joined literal of validated ints — safe (we just pulled
    # them from our own DB and cast to int) and avoids parameter
    # expansion issues for IN (...) in raw text SQL.
    visible_ids = _visible_plaid_item_ids(session, user_id)
    import sqlalchemy as _sa
    window = f"-{months} months"
    if visible_ids is None:
        sql = _sa.text(
            """
            SELECT strftime('%Y-%m', p.date) AS month,
                   p.default_budget_category AS category,
                   SUM(p.total_amount) AS total,
                   COUNT(*) AS n
              FROM purchases p
              JOIN plaid_staged_transactions s ON s.confirmed_purchase_id = p.id
             WHERE p.date >= date('now', :window)
             GROUP BY month, category
             ORDER BY month ASC, category ASC
            """
        )
        rows = session.execute(sql, {"window": window}).fetchall()
    elif not visible_ids:
        rows = []
    else:
        ids_literal = ",".join(str(int(i)) for i in visible_ids)
        sql = _sa.text(
            f"""
            SELECT strftime('%Y-%m', p.date) AS month,
                   p.default_budget_category AS category,
                   SUM(p.total_amount) AS total,
                   COUNT(*) AS n
              FROM purchases p
              JOIN plaid_staged_transactions s ON s.confirmed_purchase_id = p.id
             WHERE s.plaid_item_id IN ({ids_literal})
               AND p.date >= date('now', :window)
             GROUP BY month, category
             ORDER BY month ASC, category ASC
            """
        )
        rows = session.execute(sql, {"window": window}).fetchall()
    series = [
        {
            "month": r[0],
            "category": r[1] or "uncategorized",
            "total": float(r[2] or 0.0),
            "count": int(r[3] or 0),
        }
        for r in rows
    ]
    return jsonify({
        "months": months,
        "series": series,
    }), 200
