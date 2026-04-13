"""
Step 18: Calculate Spending Analytics
======================================
PROMPT Reference: Phase 6, Step 18

Analytics endpoints for spending reports: total by period, by category,
price history trends, and deals captured (savings quantification).
"""

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from flask import Blueprint, request, jsonify, g

from src.backend.create_flask_application import require_auth
from src.backend.initialize_database_schema import (
    Purchase, ReceiptItem, Product, Store, PriceHistory
)
from src.backend.budgeting_rollups import normalize_transaction_type, signed_purchase_total, purchase_amount_sign

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


def _transaction_counts(purchases):
    purchase_count = 0
    refund_count = 0
    for purchase in purchases:
        if normalize_transaction_type(getattr(purchase, "transaction_type", None)) == "refund":
            refund_count += 1
        else:
            purchase_count += 1
    return purchase_count, refund_count


@analytics_bp.route("/expense-summary", methods=["GET"])
@require_auth
def get_general_expense_summary():
    """Return general-expense spend and merchant/item history."""
    from src.backend.initialize_database_schema import TelegramReceipt
    import json

    session = g.db_session
    months_back = request.args.get("months", 6, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    purchases = (
        session.query(Purchase, Store, TelegramReceipt)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .outerjoin(TelegramReceipt, TelegramReceipt.purchase_id == Purchase.id)
        .filter(Purchase.domain == "general_expense", Purchase.date >= cutoff)
        .order_by(Purchase.date.desc())
        .all()
    )

    total_spend = 0.0
    purchase_total = 0.0
    refund_total = 0.0
    merchant_summary = defaultdict(lambda: {"visits": 0, "refunds": 0, "total": 0.0, "purchase_total": 0.0, "refund_total": 0.0, "latest_date": None})
    item_summary = defaultdict(lambda: {"quantity": 0.0, "total": 0.0})
    category_summary = defaultdict(lambda: {"total": 0.0, "count": 0})
    recent_receipts = []

    for purchase, store, record in purchases:
        sign = purchase_amount_sign(purchase)
        total = signed_purchase_total(purchase)
        transaction_type = normalize_transaction_type(getattr(purchase, "transaction_type", None))
        total_spend += total
        if transaction_type == "refund":
            refund_total += abs(total)
        else:
            purchase_total += total
        merchant = store.name if store and store.name else "Unknown"
        merchant_info = merchant_summary[merchant]
        if transaction_type == "refund":
            merchant_info["refunds"] += 1
            merchant_info["refund_total"] += abs(total)
        else:
            merchant_info["visits"] += 1
            merchant_info["purchase_total"] += total
        merchant_info["total"] += total
        if not merchant_info["latest_date"] or (purchase.date and purchase.date > merchant_info["latest_date"]):
            merchant_info["latest_date"] = purchase.date

        raw = {}
        if record and record.raw_ocr_json:
            try:
                raw = json.loads(record.raw_ocr_json)
            except json.JSONDecodeError:
                raw = {}
        items = raw.get("items", []) if isinstance(raw, dict) else []
        for item in items or []:
            name = str((item or {}).get("name", "") or "").strip()
            if not name:
                continue
            quantity = float((item or {}).get("quantity") or 1) * sign
            unit_price = float((item or {}).get("unit_price") or 0)
            category = str((item or {}).get("category", "") or "other").strip().lower() or "other"
            info = item_summary[name]
            info["quantity"] += quantity
            info["total"] += quantity * unit_price
            category_summary[category]["total"] += quantity * unit_price
            category_summary[category]["count"] += 1

        recent_receipts.append({
            "purchase_id": purchase.id,
            "store": merchant,
            "date": purchase.date.strftime("%Y-%m-%d") if purchase.date else None,
            "total": round(total, 2),
            "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None)),
            "item_count": len(items or []),
        })

    top_merchants = sorted(
        (
            {
                "store": merchant,
                "visits": values["visits"],
                "refunds": values["refunds"],
                "total": round(values["total"], 2),
                "purchase_total": round(values["purchase_total"], 2),
                "refund_total": round(values["refund_total"], 2),
                "average_ticket": round(values["purchase_total"] / values["visits"], 2) if values["visits"] else 0,
                "latest_date": values["latest_date"].strftime("%Y-%m-%d") if values["latest_date"] else None,
            }
            for merchant, values in merchant_summary.items()
        ),
        key=lambda item: (-item["total"], -item["visits"], item["store"]),
    )

    top_items = sorted(
        (
            {
                "name": name,
                "quantity": round(values["quantity"], 2),
                "total": round(values["total"], 2),
                "average_price": round(values["total"] / values["quantity"], 2) if values["quantity"] else 0,
            }
            for name, values in item_summary.items()
        ),
        key=lambda item: (-item["total"], -item["quantity"], item["name"]),
    )[:10]

    category_breakdown = sorted(
        (
            {
                "category": category,
                "total": round(values["total"], 2),
                "count": values["count"],
            }
            for category, values in category_summary.items()
        ),
        key=lambda item: (-item["total"], -item["count"], item["category"]),
    )

    purchase_count, refund_count = _transaction_counts([purchase for purchase, _, _ in purchases])
    return jsonify({
        "months_back": months_back,
        "receipt_count": purchase_count + refund_count,
        "purchase_count": purchase_count,
        "refund_count": refund_count,
        "total_spend": round(total_spend, 2),
        "purchase_total": round(purchase_total, 2),
        "refund_total": round(refund_total, 2),
        "average_ticket": round(purchase_total / purchase_count, 2) if purchase_count else 0,
        "top_merchants": top_merchants[:8],
        "top_items": top_items,
        "category_breakdown": category_breakdown,
        "recent_receipts": recent_receipts[:12],
    }), 200


@analytics_bp.route("/restaurant-summary", methods=["GET"])
@require_auth
def get_restaurant_summary():
    """Return restaurant-focused spend and item history for the Restaurant workspace."""
    session = g.db_session
    months_back = request.args.get("months", 6, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    purchases = (
        session.query(Purchase, Store)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .filter(Purchase.domain == "restaurant", Purchase.date >= cutoff)
        .order_by(Purchase.date.desc())
        .all()
    )

    total_spend = 0.0
    purchase_total = 0.0
    refund_total = 0.0
    store_summary = defaultdict(lambda: {"visits": 0, "refunds": 0, "total": 0.0, "purchase_total": 0.0, "refund_total": 0.0, "latest_date": None})
    purchase_ids = []
    recent_receipts = []

    for purchase, store in purchases:
        purchase_ids.append(purchase.id)
        sign = purchase_amount_sign(purchase)
        total = signed_purchase_total(purchase)
        transaction_type = normalize_transaction_type(getattr(purchase, "transaction_type", None))
        total_spend += total
        if transaction_type == "refund":
            refund_total += abs(total)
        else:
            purchase_total += total
        store_name = store.name if store and store.name else "Unknown"
        info = store_summary[store_name]
        if transaction_type == "refund":
            info["refunds"] += 1
            info["refund_total"] += abs(total)
        else:
            info["visits"] += 1
            info["purchase_total"] += total
        info["total"] += total
        if not info["latest_date"] or (purchase.date and purchase.date > info["latest_date"]):
            info["latest_date"] = purchase.date
        recent_receipts.append({
            "purchase_id": purchase.id,
            "store": store_name,
            "date": purchase.date.strftime("%Y-%m-%d") if purchase.date else None,
            "total": round(total, 2),
            "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None)),
        })

    item_summary = defaultdict(lambda: {"quantity": 0.0, "total": 0.0, "category": None})
    if purchase_ids:
        rows = (
            session.query(ReceiptItem, Product, Purchase)
            .join(Product, ReceiptItem.product_id == Product.id)
            .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
            .filter(ReceiptItem.purchase_id.in_(purchase_ids))
            .all()
        )
        for receipt_item, product, purchase in rows:
            name = product.display_name or product.name
            purchase_sign = purchase_amount_sign(purchase)
            item_summary[name]["quantity"] += float(receipt_item.quantity or 0) * purchase_sign
            item_summary[name]["total"] += float((receipt_item.unit_price or 0) * (receipt_item.quantity or 1)) * purchase_sign
            item_summary[name]["category"] = product.category

    top_restaurants = sorted(
        (
            {
                "store": store_name,
                "visits": values["visits"],
                "refunds": values["refunds"],
                "total": round(values["total"], 2),
                "purchase_total": round(values["purchase_total"], 2),
                "refund_total": round(values["refund_total"], 2),
                "average_ticket": round(values["purchase_total"] / values["visits"], 2) if values["visits"] else 0,
                "latest_date": values["latest_date"].strftime("%Y-%m-%d") if values["latest_date"] else None,
            }
            for store_name, values in store_summary.items()
        ),
        key=lambda item: (-item["visits"], -item["total"], item["store"]),
    )

    top_items = sorted(
        (
            {
                "name": name,
                "quantity": round(values["quantity"], 2),
                "total": round(values["total"], 2),
                "average_price": round(values["total"] / values["quantity"], 2) if values["quantity"] else 0,
                "category": values["category"],
            }
            for name, values in item_summary.items()
        ),
        key=lambda item: (-item["quantity"], -item["total"], item["name"]),
    )[:10]

    purchase_count, refund_count = _transaction_counts([purchase for purchase, _ in purchases])
    return jsonify({
        "months_back": months_back,
        "visit_count": purchase_count,
        "receipt_count": purchase_count + refund_count,
        "refund_count": refund_count,
        "total_spend": round(total_spend, 2),
        "purchase_total": round(purchase_total, 2),
        "refund_total": round(refund_total, 2),
        "average_ticket": round(purchase_total / purchase_count, 2) if purchase_count else 0,
        "top_restaurants": top_restaurants[:8],
        "top_items": top_items,
        "recent_receipts": recent_receipts[:12],
    }), 200


@analytics_bp.route("/spending", methods=["GET"])
@require_auth
def get_spending():
    """Get spending analytics by period and/or category."""
    session = g.db_session
    period = request.args.get("period", "monthly")
    category = request.args.get("category")
    store_name = request.args.get("store")
    domain = (request.args.get("domain") or "").strip().lower()
    months_back = request.args.get("months", 6, type=int)

    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    query = session.query(Purchase).filter(Purchase.date >= cutoff)
    if domain:
        query = query.filter(Purchase.domain == domain)

    if store_name:
        query = query.join(Store).filter(Store.name.ilike(f"%{store_name}%"))

    purchases = query.order_by(Purchase.date).all()

    # Aggregate by period
    spending_by_period = defaultdict(lambda: {
        "total": 0,
        "count": 0,
        "purchase_count": 0,
        "refund_count": 0,
        "purchase_total": 0,
        "refund_total": 0,
        "purchases": [],
    })

    for purchase in purchases:
        if not purchase.date:
            continue
        if period == "daily":
            key = purchase.date.strftime("%Y-%m-%d")
        elif period == "weekly":
            key = f"{purchase.date.year}-W{purchase.date.isocalendar()[1]:02d}"
        elif period == "yearly":
            key = str(purchase.date.year)
        else:  # monthly
            key = purchase.date.strftime("%Y-%m")

        signed_total = signed_purchase_total(purchase)
        transaction_type = normalize_transaction_type(getattr(purchase, "transaction_type", None))
        spending_by_period[key]["total"] += signed_total
        spending_by_period[key]["count"] += 1
        if transaction_type == "refund":
            spending_by_period[key]["refund_count"] += 1
            spending_by_period[key]["refund_total"] += abs(signed_total)
        else:
            spending_by_period[key]["purchase_count"] += 1
            spending_by_period[key]["purchase_total"] += signed_total

    # Category breakdown if requested
    category_breakdown = {}
    if category or True:  # Always include category breakdown
        items = (
            session.query(ReceiptItem, Product, Purchase)
            .join(Product, ReceiptItem.product_id == Product.id)
            .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
            .filter(Purchase.date >= cutoff)
        )
        if domain:
            items = items.filter(Purchase.domain == domain)
        if category:
            items = items.filter(Product.category == category)

        for item, product, purchase in items.all():
            cat = product.category or "other"
            if cat not in category_breakdown:
                category_breakdown[cat] = {"total": 0, "count": 0}
            category_breakdown[cat]["total"] += ((item.unit_price or 0) * (item.quantity or 1)) * purchase_amount_sign(purchase)
            category_breakdown[cat]["count"] += 1

    grand_total = sum(p["total"] for p in spending_by_period.values())

    return jsonify({
        "period": period,
        "domain": domain or "all",
        "months_back": months_back,
        "grand_total": round(grand_total, 2),
        "spending_by_period": {
            k: {
                "total": round(v["total"], 2),
                "count": v["count"],
                "purchase_count": v["purchase_count"],
                "refund_count": v["refund_count"],
                "purchase_total": round(v["purchase_total"], 2),
                "refund_total": round(v["refund_total"], 2),
            }
            for k, v in sorted(spending_by_period.items())
        },
        "category_breakdown": {
            k: {"total": round(v["total"], 2), "count": v["count"]}
            for k, v in sorted(category_breakdown.items())
        },
    }), 200


@analytics_bp.route("/price-history", methods=["GET"])
@require_auth
def get_price_history():
    """Get price trends for a specific product."""
    session = g.db_session
    product_id = request.args.get("product_id", type=int)

    if not product_id:
        return jsonify({"error": "product_id parameter required"}), 400

    product = session.query(Product).filter_by(id=product_id).first()
    if not product:
        return jsonify({"error": "Product not found"}), 404

    prices = (
        session.query(PriceHistory)
        .filter_by(product_id=product_id)
        .order_by(PriceHistory.date.desc())
        .limit(100)
        .all()
    )

    price_values = [p.price for p in prices if p.price]

    return jsonify({
        "product_id": product_id,
        "product_name": product.name,
        "prices": [
            {
                "price": p.price,
                "store_id": p.store_id,
                "date": p.date.strftime("%Y-%m-%d") if p.date else None,
            }
            for p in prices
        ],
        "stats": {
            "avg": round(sum(price_values) / len(price_values), 2) if price_values else None,
            "min": round(min(price_values), 2) if price_values else None,
            "max": round(max(price_values), 2) if price_values else None,
            "count": len(price_values),
        },
    }), 200


@analytics_bp.route("/deals-captured", methods=["GET"])
@require_auth
def get_deals_captured():
    """Get savings from deals over a period.

    Savings = sum((avg_price - actual_price) * quantity) for items where actual < avg
    """
    session = g.db_session
    months_back = request.args.get("months", 1, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    items = (
        session.query(ReceiptItem, Product, Purchase)
        .join(Product, ReceiptItem.product_id == Product.id)
        .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
        .filter(Purchase.date >= cutoff)
        .all()
    )

    total_saved = 0
    deal_items = []

    for item, product, purchase in items:
        # Get average price for this product
        avg_query = (
            session.query(PriceHistory.price)
            .filter_by(product_id=product.id)
            .all()
        )
        prices = [p[0] for p in avg_query if p[0] and p[0] > 0]
        if len(prices) < 2:
            continue

        avg_price = sum(prices) / len(prices)
        if item.unit_price and item.unit_price < avg_price * 0.9:
            savings = (avg_price - item.unit_price) * (item.quantity or 1)
            total_saved += savings
            deal_items.append({
                "product_name": product.name,
                "paid": round(item.unit_price, 2),
                "avg_price": round(avg_price, 2),
                "quantity": item.quantity,
                "saved": round(savings, 2),
                "date": purchase.date.strftime("%Y-%m-%d") if purchase.date else None,
            })

    return jsonify({
        "months_back": months_back,
        "total_saved": round(total_saved, 2),
        "deal_count": len(deal_items),
        "deals": deal_items,
    }), 200


@analytics_bp.route("/store-comparison", methods=["GET"])
@require_auth
def get_store_comparison():
    """Compare prices for the same product across stores."""
    session = g.db_session
    product_id = request.args.get("product_id", type=int)

    if not product_id:
        return jsonify({"error": "product_id parameter required"}), 400

    prices = (
        session.query(PriceHistory, Store)
        .join(Store, PriceHistory.store_id == Store.id)
        .filter(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.date.desc())
        .all()
    )

    # Group by store
    store_prices = defaultdict(list)
    for price, store in prices:
        store_prices[store.name].append(price.price)

    comparison = []
    for store_name, price_list in store_prices.items():
        comparison.append({
            "store": store_name,
            "avg_price": round(sum(price_list) / len(price_list), 2),
            "min_price": round(min(price_list), 2),
            "max_price": round(max(price_list), 2),
            "sample_count": len(price_list),
        })

    comparison.sort(key=lambda x: x["avg_price"])

    product = session.query(Product).filter_by(id=product_id).first()
    return jsonify({
        "product_id": product_id,
        "product_name": product.name if product else None,
        "comparison": comparison,
        "cheapest_store": comparison[0]["store"] if comparison else None,
    }), 200
        )
        if pkey not in provider_summary:
            provider_summary[pkey] = {
                "provider_name": provider_name,
                "provider_type": provider_type,
                "service_types": service_types,
                "total": 0.0,
                "purchase_count": 0,
                "refund_count": 0,
                "latest_date": None,
                "monthly_breakdown": {},
            }
        ps = provider_summary[pkey]
        for service_type in service_types:
            if service_type and service_type not in ps["service_types"]:
                ps["service_types"].append(service_type)
        ps["total"] += signed_total
        if transaction_type == "refund":
            ps["refund_count"] += 1
        else:
            ps["purchase_count"] += 1
        if purchase.date and (ps["latest_date"] is None or purchase.date > ps["latest_date"]):
            ps["latest_date"] = purchase.date
        if billing_cycle:
            ps["monthly_breakdown"][billing_cycle] = round(
                ps["monthly_breakdown"].get(billing_cycle, 0.0) + signed_total, 2
            )

        # Per-category aggregation for analytics rollups
        ckey = budget_category
        if ckey not in category_summary:
            category_summary[ckey] = {
                "budget_category": ckey,
                "total": 0.0,
                "purchase_count": 0,
                "refund_count": 0,
            }
        cs = category_summary[ckey]
        cs["total"] += signed_total
        if transaction_type == "refund":
            cs["refund_count"] += 1
        else:
            cs["purchase_count"] += 1

        # Global month totals
        if billing_cycle:
            monthly_totals[billing_cycle] = round(
                monthly_totals.get(billing_cycle, 0.0) + signed_total, 2
            )

        # Due soon (next 14 days)
        if meta and meta.due_date:
            days_until = (meta.due_date - today).days
            if 0 <= days_until <= 14:
                due_soon.append({
                    "purchase_id": purchase.id,
                "provider_name": provider_name,
                "provider_type": provider_type,
                "service_types": service_types,
                "amount": round(signed_total, 2),
                    "due_date": meta.due_date.isoformat(),
                    "days_until_due": days_until,
                    "billing_cycle_month": meta.billing_cycle_month,
                })

        recent_bills.append({
            "purchase_id": purchase.id,
            "provider_name": provider_name,
            "provider_type": provider_type,
            "service_types": service_types,
            "date": purchase.date.strftime("%Y-%m-%d") if purchase.date else None,
            "billing_cycle_month": billing_cycle,
            "amount": round(signed_total, 2),
            "transaction_type": transaction_type,
            "is_recurring": is_recurring,
            "due_date": meta.due_date.isoformat() if meta and meta.due_date else None,
            "budget_category": budget_category,
        })

    # Serialize provider summary
    provider_list = sorted(
        [
            {
                "provider_name": v["provider_name"],
                "provider_type": v["provider_type"],
                "service_types": v.get("service_types", []),
                "total": round(v["total"], 2),
                "purchase_count": v["purchase_count"],
                "refund_count": v["refund_count"],
                "average_monthly": round(
                    v["total"] / max(len(v["monthly_breakdown"]), 1), 2
                ),
                "latest_date": v["latest_date"].strftime("%Y-%m-%d") if v["latest_date"] else None,
                "monthly_breakdown": v["monthly_breakdown"],
            }
            for v in provider_summary.values()
        ],
        key=lambda x: (-x["total"], x["provider_name"]),
    )

    due_soon.sort(key=lambda x: x["days_until_due"])
    category_list = sorted(
        [
            {
                "budget_category": value["budget_category"],
                "total": round(value["total"], 2),
                "purchase_count": value["purchase_count"],
                "refund_count": value["refund_count"],
            }
            for value in category_summary.values()
        ],
        key=lambda entry: (-abs(entry["total"]), entry["budget_category"]),
    )

    purchase_count, refund_count = _transaction_counts([p for p, _, _ in rows])
    return jsonify({
        "months_back": months_back,
        "receipt_count": purchase_count + refund_count,
        "purchase_count": purchase_count,
        "refund_count": refund_count,
        "total_spend": round(total_spend, 2),
        "recurring_total": round(recurring_total, 2),
        "one_off_total": round(one_off_total, 2),
        "providers": provider_list,
        "category_breakdown": category_list,
        "monthly_totals": {k: v for k, v in sorted(monthly_totals.items())},
        "due_soon": due_soon,
        "recent_bills": recent_bills[:20],
    }), 200


@analytics_bp.route("/recurring-obligations", methods=["GET"])
@require_auth
def get_recurring_obligations():
    """Return a derived recurring-obligations planning view for a selected month."""
    from src.backend.initialize_database_schema import BillMeta  # noqa: PLC0415

    session = g.db_session
    month = (request.args.get("month") or "").strip()
    try:
        target_month = datetime.strptime(month, "%Y-%m") if month else datetime.now(timezone.utc)
    except ValueError:
        return jsonify({"error": "Month must be in YYYY-MM format"}), 400

    selected_month = target_month.strftime("%Y-%m")
    cutoff = target_month - timedelta(days=400)

    rows = (
        session.query(Purchase, Store, BillMeta)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .join(BillMeta, BillMeta.purchase_id == Purchase.id)
        .filter(
            Purchase.domain.in_(["utility", "household_obligations"]),
            Purchase.date >= cutoff,
            BillMeta.is_recurring.is_(True),
        )
        .order_by(Purchase.date.desc())
        .all()
    )

    obligations = {}
    for purchase, store, meta in rows:
        provider_name = _provider_display_name(meta, store)
        provider_type = (meta.provider_type or "other").strip() or "other"
        service_types = _service_types_from_meta(meta)
        account_label = (meta.account_label or "").strip() or None
        budget_category = getattr(purchase, "default_budget_category", None) or "other_recurring"
        key = _provider_group_key(provider_name, service_types[0] if service_types else provider_type, account_label)
        billing_cycle = (meta.billing_cycle_month or "").strip() or (purchase.date.strftime("%Y-%m") if purchase.date else None)
        transaction_type = normalize_transaction_type(getattr(purchase, "transaction_type", None))
        signed_total = round(signed_purchase_total(purchase), 2)

        obligation = obligations.setdefault(key, {
            "provider_name": provider_name,
            "provider_type": provider_type,
            "service_types": service_types,
            "account_label": account_label,
            "budget_category": budget_category,
            "history": [],
            "current_entry": None,
            "latest_date": None,
            "latest_due_date": None,
        })

        history_entry = {
            "purchase_id": purchase.id,
            "billing_cycle_month": billing_cycle,
            "date": purchase.date.strftime("%Y-%m-%d") if purchase.date else None,
            "amount": signed_total,
            "transaction_type": transaction_type,
            "due_date": meta.due_date.isoformat() if meta.due_date else None,
        }
        obligation["history"].append(history_entry)

        if billing_cycle == selected_month and obligation["current_entry"] is None:
            obligation["current_entry"] = history_entry

        if purchase.date and (obligation["latest_date"] is None or purchase.date > obligation["latest_date"]):
            obligation["latest_date"] = purchase.date
        if meta.due_date and (obligation["latest_due_date"] is None or meta.due_date > obligation["latest_due_date"]):
            obligation["latest_due_date"] = meta.due_date

    obligation_list = []
    outstanding_count = 0
    entered_count = 0
    expected_total = 0.0
    actual_total = 0.0
    fixed_count = 0
    variable_count = 0
    new_count = 0

    for obligation in obligations.values():
        non_refund_history = [entry for entry in obligation["history"] if entry["transaction_type"] != "refund"]
        recent_amounts = [abs(entry["amount"]) for entry in non_refund_history[:3] if entry["amount"] is not None]
        expected_amount = round(sum(recent_amounts) / len(recent_amounts), 2) if recent_amounts else 0.0
        amount_pattern, amount_spread = _obligation_amount_pattern(recent_amounts)
        current_entry = obligation["current_entry"]
        actual_amount = round(current_entry["amount"], 2) if current_entry else 0.0
        variance = round(actual_amount - expected_amount, 2) if current_entry else round(-expected_amount, 2)
        status = "entered" if current_entry else "outstanding"
        if status == "entered":
            entered_count += 1
        else:
            outstanding_count += 1
        if amount_pattern == "fixed":
            fixed_count += 1
        elif amount_pattern == "variable":
            variable_count += 1
        else:
            new_count += 1
        expected_total += expected_amount
        actual_total += actual_amount

        obligation_list.append({
            "provider_name": obligation["provider_name"],
            "provider_type": obligation["provider_type"],
            "service_types": obligation.get("service_types", []),
            "account_label": obligation["account_label"],
            "budget_category": obligation["budget_category"],
            "status": status,
            "amount_pattern": amount_pattern,
            "amount_spread": amount_spread,
            "expected_amount": expected_amount,
            "actual_amount": actual_amount,
            "variance": variance,
            "selected_month": selected_month,
            "purchase_id": current_entry["purchase_id"] if current_entry else (obligation["history"][0]["purchase_id"] if obligation["history"] else None),
            "current_entry": current_entry,
            "last_seen_date": obligation["latest_date"].strftime("%Y-%m-%d") if obligation["latest_date"] else None,
            "last_due_date": obligation["latest_due_date"].isoformat() if obligation["latest_due_date"] else None,
            "history_count": len(obligation["history"]),
            "history_preview": obligation["history"][:4],
        })

    obligation_list.sort(key=lambda item: (0 if item["status"] == "outstanding" else 1, item["provider_name"].lower()))

    return jsonify({
        "month": selected_month,
        "obligations": obligation_list,
        "summary": {
            "count": len(obligation_list),
            "outstanding_count": outstanding_count,
            "entered_count": entered_count,
            "fixed_count": fixed_count,
            "variable_count": variable_count,
            "new_count": new_count,
            "expected_total": round(expected_total, 2),
            "actual_total": round(actual_total, 2),
            "variance_total": round(actual_total - expected_total, 2),
        },
    }), 200
