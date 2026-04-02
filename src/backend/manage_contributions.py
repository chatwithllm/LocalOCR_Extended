"""Contribution summary and scoring transparency endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, g
from sqlalchemy import and_, func, or_

from src.backend.contribution_scores import SCORE_RULES, sum_bonus_points
from src.backend.create_flask_application import require_auth
from src.backend.enrich_product_names import product_needs_review
from src.backend.initialize_database_schema import (
    ContributionEvent,
    Inventory,
    Product,
    Purchase,
    ReceiptItem,
    ShoppingListItem,
    Store,
    TelegramReceipt,
)
from src.backend.normalize_product_names import get_product_display_name


contributions_bp = Blueprint("contributions", __name__, url_prefix="/contributions")


def _serialize_event(event_type: str, points: int, description: str, created_at, source: str) -> dict:
    return {
        "event_type": event_type,
        "points": int(points or 0),
        "description": description,
        "created_at": created_at.isoformat() if created_at else None,
        "source": source,
    }


@contributions_bp.route("/summary", methods=["GET"])
@require_auth
def contribution_summary():
    session = g.db_session
    user = g.current_user

    receipt_count = session.query(Purchase).filter(Purchase.user_id == user.id).count()
    ocr_fix_count = (
        session.query(Product)
        .filter(Product.reviewed_by_id == user.id, Product.review_state == "resolved")
        .count()
    )
    bonus_points = sum_bonus_points(session, user.id)
    receipt_points = receipt_count * 5
    ocr_points = ocr_fix_count * 20
    total_score = receipt_points + ocr_points + bonus_points

    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    contribution_events = (
        session.query(ContributionEvent)
        .filter(ContributionEvent.user_id == user.id)
        .order_by(ContributionEvent.created_at.desc())
        .limit(20)
        .all()
    )
    receipt_events = (
        session.query(Purchase, Store)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .filter(Purchase.user_id == user.id, Purchase.created_at >= recent_cutoff)
        .order_by(Purchase.created_at.desc())
        .limit(10)
        .all()
    )
    ocr_events = (
        session.query(Product)
        .filter(
            Product.reviewed_by_id == user.id,
            Product.review_state == "resolved",
            Product.reviewed_at.isnot(None),
            Product.reviewed_at >= recent_cutoff,
        )
        .order_by(Product.reviewed_at.desc())
        .limit(10)
        .all()
    )

    recent_items = [
        _serialize_event(
            event.event_type,
            event.points,
            event.description,
            event.created_at,
            "bonus",
        )
        for event in contribution_events
    ]
    recent_items.extend(
        _serialize_event(
            "receipt_processed",
            5,
            f"Processed a receipt from {store.name if store else 'Unknown store'}",
            purchase.created_at,
            "receipt",
        )
        for purchase, store in receipt_events
    )
    recent_items.extend(
        _serialize_event(
            "ocr_cleanup",
            20,
            f"Cleaned up {get_product_display_name(product)}",
            product.reviewed_at,
            "ocr",
        )
        for product in ocr_events
    )
    recent_items.sort(key=lambda item: item["created_at"] or "", reverse=True)
    recent_items = recent_items[:20]

    pending_review_count = sum(1 for product in session.query(Product).all() if product_needs_review(product))
    review_receipt_count = (
        session.query(TelegramReceipt)
        .filter(
            TelegramReceipt.status == "review",
            TelegramReceipt.purchase_id.is_(None),
        )
        .count()
    )
    low_not_on_list_count = (
        session.query(Inventory)
        .outerjoin(
            ShoppingListItem,
            and_(
                ShoppingListItem.product_id == Inventory.product_id,
                ShoppingListItem.status == "open",
            ),
        )
        .filter(
            Inventory.is_active_window.is_(True),
            or_(
                Inventory.manual_low.is_(True),
                and_(Inventory.threshold.isnot(None), Inventory.quantity < Inventory.threshold),
            ),
            ShoppingListItem.id.is_(None),
        )
        .count()
    )
    open_shopping_count = session.query(ShoppingListItem).filter(ShoppingListItem.status == "open").count()

    opportunities = [
        {
            "title": "Approve review receipts",
            "count": review_receipt_count,
            "description": "Finish receipts that still need review so they become real purchases and earn receipt credit.",
            "page": "receipts",
            "cta": "Open Receipts",
        },
        {
            "title": "Move low items to the shopping flow",
            "count": low_not_on_list_count,
            "description": "Low items without a shopping list entry are a good next fix for the household.",
            "page": "inventory",
            "cta": "Open Inventory",
        },
        {
            "title": "Close out shopping items",
            "count": open_shopping_count,
            "description": "Mark bought items so the shopping list stays fresh.",
            "page": "shopping",
            "cta": "Open Shopping List",
        },
    ]
    if getattr(user, "role", "user") == "admin":
        opportunities.insert(1, {
            "title": "Clean up OCR-heavy product names",
            "count": pending_review_count,
            "description": "Resolve fuzzy product names so the catalog stays readable and accurate.",
            "page": "settings",
            "cta": "Open Catalog Review",
        })

    return jsonify({
        "summary": {
            "total_score": total_score,
            "receipt_points": receipt_points,
            "ocr_points": ocr_points,
            "bonus_points": bonus_points,
            "receipts_processed": receipt_count,
            "ocr_fixes": ocr_fix_count,
        },
        "rules": SCORE_RULES,
        "recent_events": recent_items,
        "opportunities": opportunities,
        "notes": [
            "No points are awarded for no-op edits such as milk to MILK.",
            "Repeated toggles and duplicate actions are deduped to keep scoring fair.",
            "Marking an item low creates a pending contribution. Bigger points arrive only after that item reaches shopping and a later receipt confirms the restock.",
        ],
    }), 200
