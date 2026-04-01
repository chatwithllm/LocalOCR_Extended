"""
Session-based browser authentication endpoints.

Phase 1 adds local login with secure password hashing and Flask sessions,
while keeping bearer-token auth available for integrations and automation.
"""

import os
import hashlib
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g, session
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

from src.backend.initialize_database_schema import User

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def hash_token(token: str) -> str:
    """Hash an API token for secure storage/comparison."""
    return hashlib.sha256(token.encode()).hexdigest()


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


def active_admin_count() -> int:
    """Return the number of active admins."""
    return (
        g.db_session.query(User)
        .filter(User.role == "admin", User.is_active.is_(True))
        .count()
    )


def is_valid_login_email(email: str) -> bool:
    """Allow practical local-login emails like admin@localhost."""
    if not email or "@" not in email:
        return False
    local_part, domain = email.split("@", 1)
    return bool(local_part.strip() and domain.strip())


def get_bootstrap_admin_defaults() -> tuple[str, str, str]:
    """Return bootstrap admin display defaults from env."""
    return (
        os.getenv("INITIAL_ADMIN_NAME", "Admin"),
        os.getenv("INITIAL_ADMIN_EMAIL", "admin@localhost"),
        os.getenv("INITIAL_ADMIN_PASSWORD", "") or os.getenv("INITIAL_ADMIN_TOKEN", ""),
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
    }), 200


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
        }
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
        "user": serialize_user(user)
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
        password_hash=hash_password(password),
    )
    g.db_session.add(created)
    g.db_session.commit()

    logger.info("User %s created by admin %s", created.email, user.email or user.id)
    return jsonify({"user": serialize_user(created)}), 201


@auth_bp.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id: int):
    """Update an existing household user. Admin only."""
    actor = get_authenticated_user()
    if not actor:
        return jsonify({"error": "Authentication required"}), 401
    if not is_admin(actor):
        return jsonify({"error": "Admin access required"}), 403

    target = g.db_session.query(User).filter_by(id=user_id).first()
    if not target:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or target.name).strip()
    email = (data.get("email") or target.email or "").strip().lower()
    role = (data.get("role") or target.role).strip().lower()
    password = data.get("password")
    is_active = bool(data.get("is_active", target.is_active))

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
    if password:
        target.password_hash = hash_password(password)
        target.password_reset_requested_at = None

    g.db_session.commit()
    logger.info("User %s updated by admin %s", target.email, actor.email or actor.id)
    return jsonify({"user": serialize_user(target)}), 200
