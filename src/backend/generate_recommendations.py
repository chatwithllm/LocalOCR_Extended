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
import re
from datetime import datetime, timedelta, timezone
from statistics import median

from flask import Blueprint, g, jsonify
from sqlalchemy import and_, func, or_

from src.backend.create_flask_application import require_auth
from src.backend.initialize_database_schema import ContributionEvent, Inventory, Product, PriceHistory, ReceiptItem, Purchase, ShoppingListItem, User
from src.backend.normalize_product_names import canonicalize_product_name

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.40
FAMILY_TOKEN_STOPWORDS = {
    "organic", "org", "fresh", "large", "small", "medium", "extra", "pink", "lady",
    "red", "green", "yellow", "whole", "baby", "mini", "seedless", "boneless", "skinless",
    "count", "ct", "dozen", "pack", "packs", "pk", "case", "lb", "lbs", "oz", "gal",
    "qt", "pt", "ml", "l", "liter", "liters", "roll", "rolls", "cup", "cups", "bottle",
    "bottles", "can", "cans", "jar", "jars", "box", "boxes", "bag", "bags", "tray", "trays",
}

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
    recommendations = _filter_confirmed_shopping_recommendations(recommendations)
    recommendations = _group_recommendations_by_family(recommendations)
    _annotate_shopping_status(recommendations)

    # Sort by confidence (highest first)
    recommendations.sort(key=lambda r: r["confidence"], reverse=True)

    return recommendations


def _filter_confirmed_shopping_recommendations(recommendations: list[dict]) -> list[dict]:
    """Remove recommendations that already have an open, confirmed shopping action."""
    session = g.db_session
    open_recommendation_items = (
        session.query(ShoppingListItem)
        .filter(
            ShoppingListItem.status == "open",
            ShoppingListItem.source == "recommendation",
        )
        .all()
    )
    if not open_recommendation_items:
        return recommendations

    open_item_ids = [item.id for item in open_recommendation_items]
    confirmed_subject_ids = {
        int(subject_id)
        for (subject_id,) in (
            session.query(ContributionEvent.subject_id)
            .filter(
                ContributionEvent.subject_type == "shopping_item",
                ContributionEvent.subject_id.in_(open_item_ids),
                or_(
                    and_(
                        ContributionEvent.event_type == "recommendation_accepted",
                        ContributionEvent.status.in_(["confirmed", "validated", "finalized"]),
                    ),
                    and_(
                        ContributionEvent.event_type.in_(["recommendation_peer_confirmed", "recommendation_self_confirmed"]),
                        ContributionEvent.status.in_(["floating", "finalized"]),
                    ),
                ),
            )
            .distinct()
            .all()
        )
        if subject_id is not None
    }
    if not confirmed_subject_ids:
        return recommendations

    handled_product_ids = {
        int(item.product_id)
        for item in open_recommendation_items
        if item.id in confirmed_subject_ids and item.product_id is not None
    }
    handled_names = {
        canonicalize_product_name(item.name)
        for item in open_recommendation_items
        if item.id in confirmed_subject_ids and item.name
    }

    filtered: list[dict] = []
    for rec in recommendations:
        product_id = rec.get("product_id")
        product_name = canonicalize_product_name(rec.get("product_name") or "")
        if product_id is not None and int(product_id) in handled_product_ids:
            continue
        if product_name and product_name in handled_names:
            continue
        filtered.append(rec)
    return filtered


def _recommendation_family_name(product_name: str | None) -> str:
    text = canonicalize_product_name(product_name or "")
    tokens = re.findall(r"[a-z]+", text.lower())
    meaningful = [token for token in tokens if token not in FAMILY_TOKEN_STOPWORDS]
    if not meaningful:
      meaningful = tokens
    if not meaningful:
        return canonicalize_product_name(product_name or "Unknown Item")
    family = meaningful[-1]
    if family.endswith("ies") and len(family) > 3:
        display = family[:-3] + "ies"
    elif family.endswith("s"):
        display = family
    else:
        display = family
    return display[:1].upper() + display[1:]


def _group_recommendations_by_family(recommendations: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for rec in recommendations:
        family_name = _recommendation_family_name(rec.get("product_name"))
        grouped.setdefault((str(rec.get("category") or "other"), family_name.lower()), []).append({**rec, "family_name": family_name})

    merged: list[dict] = []
    for (_category, _family_key), recs in grouped.items():
        if len(recs) == 1:
            single = recs[0]
            family_name = single.get("family_name") or _recommendation_family_name(single.get("product_name"))
            original_name = single.get("product_name")
            single["family_name"] = family_name
            single["product_name"] = family_name
            if original_name:
                single["variant_names"] = [original_name]
                if single.get("message"):
                    single["message"] = f"{family_name} may be worth restocking."
            merged.append(single)
            continue

        primary = max(recs, key=lambda item: (float(item.get("confidence") or 0), float(item.get("discount_pct") or 0), -(item.get("current_quantity") or 9999)))
        family_name = primary.get("family_name") or _recommendation_family_name(primary.get("product_name"))
        variant_names = []
        variant_ids = []
        reasons = set()
        for rec in recs:
            name = rec.get("product_name")
            if name and name not in variant_names:
                variant_names.append(name)
            product_id = rec.get("product_id")
            if product_id is not None and product_id not in variant_ids:
                variant_ids.append(product_id)
            if rec.get("reason"):
                reasons.add(str(rec["reason"]))

        grouped_rec = dict(primary)
        grouped_rec["product_name"] = family_name
        grouped_rec["variant_names"] = variant_names
        grouped_rec["product_ids"] = variant_ids
        grouped_rec["grouped_variant_count"] = len(variant_names)
        grouped_rec["message"] = (
            f"{family_name} may be worth restocking. "
            f"Usually bought as {', '.join(variant_names[:2])}"
            + ("…" if len(variant_names) > 2 else "")
        )
        if "manual_low" in reasons:
            grouped_rec["reason"] = "manual_low"
        elif "low_stock" in reasons:
            grouped_rec["reason"] = "low_stock"
        elif "deal" in reasons:
            grouped_rec["reason"] = "deal"
        elif "seasonal" in reasons:
            grouped_rec["reason"] = "seasonal"
        merged.append(grouped_rec)

    return merged


def _annotate_shopping_status(recommendations: list) -> None:
    """Annotate recommendations with whether they are already in the shopping list."""
    session = g.db_session
    for rec in recommendations:
        product_id = rec.get("product_id")
        product_ids = [pid for pid in (rec.get("product_ids") or []) if pid is not None]
        product_name = rec.get("product_name")
        query = session.query(ShoppingListItem, User).outerjoin(User, User.id == ShoppingListItem.user_id).filter(ShoppingListItem.status == "open")
        if product_ids:
            query = query.filter(ShoppingListItem.product_id.in_(product_ids))
        elif product_id:
            query = query.filter(ShoppingListItem.product_id == product_id)
        elif product_name:
            family_lower = product_name.lower()
            query = query.filter(
                or_(
                    func.lower(ShoppingListItem.name) == family_lower,
                    func.lower(ShoppingListItem.name).like(f"%{family_lower}%")
                )
            )
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
            .filter(or_(Purchase.transaction_type.is_(None), Purchase.transaction_type != "refund"))
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
