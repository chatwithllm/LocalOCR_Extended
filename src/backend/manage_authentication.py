"""
Session-based browser authentication endpoints.

Phase 1 adds local login with secure password hashing and Flask sessions,
while keeping bearer-token auth available for integrations and automation.
"""

import os
import hashlib
import logging
import secrets
from io import BytesIO
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import qrcode
from flask import Blueprint, jsonify, request, g, session, redirect, send_file, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

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
    return {
        "app_name": os.getenv("APP_DISPLAY_NAME", "LocalOCR Extended"),
        "app_slug": os.getenv("APP_SLUG", "localocr_extended"),
        "service_name": os.getenv("APP_SERVICE_NAME", "localocr-extended-backend"),
        "modules": modules,
        "module_view_mode": "separate",
        "ports": {
            "default_backend": int(os.getenv("FLASK_PORT", "8090")),
        },
    }


def hash_token(token: str) -> str:
    """Hash an API token for secure storage/comparison."""
    return hashlib.sha256(token.encode()).hexdigest()


def build_public_base_url() -> str:
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


def get_authenticated_user():
    """Resolve current user from session or bearer token."""
    trusted_device_token = (request.headers.get("X-Trusted-Device-Token") or "").strip()
    if trusted_device_token:
        token_hash = hash_token(trusted_device_token)
        device = g.db_session.query(TrustedDevice).filter_by(token_hash=token_hash).first()
        if device and device.status == "active":
            user = g.db_session.query(User).filter_by(id=device.linked_user_id).first()
            if user and user.is_active:
                device.last_seen_at = datetime.now(timezone.utc)
                return user

    trusted_device_id = session.get("trusted_device_id")
    if trusted_device_id:
        device = g.db_session.query(TrustedDevice).filter_by(id=trusted_device_id).first()
        if device and device.status == "active":
            user = g.db_session.query(User).filter_by(id=device.linked_user_id).first()
            if user and user.is_active:
                session["user_id"] = user.id
                device.last_seen_at = datetime.now(timezone.utc)
                return user
        session.pop("trusted_device_id", None)
        session.pop("user_id", None)

    session_user_id = session.get("user_id")
    if session_user_id:
        user = g.db_session.query(User).filter_by(id=session_user_id).first()
        if user and user.is_active:
            return user
        session.pop("user_id", None)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split("Bearer ", 1)[1]
        token_hash = hash_token(token)
        user = g.db_session.query(User).filter_by(api_token_hash=token_hash).first()
        if user and user.is_active:
            return user
        return None

    return None


def is_admin(user: User | None) -> bool:
    """Return True when the given user has admin privileges."""
    return bool(user and user.role == "admin")


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
        "password_reset_requested": bool(user.password_reset_requested_at),
        "password_reset_requested_at": (
            user.password_reset_requested_at.isoformat() if user.password_reset_requested_at else None
        ),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
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

    user = (
        g.db_session.query(User)
        .filter(
            User.is_active.is_(True),
            or_(User.email == identifier, User.name == identifier),
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

    user = (
        g.db_session.query(User)
        .filter(or_(User.email == identifier, User.name == identifier))
        .first()
    )
    if not user or not verify_password(user, password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user.id
    session.permanent = True

    return jsonify({
        "user": {
            **serialize_user(user),
        },
        "stats": serialize_user_stats(user),
        "leaderboard": serialize_household_leaderboard(user.id),
        "app_config": build_app_config(),
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """End the browser session."""
    session.pop("user_id", None)
    return jsonify({"status": "logged_out"}), 200


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """Record a reset request for an existing local user without exposing account existence."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email or not is_valid_login_email(email):
        return jsonify({"message": "If that account exists, the admin can now see the reset request."}), 200

    user = g.db_session.query(User).filter_by(email=email).first()
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
        session["user_id"] = user.id

    return jsonify({
        "authenticated": True,
        "user": serialize_user(user),
        "stats": serialize_user_stats(user),
        "leaderboard": serialize_household_leaderboard(user.id),
        "app_config": build_app_config(),
    }), 200


@auth_bp.route("/qr-login-link", methods=["POST"])
def qr_login_link():
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401

    token, link = create_access_link(
        purpose="login_qr",
        created_by_id=user.id,
        target_user_id=user.id,
        expires_in_minutes=10,
    )
    g.db_session.commit()
    url = f"{build_public_base_url()}/auth/qr-login/{token}"
    return jsonify({
        "url": url,
        "qr_image_url": f"{build_public_base_url()}/auth/qr-image?data={quote(url, safe='')}",
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

    session["user_id"] = user.id
    session.permanent = True
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
    pairing_url = f"{build_public_base_url()}/auth/pair-device/{quote(pairing_token, safe='')}"
    return jsonify({
        "pairing_token": pairing_token,
        "pairing_url": pairing_url,
        "qr_image_url": f"{build_public_base_url()}/auth/qr-image?data={quote(pairing_url, safe='')}",
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
        session["user_id"] = device.linked_user_id
        session["trusted_device_id"] = device.id
        session.permanent = True
        g.db_session.commit()

        user = g.db_session.query(User).filter_by(id=device.linked_user_id).first()
        return jsonify({
            "status": "approved",
            "authenticated": True,
            "user": serialize_user(user) if user else None,
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
    session["user_id"] = device.linked_user_id
    session["trusted_device_id"] = device.id
    session.permanent = True
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

    trusted_device = matching_devices[0] if matching_devices else None
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

    for duplicate in matching_devices[1:]:
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
    revoked_at = datetime.now(timezone.utc)
    for matching_device in matching_devices:
        matching_device.status = "revoked"
        matching_device.revoked_at = revoked_at
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
        .filter(or_(User.email == email, User.name == name))
        .first()
    )
    if existing:
        return jsonify({"error": "A user with that name or email already exists"}), 409

    created = User(
        name=name,
        email=email,
        role=role,
        is_active=True,
        avatar_emoji=(data.get("avatar_emoji") or "").strip() or pick_default_avatar(name or email),
        password_hash=hash_password(password),
    )
    g.db_session.add(created)
    g.db_session.commit()

    logger.info("User %s created by admin %s", created.email, user.email or user.id)
    return jsonify({"user": serialize_user(created)}), 201


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
            or_(User.email == email, User.name == name),
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

    g.db_session.commit()
    logger.info("User %s updated by admin %s", target.email, actor.email or actor.id)
    return jsonify({"user": serialize_user(target)}), 200
