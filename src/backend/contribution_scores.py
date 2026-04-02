"""Contribution scoring helpers and shared rules."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.backend.initialize_database_schema import ContributionEvent


SCORE_RULES = [
    {
        "key": "receipt_processed",
        "title": "Process a receipt",
        "points": 5,
        "description": "Earned when a receipt becomes a saved purchase.",
    },
    {
        "key": "ocr_cleanup",
        "title": "Clean up OCR names",
        "points": 20,
        "description": "Earned when a product review is resolved with a meaningful fix.",
    },
    {
        "key": "inventory_low_marked",
        "title": "Mark an item low",
        "points": 0,
        "description": "Creates a pending low-stock contribution. Points arrive only after the shopping and receipt loop validates it.",
    },
    {
        "key": "inventory_low_cleared",
        "title": "Clear a low flag",
        "points": 3,
        "description": "Rewarded when you clear a low flag after restocking.",
    },
    {
        "key": "inventory_location_updated",
        "title": "Improve item location",
        "points": 2,
        "description": "Rewarded when you move an item to a meaningfully different storage location.",
    },
    {
        "key": "shopping_item_added",
        "title": "Add to shopping list",
        "points": 1,
        "description": "Rewarded when you add a useful new item to the shopping list.",
    },
    {
        "key": "shopping_item_purchased",
        "title": "Mark shopping item bought",
        "points": 2,
        "description": "Rewarded when you close the loop on an open shopping item.",
    },
    {
        "key": "low_workflow_validated",
        "title": "Validated low-stock call",
        "points": 5,
        "description": "Earned when a low-stock mark is confirmed by shopping activity and a later receipt.",
    },
    {
        "key": "shopping_item_validated",
        "title": "Validated shopping help",
        "points": 3,
        "description": "Earned when a shopping-list add helps close a low-stock loop and is later confirmed by a receipt.",
    },
]


POINTS = {rule["key"]: rule["points"] for rule in SCORE_RULES}


def normalize_text(value: str | None) -> str:
    """Normalize simple user-facing text for no-op comparisons."""
    return " ".join(str(value or "").strip().lower().split())


def meaningful_text_change(before: str | None, after: str | None) -> bool:
    """Return True only when a text change is meaningfully different."""
    return normalize_text(before) != normalize_text(after)


def award_contribution_event(
    session,
    *,
    user_id: int | None,
    event_type: str,
    description: str,
    points: int | None = None,
    subject_type: str | None = None,
    subject_id: int | None = None,
    status: str = "finalized",
    dedupe_minutes: int = 180,
    metadata: dict | None = None,
):
    """Create a contribution event if it is meaningful and not a near-duplicate."""
    if not user_id or not event_type or not description:
        return None

    event_points = POINTS.get(event_type, 0) if points is None else int(points)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(dedupe_minutes, 1))
    existing = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.user_id == user_id,
            ContributionEvent.event_type == event_type,
            ContributionEvent.subject_type == subject_type,
            ContributionEvent.subject_id == subject_id,
            ContributionEvent.status == status,
            ContributionEvent.description == description,
            ContributionEvent.created_at >= cutoff,
        )
        .order_by(ContributionEvent.created_at.desc())
        .first()
    )
    if existing:
        return existing

    event = ContributionEvent(
        user_id=user_id,
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        status=status,
        points=event_points,
        description=description,
        metadata_json=json.dumps(metadata or {}) if metadata else None,
    )
    session.add(event)
    return event


def sum_bonus_points(session, user_id: int | None) -> int:
    """Return contribution-event bonus points for a user."""
    if not user_id:
        return 0
    rows = (
        session.query(ContributionEvent.points)
        .filter(
            ContributionEvent.user_id == user_id,
            ContributionEvent.status == "finalized",
        )
        .all()
    )
    return int(sum(row[0] or 0 for row in rows))


def cancel_pending_low_event(session, *, product_id: int | None):
    """Cancel pending low contributions for a product when the flag is cleared."""
    if not product_id:
        return []
    events = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.event_type == "inventory_low_marked",
            ContributionEvent.subject_type == "product",
            ContributionEvent.subject_id == product_id,
            ContributionEvent.status == "pending_validation",
        )
        .all()
    )
    for event in events:
        event.status = "cancelled"
    return events


def validate_low_workflow(session, *, product_id: int, purchase_id: int, product_name: str):
    """Finalize low-stock contributions only when shopping + receipt activity confirms them."""
    from src.backend.initialize_database_schema import ShoppingListItem

    if not product_id or not purchase_id:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=45)
    pending_events = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.event_type == "inventory_low_marked",
            ContributionEvent.subject_type == "product",
            ContributionEvent.subject_id == product_id,
            ContributionEvent.status == "pending_validation",
            ContributionEvent.created_at >= cutoff,
        )
        .order_by(ContributionEvent.created_at.asc())
        .all()
    )
    awarded = []
    for event in pending_events:
        shopping_item = (
            session.query(ShoppingListItem)
            .filter(
                ShoppingListItem.product_id == product_id,
                ShoppingListItem.created_at >= event.created_at,
            )
            .order_by(ShoppingListItem.created_at.asc())
            .first()
        )
        if not shopping_item:
            continue

        event.status = "validated"
        award_contribution_event(
            session,
            user_id=event.user_id,
            event_type="low_workflow_validated",
            description=f"Low-stock call for {product_name} was validated by a later receipt",
            subject_type="purchase",
            subject_id=purchase_id,
            dedupe_minutes=60 * 24 * 45,
            metadata={"product_id": product_id, "shopping_item_id": shopping_item.id},
        )
        awarded.append(("low", event.user_id))

        if shopping_item.user_id:
            award_contribution_event(
                session,
                user_id=shopping_item.user_id,
                event_type="shopping_item_validated",
                description=f"Shopping help for {product_name} was validated by a later receipt",
                subject_type="purchase",
                subject_id=purchase_id,
                dedupe_minutes=60 * 24 * 45,
                metadata={"product_id": product_id, "shopping_item_id": shopping_item.id},
            )
            awarded.append(("shopping", shopping_item.user_id))
    return awarded
