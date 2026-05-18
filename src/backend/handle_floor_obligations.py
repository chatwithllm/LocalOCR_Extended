"""CRUD and summary endpoints for FloorObligation (monthly floor tracking)."""
from __future__ import annotations
import logging
from flask import Blueprint, g, jsonify, request
from src.backend.create_flask_application import require_auth, require_write_access

logger = logging.getLogger(__name__)

floor_obligations_bp = Blueprint(
    "floor_obligations", __name__, url_prefix="/floor-obligations"
)


def _serialize(ob) -> dict:
    return {
        "id": ob.id,
        "label": ob.label,
        "expected_monthly_amount": ob.expected_monthly_amount,
        "is_active": ob.is_active,
        "bill_provider_id": ob.bill_provider_id,
        "source": "bill_provider" if ob.bill_provider_id else "manual",
        "created_at": ob.created_at.isoformat() if ob.created_at else None,
        "updated_at": ob.updated_at.isoformat() if ob.updated_at else None,
    }


@floor_obligations_bp.route("/", methods=["GET"])
@require_auth
def list_obligations():
    from src.backend.initialize_database_schema import FloorObligation
    rows = (
        g.db_session.query(FloorObligation)
        .order_by(FloorObligation.is_active.desc(), FloorObligation.label)
        .all()
    )
    return jsonify({"obligations": [_serialize(r) for r in rows]}), 200


@floor_obligations_bp.route("/", methods=["POST"])
@require_write_access
def create_obligation():
    from src.backend.initialize_database_schema import FloorObligation
    payload = request.get_json(silent=True) or {}
    label = (payload.get("label") or "").strip()
    if not label:
        return jsonify({"error": "label is required"}), 400
    try:
        amount = float(payload.get("expected_monthly_amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "expected_monthly_amount must be a number"}), 400
    if amount < 0:
        return jsonify({"error": "expected_monthly_amount must be >= 0"}), 400
    bill_provider_id = payload.get("bill_provider_id")
    if bill_provider_id is not None:
        try:
            bill_provider_id = int(bill_provider_id)
        except (TypeError, ValueError):
            return jsonify({"error": "bill_provider_id must be an integer"}), 400
        from src.backend.initialize_database_schema import BillProvider
        if not g.db_session.get(BillProvider, bill_provider_id):
            return jsonify({"error": "bill_provider not found"}), 400
    ob = FloorObligation(
        label=label,
        expected_monthly_amount=amount,
        is_active=True,
        bill_provider_id=bill_provider_id,
    )
    g.db_session.add(ob)
    g.db_session.commit()
    return jsonify({"obligation": _serialize(ob)}), 201


@floor_obligations_bp.route("/<int:ob_id>", methods=["PATCH"])
@require_write_access
def update_obligation(ob_id: int):
    from src.backend.initialize_database_schema import FloorObligation
    ob = g.db_session.query(FloorObligation).filter_by(id=ob_id).first()
    if not ob:
        return jsonify({"error": "Not found"}), 404
    payload = request.get_json(silent=True) or {}
    if "is_active" in payload:
        ob.is_active = bool(payload["is_active"])
    if "expected_monthly_amount" in payload:
        try:
            new_amount = float(payload["expected_monthly_amount"])
        except (TypeError, ValueError):
            return jsonify({"error": "expected_monthly_amount must be a number"}), 400
        if new_amount < 0:
            return jsonify({"error": "expected_monthly_amount must be >= 0"}), 400
        ob.expected_monthly_amount = new_amount
    if "label" in payload:
        label = (payload["label"] or "").strip()
        if not label:
            return jsonify({"error": "label cannot be empty"}), 400
        ob.label = label
    g.db_session.commit()
    return jsonify({"obligation": _serialize(ob)}), 200


@floor_obligations_bp.route("/<int:ob_id>", methods=["DELETE"])
@require_write_access
def delete_obligation(ob_id: int):
    from src.backend.initialize_database_schema import FloorObligation
    ob = g.db_session.query(FloorObligation).filter_by(id=ob_id).first()
    if not ob:
        return jsonify({"error": "Not found"}), 404
    if ob.bill_provider_id is not None:
        return jsonify({"error": "Bill-linked obligations cannot be deleted — toggle is_active instead"}), 400
    g.db_session.delete(ob)
    g.db_session.commit()
    return jsonify({"deleted": ob_id}), 200
