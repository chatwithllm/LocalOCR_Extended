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

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


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
    spending_by_period = defaultdict(lambda: {"total": 0, "count": 0, "purchases": []})

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

        spending_by_period[key]["total"] += purchase.total_amount or 0
        spending_by_period[key]["count"] += 1

    # Category breakdown if requested
    category_breakdown = {}
    if category or True:  # Always include category breakdown
        items = (
            session.query(ReceiptItem, Product)
            .join(Product, ReceiptItem.product_id == Product.id)
            .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
            .filter(Purchase.date >= cutoff)
        )
        if domain:
            items = items.filter(Purchase.domain == domain)
        if category:
            items = items.filter(Product.category == category)

        for item, product in items.all():
            cat = product.category or "other"
            if cat not in category_breakdown:
                category_breakdown[cat] = {"total": 0, "count": 0}
            category_breakdown[cat]["total"] += (item.unit_price or 0) * (item.quantity or 1)
            category_breakdown[cat]["count"] += 1

    grand_total = sum(p["total"] for p in spending_by_period.values())

    return jsonify({
        "period": period,
        "domain": domain or "all",
        "months_back": months_back,
        "grand_total": round(grand_total, 2),
        "spending_by_period": {
            k: {"total": round(v["total"], 2), "count": v["count"]}
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
