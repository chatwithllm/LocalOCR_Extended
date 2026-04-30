"""Flask blueprint for the Manage Stores Settings panel.

Exposes:
  GET  /api/stores                          — bucketed list with usage stats.
  POST /api/stores/<int:store_id>/visibility — set or clear the override.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import Store
from src.backend.manage_stores import get_store_buckets

stores_bp = Blueprint("stores", __name__, url_prefix="/api/stores")

_VALID_OVERRIDES = {"frequent", "low_freq", "hidden", None}


@stores_bp.route("", methods=["GET"])
@require_auth
def list_stores():
    buckets = get_store_buckets(g.db_session)
    return jsonify(buckets)


@stores_bp.route("/<int:store_id>/visibility", methods=["POST"])
@require_write_access
def set_visibility(store_id: int):
    payload = request.get_json(silent=True) or {}
    override = payload.get("override")
    if override not in _VALID_OVERRIDES:
        return jsonify({"error": "invalid override"}), 400

    store = g.db_session.query(Store).filter(Store.id == store_id).first()
    if not store:
        return jsonify({"error": "store not found"}), 404

    store.visibility_override = override
    g.db_session.commit()
    return jsonify({
        "id": store.id,
        "name": store.name,
        "override": store.visibility_override,
    })
