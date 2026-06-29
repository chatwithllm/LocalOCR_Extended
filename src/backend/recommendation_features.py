"""Per-product features + candidate set for the recommendation pipeline. The
LLM is bad at arithmetic, so we compute the quantitative signals here and let it
judge relevance over them."""
from __future__ import annotations
import statistics
from datetime import datetime, timezone
from sqlalchemy import or_
from src.backend.initialize_database_schema import Product, Purchase, ReceiptItem


def _purchase_dates(session, product_id: int) -> list[datetime]:
    rows = (
        session.query(Purchase.date)
        .join(ReceiptItem, ReceiptItem.purchase_id == Purchase.id)
        .filter(ReceiptItem.product_id == product_id)
        .filter(or_(Purchase.transaction_type.is_(None),
                    Purchase.transaction_type != "refund"))
        .order_by(Purchase.date)
        .all()
    )
    return [r[0] for r in rows if r[0] is not None]


def _cobought_names(session, product_id: int, limit: int = 3) -> list[str]:
    purchase_ids = [
        r[0] for r in session.query(ReceiptItem.purchase_id)
        .filter(ReceiptItem.product_id == product_id).distinct().all()
    ]
    if not purchase_ids:
        return []
    from collections import Counter
    counts: Counter = Counter()
    rows = (
        session.query(ReceiptItem.product_id, Product.name)
        .join(Product, Product.id == ReceiptItem.product_id)
        .filter(ReceiptItem.purchase_id.in_(purchase_ids))
        .filter(ReceiptItem.product_id != product_id)
        .all()
    )
    for pid, name in rows:
        if name:
            counts[name] += 1
    return [name for name, _ in counts.most_common(limit)]


def build_recommendation_candidates(session, *, now: datetime | None = None,
                                    cap: int = 30) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    candidates: list[dict] = []
    for product in session.query(Product).all():
        dates = _purchase_dates(session, product.id)
        if not dates:
            continue
        count = len(dates)
        last = dates[-1]
        last_cmp = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        days_since_last = (now - last_cmp).days
        intervals = [
            (dates[i + 1] - dates[i]).days
            for i in range(len(dates) - 1)
            if (dates[i + 1] - dates[i]).days > 0
        ]
        mean_interval = statistics.fmean(intervals) if intervals else None
        interval_stdev = statistics.pstdev(intervals) if len(intervals) > 1 else None
        overdue_ratio = (days_since_last / mean_interval) if mean_interval else None
        one_off = count <= 1 or (count == 2 and days_since_last > 120)
        candidates.append({
            "product_id": product.id,
            "name": product.name,
            "category": product.category,
            "purchase_count": count,
            "days_since_last": days_since_last,
            "mean_interval": round(mean_interval, 1) if mean_interval else None,
            "interval_stdev": round(interval_stdev, 1) if interval_stdev else None,
            "overdue_ratio": round(overdue_ratio, 2) if overdue_ratio else None,
            "on_hand_low": bool(getattr(product, "is_low", False)),
            "price_drop": False,
            "one_off": one_off,
            "cobought_with": _cobought_names(session, product.id),
        })

    def sort_key(c):
        return (c["overdue_ratio"] or 0, -(c["days_since_last"] or 9999))
    candidates.sort(key=sort_key, reverse=True)
    return candidates[:cap]
