"""Flask blueprint serving the /features documentation page."""
from __future__ import annotations

import os

from flask import Blueprint, send_from_directory

from src.backend.create_flask_application import require_auth

features_bp = Blueprint("features", __name__)

_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


@features_bp.route("/features")
def features_page():
    return send_from_directory(_frontend_dir, "features.html")


@features_bp.route("/features/data")
@require_auth
def features_data():
    return send_from_directory(_frontend_dir, "features-data.js", mimetype="application/javascript")
