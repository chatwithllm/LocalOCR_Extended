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
from flask import Blueprint, jsonify, request, g, session, redirect, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

from src.backend.contribution_scores import sum_bonus_points, sum_floating_points
from src.backend.initialize_database_schema import AccessLink, Product, Purchase, User

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
