"""Contribution summary and scoring transparency endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, g
from sqlalchemy import and_, func, or_

from src.backend.contribution_scores import SCORE_RULES, sum_bonus_points, sum_floating_points
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
    User,
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


def _build_user_contribution_payload(session, user) -> dict:
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    receipt_count = session.query(Purchase).filter(Purchase.user_id == user.id).count()
    ocr_fix_count = (
        session.query(Product)
        .filter(Product.reviewed_by_id == user.id, Product.review_state == "resolved")
        .count()
    )
    bonus_points = sum_bonus_points(session, user.id)
    floating_points = sum_floating_points(session, user.id)
    receipt_points = receipt_count * 5
    ocr_points = ocr_fix_count * 20
    total_score = receipt_points + ocr_points + bonus_points

    contribution_events = (
        session.query(ContributionEvent)
        .filter(ContributionEvent.user_id == user.id)
        .order_by(ContributionEvent.created_at.desc())
        .limit(30)
        .all()
    )
    receipt_events = (
        session.query(Purchase, Store)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .filter(Purchase.user_id == user.id, Purchase.created_at >= recent_cutoff)
        .order_by(Purchase.created_at.desc())
        .limit(12)
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
        .limit(12)
        .all()
    )

    recent_items = [
        {
            **_serialize_event(
                event.event_type,
                event.points,
                event.description,
                event.created_at,
                "bonus",
            ),
            "status": event.status,
            "metadata": json.loads(event.metadata_json) if event.metadata_json else {},
        }
        for event in contribution_events
    ]
    recent_items.extend(
        {
            **_serialize_event(
                "receipt_processed",
                5,
                f"Processed a receipt from {store.name if store else 'Unknown store'}",
                purchase.created_at,
                "receipt",
            ),
            "status": "finalized",
            "metadata": {"purchase_id": purchase.id},
        }
        for purchase, store in receipt_events
    )
    recent_items.extend(
        {
            **_serialize_event(
                "ocr_cleanup",
                20,
                f"Cleaned up {get_product_display_name(product)}",
                product.reviewed_at,
                "ocr",
            ),
            "status": "finalized",
            "metadata": {"product_id": product.id},
        }
        for product in ocr_events
    )
    recent_items.sort(key=lambda item: item["created_at"] or "", reverse=True)
    recent_items = recent_items[:30]

    category_totals = {
        "receipts": receipt_points,
        "ocr_cleanup": ocr_points,
        "system_help": bonus_points,
        "floating": floating_points,
    }

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "avatar_emoji": user.avatar_emoji,
        },
        "summary": {
            "total_score": total_score,
            "receipt_points": receipt_points,
            "ocr_points": ocr_points,
            "bonus_points": bonus_points,
            "floating_points": floating_points,
            "receipts_processed": receipt_count,
            "ocr_fixes": ocr_fix_count,
        },
        "categories": category_totals,
        "recent_events": recent_items,
    }


@contributions_bp.route("/summary", methods=["GET"])
@require_auth
def contribution_summary():
    session = g.db_session
    user = g.current_user
    payload = _build_user_contribution_payload(session, user)

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
    missing_store_preference_count = (
        session.query(ShoppingListItem)
        .filter(
            ShoppingListItem.status == "open",
            or_(ShoppingListItem.preferred_store.is_(None), ShoppingListItem.preferred_store == ""),
        )
        .count()
    )

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
        {
            "title": "Route shopping items to stores",
            "count": missing_store_preference_count,
            "description": "Assign store preference so the shopping list groups cleanly and future trips are easier to plan.",
            "page": "shopping",
            "cta": "Set Store Preferences",
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
        "summary": payload["summary"],
        "rules": SCORE_RULES,
        "recent_events": payload["recent_events"],
        "opportunities": opportunities,
        "notes": [
            "No points are awarded for no-op edits such as milk to MILK.",
            "Repeated toggles and duplicate actions are deduped to keep scoring fair.",
            "Marking an item low creates a pending contribution. Bigger points arrive only after that item reaches shopping and a later receipt confirms the restock.",
            "Setting a missing store preference for a shopping item earns points because it helps group the list into real store stops.",
            "Recommendation confirmations are floating points until the item is actually bought. Deleting or reopening the item removes those points from the live score.",
        ],
    }), 200


@contributions_bp.route("/users/<int:user_id>", methods=["GET"])
@require_auth
def contribution_detail(user_id: int):
    session = g.db_session
    user = session.query(User).filter_by(id=user_id, is_active=True).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(_build_user_contribution_payload(session, user)), 200
