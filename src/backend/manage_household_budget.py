"""
Step 19: Implement Budget Management
======================================
PROMPT Reference: Phase 6, Step 19

Budget setting and tracking endpoints. Alerts at 80% threshold via MQTT.

MQTT Topic: home/grocery/alerts/budget
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g

from src.backend.budgeting_domains import (
    BUDGET_CATEGORIES,
    default_budget_category_for_spending_domain,
    normalize_budget_category,
    normalize_spending_domain,
)
from src.backend.budgeting_rollups import (
    calculate_budget_allocations,
    calculate_budget_breakdowns,
    month_bounds,
    normalize_transaction_type,
    signed_purchase_total,
)
from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import Budget, BudgetChangeLog, BillMeta, Product, Purchase, ReceiptItem, Store
from src.backend.manage_authentication import is_admin

logger = logging.getLogger(__name__)

budget_bp = Blueprint("budget", __name__, url_prefix="/budget")

HOUSEHOLD_OBLIGATION_CATEGORIES = [
    "utilities",
    "housing",
    "insurance",
    "childcare",
    "subscriptions",
    "health",
    "other_recurring",
]


def _current_budget_owner_id():
    current_user = getattr(g, "current_user", None)
    return current_user.id if current_user else None


def _budget_storage_domain(domain: str | None = None, budget_category: str | None = None) -> str:
    if budget_category:
        return f"category:{normalize_budget_category(budget_category)}"
    return normalize_spending_domain(domain or "grocery")


def _fetch_budget(session, user_id, month, domain=None, budget_category=None):
    storage_domain = _budget_storage_domain(domain=domain, budget_category=budget_category)
    normalized_category = normalize_budget_category(budget_category) if budget_category else None

    query = session.query(Budget).filter_by(user_id=user_id, month=month, domain=storage_domain)
    if normalized_category:
        query = query.filter(Budget.budget_category == normalized_category)
    budget = query.first()
    if budget:
        return budget

    query = session.query(Budget).filter_by(user_id=None, month=month, domain=storage_domain)
    if normalized_category:
        query = query.filter(Budget.budget_category == normalized_category)
    return query.first()


def _domain_fallback_budget(session, user_id, month, domain):
    budget = _fetch_budget(session, user_id, month, domain=domain)
    if budget:
        return budget
    fallback_category = default_budget_category_for_spending_domain(domain)
    return _fetch_budget(session, user_id, month, budget_category=fallback_category)


def _build_category_status(month, budget_category, target_amount, spent_amount):
    remaining = target_amount - spent_amount
    percentage = (spent_amount / target_amount * 100) if target_amount > 0 else 0
    return {
        "month": month,
        "budget_category": budget_category,
        "budget_amount": round(target_amount, 2),
        "spent": round(spent_amount, 2),
        "remaining": round(remaining, 2),
        "percentage": round(percentage, 1),
    }


def _household_obligations_summary(month, computed, category_rows):
    domain_spent = float(computed["domains"].get("household_obligations", 0) or 0)
    category_map = {row["budget_category"]: row for row in category_rows}
    obligation_rows = [category_map[category] for category in HOUSEHOLD_OBLIGATION_CATEGORIES if category in category_map]
    target_total = sum(float(row.get("budget_amount", 0) or 0) for row in obligation_rows)
    remaining = target_total - domain_spent
    percentage = (domain_spent / target_total * 100) if target_total > 0 else 0

    purchases = computed["purchases"]
    household_purchase_ids = [
        purchase.id
        for purchase in purchases
        if normalize_spending_domain(getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", None), default="other")
        == "household_obligations"
    ]

    recurring_purchase_ids = set()
    if household_purchase_ids:
        recurring_purchase_ids = {
            purchase_id
            for (purchase_id,) in computed["session"].query(BillMeta.purchase_id)
            .filter(
                BillMeta.purchase_id.in_(household_purchase_ids),
                BillMeta.is_recurring.is_(True),
            )
            .all()
        }

    recurring_total = 0.0
    one_off_total = 0.0
    recurring_count = 0
    one_off_count = 0
    for purchase in purchases:
        normalized_domain = normalize_spending_domain(
            getattr(purchase, "default_spending_domain", None) or getattr(purchase, "domain", None),
            default="other",
        )
        if normalized_domain != "household_obligations":
            continue
        signed_total = signed_purchase_total(purchase)
        if purchase.id in recurring_purchase_ids:
            recurring_total += signed_total
            recurring_count += 1
        else:
            one_off_total += signed_total
            one_off_count += 1

    return {
        "domain": "household_obligations",
        "label": "Household Obligations",
        "spent": round(domain_spent, 2),
        "target_total": round(target_total, 2),
        "remaining": round(remaining, 2),
        "percentage": round(percentage, 1),
        "committed_this_month": round(recurring_total, 2),
        "one_off_this_month": round(one_off_total, 2),
        "recurring_count": recurring_count,
        "one_off_count": one_off_count,
        "categories": obligation_rows,
    }


@budget_bp.route("/set-monthly", methods=["POST"])
@require_write_access
def set_monthly_budget():
    """Set a monthly budget target for a spending domain or budget category."""
    session = g.db_session
    data = request.get_json(silent=True)
    current_user = getattr(g, "current_user", None)

    if not is_admin(current_user):
        return jsonify({"error": "Only admins can update budgets"}), 403

    if not data or not data.get("budget_amount"):
        return jsonify({"error": "budget_amount is required"}), 400

    month = data.get("month", datetime.now().strftime("%Y-%m"))
    budget_category = data.get("budget_category")
    domain = data.get("domain")
    if budget_category:
        budget_category = normalize_budget_category(budget_category)
        domain = _budget_storage_domain(budget_category=budget_category)
    else:
        domain = normalize_spending_domain(domain or "grocery")
    budget_amount = float(data["budget_amount"])

    user_id = _current_budget_owner_id()

    # Upsert budget
    existing = session.query(Budget).filter_by(user_id=user_id, month=month, domain=domain).first()
    previous_amount = float(existing.budget_amount) if existing else None
    if existing:
        existing.budget_amount = budget_amount
        existing.budget_category = budget_category
    else:
        budget = Budget(
            user_id=user_id,
            month=month,
            domain=domain,
            budget_category=budget_category,
            budget_amount=budget_amount,
        )
        session.add(budget)

    session.add(BudgetChangeLog(
        user_id=user_id,
        month=month,
        domain=domain,
        budget_category=budget_category,
        previous_amount=previous_amount,
        new_amount=budget_amount,
    ))

    session.commit()

    return jsonify({
        "month": month,
        "domain": domain,
        "budget_category": budget_category,
        "budget_amount": budget_amount,
        "message": f"{(budget_category or domain).replace('_', ' ').title()} budget set to ${budget_amount:.2f} for {month}",
    }), 200


@budget_bp.route("/status", methods=["GET"])
@require_auth
def get_budget_status():
    """Get current month's budget vs actual spending."""
    session = g.db_session
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    domain = request.args.get("domain")
    budget_category = request.args.get("budget_category")

    user_id = _current_budget_owner_id()

    if budget_category:
        normalized_category = normalize_budget_category(budget_category)
        budget = _fetch_budget(session, user_id, month, budget_category=normalized_category)
        budget_amount = budget.budget_amount if budget else 0
        rollups = _compute_budget_rollups(session, month)
        summary = _build_category_status(
            month,
            normalized_category,
            budget_amount,
            float(rollups["categories"].get(normalized_category, 0) or 0),
        )
        summary["alert_triggered"] = False
        return jsonify(summary), 200

    domain = normalize_spending_domain(domain or "grocery")
    budget = _domain_fallback_budget(session, user_id, month, domain)
    budget_amount = budget.budget_amount if budget else 0

    # Calculate actual spending for the month
    start_date, end_date = month_bounds(month)
    now_dt = datetime.now(timezone.utc)

    purchases = session.query(Purchase).filter(
        Purchase.date >= start_date,
        Purchase.date < end_date,
        Purchase.date <= now_dt,
        Purchase.domain == domain,
    ).all()

    spent = sum(signed_purchase_total(p) for p in purchases)
    purchase_count = sum(1 for p in purchases if normalize_transaction_type(getattr(p, "transaction_type", None)) != "refund")
    refund_count = sum(1 for p in purchases if normalize_transaction_type(getattr(p, "transaction_type", None)) == "refund")
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
        "budget_category": budget.budget_category if budget else None,
        "budget_amount": round(budget_amount, 2),
        "spent": round(spent, 2),
        "remaining": round(remaining, 2),
        "percentage": round(percentage, 1),
        "alert_triggered": alert_triggered,
        "purchase_count": purchase_count,
        "refund_count": refund_count,
        "receipt_count": len(purchases),
    }), 200


def _compute_budget_rollups(session, month):
    start_date, end_date = month_bounds(month)
    now_dt = datetime.now(timezone.utc)
    purchases = session.query(Purchase).filter(
        Purchase.date >= start_date,
        Purchase.date < end_date,
        Purchase.date <= now_dt,
    ).all()
    store_ids = {purchase.store_id for purchase in purchases if getattr(purchase, "store_id", None)}
    stores_by_id = {}
    if store_ids:
        stores_by_id = {
            store.id: store
            for store in session.query(Store).filter(Store.id.in_(store_ids)).all()
        }
    for purchase in purchases:
        store = stores_by_id.get(getattr(purchase, "store_id", None))
        purchase.store_name = store.name if store else None

    purchase_ids = [purchase.id for purchase in purchases]
    receipt_items = session.query(ReceiptItem).filter(ReceiptItem.purchase_id.in_(purchase_ids)).all() if purchase_ids else []
    product_ids = {item.product_id for item in receipt_items if getattr(item, "product_id", None)}
    products_by_id = {}
    if product_ids:
        products_by_id = {
            product.id: product
            for product in session.query(Product).filter(Product.id.in_(product_ids)).all()
        }
    receipt_items_by_purchase = defaultdict(list)
    for item in receipt_items:
        product = products_by_id.get(getattr(item, "product_id", None))
        item.product_name = product.display_name or product.name if product else None
        receipt_items_by_purchase[item.purchase_id].append(item)
    rollups = calculate_budget_allocations(purchases, receipt_items_by_purchase)
    breakdowns = calculate_budget_breakdowns(purchases, receipt_items_by_purchase)
    category_map = {
        entry["key"]: float(entry.get("spent", 0) or 0)
        for entry in rollups["categories"]
    }
    domain_map = {
        entry["key"]: float(entry.get("spent", 0) or 0)
        for entry in rollups["domains"]
    }
    return {
        "session": session,
        "purchases": purchases,
        "rollups": rollups,
        "categories": category_map,
        "domains": domain_map,
        "category_rows": rollups["categories"],
        "domain_rows": rollups["domains"],
        "breakdowns": breakdowns,
    }


@budget_bp.route("/allocation-summary", methods=["GET"])
@require_auth
def get_budget_allocation_summary():
    """Return monthly spending rollups using effective line-item allocations."""
    session = g.db_session
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    computed = _compute_budget_rollups(session, month)
    return jsonify({
        "month": month,
        "categories": computed["category_rows"],
        "domains": computed["domain_rows"],
        "purchase_count": sum(1 for p in computed["purchases"] if normalize_transaction_type(getattr(p, "transaction_type", None)) != "refund"),
        "refund_count": sum(1 for p in computed["purchases"] if normalize_transaction_type(getattr(p, "transaction_type", None)) == "refund"),
        "receipt_count": len(computed["purchases"]),
    }), 200


@budget_bp.route("/category-summary", methods=["GET"])
@require_auth
def get_budget_category_summary():
    """Return monthly category targets + spending summary for the Budget page."""
    session = g.db_session
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    user_id = _current_budget_owner_id()

    computed = _compute_budget_rollups(session, month)
    category_spend = computed["categories"]
    category_breakdowns = computed["breakdowns"]

    budgets = session.query(Budget).filter(
        Budget.month == month,
        Budget.budget_category.isnot(None),
        ((Budget.user_id == user_id) if user_id is not None else (Budget.user_id.is_(None))),
    ).all()
    if user_id is not None:
        household_budgets = session.query(Budget).filter(
            Budget.month == month,
            Budget.budget_category.isnot(None),
            Budget.user_id.is_(None),
        ).all()
    else:
        household_budgets = []

    current_map = {}
    for budget in household_budgets:
        current_map[normalize_budget_category(budget.budget_category)] = budget
    for budget in budgets:
        current_map[normalize_budget_category(budget.budget_category)] = budget

    targets = {normalize_budget_category(budget.budget_category): float(budget.budget_amount or 0) for budget in household_budgets}
    targets.update({normalize_budget_category(budget.budget_category): float(budget.budget_amount or 0) for budget in budgets})

    categories = []
    for category in BUDGET_CATEGORIES:
        current_target = current_map.get(category)
        status = _build_category_status(
            month,
            category,
            float(targets.get(category, 0) or 0),
            float(category_spend.get(category, 0) or 0),
        )
        status["updated_at"] = (current_target.updated_at or current_target.created_at).isoformat() if current_target and (current_target.updated_at or current_target.created_at) else None
        status["contributions"] = category_breakdowns.get(category, [])
        categories.append(status)

    active_categories = [
        entry for entry in categories
        if (entry["budget_amount"] > 0) or (entry["spent"] > 0)
    ]
    inactive_categories = [
        entry for entry in categories
        if not ((entry["budget_amount"] > 0) or (entry["spent"] > 0))
    ]

    return jsonify({
        "month": month,
        "household_obligations": _household_obligations_summary(month, computed, categories),
        "categories": active_categories + inactive_categories,
        "active_count": len(active_categories),
    }), 200


@budget_bp.route("/target-history", methods=["GET"])
@require_auth
def get_budget_target_history():
    """Return current category targets plus change history for the selected month."""
    session = g.db_session
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    user_id = _current_budget_owner_id()

    current_rows = session.query(Budget).filter(
        Budget.month == month,
        Budget.budget_category.isnot(None),
        ((Budget.user_id == user_id) if user_id is not None else (Budget.user_id.is_(None))),
    ).all()
    if user_id is not None:
        household_rows = session.query(Budget).filter(
            Budget.month == month,
            Budget.budget_category.isnot(None),
            Budget.user_id.is_(None),
        ).all()
    else:
        household_rows = []

    current_map = {}
    for row in household_rows:
        category = normalize_budget_category(row.budget_category)
        current_map[category] = row
    for row in current_rows:
        category = normalize_budget_category(row.budget_category)
        current_map[category] = row

    current_targets = [
        {
            "month": month,
            "budget_category": category,
            "budget_amount": round(float(row.budget_amount or 0), 2),
            "updated_at": (row.updated_at or row.created_at).isoformat() if (row.updated_at or row.created_at) else None,
        }
        for category, row in sorted(current_map.items(), key=lambda item: item[0])
    ]

    history_rows = session.query(BudgetChangeLog).filter(
        BudgetChangeLog.month == month,
        BudgetChangeLog.budget_category.isnot(None),
        ((BudgetChangeLog.user_id == user_id) if user_id is not None else (BudgetChangeLog.user_id.is_(None))),
    ).order_by(BudgetChangeLog.changed_at.desc(), BudgetChangeLog.id.desc()).limit(100).all()

    if user_id is not None:
        household_history = session.query(BudgetChangeLog).filter(
            BudgetChangeLog.month == month,
            BudgetChangeLog.budget_category.isnot(None),
            BudgetChangeLog.user_id.is_(None),
        ).order_by(BudgetChangeLog.changed_at.desc(), BudgetChangeLog.id.desc()).limit(100).all()
    else:
        household_history = []

    seen = set()
    merged_history = []
    for row in list(history_rows) + list(household_history):
        key = row.id
        if key in seen:
            continue
        seen.add(key)
        merged_history.append(row)
    merged_history.sort(key=lambda row: ((row.changed_at or datetime.min.replace(tzinfo=timezone.utc)), row.id), reverse=True)

    history = [{
        "month": row.month,
        "budget_category": normalize_budget_category(row.budget_category),
        "previous_amount": None if row.previous_amount is None else round(float(row.previous_amount), 2),
        "new_amount": round(float(row.new_amount or 0), 2),
        "changed_at": row.changed_at.isoformat() if row.changed_at else None,
    } for row in merged_history[:100]]

    return jsonify({
        "month": month,
        "current_targets": current_targets,
        "history": history,
    }), 200
