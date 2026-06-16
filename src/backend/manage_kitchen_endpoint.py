"""Flask blueprint for the Kitchen essentials read endpoint.

Exposes:
  GET /api/kitchen/essentials — user-curated essentials grid (+ suggestions
  when the user has tagged nothing yet).

All mutations reuse existing /inventory and /shopping-list routes; this
blueprint is read-only by design.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from src.backend.create_flask_application import require_auth
from src.backend.manage_kitchen import get_kitchen_essentials


kitchen_bp = Blueprint("kitchen", __name__, url_prefix="/api/kitchen")


@kitchen_bp.route("/essentials", methods=["GET"])
@require_auth
def get_essentials():
    return jsonify(get_kitchen_essentials(g.db_session)), 200
