"""
Step 3: Setup Flask Backend API
================================
PROMPT Reference: Phase 1, Step 3

Initializes the Flask application with blueprint structure, authentication
middleware (Bearer token), error handling, logging, and CORS configuration.

Port: 8090 by default for the Extended runtime
"""

import os
import logging
import secrets
from datetime import timedelta
from functools import wraps

# Auto-load .env file (works locally; in Docker env vars come from docker-compose)
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # Don't override vars already set in environment
except ImportError:
    pass  # python-dotenv not installed — use system env vars

from flask import Flask, jsonify, g, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from src.backend.initialize_database_schema import (
    create_db_engine, create_session_factory, initialize_database, User
)

logger = logging.getLogger(__name__)

# Module-level engine and session factory (initialized once)
_engine = None
_SessionFactory = None

_PLACEHOLDER_CONFIG_VALUES = {
    "",
    "replace-me-in-production",
    "replace_with_a_long_random_token",
    "replace_with_another_long_random_secret",
    "replace_with_a_strong_password",
}


def _is_placeholder_config_value(value: str | None) -> bool:
    """Return True when a config value is missing or still a shipped placeholder."""
    return (value or "").strip() in _PLACEHOLDER_CONFIG_VALUES


def _resolve_secret_key() -> str:
    """Return a production-safe secret key, falling back to a random process-local value."""
    session_secret = (os.getenv("SESSION_SECRET") or "").strip()
    admin_token = (os.getenv("INITIAL_ADMIN_TOKEN") or "").strip()

    if not _is_placeholder_config_value(session_secret):
        return session_secret
    if not _is_placeholder_config_value(admin_token):
        logger.warning("SESSION_SECRET missing; falling back to INITIAL_ADMIN_TOKEN for session signing.")
        return admin_token

    generated = secrets.token_urlsafe(64)
    logger.critical(
        "SESSION_SECRET and INITIAL_ADMIN_TOKEN are missing or placeholder values. "
        "Using a generated process-local secret; rotate deployment secrets immediately."
    )
    return generated


def _get_db():
    """Get or create the database engine and session factory."""
    global _engine, _SessionFactory
    if _engine is None:
        _engine, _SessionFactory = initialize_database()
    return _engine, _SessionFactory


def _require_authenticated_user():
    from src.backend.manage_authentication import get_authenticated_user

    user = getattr(g, "current_user", None) or get_authenticated_user()
    if not user:
        return None, (jsonify({"error": "Authentication required"}), 401)
    g.current_user = user
    return user, None


def require_auth(f):
    """Decorator to require session or bearer-token authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        _user, error = _require_authenticated_user()
        if error:
            return error
        return f(*args, **kwargs)
    return decorated


def require_write_access(f):
    """Decorator to block writes from trusted devices in read-only mode."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from src.backend.manage_authentication import is_read_only_device_request

        user, error = _require_authenticated_user()
        if error:
            return error
        if is_read_only_device_request():
            return jsonify({
                "error": "This trusted device is in read-only mode",
                "scope": "read_only",
            }), 403
        # Service accounts are read-only unless explicitly granted
        # allow_write. Rejects external apps (e.g. smart mirror
        # display) from mutating household data without opt-in.
        if user and getattr(user, "role", None) == "service" and not bool(getattr(user, "allow_write", False)):
            return jsonify({
                "error": "This service account is read-only",
                "scope": "service_read_only",
            }), 403
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------

def register_error_handlers(app):
    """Register standard error handlers for the Flask app."""

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad request", "message": str(e)}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"error": "Unauthorized"}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"error": "Forbidden"}), 403

    @app.errorhandler(404)
    def not_found(e):
        # Serve the frontend for the root path; return JSON for API paths
        return jsonify({"error": "Not found"}), 404

    @app.route("/")
    @app.route("/dashboard")
    @app.route("/shopping-helper/<token>")
    def serve_frontend(token=None):
        """Serve the web dashboard."""
        import os
        frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
        return send_from_directory(frontend_dir, "index.html")

    @app.route("/styles/<path:filename>")
    def serve_frontend_styles(filename):
        """Serve stylesheets from src/frontend/styles/."""
        import os
        styles_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "frontend", "styles"
        )
        return send_from_directory(styles_dir, filename)

    @app.route("/assets/<path:filename>")
    def serve_frontend_assets(filename):
        """Serve extracted JS/CSS modules from src/frontend/assets/."""
        import os
        assets_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "frontend", "assets"
        )
        return send_from_directory(assets_dir, filename)

    @app.route("/design/")
    @app.route("/design/<path:filename>")
    def serve_design_system(filename="preview/ui-kit-localocr.html"):
        """Serve the LocalOCR design system bundle (tokens, preview cards,
        UI kit, and marketing variants). Public — no auth required."""
        import os
        design_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "design"
        )
        return send_from_directory(design_dir, filename)

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Blueprint Registration
# ---------------------------------------------------------------------------

def register_blueprints(app):
    """Register all API blueprints."""
    from src.backend.manage_authentication import auth_bp
    from src.backend.handle_telegram_messages import telegram_bp
    from src.backend.manage_product_catalog import products_bp
    from src.backend.manage_inventory import inventory_bp
    from src.backend.handle_receipt_upload import receipts_bp
    from src.backend.calculate_spending_analytics import analytics_bp
    from src.backend.manage_household_budget import budget_bp
    from src.backend.generate_recommendations import recommendations_bp
    from src.backend.manage_shopping_list import shopping_list_bp
    from src.backend.manage_contributions import contributions_bp
    from src.backend.manage_environment_ops import environment_ops_bp
    from src.backend.manage_product_snapshots import product_snapshots_bp
    from src.backend.manage_cash_transactions import cash_transactions_bp, bill_edit_bp
    from src.backend.manage_ai_models import ai_models_bp, admin_ai_models_bp
    from src.backend.plaid_integration import plaid_bp
    from src.backend.chat_endpoints import chat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(telegram_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(receipts_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(budget_bp)
    app.register_blueprint(recommendations_bp)
    app.register_blueprint(shopping_list_bp)
    app.register_blueprint(contributions_bp)
    app.register_blueprint(environment_ops_bp)
    app.register_blueprint(product_snapshots_bp)
    app.register_blueprint(cash_transactions_bp)
    app.register_blueprint(bill_edit_bp)
    app.register_blueprint(ai_models_bp)
    app.register_blueprint(admin_ai_models_bp)
    app.register_blueprint(plaid_bp)
    app.register_blueprint(chat_bp)

    logger.info("All blueprints registered.")


# ---------------------------------------------------------------------------
# Database Session Lifecycle
# ---------------------------------------------------------------------------

def setup_db_session_lifecycle(app):
    """Open a DB session before each request, close after."""

    @app.before_request
    def open_session():
        _, SessionFactory = _get_db()
        g.db_session = SessionFactory()

    @app.teardown_request
    def close_session(exception=None):
        session = g.pop("db_session", None)
        if session is not None:
            if exception:
                session.rollback()
            session.close()


# ---------------------------------------------------------------------------
# First-Run Admin Setup
# ---------------------------------------------------------------------------

def ensure_admin_user():
    """Create or backfill the initial admin user from env bootstrap values."""
    from src.backend.manage_authentication import (
        get_bootstrap_admin_defaults,
        hash_password,
        hash_token,
    )
    _, SessionFactory = _get_db()
    session = SessionFactory()
    try:
        admin_name, admin_email, bootstrap_password = get_bootstrap_admin_defaults()
        admin_token = (os.getenv("INITIAL_ADMIN_TOKEN") or "").strip()
        if _is_placeholder_config_value(admin_token):
            admin_token = ""
        user_count = session.query(User).count()
        if user_count == 0:
            if bootstrap_password or admin_token:
                admin = User(
                    name=admin_name,
                    email=admin_email,
                    role="admin",
                    is_active=True,
                    password_hash=hash_password(bootstrap_password) if bootstrap_password else None,
                    api_token_hash=hash_token(admin_token) if admin_token else None,
                )
                session.add(admin)
                session.commit()
                logger.info("Initial admin user created from bootstrap credentials.")
            else:
                logger.warning(
                    "No users in database and no bootstrap auth credentials are set. "
                    "API authentication will reject all requests."
                )
        else:
            admin = (
                session.query(User)
                .filter(User.role == "admin")
                .order_by(User.id.asc())
                .first()
            )
            if admin:
                changed = False
                if not admin.email:
                    admin.email = admin_email
                    changed = True
                if not admin.name:
                    admin.name = admin_name
                    changed = True
                if admin.is_active is None:
                    admin.is_active = True
                    changed = True
                if not admin.password_hash and bootstrap_password:
                    admin.password_hash = hash_password(bootstrap_password)
                    changed = True
                if not admin.api_token_hash and admin_token:
                    admin.api_token_hash = hash_token(admin_token)
                    changed = True
                if changed:
                    session.commit()
                    logger.info("Bootstrap admin user updated with local login credentials.")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Honour X-Forwarded-For / X-Forwarded-Proto from our trusted reverse proxy
    # (Nginx Proxy Manager). Without this, request.remote_addr is always the
    # proxy's IP, which breaks per-user IP allowlists for service-account
    # bearer auth. Set PROXY_FIX_X_FOR=0 to disable if the app is ever exposed
    # directly to untrusted clients.
    _proxy_for = int(os.getenv("PROXY_FIX_X_FOR", "1"))
    if _proxy_for > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=_proxy_for,
            x_proto=int(os.getenv("PROXY_FIX_X_PROTO", "1")),
            x_host=int(os.getenv("PROXY_FIX_X_HOST", "0")),
            x_port=int(os.getenv("PROXY_FIX_X_PORT", "0")),
            x_prefix=int(os.getenv("PROXY_FIX_X_PREFIX", "0")),
        )

    # Configuration
    app.config["FLASK_ENV"] = os.getenv("FLASK_ENV", "development")
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL", "sqlite:////data/db/localocr_extended.db")
    app.config["SECRET_KEY"] = _resolve_secret_key()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=14)

    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Initialize database
    _get_db()

    # Create initial admin user if needed
    ensure_admin_user()

    # Error handlers
    register_error_handlers(app)

    # Database session lifecycle (per-request)
    setup_db_session_lifecycle(app)

    # Blueprints
    register_blueprints(app)

    # Health check endpoint (used by Docker healthcheck)
    @app.route("/health")
    def health():
        return jsonify({
            "status": "healthy",
            "service": os.getenv("APP_SERVICE_NAME", "localocr-extended-backend"),
        }), 200

    should_start_background_services = (
        os.getenv("FLASK_DEBUG", "0") != "1"
        or os.getenv("WERKZEUG_RUN_MAIN") == "true"
    )

    if should_start_background_services:
        # Initialize MQTT connection
        try:
            from src.backend.setup_mqtt_connection import setup_mqtt_connection
            setup_mqtt_connection()
        except Exception as e:
            logger.warning(f"MQTT connection failed (will retry): {e}")

        # Start schedulers
        try:
            from src.backend.schedule_daily_recommendations import start_recommendation_scheduler
            start_recommendation_scheduler()
        except Exception as e:
            logger.warning(f"Recommendation scheduler failed to start: {e}")
    else:
        logger.info("Skipping MQTT and schedulers in the Flask reloader parent process.")

    logger.info("Flask application created successfully.")
    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("FLASK_PORT", 8090))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
