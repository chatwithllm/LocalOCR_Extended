"""
Step 18: Calculate Spending Analytics
======================================
PROMPT Reference: Phase 6, Step 18

Analytics endpoints for spending reports: total by period, by category,
price history trends, and deals captured (savings quantification).
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from flask import Blueprint, request, jsonify, g

from src.backend.create_flask_application import require_auth
from src.backend.initialize_database_schema import (
    Purchase, ReceiptItem, Product, Store, PriceHistory, BillMeta, BillProvider, BillServiceLine, CashTransaction
)
from src.backend.budgeting_domains import normalize_spending_domain
from src.backend.budgeting_rollups import normalize_transaction_type, signed_purchase_total, purchase_amount_sign
from src.backend.bill_cadence import month_matches_billing_cycle, normalize_billing_cycle
from src.backend.generate_bill_projections import generate_monthly_obligation_slots
from src.backend.manage_cash_transactions import (
    default_budget_category_for_personal_service,
    reconcile_personal_service_slots,
)

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")

_PROVIDER_ALIAS_STOPWORDS = {
    "inc",
    "llc",
    "ltd",
    "corp",
    "corporation",
    "company",
    "co",
    "services",
    "service",
    "billing",
    "bill",
    "payment",
    "payments",
    "portal",
    "online",
    "delivery",
    "energy",
    "utility",
    "utilities",
}

_PROVIDER_LOCATION_STOPWORDS = {
    "indiana",
    "indianapolis",
}


def _provider_display_name(meta, store) -> str:
    return ((getattr(meta, "provider_name", None) if meta else None) or (store.name if store else "") or "Unknown").strip() or "Unknown"


def _canonical_provider_name(name: str | None) -> str:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return "unknown"
    normalized = normalized.replace("&", "")
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    tokens = [token for token in normalized.split() if token]
    if not tokens:
        return "unknown"
    filtered = [
        token for token in tokens
        if token not in _PROVIDER_ALIAS_STOPWORDS
        and token not in _PROVIDER_LOCATION_STOPWORDS
    ]
    return " ".join(filtered or tokens)


def _provider_group_key(provider_name: str | None, provider_type: str | None, account_label: str | None = None) -> str:
    provider_token = _canonical_provider_name(provider_name)
    provider_type_token = str(provider_type or "other").strip().lower() or "other"
    account_token = str(account_label or "").strip().lower()
    return f"{provider_token}|{provider_type_token}|{account_token}"


def _service_types_from_meta(meta) -> list[str]:
    raw = getattr(meta, "service_types", None) if meta else None
    if not raw:
        fallback = str(getattr(meta, "provider_type", None) or "").strip().lower() if meta else ""
        return [fallback] if fallback else []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            values = [str(value or "").strip().lower() for value in parsed if str(value or "").strip()]
            fallback = str(getattr(meta, "provider_type", None) or "").strip().lower() if meta else ""
            return values or ([fallback] if fallback else [])
    except Exception:
        pass
    fallback = str(getattr(meta, "provider_type", None) or "").strip().lower() if meta else ""
    return [fallback] if fallback else []


def _obligation_amount_pattern(amounts: list[float]) -> tuple[str, float]:
    if not amounts or len(amounts) == 1:
        return "new", 0.0
    avg_amount = sum(amounts) / len(amounts)
    spread = max(amounts) - min(amounts)
    tolerance = max(5.0, abs(avg_amount) * 0.05)
    return ("fixed", round(spread, 2)) if spread <= tolerance else ("variable", round(spread, 2))


def _transaction_counts(purchases):
    purchase_count = 0
    refund_count = 0
    for purchase in purchases:
        if normalize_transaction_type(getattr(purchase, "transaction_type", None)) == "refund":
            refund_count += 1
        else:
            purchase_count += 1
    return purchase_count, refund_count


_BILL_RECEIPT_TYPES = {"utility_bill", "household_bill"}
_BILL_ITEM_KEYWORDS = (
    "gas charge",
    "water charge",
    "sewer charge",
    "electric charge",
    "trash charge",
    "service charge",
    "monthly service",
    "account balance as of",
    "balance forward",
    "late fee",
    "kwh",
    "ccf",
    "usage charge",
    "distribution charge",
    "delivery charge",
    "fuel charge",
)


def _is_bill_item_name(name: str | None) -> bool:
    """Heuristic: does this item name look like a utility/bill line item?"""
    lowered = str(name or "").strip().lower()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in _BILL_ITEM_KEYWORDS)


def _bill_provider_store_ids(session) -> set[int]:
    """Return store_ids for any merchant that has ever been seen as a bill provider.

    Once a merchant has had even a single household_obligations receipt (or a
    BillMeta sidecar), we treat all receipts from that merchant as bills — this
    papers over OCR misclassifications where some receipts from the same
    utility land in general_expense by mistake.
    """
    store_ids: set[int] = set()
    for row in (
        session.query(Purchase.store_id)
        .filter(
            Purchase.store_id.isnot(None),
            Purchase.domain.in_(("household_obligations", "utility")),
        )
        .distinct()
        .all()
    ):
        if row[0] is not None:
            store_ids.add(int(row[0]))
    for row in (
        session.query(Purchase.store_id)
        .join(BillMeta, BillMeta.purchase_id == Purchase.id)
        .filter(Purchase.store_id.isnot(None))
        .distinct()
        .all()
    ):
        if row[0] is not None:
            store_ids.add(int(row[0]))
    return store_ids


@analytics_bp.route("/expense-summary", methods=["GET"])
@require_auth
def get_general_expense_summary():
    """Return general-expense spend and merchant/item history."""
    from src.backend.initialize_database_schema import TelegramReceipt
    import json

    session = g.db_session
    months_back = request.args.get("months", 6, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    bill_store_ids = _bill_provider_store_ids(session)

    purchases = (
        session.query(Purchase, Store, TelegramReceipt)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .outerjoin(TelegramReceipt, TelegramReceipt.purchase_id == Purchase.id)
        .filter(Purchase.domain == "general_expense", Purchase.date >= cutoff)
        .order_by(Purchase.date.desc())
        .all()
    )

    total_spend = 0.0
    excluded_bill_purchases = 0
    excluded_bill_items = 0
    purchase_total = 0.0
    refund_total = 0.0
    merchant_summary = defaultdict(lambda: {"visits": 0, "refunds": 0, "total": 0.0, "purchase_total": 0.0, "refund_total": 0.0, "latest_date": None})
    item_summary = defaultdict(lambda: {"quantity": 0.0, "total": 0.0})
    category_summary = defaultdict(lambda: {"total": 0.0, "count": 0})
    recent_receipts = []

    for purchase, store, record in purchases:
        # Skip bill/utility receipts that landed in general_expense via OCR
        # misclassification (merchant previously identified as a bill provider,
        # receipt_type flagged as a bill, or default domain says household).
        receipt_type = str(getattr(record, "receipt_type", "") or "").strip().lower()
        default_domain = str(getattr(purchase, "default_spending_domain", "") or "").strip().lower()
        if (
            (purchase.store_id is not None and int(purchase.store_id) in bill_store_ids)
            or receipt_type in _BILL_RECEIPT_TYPES
            or default_domain in {"household_obligations", "utility"}
        ):
            excluded_bill_purchases += 1
            continue

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
            if _is_bill_item_name(name):
                excluded_bill_items += 1
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
        "excluded_bill_purchases": excluded_bill_purchases,
        "excluded_bill_items": excluded_bill_items,
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


@analytics_bp.route("/utility-summary", methods=["GET"])
@require_auth
def get_utility_summary():
    """Return utility & recurring bill spend analytics."""
    from datetime import date as date_type

    session = g.db_session
    months_back = request.args.get("months", 12, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)
    now_dt = datetime.now(timezone.utc)

    rows = (
        session.query(Purchase, Store, BillMeta)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .join(BillMeta, BillMeta.purchase_id == Purchase.id)
        .filter(
            Purchase.domain.in_(["utility", "household_obligations"]),
            Purchase.date >= cutoff,
            Purchase.date <= now_dt,
        )
        .order_by(Purchase.date.desc())
        .all()
    )

    total_spend = 0.0
    recurring_total = 0.0
    one_off_total = 0.0
    provider_summary: dict = {}
    category_summary: dict = {}
    monthly_totals: dict = {}
    recent_bills = []
    today = date_type.today()
    due_soon = []

    for purchase, store, meta in rows:
        signed_total = signed_purchase_total(purchase)
        transaction_type = normalize_transaction_type(getattr(purchase, "transaction_type", None))
        total_spend += signed_total

        is_recurring = bool(meta.is_recurring) if meta else True
        provider_name = _provider_display_name(meta, store)
        provider_type = (meta.provider_type if meta else None) or "other"
        service_types = _service_types_from_meta(meta)
        billing_cycle = (meta.billing_cycle_month if meta else None) or (
            purchase.date.strftime("%Y-%m") if purchase.date else None
        )
        budget_category = getattr(purchase, "default_budget_category", None) or "other_recurring"

        if is_recurring:
            recurring_total += signed_total
        else:
            one_off_total += signed_total

        pkey = _provider_group_key(
            provider_name,
            service_types[0] if service_types else provider_type,
            getattr(meta, "account_label", None) if meta else None,
        )
        if pkey not in provider_summary:
            provider_summary[pkey] = {
                "provider_name": provider_name,
                "provider_type": provider_type,
                "provider_category": "utility",
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

        if billing_cycle:
            monthly_totals[billing_cycle] = round(
                monthly_totals.get(billing_cycle, 0.0) + signed_total, 2
            )

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
            "source_type": "bill_receipt",
        })

    cash_rows = (
        session.query(CashTransaction, Purchase, BillServiceLine, BillProvider)
        .join(Purchase, Purchase.id == CashTransaction.purchase_id)
        .join(BillServiceLine, BillServiceLine.id == CashTransaction.service_line_id)
        .join(BillProvider, BillProvider.id == BillServiceLine.provider_id)
        .filter(Purchase.date >= cutoff, Purchase.date <= now_dt)
        .order_by(Purchase.date.desc())
        .all()
    )
    for tx, purchase, service_line, provider in cash_rows:
        signed_total = signed_purchase_total(purchase)
        transaction_type = normalize_transaction_type(getattr(purchase, "transaction_type", None))
        total_spend += signed_total
        recurring_total += signed_total
        provider_name = provider.canonical_name
        provider_type = service_line.service_type or provider.provider_type_hint or "other_personal_service"
        service_types = [provider_type]
        billing_cycle = tx.planning_month or (purchase.date.strftime("%Y-%m") if purchase.date else None)
        budget_category = getattr(purchase, "default_budget_category", None) or "other_recurring"

        pkey = _provider_group_key(provider_name, provider_type, service_line.account_label)
        if pkey not in provider_summary:
            provider_summary[pkey] = {
                "provider_name": provider_name,
                "provider_type": provider_type,
                "provider_category": provider.provider_category or "personal_service",
                "service_types": service_types,
                "total": 0.0,
                "purchase_count": 0,
                "refund_count": 0,
                "latest_date": None,
                "monthly_breakdown": {},
            }
        ps = provider_summary[pkey]
        ps["provider_category"] = provider.provider_category or ps.get("provider_category") or "personal_service"
        ps["total"] += signed_total
        if transaction_type == "refund":
            ps["refund_count"] += 1
        else:
            ps["purchase_count"] += 1
        if purchase.date and (ps["latest_date"] is None or purchase.date > ps["latest_date"]):
            ps["latest_date"] = purchase.date
        if billing_cycle:
            ps["monthly_breakdown"][billing_cycle] = round(
                ps["monthly_breakdown"].get(billing_cycle, 0.0) + signed_total,
                2,
            )

        if budget_category not in category_summary:
            category_summary[budget_category] = {
                "budget_category": budget_category,
                "total": 0.0,
                "purchase_count": 0,
                "refund_count": 0,
            }
        category_summary[budget_category]["total"] += signed_total
        category_summary[budget_category]["purchase_count"] += 1

        if billing_cycle:
            monthly_totals[billing_cycle] = round(monthly_totals.get(billing_cycle, 0.0) + signed_total, 2)

        if service_line.expected_payment_day:
            due_day = max(1, min(28, int(service_line.expected_payment_day)))
            due_soon_date = date_type.fromisoformat(f"{billing_cycle}-{due_day:02d}") if billing_cycle else None
            if due_soon_date:
                days_until = (due_soon_date - today).days
                if 0 <= days_until <= 14:
                    due_soon.append({
                        "purchase_id": purchase.id,
                        "provider_name": provider_name,
                        "provider_type": provider_type,
                        "provider_category": provider.provider_category or "personal_service",
                        "service_types": service_types,
                        "amount": round(signed_total, 2),
                        "due_date": due_soon_date.isoformat(),
                        "days_until_due": days_until,
                        "billing_cycle_month": billing_cycle,
                    })

        recent_bills.append({
            "purchase_id": purchase.id,
            "provider_name": provider_name,
            "provider_type": provider_type,
            "provider_category": provider.provider_category or "personal_service",
            "service_types": service_types,
            "date": purchase.date.strftime("%Y-%m-%d") if purchase.date else None,
            "billing_cycle_month": billing_cycle,
            "amount": round(signed_total, 2),
            "transaction_type": transaction_type,
            "is_recurring": True,
            "due_date": None,
            "budget_category": budget_category,
            "source_type": "cash_transaction",
        })

    provider_list = sorted(
        [
            {
                "provider_name": value["provider_name"],
                "provider_type": value["provider_type"],
                "provider_category": value.get("provider_category", "utility"),
                "service_types": value.get("service_types", []),
                "total": round(value["total"], 2),
                "purchase_count": value["purchase_count"],
                "refund_count": value["refund_count"],
                "average_monthly": round(
                    value["total"] / max(len(value["monthly_breakdown"]), 1), 2
                ),
                "latest_date": value["latest_date"].strftime("%Y-%m-%d") if value["latest_date"] else None,
                "monthly_breakdown": value["monthly_breakdown"],
            }
            for value in provider_summary.values()
        ],
        key=lambda item: (-item["total"], item["provider_name"]),
    )

    due_soon.sort(key=lambda item: item["days_until_due"])
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

    purchase_count, refund_count = _transaction_counts(
        [purchase for purchase, _, _ in rows] + [purchase for _, purchase, _, _ in cash_rows]
    )
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
        "monthly_totals": {key: value for key, value in sorted(monthly_totals.items())},
        "due_soon": due_soon,
        "recent_bills": recent_bills[:20],
    }), 200


@analytics_bp.route("/spend-by-person", methods=["GET"])
@require_auth
def get_spend_by_person():
    """Attribution-aware spend summary for a month.

    Returns per-person spend totals based on the receipt/line-item
    attribution fields (phase 1 of the attribution feature):

      - Line items with explicit per-item attribution roll up against
        that attribution (kind + user).
      - Line items without per-item attribution fall back to the
        receipt-level attribution.
      - Items still without any attribution roll into an "unset"
        bucket so the user can see how much hasn't been tagged yet.

    Response:
      {
        "month": "YYYY-MM",
        "household_total": 0.00,
        "unset_total": 0.00,
        "per_person": [
          {"user_id": 7, "name": "Sam", "total": 123.45}
        ],
        "grand_total": 0.00
      }
    """
    from src.backend.initialize_database_schema import User

    session = g.db_session
    month = (request.args.get("month") or "").strip()
    try:
        anchor = datetime.strptime(month, "%Y-%m") if month else datetime.now(timezone.utc)
    except ValueError:
        return jsonify({"error": "Month must be in YYYY-MM format"}), 400

    month_start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)

    rows = (
        session.query(ReceiptItem, Purchase)
        .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
        .filter(Purchase.date >= month_start)
        .filter(Purchase.date < next_month_start)
        .all()
    )

    household_total = 0.0
    unset_total = 0.0
    per_user_totals: dict[int, float] = {}

    for item, purchase in rows:
        line_total = float(item.quantity or 0) * float(item.unit_price or 0)
        if (getattr(purchase, "transaction_type", None) or "").lower() == "refund":
            line_total = -line_total

        # Per-item attribution wins; fall back to receipt-level.
        kind = item.attribution_kind or purchase.attribution_kind
        user_id = item.attribution_user_id or purchase.attribution_user_id

        if kind == "personal" and user_id:
            per_user_totals[user_id] = per_user_totals.get(user_id, 0.0) + line_total
        elif kind == "household":
            household_total += line_total
        else:
            unset_total += line_total

    user_names: dict[int, str] = {}
    if per_user_totals:
        for u in (
            session.query(User)
            .filter(User.id.in_(list(per_user_totals.keys())))
            .all()
        ):
            user_names[u.id] = u.name or u.email or f"User {u.id}"

    per_person = sorted(
        [
            {
                "user_id": uid,
                "name": user_names.get(uid, f"User {uid}"),
                "total": round(total, 2),
            }
            for uid, total in per_user_totals.items()
        ],
        key=lambda row: row["total"],
        reverse=True,
    )

    grand_total = household_total + unset_total + sum(p["total"] for p in per_person)

    return jsonify({
        "month": month_start.strftime("%Y-%m"),
        "household_total": round(household_total, 2),
        "unset_total": round(unset_total, 2),
        "per_person": per_person,
        "grand_total": round(grand_total, 2),
    }), 200


@analytics_bp.route("/recurring-obligations", methods=["GET"])
@require_auth
def get_recurring_obligations():
    """Return a derived recurring-obligations planning view for a selected month."""
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
            Purchase.date <= datetime.now(timezone.utc),
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
            "billing_cycle": normalize_billing_cycle(getattr(meta, "billing_cycle", None)),
            "anchor_month": (meta.planning_month or meta.billing_cycle_month or "").strip() or None,
            "history": [],
            "current_entry": None,
            "latest_date": None,
            "latest_due_date": None,
            "latest_auto_pay": False,
            "latest_payment_status": None,
            "latest_payment_confirmed_at": None,
            "latest_billing_cycle": None,
            "provider_id": meta.provider_id,
            "service_line_id": meta.service_line_id,
        })

        history_entry = {
            "purchase_id": purchase.id,
            "billing_cycle_month": billing_cycle,
            "date": purchase.date.strftime("%Y-%m-%d") if purchase.date else None,
            "amount": signed_total,
            "transaction_type": transaction_type,
            "due_date": meta.due_date.isoformat() if meta.due_date else None,
            "auto_pay": bool(meta.auto_pay),
            "payment_status": meta.payment_status,
        }
        obligation["history"].append(history_entry)

        if billing_cycle == selected_month and obligation["current_entry"] is None:
            obligation["current_entry"] = history_entry

        # Track the most-recent BillMeta's auto-pay + payment status so the
        # status derivation below can recognise an already-settled autopay
        # obligation (the sync-autopay sweep may have flipped payment_status
        # to "paid" on the *previous* month's BillMeta; without this the
        # current-month view renders "OVERDUE" even though the bill in hand
        # is fully settled).
        if purchase.date and (obligation["latest_date"] is None or purchase.date >= obligation["latest_date"]):
            obligation["latest_date"] = purchase.date
            obligation["latest_auto_pay"] = bool(meta.auto_pay)
            obligation["latest_payment_status"] = (meta.payment_status or "").strip().lower() or None
            obligation["latest_payment_confirmed_at"] = meta.payment_confirmed_at
            obligation["latest_billing_cycle"] = billing_cycle
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
        is_due = month_matches_billing_cycle(
            selected_month,
            obligation.get("anchor_month"),
            obligation.get("billing_cycle"),
        )
        variance = round(actual_amount - expected_amount, 2) if current_entry else round(-expected_amount, 2)
        status = "entered" if current_entry else ("outstanding" if is_due else "not_due")

        # Autopay-settled rescue: when the latest BillMeta has auto_pay=True
        # and its payment_status has been flipped to "paid" by the
        # sync-autopay sweep, don't surface the obligation as outstanding
        # /overdue in the current view. The user set up autopay explicitly;
        # the previous cycle's bill is confirmed paid, and no action is
        # required until the next bill actually arrives from the provider.
        is_autopay_settled = (
            status == "outstanding"
            and bool(obligation.get("latest_auto_pay"))
            and obligation.get("latest_payment_status") == "paid"
        )
        if is_autopay_settled:
            status = "autopay_settled"

        if status == "entered":
            entered_count += 1
        elif status == "outstanding":
            outstanding_count += 1
        elif status == "autopay_settled":
            entered_count += 1
        if amount_pattern == "fixed":
            fixed_count += 1
        elif amount_pattern == "variable":
            variable_count += 1
        else:
            new_count += 1
        expected_total += expected_amount
        actual_total += actual_amount

        latest_payment_confirmed_at = obligation.get("latest_payment_confirmed_at")
        obligation_list.append({
            "provider_name": obligation["provider_name"],
            "provider_type": obligation["provider_type"],
            "service_types": obligation.get("service_types", []),
            "account_label": obligation["account_label"],
            "budget_category": obligation["budget_category"],
            "billing_cycle": obligation["billing_cycle"],
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
            "is_autopay": bool(obligation.get("latest_auto_pay")),
            "is_autopay_settled": status == "autopay_settled",
            "latest_payment_status": obligation.get("latest_payment_status"),
            "latest_payment_confirmed_at": latest_payment_confirmed_at.isoformat() if latest_payment_confirmed_at else None,
            "latest_billing_cycle_month": obligation.get("latest_billing_cycle"),
            "history_count": len(obligation["history"]),
            "history_preview": obligation["history"][:4],
            "provider_category": "utility",
            "provider_id": obligation.get("provider_id"),
            "service_line_id": obligation.get("service_line_id"),
        })

    personal_status_map = reconcile_personal_service_slots(session, selected_month)
    personal_service_lines = (
        session.query(BillServiceLine, BillProvider)
        .join(BillProvider, BillProvider.id == BillServiceLine.provider_id)
        .filter(
            BillProvider.provider_category == "personal_service",
            BillServiceLine.is_active.is_(True),
        )
        .all()
    )
    for service_line, provider in personal_service_lines:
        history_rows = (
            session.query(CashTransaction, Purchase)
            .join(Purchase, Purchase.id == CashTransaction.purchase_id)
            .filter(CashTransaction.service_line_id == service_line.id)
            .order_by(CashTransaction.transaction_date.desc(), CashTransaction.id.desc())
            .limit(6)
            .all()
        )
        history = [
            {
                "purchase_id": tx.purchase_id,
                "cash_transaction_id": tx.id,
                "billing_cycle_month": tx.planning_month,
                "date": tx.transaction_date.isoformat() if tx.transaction_date else None,
                "amount": round(float(tx.amount or 0), 2),
                "transaction_type": normalize_transaction_type(getattr(purchase, "transaction_type", None)),
                "due_date": None,
                "source_type": "cash_transaction",
            }
            for tx, purchase in history_rows
        ]
        amounts = [abs(entry["amount"]) for entry in history if entry["amount"] is not None]
        expected_amount = round(sum(amounts) / len(amounts), 2) if amounts else 0.0
        amount_pattern, amount_spread = _obligation_amount_pattern(amounts)
        status_info = personal_status_map.get(service_line.id, {})
        latest_entry = history[0] if history else None
        current_entry = (
            latest_entry
            if latest_entry
            and latest_entry.get("billing_cycle_month") == selected_month
            and latest_entry.get("date")
            and latest_entry["date"] <= datetime.now().date().isoformat()
            else None
        )
        if current_entry:
            entered_count += 1
            actual_amount = current_entry["amount"]
            status = "entered"
        else:
            status = status_info.get("status", "upcoming")
            actual_amount = 0.0
            if status == "overdue":
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
            "provider_name": provider.canonical_name,
            "provider_type": service_line.service_type or provider.provider_type_hint or "other_personal_service",
            "provider_category": provider.provider_category or "personal_service",
            "service_types": [service_line.service_type] if service_line.service_type else [],
            "account_label": service_line.account_label,
            "budget_category": default_budget_category_for_personal_service(service_line.service_type),
            "billing_cycle": "monthly",
            "status": "entered" if status == "paid" else status,
            "amount_pattern": amount_pattern,
            "amount_spread": amount_spread,
            "expected_amount": expected_amount,
            "actual_amount": actual_amount,
            "variance": round(actual_amount - expected_amount, 2) if actual_amount else round(-expected_amount, 2),
            "selected_month": selected_month,
            "purchase_id": latest_entry["purchase_id"] if latest_entry else None,
            "current_entry": current_entry,
            "last_seen_date": latest_entry["date"] if latest_entry else None,
            "last_due_date": (
                f"{selected_month}-{int(service_line.expected_payment_day):02d}"
                if service_line.expected_payment_day
                else None
            ),
            "history_count": len(history),
            "history_preview": history[:4],
            "transaction_history_count": len(history),
            "source_type": "cash_transaction",
            "service_line_id": service_line.id,
            "provider_id": provider.id,
            "expected_payment_day": service_line.expected_payment_day,
            "preferred_payment_method": service_line.preferred_payment_method,
            "planning_month_rule": service_line.planning_month_rule,
            "preferred_contact_method": provider.preferred_contact_method,
            "payment_handle": provider.payment_handle,
        })

    obligation_list.sort(
        key=lambda item: (
            0 if item["status"] == "outstanding" else 1 if item["status"] == "entered" else 2,
            item["provider_name"].lower(),
        )
    )

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


@analytics_bp.route("/bill-projections", methods=["GET"])
@require_auth
def get_bill_projections():
    """Expose the Phase 6 analytical projection engine to the frontend."""
    session = g.db_session
    month = (request.args.get("month") or "").strip()
    if not month:
        month = datetime.now(timezone.utc).strftime("%Y-%m")

    user_id = getattr(g, "current_user", None).id if getattr(g, "current_user", None) else None
    
    try:
        slots = generate_monthly_obligation_slots(session, month, user_id=user_id)
        
        # Add summary stats for the frontend dashboard
        summary = {
            "total_count": len(slots),
            "actual_count": sum(1 for s in slots if s["slot_type"] == "actual"),
            "projected_count": sum(1 for s in slots if s["slot_type"] == "projected"),
            "missing_count": sum(1 for s in slots if s["slot_type"] == "projected" and s["payment_status"] == "missing"),
            "anomaly_count": sum(1 for s in slots if s["is_anomaly"]),
            "total_expected_value": round(sum(s["amount"] for s in slots), 2)
        }
        
        return jsonify({
            "month": month,
            "slots": slots,
            "summary": summary
        }), 200
    except Exception as e:
        logger.error(f"Failed to generate bill projections: {e}")
        return jsonify({"error": str(e)}), 500
