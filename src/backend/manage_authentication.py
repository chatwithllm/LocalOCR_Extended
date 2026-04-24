"""
Session-based browser authentication endpoints.

Phase 1 adds local login with secure password hashing and Flask sessions,
while keeping bearer-token auth available for integrations and automation.
"""

import os
import hashlib
import ipaddress
import logging
import secrets
from io import BytesIO
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from urllib.parse import urlparse

import qrcode
from flask import Blueprint, jsonify, request, g, session, redirect, send_file, render_template_string, has_request_context
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, func

from src.backend.contribution_scores import sum_bonus_points, sum_floating_points
from src.backend.initialize_database_schema import (
    AccessLink,
    DevicePairingSession,
    Product,
    Purchase,
    TrustedDevice,
    User,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


DEFAULT_AVATARS = ["🦊", "🐼", "🦉", "🐸", "🐯", "🐻", "🐨", "🦁", "🐧", "🦄"]
PLACEHOLDER_BOOTSTRAP_VALUES = {
    "",
    "replace_with_a_strong_password",
    "replace_with_a_long_random_token",
    "replace_with_another_long_random_secret",
}


def get_enabled_modules() -> dict:
    """Return deploy-time module flags for the Extended app."""
    grocery_enabled = os.getenv("ENABLE_GROCERY", "1").strip().lower() not in {"0", "false", "no"}
    restaurant_enabled = os.getenv("ENABLE_RESTAURANT", "1").strip().lower() not in {"0", "false", "no"}
    if not grocery_enabled and not restaurant_enabled:
        grocery_enabled = True
    return {
        "grocery": grocery_enabled,
        "restaurant": restaurant_enabled,
        "general_expense": True,
    }


def build_app_config() -> dict:
    modules = get_enabled_modules()
    public_base = (os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/"))
    request_base = request.host_url.rstrip("/") if has_request_context() else ""
    return {
        "app_name": os.getenv("APP_DISPLAY_NAME", "LocalOCR Extended"),
        "app_slug": os.getenv("APP_SLUG", "localocr_extended"),
        "service_name": os.getenv("APP_SERVICE_NAME", "localocr-extended-backend"),
        "public_base_url_default": public_base,
        "request_base_url": request_base,
        "modules": modules,
        "module_view_mode": "separate",
        "ports": {
            "default_backend": int(os.getenv("FLASK_PORT", "8090")),
        },
        "google_oauth_enabled": _is_google_oauth_configured(),
    }


def hash_token(token: str) -> str:
    """Hash an API token for secure storage/comparison."""
    return hashlib.sha256(token.encode()).hexdigest()


def build_public_base_url(preferred_base_url: str | None = None) -> str:
    candidate = (preferred_base_url or "").strip().rstrip("/")
    if candidate:
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return (
        os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        or request.host_url.rstrip("/")
    )


def create_access_link(
    *,
    purpose: str,
    created_by_id: int | None = None,
    target_user_id: int | None = None,
    expires_in_minutes: int = 60,
    metadata_json: str | None = None,
):
    token = secrets.token_urlsafe(32)
    link = AccessLink(
        created_by_id=created_by_id,
        target_user_id=target_user_id,
        purpose=purpose,
        token_hash=hash_token(token),
        metadata_json=metadata_json,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
    )
    g.db_session.add(link)
    g.db_session.flush()
    return token, link


def get_valid_access_link(token: str, purpose: str, *, allow_used: bool = False):
    if not token:
        return None
    link = (
        g.db_session.query(AccessLink)
        .filter(
            AccessLink.token_hash == hash_token(token),
            AccessLink.purpose == purpose,
        )
        .first()
    )
    if not link:
        return None
    now = datetime.now(timezone.utc)
    if link.expires_at:
        expires_at = link.expires_at
        compare_now = now.replace(tzinfo=None) if expires_at.tzinfo is None else now
        if expires_at < compare_now:
            return None
    if not allow_used and link.used_at:
        return None
    return link


def hash_password(password: str) -> str:
    """Create a secure password hash."""
    return generate_password_hash(password)


def verify_password(user: User, password: str) -> bool:
    """Check password against password_hash or legacy token fallback."""
    if not password or not user or not user.is_active:
        return False

    if user.password_hash:
        try:
            if check_password_hash(user.password_hash, password):
                return True
        except ValueError:
            logger.warning("Stored password hash for user %s is invalid.", user.id)

    if user.api_token_hash and hash_token(password) == user.api_token_hash:
        return True

    return False


def _clear_auth_session():
    session.pop("user_id", None)
    session.pop("trusted_device_id", None)
    session.pop("auth_source", None)
    session.pop("session_version", None)


def _set_browser_session(user: User):
    session["user_id"] = user.id
    session["auth_source"] = "browser_session"
    session["session_version"] = int(user.session_version or 0)
    session.pop("trusted_device_id", None)
    session.permanent = True
    # Capture activity markers so Settings can show the user when/where
    # they last signed in. last_login_at moves forward to the PREVIOUS
    # current_session start (not "now") so the user can see an actual
    # prior login, not an always-"just-now" value.
    now = datetime.now(timezone.utc)
    ua = (request.headers.get("User-Agent") or "").strip()[:500] if has_request_context() else None
    try:
        prior_session_start = getattr(user, "current_session_started_at", None)
        user.last_login_at = prior_session_start or now
        user.current_session_started_at = now
        if ua:
            user.last_login_user_agent = ua
        g.db_session.add(user)
        g.db_session.commit()
    except Exception:  # noqa: BLE001
        # Never block login on a bookkeeping failure.
        try:
            g.db_session.rollback()
        except Exception:
            pass


def _set_trusted_device_session(user: User, device: TrustedDevice):
    session["user_id"] = user.id
    session["trusted_device_id"] = device.id
    session["auth_source"] = "trusted_device"
    session["session_version"] = int(user.session_version or 0)
    session.permanent = True


def _set_auth_context(source: str, user: User | None = None, device: TrustedDevice | None = None):
    g.auth_source = source
    g.auth_user = user
    g.auth_trusted_device = device


def get_authenticated_user():
    """Resolve current user from session or bearer token."""
    _set_auth_context("anonymous")
    trusted_device_token = (request.headers.get("X-Trusted-Device-Token") or "").strip()
    if trusted_device_token:
        token_hash = hash_token(trusted_device_token)
        device = g.db_session.query(TrustedDevice).filter_by(token_hash=token_hash).first()
        if device and device.status == "active":
            user = g.db_session.query(User).filter_by(id=device.linked_user_id).first()
            if user and user.is_active:
                device.last_seen_at = datetime.now(timezone.utc)
                _set_auth_context("trusted_device_token", user, device)
                return user
        # A request that presents a trusted-device token must not silently fall
        # back to a normal browser session after revoke/expiration.
        _clear_auth_session()
        return None

    session_auth_source = session.get("auth_source")
    trusted_device_id = session.get("trusted_device_id")
    if trusted_device_id:
        device = g.db_session.query(TrustedDevice).filter_by(id=trusted_device_id).first()
        if device and device.status == "active":
            user = g.db_session.query(User).filter_by(id=device.linked_user_id).first()
            if user and user.is_active:
                if int(session.get("session_version", -1)) != int(user.session_version or 0):
                    _clear_auth_session()
                    return None
                session["user_id"] = user.id
                device.last_seen_at = datetime.now(timezone.utc)
                _set_auth_context("trusted_device_session", user, device)
                return user
        _clear_auth_session()
        return None

    if session_auth_source == "trusted_device":
        _clear_auth_session()
        return None

    session_user_id = session.get("user_id")
    if session_user_id:
        user = g.db_session.query(User).filter_by(id=session_user_id).first()
        if user and user.is_active:
            if int(session.get("session_version", -1)) != int(user.session_version or 0):
                _clear_auth_session()
                return None
            _set_auth_context(session_auth_source or "browser_session", user)
            return user
        _clear_auth_session()

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split("Bearer ", 1)[1]
        token_hash = hash_token(token)
        user = g.db_session.query(User).filter_by(api_token_hash=token_hash).first()
        if user and user.is_active:
            allowed = _parse_allowed_ips(getattr(user, "allowed_ips", None))
            if allowed:
                client_ip = _client_ip()
                if not _ip_in_allowlist(client_ip, allowed):
                    logger.warning(
                        "Bearer auth rejected for user_id=%s (name=%s) — client IP %s not in allowlist",
                        user.id, user.name, client_ip,
                    )
                    return None
            _set_auth_context("api_token", user)
            return user
        return None

    return None


def is_admin(user: User | None) -> bool:
    """Return True when the given user has admin privileges."""
    return bool(user and user.role == "admin")


def _parse_allowed_pages(raw) -> list[str] | None:
    """Decode the allowed_pages JSON column. None = no restriction."""
    import json as _json
    if raw is None:
        return None
    try:
        parsed = _json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (TypeError, ValueError):
        pass
    return None


# Pages the admin cannot be locked out of (prevents bricking their account
# during self-edit). Admins bypass the allowed_pages restriction anyway,
# but this enforces the rule at the API level too for future-proofing.
_ALWAYS_ALLOWED_FOR_ADMIN_SELF = {"dashboard", "settings"}


def _serialize_allowed_pages(value) -> str | None:
    """Normalize an allowed_pages payload into the stored JSON string.

    None / missing → None (no restriction, legacy behaviour).
    Empty list     → '[]' (explicit: no pages granted).
    Populated      → JSON array of de-duplicated page ids.
    """
    import json as _json
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("allowed_pages must be a list")
    cleaned: list[str] = []
    seen = set()
    for item in value:
        page = str(item).strip().lower()
        if not page or page in seen:
            continue
        seen.add(page)
        cleaned.append(page)
    return _json.dumps(cleaned)


def _parse_allowed_ips(raw) -> list[str] | None:
    """Decode the allowed_ips JSON column. None / [] = no restriction."""
    import json as _json
    if raw is None:
        return None
    try:
        parsed = _json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if str(x).strip()]
    except (TypeError, ValueError):
        pass
    return None


def _serialize_allowed_ips(value) -> str | None:
    """Normalize an allowed_ips payload into the stored JSON string.

    None / missing  → None (no restriction).
    Empty list      → None (treat as no restriction; there is no reason
                      to store an empty allowlist that would lock the
                      account out entirely).
    Populated       → JSON array of validated IP/CIDR strings.

    Raises ValueError on malformed entries so the caller can 400.
    """
    import json as _json
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("allowed_ips must be a list")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        entry = str(item).strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                network = ipaddress.ip_network(entry, strict=False)
                canonical = str(network)
            else:
                address = ipaddress.ip_address(entry)
                canonical = str(address)
        except ValueError as exc:
            raise ValueError(f"Invalid IP or CIDR '{entry}': {exc}") from exc
        if canonical in seen:
            continue
        seen.add(canonical)
        cleaned.append(canonical)
    if not cleaned:
        return None
    return _json.dumps(cleaned)


def _client_ip() -> str | None:
    """Return the best-effort client IP for the current request.

    ProxyFix (configured in create_flask_application) rewrites
    request.remote_addr from the first X-Forwarded-For hop when we run
    behind a trusted reverse proxy. Falls back to the raw header or
    remote_addr.
    """
    if not has_request_context():
        return None
    remote = (request.remote_addr or "").strip()
    if remote:
        return remote
    raw = (request.headers.get("X-Forwarded-For") or "").strip()
    if raw:
        return raw.split(",")[0].strip() or None
    return None


def _ip_in_allowlist(client_ip: str | None, allowed: list[str] | None) -> bool:
    """Return True if client_ip matches any entry in allowed (IPs or CIDRs)."""
    if not allowed:
        return True  # no restriction
    if not client_ip:
        return False
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if "/" in entry:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if ip == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


def _user_has_plaid_visibility(user: User) -> bool:
    """Return True when the user can see at least one PlaidItem — either
    one they linked themselves, or one shared with them by an admin.

    Used to auto-unlock the Accounts page in the sidebar when admin has
    shared a bank with this user even if the Pages modal doesn't
    explicitly grant Accounts. Sharing expresses intent strongly enough
    that a second permission ceremony would just cause bugs like
    "I shared BOA with her, why can't she see Accounts?".
    """
    try:
        from src.backend.initialize_database_schema import PlaidItem
    except ImportError:
        return False
    session = g.db_session
    # Owned item short-circuits.
    if session.query(PlaidItem.id).filter(PlaidItem.user_id == user.id).first():
        return True
    # Scan shared_with_user_ids. The plaid_items table is tiny (one row
    # per linked bank) so a Python-side scan is fine.
    import json as _json
    for (raw,) in session.query(PlaidItem.shared_with_user_ids).all():
        if not raw:
            continue
        try:
            ids = _json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(ids, list) and user.id in ids:
            return True
    return False


def serialize_user(user: User) -> dict:
    """Return a safe JSON representation for auth responses."""
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar_emoji": user.avatar_emoji or pick_default_avatar(user.name or user.email or str(user.id)),
        "role": user.role,
        "is_active": bool(user.is_active),
        "has_password": bool(user.password_hash),
        "has_api_token": bool(user.api_token_hash),
        "has_google": bool(getattr(user, "google_sub", None)),
        "google_email": getattr(user, "google_email", None),
        "password_reset_requested": bool(user.password_reset_requested_at),
        "password_reset_requested_at": (
            user.password_reset_requested_at.isoformat() if user.password_reset_requested_at else None
        ),
        "allowed_pages": _parse_allowed_pages(getattr(user, "allowed_pages", None)),
        "has_plaid_visibility": _user_has_plaid_visibility(user),
        "allow_write": bool(getattr(user, "allow_write", False)),
        "allowed_ips": _parse_allowed_ips(getattr(user, "allowed_ips", None)),
        "is_service": (user.role or "") == "service",
        "last_login_at": (
            (user.last_login_at.isoformat() + "Z")
            if getattr(user, "last_login_at", None) and not user.last_login_at.isoformat().endswith("Z")
            else (user.last_login_at.isoformat() if getattr(user, "last_login_at", None) else None)
        ),
        "current_session_started_at": (
            (user.current_session_started_at.isoformat() + "Z")
            if getattr(user, "current_session_started_at", None)
            and not user.current_session_started_at.isoformat().endswith("Z")
            else (
                user.current_session_started_at.isoformat()
                if getattr(user, "current_session_started_at", None)
                else None
            )
        ),
        "last_login_user_agent": getattr(user, "last_login_user_agent", None),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


def serialize_auth_context() -> dict:
    source = getattr(g, "auth_source", "anonymous")
    device = getattr(g, "auth_trusted_device", None)
    return {
        "source": source,
        "trusted_device": serialize_trusted_device(device) if device else None,
    }


def serialize_trusted_device(device: TrustedDevice) -> dict:
    linked_user = g.db_session.query(User).filter_by(id=device.linked_user_id).first()
    creator = g.db_session.query(User).filter_by(id=device.created_by_id).first() if device.created_by_id else None
    return {
        "id": device.id,
        "name": device.name,
        "scope": device.scope,
        "status": device.status,
        "linked_user_id": device.linked_user_id,
        "linked_user_name": linked_user.name if linked_user else None,
        "created_by_id": device.created_by_id,
        "created_by_name": creator.name if creator else None,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "revoked_at": device.revoked_at.isoformat() if device.revoked_at else None,
        "created_at": device.created_at.isoformat() if device.created_at else None,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
    }


def get_current_trusted_device() -> TrustedDevice | None:
    return getattr(g, "auth_trusted_device", None)


def is_trusted_device_request() -> bool:
    return str(getattr(g, "auth_source", "") or "").startswith("trusted_device")


def get_current_trusted_device_scope() -> str:
    device = get_current_trusted_device()
    if not device:
        return "shared_household"
    return _normalize_device_scope(device.scope)


def is_read_only_device_request() -> bool:
    return is_trusted_device_request() and get_current_trusted_device_scope() == "read_only"


def is_kitchen_display_device_request() -> bool:
    return is_trusted_device_request() and get_current_trusted_device_scope() == "kitchen_display"


def _normalize_device_scope(value: str | None) -> str:
    scope = (value or "shared_household").strip().lower()
    if scope not in {"shared_household", "kitchen_display", "read_only"}:
        return "shared_household"
    return scope


def _device_pairing_expired(pairing: DevicePairingSession) -> bool:
    now = datetime.now(timezone.utc)
    expires_at = pairing.expires_at
    compare_now = now.replace(tzinfo=None) if expires_at and expires_at.tzinfo is None else now
    return bool(expires_at and expires_at < compare_now)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_valid_pairing_session(token: str, *, allow_claimed: bool = False) -> DevicePairingSession | None:
    if not token:
        return None
    pairing = (
        g.db_session.query(DevicePairingSession)
        .filter(DevicePairingSession.pairing_token_hash == hash_token(token))
        .first()
    )
    if not pairing:
        return None
    if _device_pairing_expired(pairing):
        if pairing.status not in {"claimed", "rejected"}:
            pairing.status = "expired"
        return None
    if not allow_claimed and pairing.status not in {"pending", "approved"}:
        return None
    return pairing


def _get_admin_actor_from_request_payload(data: dict | None = None) -> User | None:
    actor = get_authenticated_user()
    if actor and is_admin(actor):
        return actor

    payload = data or request.get_json(silent=True) or {}
    identifier = (payload.get("admin_email") or payload.get("admin_identifier") or "").strip()
    password = payload.get("admin_password") or ""
    if not identifier or not password:
        return None

    ident_lower = identifier.lower()
    user = (
        g.db_session.query(User)
        .filter(
            User.is_active.is_(True),
            or_(
                func.lower(User.email) == ident_lower,
                func.lower(User.name) == ident_lower,
            ),
        )
        .first()
    )
    if not user or not is_admin(user) or not verify_password(user, password):
        return None
    return user


def serialize_user_stats(user: User) -> dict:
    """Return contribution stats for the current user."""
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    tomorrow_start = today_start + timedelta(days=1)
    month_start = datetime(now.year, now.month, 1)

    receipts_processed = (
        g.db_session.query(Purchase)
        .filter(Purchase.user_id == user.id)
        .count()
    )
    receipts_today = (
        g.db_session.query(Purchase)
        .filter(Purchase.user_id == user.id)
        .filter(Purchase.created_at >= today_start, Purchase.created_at < tomorrow_start)
        .count()
    )
    ocr_corrections = (
        g.db_session.query(Product)
        .filter(Product.reviewed_by_id == user.id, Product.review_state == "resolved")
        .count()
    )
    receipts_month = (
        g.db_session.query(Purchase)
        .filter(Purchase.user_id == user.id, Purchase.created_at >= month_start)
        .count()
    )
    ocr_corrections_month = (
        g.db_session.query(Product)
        .filter(
            Product.reviewed_by_id == user.id,
            Product.review_state == "resolved",
            Product.reviewed_at.isnot(None),
            Product.reviewed_at >= month_start,
        )
        .count()
    )
    bonus_points = sum_bonus_points(g.db_session, user.id)
    floating_points = sum_floating_points(g.db_session, user.id)
    total_score = receipts_processed * 5 + ocr_corrections * 20 + bonus_points
    return {
        "receipts_today": receipts_today,
        "receipts_month": receipts_month,
        "receipts_processed": receipts_processed,
        "ocr_corrections": ocr_corrections,
        "ocr_corrections_month": ocr_corrections_month,
        "bonus_points": bonus_points,
        "floating_points": floating_points,
        "score": total_score,
    }


def serialize_household_leaderboard(current_user_id: int | None = None) -> dict:
    """Return monthly top contributors and current-user rank."""
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)
    active_users = (
        g.db_session.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.name.asc(), User.email.asc())
        .all()
    )

    rankings = []
    for user in active_users:
        today_start = datetime(now.year, now.month, now.day)
        tomorrow_start = today_start + timedelta(days=1)
        receipts_today = (
            g.db_session.query(Purchase)
            .filter(
                Purchase.user_id == user.id,
                Purchase.created_at >= today_start,
                Purchase.created_at < tomorrow_start,
            )
            .count()
        )
        receipts_processed = (
            g.db_session.query(Purchase)
            .filter(Purchase.user_id == user.id)
            .count()
        )
        receipts_month = (
            g.db_session.query(Purchase)
            .filter(Purchase.user_id == user.id, Purchase.created_at >= month_start)
            .count()
        )
        ocr_corrections = (
            g.db_session.query(Product)
            .filter(Product.reviewed_by_id == user.id, Product.review_state == "resolved")
            .count()
        )
        ocr_corrections_month = (
            g.db_session.query(Product)
            .filter(
                Product.reviewed_by_id == user.id,
                Product.review_state == "resolved",
                Product.reviewed_at.isnot(None),
                Product.reviewed_at >= month_start,
            )
            .count()
        )
        bonus_points = sum_bonus_points(g.db_session, user.id)
        floating_points = sum_floating_points(g.db_session, user.id)
        score = receipts_processed * 5 + ocr_corrections * 20 + bonus_points
        rankings.append({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "avatar_emoji": user.avatar_emoji or pick_default_avatar(user.name or user.email or str(user.id)),
            "score": score,
            "receipts_today": receipts_today,
            "receipts_processed": receipts_processed,
            "receipts_month": receipts_month,
            "ocr_corrections": ocr_corrections,
            "ocr_corrections_month": ocr_corrections_month,
            "bonus_points": bonus_points,
            "floating_points": floating_points,
        })

    rankings.sort(key=lambda item: (-item["score"], -item["ocr_corrections"], -item["receipts_processed"], item["name"] or item["email"] or ""))
    previous_score = None
    previous_rank = 0
    for index, item in enumerate(rankings, start=1):
        if previous_score is not None and item["score"] == previous_score:
            item["rank"] = previous_rank
        else:
            item["rank"] = index
            previous_rank = index
            previous_score = item["score"]

    current_user_rank = next((item["rank"] for item in rankings if item["id"] == current_user_id), None)
    return {
        "month": month_start.strftime("%Y-%m"),
        "rankings": rankings,
        "leaders": rankings[:3],
        "current_user_rank": current_user_rank,
        "total_users": len(rankings),
    }


def active_admin_count() -> int:
    """Return the number of active admins."""
    return (
        g.db_session.query(User)
        .filter(User.role == "admin", User.is_active.is_(True))
        .count()
    )


def pick_default_avatar(seed: str) -> str:
    seed_text = str(seed or "user")
    index = sum(ord(ch) for ch in seed_text) % len(DEFAULT_AVATARS)
    return DEFAULT_AVATARS[index]


def is_valid_login_email(email: str) -> bool:
    """Allow practical local-login emails like admin@localhost."""
    if not email or "@" not in email:
        return False
    local_part, domain = email.split("@", 1)
    return bool(local_part.strip() and domain.strip())


def get_bootstrap_admin_defaults() -> tuple[str, str, str]:
    """Return bootstrap admin display defaults from env."""
    bootstrap_password = (
        os.getenv("INITIAL_ADMIN_PASSWORD", "") or os.getenv("INITIAL_ADMIN_TOKEN", "")
    ).strip()
    if bootstrap_password in PLACEHOLDER_BOOTSTRAP_VALUES:
        bootstrap_password = ""
    return (
        os.getenv("INITIAL_ADMIN_NAME", "Admin"),
        os.getenv("INITIAL_ADMIN_EMAIL", "admin@localhost"),
        bootstrap_password,
    )


@auth_bp.route("/bootstrap-info", methods=["GET"])
def bootstrap_info():
    """Return safe login hints for the first local admin login."""
    _, admin_email, _ = get_bootstrap_admin_defaults()
    admin = (
        g.db_session.query(User)
        .filter(User.role == "admin")
        .order_by(User.id.asc())
        .first()
    )
    return jsonify({
        "default_email": (admin.email if admin and admin.email else admin_email),
        "has_users": g.db_session.query(User).count() > 0,
        "app_config": build_app_config(),
    }), 200


@auth_bp.route("/app-config", methods=["GET"])
def app_config():
    """Return public frontend config such as enabled modules and branding."""
    return jsonify(build_app_config()), 200


@auth_bp.route("/login", methods=["POST"])
def login():
    """Create a browser session for a local user."""
    data = request.get_json(silent=True) or {}
    identifier = (data.get("email") or data.get("identifier") or "").strip()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify({"error": "Email and password are required"}), 400

    # Case-insensitive identifier match — users shouldn't have to remember
    # whether they typed "Chamu" or "chamu" at signup. Password check
    # stays byte-exact.
    ident_lower = identifier.lower()
    user = (
        g.db_session.query(User)
        .filter(
            or_(
                func.lower(User.email) == ident_lower,
                func.lower(User.name) == ident_lower,
            )
        )
        .first()
    )
    if not user or not verify_password(user, password):
        return jsonify({"error": "Invalid email or password"}), 401

    _set_browser_session(user)

    return jsonify({
        "user": {
            **serialize_user(user),
        },
        "auth": {
            "source": "browser_session",
            "trusted_device": None,
        },
        "stats": serialize_user_stats(user),
        "leaderboard": serialize_household_leaderboard(user.id),
        "app_config": build_app_config(),
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """End the browser session."""
    _clear_auth_session()
    return jsonify({"status": "logged_out"}), 200


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """Record a reset request for an existing local user without exposing account existence."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email or not is_valid_login_email(email):
        return jsonify({"message": "If that account exists, the admin can now see the reset request."}), 200

    user = (
        g.db_session.query(User)
        .filter(func.lower(User.email) == email.lower())
        .first()
    )
    if user and user.is_active:
        user.password_reset_requested_at = datetime.now(timezone.utc)
        g.db_session.commit()
        logger.info("Password reset requested for user %s", user.email)

    return jsonify({"message": "If that account exists, the admin can now see the reset request."}), 200


@auth_bp.route("/me", methods=["GET"])
def me():
    """Return the current authenticated user from session or token."""
    user = get_authenticated_user()
    if not user:
        return jsonify({"authenticated": False}), 401

    if session.get("user_id") != user.id and "Authorization" not in request.headers:
        if getattr(g, "auth_source", "") == "trusted_device_session" and getattr(g, "auth_trusted_device", None):
            _set_trusted_device_session(user, g.auth_trusted_device)
        else:
            _set_browser_session(user)

    return jsonify({
        "authenticated": True,
        "user": serialize_user(user),
        "auth": serialize_auth_context(),
        "stats": serialize_user_stats(user),
        "leaderboard": serialize_household_leaderboard(user.id),
        "app_config": build_app_config(),
    }), 200


@auth_bp.route("/qr-login-link", methods=["POST"])
def qr_login_link():
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    data = request.get_json(silent=True) or {}
    base_url = build_public_base_url(data.get("current_base_url"))

    token, link = create_access_link(
        purpose="login_qr",
        created_by_id=user.id,
        target_user_id=user.id,
        expires_in_minutes=10,
    )
    g.db_session.commit()
    url = f"{base_url}/auth/qr-login/{token}"
    return jsonify({
        "url": url,
        "qr_image_url": f"{base_url}/auth/qr-image?data={quote(url, safe='')}",
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
    }), 200


@auth_bp.route("/qr-login/<token>", methods=["GET"])
def qr_login(token: str):
    link = get_valid_access_link(token, "login_qr")
    if not link or not link.target_user_id:
        return redirect("/")

    user = g.db_session.query(User).filter_by(id=link.target_user_id, is_active=True).first()
    if not user:
        return redirect("/")

    _set_browser_session(user)
    link.used_at = datetime.now(timezone.utc)
    g.db_session.commit()
    return redirect("/")


@auth_bp.route("/qr-image", methods=["GET"])
def qr_image():
    data = (request.args.get("data") or "").strip()
    if not data:
        return jsonify({"error": "Missing data"}), 400

    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png", max_age=300)


@auth_bp.route("/device-pairing/start", methods=["POST"])
def device_pairing_start():
    """Start a short-lived trusted-device pairing session."""
    data = request.get_json(silent=True) or {}
    device_name = (data.get("device_name") or "Kitchen Fridge").strip()
    scope = _normalize_device_scope(data.get("scope"))
    base_url = build_public_base_url(data.get("current_base_url"))
    pairing_token = secrets.token_urlsafe(32)
    pairing = DevicePairingSession(
        pairing_token_hash=hash_token(pairing_token),
        device_name=device_name[:120] or "Kitchen Fridge",
        scope=scope,
        status="pending",
        created_by_device=(request.headers.get("User-Agent") or "")[:255] or None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    g.db_session.add(pairing)
    g.db_session.commit()
    pairing_url = f"{base_url}/auth/pair-device/{quote(pairing_token, safe='')}"
    return jsonify({
        "pairing_token": pairing_token,
        "pairing_url": pairing_url,
        "qr_image_url": f"{base_url}/auth/qr-image?data={quote(pairing_url, safe='')}",
        "expires_at": pairing.expires_at.isoformat() if pairing.expires_at else None,
        "device_name": pairing.device_name,
        "scope": pairing.scope,
        "status": pairing.status,
    }), 201


@auth_bp.route("/pair-device/<token>", methods=["GET"])
def device_pairing_handoff(token: str):
    """Render a simple handoff page so QR scans never land on a blank SPA boot."""
    approve_url = f"{build_public_base_url()}/?pair_device={quote(token, safe='')}"
    app_name = os.getenv("APP_DISPLAY_NAME", "Extended")
    return render_template_string(
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ app_name }} Device Pairing</title>
  <style>
    :root { color-scheme: dark; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0f1117;
      color: #f5f7ff;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      padding: 24px;
    }
    .card {
      width: min(560px, 100%);
      background: #171b26;
      border: 1px solid rgba(124, 92, 255, 0.28);
      border-radius: 18px;
      padding: 28px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.28);
      display: grid;
      gap: 14px;
    }
    .brand { color: #8a76ff; font-size: .92rem; font-weight: 700; }
    h1 { margin: 0; font-size: 1.55rem; line-height: 1.15; }
    p { margin: 0; color: #b0b8cb; line-height: 1.55; }
    .actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; }
    .btn {
      appearance: none;
      border: 1px solid rgba(124, 92, 255, 0.35);
      background: #7c5cff;
      color: white;
      text-decoration: none;
      padding: 12px 16px;
      border-radius: 12px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .btn.secondary {
      background: transparent;
      color: #d9def0;
      border-color: rgba(255, 255, 255, 0.12);
    }
    .hint {
      margin-top: 4px;
      padding: 12px 14px;
      border-radius: 12px;
      background: rgba(255,255,255,.03);
      border: 1px solid rgba(255,255,255,.06);
      font-size: .92rem;
    }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: .85rem;
      color: #d8c8ff;
      word-break: break-all;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="brand">{{ app_name }}</div>
    <h1>Approve this trusted device</h1>
    <p>Open this on a browser where an admin can sign in. After sign-in, approve the request to pair your fridge or shared screen.</p>
    <div class="actions">
      <a class="btn" href="{{ approve_url }}">Continue to approval</a>
      <a class="btn secondary" href="{{ base_url }}">Open app home</a>
    </div>
    <div class="hint">
      If the approval page still feels empty, sign in first on this same browser and then reopen this link.
    </div>
    <code>{{ approve_url }}</code>
  </div>
</body>
</html>""",
        app_name=app_name,
        approve_url=approve_url,
        base_url=build_public_base_url(),
    )


@auth_bp.route("/device-pairing/status/<token>", methods=["GET"])
def device_pairing_status(token: str):
    """Poll pairing state and claim a trusted-device session after admin approval."""
    pairing = _get_valid_pairing_session(token, allow_claimed=True)
    if not pairing:
        return jsonify({"status": "expired"}), 404

    if pairing.status == "rejected":
        return jsonify({"status": "rejected"}), 200

    if pairing.status == "approved":
        device = g.db_session.query(TrustedDevice).filter_by(id=pairing.trusted_device_id).first()
        if not device or device.status != "active":
            return jsonify({"status": "error", "error": "Trusted device not available"}), 409

        if not pairing.claimed_at:
            pairing.claimed_at = datetime.now(timezone.utc)
            pairing.status = "claimed"
        device.last_seen_at = datetime.now(timezone.utc)
        user = g.db_session.query(User).filter_by(id=device.linked_user_id).first()
        if not user or not user.is_active:
            return jsonify({"status": "error", "error": "Linked user not available"}), 409
        _set_trusted_device_session(user, device)
        g.db_session.commit()
        return jsonify({
            "status": "approved",
            "authenticated": True,
            "user": serialize_user(user) if user else None,
            "auth": {
                "source": "trusted_device_session",
                "trusted_device": serialize_trusted_device(device),
            },
            "trusted_device": serialize_trusted_device(device),
            "app_config": build_app_config(),
        }), 200

    if pairing.status == "claimed":
        trusted_device_id = session.get("trusted_device_id")
        if trusted_device_id == pairing.trusted_device_id:
            device = g.db_session.query(TrustedDevice).filter_by(id=pairing.trusted_device_id).first()
            user = g.db_session.query(User).filter_by(id=device.linked_user_id).first() if device else None
            return jsonify({
                "status": "claimed",
                "authenticated": True,
                "user": serialize_user(user) if user else None,
                "auth": {
                    "source": "trusted_device_session",
                    "trusted_device": serialize_trusted_device(device) if device else None,
                },
                "trusted_device": serialize_trusted_device(device) if device else None,
                "app_config": build_app_config(),
            }), 200
        return jsonify({"status": "claimed"}), 200

    return jsonify({
        "status": pairing.status,
        "expires_at": pairing.expires_at.isoformat() if pairing.expires_at else None,
        "device_name": pairing.device_name,
        "scope": pairing.scope,
    }), 200


@auth_bp.route("/device-pairing/claim/<token>", methods=["GET"])
def claim_device_pairing(token: str):
    """Claim an approved pairing via a top-level navigation so the session persists reliably."""
    pairing = _get_valid_pairing_session(token, allow_claimed=True)
    if not pairing:
        return redirect("/?pairing_claim=expired")

    if pairing.status == "rejected":
        return redirect("/?pairing_claim=rejected")

    if pairing.status not in {"approved", "claimed"}:
        return redirect("/?pairing_claim=pending")

    device = g.db_session.query(TrustedDevice).filter_by(id=pairing.trusted_device_id).first()
    if not device or device.status != "active":
        return redirect("/?pairing_claim=unavailable")

    if not pairing.claimed_at:
        pairing.claimed_at = datetime.now(timezone.utc)
        pairing.status = "claimed"
    device.last_seen_at = datetime.now(timezone.utc)
    user = g.db_session.query(User).filter_by(id=device.linked_user_id).first()
    if not user or not user.is_active:
        return redirect("/?pairing_claim=unavailable")
    _set_trusted_device_session(user, device)
    g.db_session.commit()
    return redirect("/?pairing_claim=ok")


@auth_bp.route("/device-pairing/approve", methods=["POST"])
def approve_device_pairing():
    """Approve a pending pairing request and mint a managed trusted device."""
    data = request.get_json(silent=True) or {}
    actor = _get_admin_actor_from_request_payload(data)
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    pairing_token = (data.get("pairing_token") or "").strip()
    pairing = _get_valid_pairing_session(pairing_token)
    if not pairing:
        return jsonify({"error": "Pairing session not found or expired"}), 404
    if pairing.status != "pending":
        return jsonify({"error": f"Pairing session is already {pairing.status}"}), 409

    linked_user_id = int(data.get("linked_user_id") or actor.id)
    linked_user = g.db_session.query(User).filter_by(id=linked_user_id, is_active=True).first()
    if not linked_user:
        return jsonify({"error": "Linked user not found"}), 404

    device_name = (data.get("device_name") or pairing.device_name or "Trusted Device").strip()[:120] or "Trusted Device"
    scope = _normalize_device_scope(data.get("scope") or pairing.scope)
    matching_devices = (
        g.db_session.query(TrustedDevice)
        .filter(
            TrustedDevice.linked_user_id == linked_user.id,
            TrustedDevice.name == device_name,
        )
        .order_by(TrustedDevice.created_at.desc(), TrustedDevice.id.desc())
        .all()
    )

    pairing_created_at = _coerce_utc(pairing.created_at)
    stale_revoke = None
    revoked_same_name_devices = [
        device for device in matching_devices
        if device.revoked_at and device.status == "revoked"
    ]
    if pairing_created_at:
        revoked_same_name_devices.sort(
            key=lambda device: (_coerce_utc(device.revoked_at) or datetime.min.replace(tzinfo=timezone.utc), device.id),
            reverse=True,
        )
        for revoked_device in revoked_same_name_devices:
            revoked_at = _coerce_utc(revoked_device.revoked_at)
            if revoked_at and revoked_at >= pairing_created_at:
                stale_revoke = revoked_device
                break
    if stale_revoke:
        pairing.status = "rejected"
        pairing.approved_by_user_id = actor.id
        pairing.approved_at = datetime.now(timezone.utc)
        g.db_session.commit()
        return jsonify({"error": "This device pairing was revoked and must be restarted from a fresh QR code"}), 409

    active_matching_devices = [device for device in matching_devices if device.status == "active"]
    trusted_device = active_matching_devices[0] if active_matching_devices else None
    if trusted_device:
        trusted_device.scope = scope
        trusted_device.status = "active"
        trusted_device.token_hash = hash_token(pairing_token)
        trusted_device.created_by_id = actor.id
        trusted_device.revoked_at = None
        trusted_device.last_seen_at = None
    else:
        trusted_device = TrustedDevice(
            name=device_name,
            scope=scope,
            status="active",
            token_hash=hash_token(pairing_token),
            linked_user_id=linked_user.id,
            created_by_id=actor.id,
            last_seen_at=None,
        )
        g.db_session.add(trusted_device)
        g.db_session.flush()

    duplicate_pool = active_matching_devices[1:] if active_matching_devices else matching_devices
    for duplicate in duplicate_pool:
        duplicate.status = "revoked"
        duplicate.revoked_at = datetime.now(timezone.utc)

    pairing.scope = scope
    pairing.device_name = device_name
    pairing.status = "approved"
    pairing.approved_by_user_id = actor.id
    pairing.trusted_device_id = trusted_device.id
    pairing.approved_at = datetime.now(timezone.utc)
    g.db_session.commit()

    return jsonify({
        "status": "approved",
        "trusted_device": serialize_trusted_device(trusted_device),
        "linked_user": serialize_user(linked_user),
    }), 200


@auth_bp.route("/device-pairing/reject", methods=["POST"])
def reject_device_pairing():
    data = request.get_json(silent=True) or {}
    actor = _get_admin_actor_from_request_payload(data)
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    pairing_token = (data.get("pairing_token") or "").strip()
    pairing = _get_valid_pairing_session(pairing_token)
    if not pairing:
        return jsonify({"error": "Pairing session not found or expired"}), 404

    pairing.status = "rejected"
    pairing.approved_by_user_id = actor.id
    pairing.approved_at = datetime.now(timezone.utc)
    g.db_session.commit()
    return jsonify({"status": "rejected"}), 200


@auth_bp.route("/trusted-devices", methods=["GET"])
def list_trusted_devices():
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    include_revoked = str(request.args.get("include_revoked") or "").strip().lower() in {"1", "true", "yes"}
    query = g.db_session.query(TrustedDevice)
    if not include_revoked:
        query = query.filter(TrustedDevice.status == "active")
    devices = query.order_by(TrustedDevice.status.asc(), TrustedDevice.created_at.desc()).all()
    return jsonify({
        "devices": [serialize_trusted_device(device) for device in devices],
        "count": len(devices),
    }), 200


@auth_bp.route("/trusted-devices/<int:device_id>", methods=["PUT"])
def update_trusted_device(device_id: int):
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    device = g.db_session.query(TrustedDevice).filter_by(id=device_id).first()
    if not device:
        return jsonify({"error": "Trusted device not found"}), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or device.name or "").strip()
    scope = _normalize_device_scope(data.get("scope") or device.scope)
    if not name:
        return jsonify({"error": "Device name is required"}), 400

    device.name = name[:120]
    device.scope = scope
    g.db_session.commit()
    return jsonify({"trusted_device": serialize_trusted_device(device)}), 200


@auth_bp.route("/trusted-devices/<int:device_id>", methods=["DELETE"])
def delete_trusted_device(device_id: int):
    """Permanently remove a trusted device row (admin only).

    Differs from /revoke in that revoke leaves a 'revoked' row behind
    for audit; delete wipes the row and any pairing sessions that
    reference it. Any token the device still has is implicitly
    invalidated because the lookup returns no match.

    Also clears DevicePairingSessions that reference this device so
    we don't leave dangling FKs.
    """
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    device = g.db_session.query(TrustedDevice).filter_by(id=device_id).first()
    if not device:
        return jsonify({"error": "Trusted device not found"}), 404

    name = device.name
    pairing_sessions = (
        g.db_session.query(DevicePairingSession)
        .filter(DevicePairingSession.trusted_device_id == device_id)
        .all()
    )
    try:
        for pairing in pairing_sessions:
            g.db_session.delete(pairing)
        g.db_session.delete(device)
        g.db_session.commit()
    except Exception as exc:
        g.db_session.rollback()
        logger.exception("Failed to delete trusted device id=%s", device_id)
        return jsonify({"error": f"Could not delete: {exc}"}), 409
    logger.info(
        "Trusted device '%s' (id=%s) deleted by admin %s",
        name, device_id, actor.email or actor.id,
    )
    return jsonify({"deleted": True, "id": device_id, "name": name}), 200


@auth_bp.route("/trusted-devices/<int:device_id>/revoke", methods=["POST"])
def revoke_trusted_device(device_id: int):
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    device = g.db_session.query(TrustedDevice).filter_by(id=device_id).first()
    if not device:
        return jsonify({"error": "Trusted device not found"}), 404

    matching_devices = (
        g.db_session.query(TrustedDevice)
        .filter(
            TrustedDevice.linked_user_id == device.linked_user_id,
            TrustedDevice.name == device.name,
            TrustedDevice.status == "active",
        )
        .all()
    )
    pairing_sessions = (
        g.db_session.query(DevicePairingSession)
        .filter(
            DevicePairingSession.device_name == device.name,
            DevicePairingSession.status.in_(["pending", "approved", "claimed"]),
        )
        .all()
    )
    revoked_at = datetime.now(timezone.utc)
    for matching_device in matching_devices:
        matching_device.status = "revoked"
        matching_device.revoked_at = revoked_at
    for pairing in pairing_sessions:
        pairing.status = "rejected"
        pairing.approved_at = revoked_at
    g.db_session.commit()
    return jsonify({
        "status": "revoked",
        "trusted_device": serialize_trusted_device(device),
        "revoked_count": len(matching_devices) or 1,
    }), 200


@auth_bp.route("/me/stats", methods=["GET"])
def my_stats():
    """Return contribution stats for the current authenticated user."""
    user = get_authenticated_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "stats": serialize_user_stats(user),
        "leaderboard": serialize_household_leaderboard(user.id),
        "app_config": build_app_config(),
    }), 200


@auth_bp.route("/household-members", methods=["GET"])
def list_household_members():
    """Return the signed-in user's household roster in a trimmed form.

    Any authenticated household member (not just admins) can fetch this
    because the UI uses it to populate the receipt-attribution picker
    — members need to see who to assign a receipt/item to.
    """
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401

    members = (
        g.db_session.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.name.asc(), User.email.asc())
        .all()
    )
    return jsonify({
        "members": [
            {
                "id": m.id,
                "name": m.name or m.email or f"User {m.id}",
                "is_self": m.id == user.id,
            }
            for m in members
        ],
    }), 200


@auth_bp.route("/users", methods=["GET"])
def list_users():
    """List local household users for admin management."""
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(user):
        return jsonify({"error": "Admin access required"}), 403

    users = (
        g.db_session.query(User)
        .order_by(User.role.desc(), User.name.asc(), User.email.asc())
        .all()
    )

    return jsonify({
        "users": [serialize_user(record) for record in users],
        "count": len(users),
    }), 200


@auth_bp.route("/users", methods=["POST"])
def create_user():
    """Create a new household user account. Admin only."""
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(user):
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip().lower()

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not email:
        return jsonify({"error": "Email is required"}), 400
    if not is_valid_login_email(email):
        return jsonify({"error": "Enter a valid email address"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if role not in {"admin", "user"}:
        return jsonify({"error": "Role must be 'admin' or 'user'"}), 400

    existing = (
        g.db_session.query(User)
        .filter(
            or_(
                func.lower(User.email) == email.lower(),
                func.lower(User.name) == name.lower(),
            )
        )
        .first()
    )
    if existing:
        return jsonify({"error": "A user with that name or email already exists"}), 409

    # Page-access restriction. Default new users to an empty list so
    # the admin has to explicitly grant each page — safer than granting
    # all pages and remembering to prune.
    raw_pages = data.get("allowed_pages", [])
    try:
        allowed_pages_json = _serialize_allowed_pages(raw_pages)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    created = User(
        name=name,
        email=email,
        role=role,
        is_active=True,
        avatar_emoji=(data.get("avatar_emoji") or "").strip() or pick_default_avatar(name or email),
        password_hash=hash_password(password),
        allowed_pages=allowed_pages_json,
    )
    g.db_session.add(created)
    g.db_session.commit()

    logger.info("User %s created by admin %s", created.email, user.email or user.id)
    return jsonify({"user": serialize_user(created)}), 201


@auth_bp.route("/service-accounts", methods=["POST"])
def create_service_account():
    """Create a non-human API-only account with a bearer token.

    Admin only. Returns the raw token ONCE — never again retrievable
    since only the hash is stored. Defaults to read-only unless
    allow_write=true is passed.

    Body: {"name": str, "allow_write": bool (default false)}
    """
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "Name must be 100 characters or fewer"}), 400
    allow_write = bool(data.get("allow_write", False))

    try:
        allowed_ips_json = _serialize_allowed_ips(data.get("allowed_ips"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Reject duplicate service names (case-insensitive).
    existing = (
        g.db_session.query(User)
        .filter(func.lower(User.name) == name.lower(), User.role == "service")
        .first()
    )
    if existing:
        return jsonify({"error": "A service account with that name exists"}), 409

    token = secrets.token_urlsafe(32)
    created = User(
        name=name,
        email=None,
        role="service",
        is_active=True,
        avatar_emoji="🤖",
        password_hash=None,
        api_token_hash=hash_token(token),
        allow_write=allow_write,
        allowed_ips=allowed_ips_json,
    )
    g.db_session.add(created)
    g.db_session.commit()
    logger.info(
        "Service account '%s' created by admin %s (allow_write=%s)",
        name, actor.email or actor.id, allow_write,
    )
    return jsonify({
        "user": serialize_user(created),
        "token": token,
        "note": "Save this token now — it cannot be retrieved again.",
    }), 201


@auth_bp.route("/service-accounts/<int:user_id>/rotate", methods=["POST"])
def rotate_service_account(user_id: int):
    """Issue a new bearer token, invalidating the old one."""
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403
    target = g.db_session.query(User).filter_by(id=user_id, role="service").first()
    if not target:
        return jsonify({"error": "Service account not found"}), 404
    token = secrets.token_urlsafe(32)
    target.api_token_hash = hash_token(token)
    target.session_version = int(target.session_version or 0) + 1
    g.db_session.commit()
    logger.info("Service account '%s' rotated by admin %s", target.name, actor.email or actor.id)
    return jsonify({
        "user": serialize_user(target),
        "token": token,
        "note": "Save this token now — it cannot be retrieved again.",
    }), 200


@auth_bp.route("/service-accounts/<int:user_id>", methods=["DELETE"])
def delete_service_account(user_id: int):
    """Permanently remove a service account and invalidate its token.

    Admin only. Service-accounts only — human-user deletion requires
    separate review of attribution / receipts / ownership and is not
    exposed via this endpoint.
    """
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403
    target = g.db_session.query(User).filter_by(id=user_id, role="service").first()
    if not target:
        return jsonify({"error": "Service account not found"}), 404
    name = target.name
    try:
        g.db_session.delete(target)
        g.db_session.commit()
    except Exception as exc:
        g.db_session.rollback()
        logger.exception("Failed to delete service account '%s'", name)
        return jsonify({"error": f"Could not delete: {exc}"}), 409
    logger.info("Service account '%s' deleted by admin %s", name, actor.email or actor.id)
    return jsonify({"deleted": True, "id": user_id, "name": name}), 200


@auth_bp.route("/service-accounts/<int:user_id>", methods=["PATCH"])
def update_service_account(user_id: int):
    """Admin-only updates to a service account's policy fields.

    Accepts any subset of:
      - allow_write: bool
      - allowed_ips: list[str]  (IPs / CIDRs; [] clears restriction)

    Rotating session_version on allowed_ips change is unnecessary —
    IP enforcement is evaluated per-request, so the next call with a
    mismatched IP is rejected automatically.
    """
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403
    target = g.db_session.query(User).filter_by(id=user_id, role="service").first()
    if not target:
        return jsonify({"error": "Service account not found"}), 404

    data = request.get_json(silent=True) or {}
    changed: list[str] = []
    if "allow_write" in data:
        target.allow_write = bool(data.get("allow_write"))
        changed.append(f"allow_write={target.allow_write}")
    if "allowed_ips" in data:
        try:
            target.allowed_ips = _serialize_allowed_ips(data.get("allowed_ips"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        changed.append(f"allowed_ips={_parse_allowed_ips(target.allowed_ips) or []}")
    if not changed:
        return jsonify({"user": serialize_user(target)}), 200
    g.db_session.commit()
    logger.info(
        "Service account '%s' updated by admin %s — %s",
        target.name, actor.email or actor.id, ", ".join(changed),
    )
    return jsonify({"user": serialize_user(target)}), 200


@auth_bp.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id: int):
    """Update an existing household user. Admins can edit anyone; users can update their own basic profile."""
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401

    target = g.db_session.query(User).filter_by(id=user_id).first()
    if not target:
        return jsonify({"error": "User not found"}), 404

    acting_on_self = actor.id == target.id
    if not is_admin(actor) and not acting_on_self:
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or target.name).strip()
    email = (data.get("email") or target.email or "").strip().lower()
    role = (data.get("role") or target.role).strip().lower()
    password = data.get("password")
    is_active = bool(data.get("is_active", target.is_active))
    avatar_emoji = (data.get("avatar_emoji") or target.avatar_emoji or "").strip()

    if not is_admin(actor):
        role = target.role
        is_active = target.is_active

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not email:
        return jsonify({"error": "Email is required"}), 400
    if not is_valid_login_email(email):
        return jsonify({"error": "Enter a valid email address"}), 400
    if role not in {"admin", "user"}:
        return jsonify({"error": "Role must be 'admin' or 'user'"}), 400
    if password is not None and password != "" and len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    conflict = (
        g.db_session.query(User)
        .filter(
            User.id != target.id,
            or_(
                func.lower(User.email) == email.lower(),
                func.lower(User.name) == name.lower(),
            ),
        )
        .first()
    )
    if conflict:
        return jsonify({"error": "Another user already uses that name or email"}), 409

    if target.id == actor.id and not is_active:
        return jsonify({"error": "You cannot deactivate the account you are currently using"}), 400

    removing_active_admin = (
        target.role == "admin"
        and bool(target.is_active)
        and (role != "admin" or not is_active)
    )
    if removing_active_admin and active_admin_count() <= 1:
        return jsonify({"error": "At least one active admin account must remain"}), 400

    target.name = name
    target.email = email
    target.role = role
    target.is_active = is_active
    target.avatar_emoji = avatar_emoji or pick_default_avatar(name or email)
    if password:
        target.password_hash = hash_password(password)
        target.password_reset_requested_at = None

    # allowed_pages is admin-only. Non-admins editing their own profile
    # can't change their own restriction set (would defeat the purpose).
    if is_admin(actor) and "allowed_pages" in data:
        try:
            pages_json = _serialize_allowed_pages(data.get("allowed_pages"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        # Self-edit guardrail: admin editing themselves keeps Dashboard
        # + Settings no matter what, so they can't brick their own
        # access. (Admins bypass the restriction anyway, but enforce
        # the invariant in case role changes later.)
        if acting_on_self and pages_json is not None:
            parsed = _parse_allowed_pages(pages_json) or []
            for must in _ALWAYS_ALLOWED_FOR_ADMIN_SELF:
                if must not in parsed:
                    parsed.append(must)
            pages_json = _serialize_allowed_pages(parsed)
        target.allowed_pages = pages_json

    # allow_write toggle is admin-only; used primarily for service
    # accounts but harmless on human users (their writes go through
    # session cookies which aren't gated by this field).
    if is_admin(actor) and "allow_write" in data:
        target.allow_write = bool(data.get("allow_write"))

    g.db_session.commit()
    logger.info("User %s updated by admin %s", target.email, actor.email or actor.id)
    return jsonify({"user": serialize_user(target)}), 200


# ---------------------------------------------------------------------------
# Google OAuth — helpers
# ---------------------------------------------------------------------------

def _is_google_oauth_configured() -> bool:
    """Return True when GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set."""
    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    enabled = os.getenv("GOOGLE_OAUTH_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
    return bool(client_id and client_secret and enabled)


def _get_oauth_redirect_uri() -> str:
    """Build the Google OAuth redirect URI from config or request context."""
    base = (
        os.getenv("OAUTH_REDIRECT_BASE_URL", "").strip().rstrip("/")
        or os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        or request.host_url.rstrip("/")
    )
    return f"{base}/auth/oauth/google/callback"


def _build_oauth_state(invite_token: str | None) -> str:
    """Create an HMAC-signed state string for CSRF protection."""
    import hmac
    from flask import current_app
    nonce = secrets.token_urlsafe(16)
    payload = f"{nonce}:{invite_token or ''}"
    sig = hmac.new(
        current_app.secret_key.encode() if isinstance(current_app.secret_key, str)
        else current_app.secret_key,
        payload.encode(),
        "sha256",
    ).hexdigest()
    return f"{payload}:{sig}"


def _verify_oauth_state(state: str) -> tuple[bool, str | None]:
    """Verify HMAC state; returns (valid, invite_token | None)."""
    import hmac
    from flask import current_app
    try:
        parts = state.split(":")
        if len(parts) < 3:
            return False, None
        sig = parts[-1]
        payload = ":".join(parts[:-1])
        expected = hmac.new(
            current_app.secret_key.encode() if isinstance(current_app.secret_key, str)
            else current_app.secret_key,
            payload.encode(),
            "sha256",
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False, None
        # payload is  nonce:invite_token_or_empty
        invite_token = parts[1] if len(parts) >= 3 and parts[1] else None
        return True, invite_token
    except Exception:
        return False, None


def _fetch_google_user_info(access_token: str) -> dict:
    """Exchange access token for Google user info."""
    import requests as _requests
    resp = _requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _find_or_create_oauth_user(
    session,
    google_info: dict,
    invite_token: str | None,
) -> User | None:
    """Resolve the User for a Google OAuth login.

    Resolution order:
      A. Existing user with matching google_sub  → log in directly
      B. Existing user with matching email        → link google_sub
      C. New user with a valid pending invite     → create + claim invite
      D. None                                     → reject (403)
    """
    google_sub = str(google_info.get("sub") or "").strip()
    google_email = str(google_info.get("email") or "").strip().lower()
    google_name = str(google_info.get("name") or "").strip()

    if not google_sub or not google_email:
        logger.warning("Google OAuth: missing sub or email in userinfo response")
        return None

    # Path A — already linked
    user = session.query(User).filter(
        User.google_sub == google_sub,
        User.is_active.is_(True),
    ).first()
    if user:
        user.google_email = google_email
        return user

    # Path B — same email, link google_sub (case-insensitive match
    # so Google-provided casing doesn't miss existing accounts).
    user = session.query(User).filter(
        func.lower(User.email) == (google_email or "").lower(),
        User.is_active.is_(True),
    ).first()
    if user:
        user.google_sub = google_sub
        user.google_email = google_email
        logger.info("Google OAuth: linked google_sub to existing user %s", google_email)
        return user

    # Path C — new user via invite
    if invite_token:
        import json as _json
        link = get_valid_access_link(invite_token, "google_invite")
        if link:
            meta = _json.loads(link.metadata_json or "{}")
            invited_email = (meta.get("email") or "").strip().lower()
            if invited_email and invited_email != google_email:
                logger.warning(
                    "Google OAuth: invite email (%s) does not match Google email (%s)",
                    invited_email, google_email,
                )
                return None
            role = (meta.get("role") or "user").strip().lower()
            if role not in {"admin", "user"}:
                role = "user"
            name = (meta.get("name") or google_name or google_email).strip()
            new_user = User(
                name=name,
                email=google_email,
                role=role,
                is_active=True,
                google_sub=google_sub,
                google_email=google_email,
                avatar_emoji=pick_default_avatar(name),
            )
            session.add(new_user)
            link.used_at = datetime.now(timezone.utc)
            session.flush()
            logger.info("Google OAuth: new user created via invite for %s", google_email)
            return new_user

    # Path D — no match
    return None


# ---------------------------------------------------------------------------
# Google OAuth — invite management endpoints
# ---------------------------------------------------------------------------

@auth_bp.route("/invites", methods=["POST"])
def create_invite():
    """Admin: create a google_invite for a specific email address."""
    import json as _json
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    role = (data.get("role") or "user").strip().lower()
    expires_in_days = int(data.get("expires_in_days") or 7)

    if not email or not is_valid_login_email(email):
        return jsonify({"error": "A valid email address is required"}), 400
    if role not in {"admin", "user"}:
        return jsonify({"error": "Role must be 'admin' or 'user'"}), 400

    # Block invite if there is already an active user with this email
    # (case-insensitive to catch legacy rows stored with mixed casing).
    existing = g.db_session.query(User).filter(
        func.lower(User.email) == email.lower(), User.is_active.is_(True)
    ).first()
    if existing:
        return jsonify({"error": "An active user with this email already exists"}), 409

    # Expire any prior pending invite for the same email
    prior_links = (
        g.db_session.query(AccessLink)
        .filter(
            AccessLink.purpose == "google_invite",
            AccessLink.used_at.is_(None),
        )
        .all()
    )
    for prior in prior_links:
        try:
            meta = _json.loads(prior.metadata_json or "{}")
            if (meta.get("email") or "").strip().lower() == email:
                prior.used_at = datetime.now(timezone.utc)  # mark consumed
        except Exception:
            pass

    token, link = create_access_link(
        purpose="google_invite",
        created_by_id=actor.id,
        expires_in_minutes=expires_in_days * 24 * 60,
        metadata_json=_json.dumps({"email": email, "name": name, "role": role}),
    )
    g.db_session.commit()

    invite_url = f"{build_public_base_url()}/auth/invite/{token}"
    return jsonify({
        "invite_url": invite_url,
        "qr_image_url": f"{build_public_base_url()}/auth/qr-image?data={quote(invite_url, safe='')}",
        "email": email,
        "name": name,
        "role": role,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
    }), 201


@auth_bp.route("/invites", methods=["GET"])
def list_invites():
    """Admin: list pending (unused, unexpired) google invites."""
    import json as _json
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    now = datetime.now(timezone.utc)
    links = (
        g.db_session.query(AccessLink)
        .filter(
            AccessLink.purpose == "google_invite",
            AccessLink.used_at.is_(None),
        )
        .order_by(AccessLink.created_at.desc())
        .all()
    )

    result = []
    for link in links:
        expires_at = link.expires_at
        compare_now = now.replace(tzinfo=None) if expires_at and expires_at.tzinfo is None else now
        if expires_at and expires_at < compare_now:
            continue  # skip expired
        try:
            meta = _json.loads(link.metadata_json or "{}")
        except Exception:
            meta = {}
        result.append({
            "id": link.id,
            "email": meta.get("email"),
            "name": meta.get("name"),
            "role": meta.get("role", "user"),
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "created_at": link.created_at.isoformat() if link.created_at else None,
        })

    return jsonify({"invites": result, "count": len(result)}), 200


@auth_bp.route("/invites/<int:invite_id>", methods=["DELETE"])
def revoke_invite(invite_id: int):
    """Admin: revoke a pending invite."""
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    link = g.db_session.query(AccessLink).filter_by(id=invite_id, purpose="google_invite").first()
    if not link:
        return jsonify({"error": "Invite not found"}), 404

    link.used_at = datetime.now(timezone.utc)  # mark consumed = revoked
    g.db_session.commit()
    return jsonify({"status": "revoked"}), 200


@auth_bp.route("/invite/<token>", methods=["GET"])
def accept_invite_redirect(token: str):
    """Validate invite token and redirect to the SPA invite landing page."""
    link = get_valid_access_link(token, "google_invite")
    if not link:
        return redirect("/?invite_error=invalid")
    return redirect(f"/?invite={token}")


# ---------------------------------------------------------------------------
# Google OAuth — OAuth flow endpoints
# ---------------------------------------------------------------------------

@auth_bp.route("/oauth/google/status", methods=["GET"])
def google_oauth_status():
    """Return whether Google OAuth is configured on this server."""
    return jsonify({"enabled": _is_google_oauth_configured()}), 200


@auth_bp.route("/oauth/google", methods=["GET"])
def google_oauth_start():
    """Initiate Google OAuth flow. Accepts optional invite_token query param."""
    if not _is_google_oauth_configured():
        return jsonify({"error": "Google OAuth is not configured on this server"}), 503

    try:
        from authlib.integrations.requests_client import OAuth2Session
    except ImportError:
        return jsonify({"error": "authlib is not installed"}), 503

    invite_token = (request.args.get("invite_token") or "").strip() or None
    state = _build_oauth_state(invite_token)

    client = OAuth2Session(
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        redirect_uri=_get_oauth_redirect_uri(),
        scope="openid email profile",
    )
    authorization_url, _ = client.create_authorization_url(
        "https://accounts.google.com/o/oauth2/v2/auth",
        state=state,
        access_type="online",
        prompt="select_account",
    )
    return redirect(authorization_url)


@auth_bp.route("/oauth/google/callback", methods=["GET"])
def google_oauth_callback():
    """Handle Google's redirect after user grants consent."""
    if not _is_google_oauth_configured():
        return redirect("/?oauth_error=not_configured")

    try:
        from authlib.integrations.requests_client import OAuth2Session
    except ImportError:
        return redirect("/?oauth_error=library_missing")

    error = request.args.get("error")
    if error:
        logger.warning("Google OAuth returned an error: %s", error)
        return redirect(f"/?oauth_error={quote(error, safe='')}")

    state = request.args.get("state", "")
    valid, invite_token = _verify_oauth_state(state)
    if not valid:
        logger.warning("Google OAuth: invalid state parameter (possible CSRF)")
        return redirect("/?oauth_error=invalid_state")

    code = request.args.get("code", "")
    if not code:
        return redirect("/?oauth_error=no_code")

    # Exchange auth code for access token
    try:
        client = OAuth2Session(
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            redirect_uri=_get_oauth_redirect_uri(),
        )
        token_response = client.fetch_token(
            "https://oauth2.googleapis.com/token",
            code=code,
        )
        access_token = token_response.get("access_token")
        if not access_token:
            raise ValueError("No access_token in token response")
    except Exception as exc:
        logger.error("Google OAuth token exchange failed: %s", exc)
        return redirect("/?oauth_error=token_exchange_failed")

    # Fetch user info
    try:
        google_info = _fetch_google_user_info(access_token)
    except Exception as exc:
        logger.error("Google OAuth: failed to fetch user info: %s", exc)
        return redirect("/?oauth_error=userinfo_failed")

    # Check if this is a link-to-existing-account flow
    if invite_token and str(invite_token).startswith("link:"):
        try:
            target_user_id = int(str(invite_token).split(":", 1)[1])
        except (ValueError, IndexError):
            return redirect("/?oauth_error=invalid_link_state")

        db_session = g.db_session
        target_user = db_session.query(User).filter_by(id=target_user_id, is_active=True).first()
        if not target_user:
            return redirect("/?oauth_error=user_not_found")

        google_sub = str(google_info.get("sub") or "").strip()
        google_email_val = str(google_info.get("email") or "").strip().lower()

        # Ensure this google_sub isn't already claimed by another user
        existing_owner = db_session.query(User).filter(
            User.google_sub == google_sub,
        ).first()
        if existing_owner and existing_owner.id != target_user.id:
            return redirect("/?oauth_error=google_already_linked")

        target_user.google_sub = google_sub
        target_user.google_email = google_email_val
        db_session.commit()
        _set_browser_session(target_user)
        logger.info("Google OAuth: linked google account to user %s", target_user.email)
        return redirect("/?oauth_success=linked")

    # Resolve or create user (normal login / invite flow)
    db_session = g.db_session
    user = _find_or_create_oauth_user(db_session, google_info, invite_token)
    if not user:
        google_email = (google_info.get("email") or "").lower()
        logger.warning("Google OAuth: no matching user or invite for %s", google_email)
        return redirect("/?oauth_error=no_invite")

    db_session.commit()
    _set_browser_session(user)
    logger.info("Google OAuth: user %s signed in via Google", user.email)
    return redirect("/?oauth_success=1")


# ---------------------------------------------------------------------------
# Google Link / Unlink (for existing password users in Settings)
# ---------------------------------------------------------------------------

@auth_bp.route("/oauth/google/link", methods=["GET"])
def google_oauth_link_start():
    """Start OAuth flow to link Google to an already-authenticated account."""
    if not _is_google_oauth_configured():
        return jsonify({"error": "Google OAuth is not configured on this server"}), 503

    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401

    try:
        from authlib.integrations.requests_client import OAuth2Session
    except ImportError:
        return jsonify({"error": "authlib is not installed"}), 503

    # Encode user id into state so we know who to link after callback
    state = _build_oauth_state(f"link:{user.id}")
    client = OAuth2Session(
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        redirect_uri=_get_oauth_redirect_uri(),
        scope="openid email profile",
    )
    authorization_url, _ = client.create_authorization_url(
        "https://accounts.google.com/o/oauth2/v2/auth",
        state=state,
        access_type="online",
        prompt="select_account",
    )
    return redirect(authorization_url)


@auth_bp.route("/oauth/google/unlink", methods=["POST"])
def google_oauth_unlink():
    """Remove the Google link from the current user's account."""
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    if not getattr(user, "google_sub", None):
        return jsonify({"error": "No Google account is linked"}), 400
    if not user.password_hash:
        return jsonify({"error": "Set a password before unlinking Google to avoid being locked out"}), 400

    user.google_sub = None
    user.google_email = None
    g.db_session.commit()
    return jsonify({"status": "unlinked", "user": serialize_user(user)}), 200
