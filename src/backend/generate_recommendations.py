"""
Step 16: Build Recommendation Engine
======================================
PROMPT Reference: Phase 5, Step 16

Generates deal and seasonal recommendations based on purchase history.
Uses scaled confidence formulas — threshold ≥0.40.

Deal: min((avg_price - current_price) / avg_price * 5, 1.0)
Seasonal: min((days_since_last / avg_frequency - 1.0) * 2.5, 1.0)
"""

import logging
from datetime import datetime, timedelta, timezone
from statistics import median

from flask import Blueprint, g, jsonify
from sqlalchemy import func

from src.backend.create_flask_application import require_auth
from src.backend.initialize_database_schema import Inventory, Product, PriceHistory, ReceiptItem, Purchase, ShoppingListItem, User

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.40

recommendations_bp = Blueprint("recommendations", __name__, url_prefix="/recommendations")


def _coerce_datetime_for_comparison(value: datetime, reference_now: datetime) -> datetime:
    """Align stored datetimes with the timezone-awareness of the comparison value."""
    if value.tzinfo is None:
        return value.replace(tzinfo=None)
    return value.astimezone(reference_now.tzinfo) if reference_now.tzinfo else value.replace(tzinfo=None)


@recommendations_bp.route("", methods=["GET"])
@require_auth
def get_recommendations():
    """Get current recommendations (deals + seasonal)."""
    recs = generate_all_recommendations()
    return jsonify({
        "recommendations": recs,
        "count": len(recs),
    }), 200


def generate_all_recommendations() -> list:
    """Generate all recommendations for the household."""
    recommendations = []

    try:
        recommendations.extend(detect_price_deals())
    except Exception as e:
        logger.warning(f"Deal detection failed: {e}")

    try:
        recommendations.extend(detect_seasonal_patterns())
    except Exception as e:
        logger.warning(f"Seasonal detection failed: {e}")

    try:
        recommendations.extend(detect_low_inventory_items())
    except Exception as e:
        logger.warning(f"Low inventory detection failed: {e}")

    # Filter by confidence threshold
    recommendations = [r for r in recommendations if r["confidence"] >= CONFIDENCE_THRESHOLD]
    _annotate_shopping_status(recommendations)

    # Sort by confidence (highest first)
    recommendations.sort(key=lambda r: r["confidence"], reverse=True)

    return recommendations


def _annotate_shopping_status(recommendations: list) -> None:
    """Annotate recommendations with whether they are already in the shopping list."""
    session = g.db_session
    for rec in recommendations:
        product_id = rec.get("product_id")
        product_name = rec.get("product_name")
        query = session.query(ShoppingListItem, User).outerjoin(User, User.id == ShoppingListItem.user_id).filter(ShoppingListItem.status == "open")
        if product_id:
            query = query.filter(ShoppingListItem.product_id == product_id)
        elif product_name:
            query = query.filter(func.lower(ShoppingListItem.name) == product_name.lower())
        else:
            rec["in_shopping_list"] = False
            continue
        existing = query.order_by(ShoppingListItem.created_at.desc()).first()
        rec["in_shopping_list"] = bool(existing)
        if existing:
            item, user = existing
            rec["shopping_list_item_id"] = item.id
            rec["shopping_list_by"] = user.name if user and user.name else None


def detect_price_deals() -> list:
    """Detect products currently priced below their 3-month average."""
    deals = []
    session = g.db_session
    three_months_ago = datetime.now(timezone.utc) - timedelta(days=90)

    products = session.query(Product).all()

    for product in products:
        prices = (
            session.query(PriceHistory.price)
            .filter(
                PriceHistory.product_id == product.id,
                PriceHistory.date >= three_months_ago,
            )
            .order_by(PriceHistory.date)
            .all()
        )

        price_values = [p[0] for p in prices if p[0] is not None and p[0] > 0]

        if len(price_values) < 3:
            continue

        avg_price = sum(price_values) / len(price_values)
        current_price = price_values[-1]  # Most recent

        if current_price < avg_price * 0.9:
            confidence = min((avg_price - current_price) / avg_price * 5, 1.0)
            if confidence >= CONFIDENCE_THRESHOLD:
                discount_pct = round((1 - current_price / avg_price) * 100, 1)
                deals.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "category": product.category,
                    "reason": "deal",
                    "confidence": round(confidence, 2),
                    "current_price": round(current_price, 2),
                    "avg_price": round(avg_price, 2),
                    "discount_pct": discount_pct,
                    "message": (
                        f"💰 {product.name} on sale! "
                        f"Usually ${avg_price:.2f}, now ${current_price:.2f} "
                        f"({discount_pct}% off)"
                    ),
                })

    return deals


def detect_seasonal_patterns() -> list:
    """Detect products overdue for repurchase based on buying frequency."""
    seasonal = []
    session = g.db_session

    products = session.query(Product).all()

    for product in products:
        # Get purchase dates for this product
        purchase_dates = (
            session.query(Purchase.date)
            .join(ReceiptItem, ReceiptItem.purchase_id == Purchase.id)
            .filter(ReceiptItem.product_id == product.id)
            .order_by(Purchase.date)
            .all()
        )

        dates = [p[0] for p in purchase_dates if p[0] is not None]

        if len(dates) < 3:
            continue

        # Calculate intervals between purchases
        intervals = []
        for i in range(len(dates) - 1):
            delta = (dates[i + 1] - dates[i]).days
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            continue

        avg_frequency = median(intervals)
        now = datetime.now(timezone.utc)
        last_purchase = _coerce_datetime_for_comparison(dates[-1], now)
        compare_now = now if last_purchase.tzinfo is not None else now.replace(tzinfo=None)
        days_since_last = (compare_now - last_purchase).days

        if days_since_last > avg_frequency * 1.2:
            confidence = min((days_since_last / avg_frequency - 1.0) * 2.5, 1.0)
            if confidence >= CONFIDENCE_THRESHOLD:
                seasonal.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "category": product.category,
                    "reason": "seasonal",
                    "confidence": round(confidence, 2),
                    "days_since_last": days_since_last,
                    "avg_frequency_days": round(avg_frequency, 1),
                    "message": (
                        f"🛒 You usually buy {product.name} every "
                        f"{avg_frequency:.0f} days. It's been {days_since_last} days."
                    ),
                })

    return seasonal


def detect_low_inventory_items() -> list:
    """Recommend items that were manually marked low or fell below threshold."""
    session = g.db_session
    low_items = (
        session.query(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .filter(
            Inventory.is_active_window.is_(True),
            (Inventory.manual_low.is_(True)) |
            ((Inventory.threshold.isnot(None)) & (Inventory.quantity < Inventory.threshold))
        )
        .all()
    )

    recommendations = []
    for inventory_item, product in low_items:
        reason = "manual_low" if inventory_item.manual_low else "low_stock"
        confidence = 0.95 if inventory_item.manual_low else 0.85
        display_name = product.display_name or product.name
        message = (
            f"🛒 {display_name} was marked low and may need restocking."
            if inventory_item.manual_low
            else f"🛒 {display_name} is below its low-stock threshold."
        )
        recommendations.append({
            "product_id": product.id,
            "product_name": display_name,
            "category": product.category,
            "reason": reason,
            "confidence": round(confidence, 2),
            "current_quantity": inventory_item.quantity,
            "threshold": inventory_item.threshold,
            "message": message,
        })
    return recommendations
