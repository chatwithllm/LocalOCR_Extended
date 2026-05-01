"""Flask blueprint for the Kitchen View read endpoint.

Exposes:
  GET /api/kitchen/catalog — bucketed in-stock catalog plus skipped items.

All mutations reuse existing /shopping-list and /inventory routes; this
blueprint is read-only by design.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from src.backend.create_flask_application import require_auth
from src.backend.manage_kitchen import get_kitchen_catalog


kitchen_bp = Blueprint("kitchen", __name__, url_prefix="/api/kitchen")


@kitchen_bp.route("/catalog", methods=["GET"])
@require_auth
def get_catalog():
    return jsonify(get_kitchen_catalog(g.db_session)), 200
