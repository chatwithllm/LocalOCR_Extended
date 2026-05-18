"""CRUD and summary endpoints for FloorObligation (monthly floor tracking)."""
from __future__ import annotations
import logging
from flask import Blueprint, g, jsonify, request
from src.backend.create_flask_application import require_auth, require_write_access

logger = logging.getLogger(__name__)

floor_obligations_bp = Blueprint(
    "floor_obligations", __name__, url_prefix="/floor-obligations"
)


def _serialize(ob, avg_6mo=None, latest_actual=None) -> dict:
    return {
        "id": ob.id,
        "label": ob.label,
        "expected_monthly_amount": ob.expected_monthly_amount,
        "is_active": ob.is_active,
        "bill_provider_id": ob.bill_provider_id,
        "source": "bill_provider" if ob.bill_provider_id else "manual",
        "created_at": ob.created_at.isoformat() if ob.created_at else None,
        "updated_at": ob.updated_at.isoformat() if ob.updated_at else None,
        "avg_6mo": avg_6mo,
        "latest_actual": latest_actual,
    }


def _compute_history(session, provider_id):
    """Return (avg_6mo, latest_actual) from last 6 complete calendar months (naïve datetimes)."""
    from datetime import datetime, timezone
    from src.backend.initialize_database_schema import BillMeta, Purchase
    now = datetime.now(timezone.utc)
    window_end = datetime(now.year, now.month, 1)  # first of this month (exclusive)
    if now.month <= 6:
        window_start = datetime(now.year - 1, now.month + 6, 1)
    else:
        window_start = datetime(now.year, now.month - 6, 1)

    rows = (
        session.query(Purchase)
        .join(BillMeta, BillMeta.purchase_id == Purchase.id)
        .filter(
            BillMeta.provider_id == provider_id,
            Purchase.date >= window_start,
            Purchase.date < window_end,
        )
        .all()
    )
    if not rows:
        return None, None

    by_month: dict = {}
    for p in rows:
        key = (p.date.year, p.date.month)
        by_month[key] = by_month.get(key, 0.0) + float(p.total_amount or 0)

    monthly_totals = list(by_month.values())
    avg_6mo = round(sum(monthly_totals) / len(monthly_totals), 2)
    latest_key = max(by_month.keys())
    latest_actual = round(by_month[latest_key], 2)
    return avg_6mo, latest_actual


def _summary_row(ob, this_actual, last_actual, delta, status) -> dict:
    return {
        "id": ob.id,
        "label": ob.label,
        "expected_monthly_amount": ob.expected_monthly_amount,
        "is_active": ob.is_active,
        "source": "bill_provider" if ob.bill_provider_id else "manual",
        "this_month_actual": this_actual,
        "last_month_actual": last_actual,
        "delta": delta,
        "status": status,
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
    result = []
    for r in rows:
        if r.bill_provider_id is not None:
            avg_6mo, latest_actual = _compute_history(g.db_session, r.bill_provider_id)
        else:
            avg_6mo, latest_actual = None, None
        result.append(_serialize(r, avg_6mo=avg_6mo, latest_actual=latest_actual))
    return jsonify({"obligations": result}), 200


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


@floor_obligations_bp.route("/summary", methods=["GET"])
@require_auth
def obligations_summary():
    """Monthly floor summary with this-month and last-month actuals."""
    import re
    from datetime import datetime, timezone
    from src.backend.initialize_database_schema import FloorObligation, BillMeta, Purchase

    month_str = (request.args.get("month") or "").strip()
    if not month_str:
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")
    if not re.match(r"^\d{4}-\d{2}$", month_str):
        return jsonify({"error": "month must be YYYY-MM"}), 400

    year, mon = int(month_str[:4]), int(month_str[5:7])
    if not (1 <= mon <= 12) or year < 2 or year > 9998:
        return jsonify({"error": "month must be a valid calendar month"}), 400
    this_start = datetime(year, mon, 1)
    this_end = datetime(year + 1, 1, 1) if mon == 12 else datetime(year, mon + 1, 1)
    prev_end = this_start
    prev_start = datetime(year - 1, 12, 1) if mon == 1 else datetime(year, mon - 1, 1)

    session = g.db_session
    obligations = (
        session.query(FloorObligation)
        .filter_by(is_active=True)
        .order_by(FloorObligation.label)
        .all()
    )

    def _month_actual(provider_id, start, end):
        rows = (
            session.query(Purchase)
            .join(BillMeta, BillMeta.purchase_id == Purchase.id)
            .filter(BillMeta.provider_id == provider_id, Purchase.date >= start, Purchase.date < end)
            .all()
        )
        if not rows:
            return None
        return round(sum(float(p.total_amount or 0) for p in rows), 2)

    result = []
    floor_total = 0.0
    for ob in obligations:
        floor_total += ob.expected_monthly_amount or 0.0
        if ob.bill_provider_id is None:
            result.append(_summary_row(ob, None, None, None, "manual"))
            continue
        this_actual = _month_actual(ob.bill_provider_id, this_start, this_end)
        last_actual = _month_actual(ob.bill_provider_id, prev_start, prev_end)
        delta = round(this_actual - last_actual, 2) if this_actual is not None and last_actual is not None else None
        if this_actual is None:
            status = "not_recorded"
        elif this_actual <= (ob.expected_monthly_amount or 0):
            status = "paid"
        else:
            status = "paid_over"
        result.append(_summary_row(ob, this_actual, last_actual, delta, status))

    return jsonify({"month": month_str, "floor_total": round(floor_total, 2), "obligations": result}), 200
