"""
Step 19: Implement Budget Management
======================================
PROMPT Reference: Phase 6, Step 19

Budget setting and tracking endpoints. Alerts at 80% threshold via MQTT.

MQTT Topic: home/grocery/alerts/budget
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g

from src.backend.create_flask_application import require_auth
from src.backend.initialize_database_schema import Budget, Purchase
from src.backend.manage_authentication import is_admin

logger = logging.getLogger(__name__)

budget_bp = Blueprint("budget", __name__, url_prefix="/budget")


@budget_bp.route("/set-monthly", methods=["POST"])
@require_auth
def set_monthly_budget():
    """Set the monthly grocery budget.

    Body: { "month": "2026-04", "budget_amount": 600.00 }
    """
    session = g.db_session
    data = request.get_json(silent=True)
    current_user = getattr(g, "current_user", None)

    if not is_admin(current_user):
        return jsonify({"error": "Only admins can update budgets"}), 403

    if not data or not data.get("budget_amount"):
        return jsonify({"error": "budget_amount is required"}), 400

    month = data.get("month", datetime.now().strftime("%Y-%m"))
    domain = (data.get("domain") or "grocery").strip().lower()
    budget_amount = float(data["budget_amount"])

    user_id = current_user.id if current_user else None

    # Upsert budget
    existing = session.query(Budget).filter_by(user_id=user_id, month=month, domain=domain).first()
    if existing:
        existing.budget_amount = budget_amount
    else:
        budget = Budget(
            user_id=user_id,
            month=month,
            domain=domain,
            budget_amount=budget_amount,
        )
        session.add(budget)

    session.commit()

    return jsonify({
        "month": month,
        "domain": domain,
        "budget_amount": budget_amount,
        "message": f"{domain.title()} budget set to ${budget_amount:.2f} for {month}",
    }), 200


@budget_bp.route("/status", methods=["GET"])
@require_auth
def get_budget_status():
    """Get current month's budget vs actual spending."""
    session = g.db_session
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    domain = (request.args.get("domain") or "grocery").strip().lower()

    user_id = getattr(g, "current_user", None)
    user_id = user_id.id if user_id else None

    # Get budget
    budget = session.query(Budget).filter_by(user_id=user_id, month=month, domain=domain).first()
    if not budget:
        # Try household-wide budget (user_id=None)
        budget = session.query(Budget).filter_by(user_id=None, month=month, domain=domain).first()

    budget_amount = budget.budget_amount if budget else 0

    # Calculate actual spending for the month
    year, month_num = month.split("-")
    start_date = datetime(int(year), int(month_num), 1)
    if int(month_num) == 12:
        end_date = datetime(int(year) + 1, 1, 1)
    else:
        end_date = datetime(int(year), int(month_num) + 1, 1)

    purchases = session.query(Purchase).filter(
        Purchase.date >= start_date,
        Purchase.date < end_date,
        Purchase.domain == domain,
    ).all()

    spent = sum(p.total_amount or 0 for p in purchases)
    remaining = budget_amount - spent
    percentage = (spent / budget_amount * 100) if budget_amount > 0 else 0

    # Trigger alert at 80%
    alert_triggered = False
    if percentage >= 80 and budget_amount > 0:
        alert_triggered = True
        try:
            from src.backend.publish_mqtt_events import publish_budget_alert
            publish_budget_alert(budget_amount, spent, percentage)
        except Exception as e:
            logger.warning(f"Failed to send budget alert: {e}")

    return jsonify({
        "month": month,
        "domain": domain,
        "budget_amount": round(budget_amount, 2),
        "spent": round(spent, 2),
        "remaining": round(remaining, 2),
        "percentage": round(percentage, 1),
        "alert_triggered": alert_triggered,
        "purchase_count": len(purchases),
    }), 200
