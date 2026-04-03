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
        "key": "shopping_store_preference_set",
        "title": "Set shopping store preference",
        "points": 2,
        "description": "Rewarded when you help route a shopping item to the right store.",
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
        "key": "low_peer_confirmed",
        "title": "Confirm a low-stock call",
        "points": 2,
        "description": "Earned by both the suggester and confirmer when another household member agrees an item is low.",
    },
    {
        "key": "low_self_confirmed",
        "title": "Self-confirm a low-stock call",
        "points": 1,
        "description": "Earned when the same household member confirms their own low-stock call. This is weaker than peer confirmation.",
    },
    {
        "key": "recommendation_accepted",
        "title": "Accept a recommendation",
        "points": 0,
        "description": "Starts a pending recommendation contribution when a recommended item is added to shopping.",
    },
    {
        "key": "recommendation_peer_confirmed",
        "title": "Confirm a recommendation",
        "points": 2,
        "description": "Earned by both the suggester and confirmer when another household member agrees with a recommendation.",
    },
    {
        "key": "recommendation_self_confirmed",
        "title": "Self-confirm a recommendation",
        "points": 1,
        "description": "Creates a weaker self-confirmation path for single-user or solo-shopping households. It finalizes only after purchase.",
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


def sum_floating_points(session, user_id: int | None) -> int:
    """Return not-yet-finalized contribution points for a user."""
    if not user_id:
        return 0
    rows = (
        session.query(ContributionEvent.points)
        .filter(
            ContributionEvent.user_id == user_id,
            ContributionEvent.status == "floating",
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


def confirm_low_peer(session, *, confirmer_user_id: int | None, product_id: int | None, product_name: str):
    """Confirm that a low-stock call was valid, with weaker self-confirm support."""
    if not confirmer_user_id or not product_id:
        return {"error": "Missing confirmer or product"}

    pending = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.event_type == "inventory_low_marked",
            ContributionEvent.subject_type == "product",
            ContributionEvent.subject_id == product_id,
            ContributionEvent.status.in_(["pending_validation", "confirmed"]),
        )
        .order_by(ContributionEvent.created_at.desc())
        .first()
    )
    if not pending:
        return {"error": "No pending low-stock contribution to confirm"}
    is_self_confirm = pending.user_id == confirmer_user_id

    existing = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.event_type.in_(["low_peer_confirmed", "low_self_confirmed"]),
            ContributionEvent.subject_type == "product",
            ContributionEvent.subject_id == product_id,
            ContributionEvent.user_id == confirmer_user_id,
            ContributionEvent.status == "finalized",
        )
        .first()
    )
    if existing:
        return {"error": "This low-stock action is already confirmed"}

    pending.status = "confirmed"
    if is_self_confirm:
        award_contribution_event(
            session,
            user_id=pending.user_id,
            event_type="low_self_confirmed",
            description=f"Self-confirmed that {product_name} is low",
            subject_type="product",
            subject_id=product_id,
            metadata={"role": "self_confirmer"},
        )
        return {"ok": True, "suggested_by": pending.user_id, "status": "self_confirmed"}

    award_contribution_event(
        session,
        user_id=pending.user_id,
        event_type="low_peer_confirmed",
        description=f"Low-stock call for {product_name} was confirmed by another household member",
        subject_type="product",
        subject_id=product_id,
        metadata={"role": "suggester", "confirmed_by": confirmer_user_id},
    )
    award_contribution_event(
        session,
        user_id=confirmer_user_id,
        event_type="low_peer_confirmed",
        description=f"Confirmed that {product_name} is low",
        subject_type="product",
        subject_id=product_id,
        metadata={"role": "confirmer", "suggested_by": pending.user_id},
    )
    return {"ok": True, "suggested_by": pending.user_id, "status": "peer_confirmed"}


def reverse_low_confirmation(session, *, product_id: int | None):
    """Reverse low confirmations when the low flag is cleared or removed."""
    if not product_id:
        return []
    events = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.event_type.in_(["low_peer_confirmed", "low_self_confirmed"]),
            ContributionEvent.subject_type == "product",
            ContributionEvent.subject_id == product_id,
            ContributionEvent.status == "finalized",
        )
        .all()
    )
    for event in events:
        event.status = "reversed"
    return events


def confirm_recommendation_peer(session, *, confirmer_user_id: int | None, shopping_item_id: int | None, item_name: str):
    """Confirm a recommendation-based shopping action, with weaker self-confirm support."""
    if not confirmer_user_id or not shopping_item_id:
        return {"error": "Missing confirmer or shopping item"}

    pending = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.event_type == "recommendation_accepted",
            ContributionEvent.subject_type == "shopping_item",
            ContributionEvent.subject_id == shopping_item_id,
            ContributionEvent.status.in_(["pending_confirmation", "confirmed"]),
        )
        .order_by(ContributionEvent.created_at.desc())
        .first()
    )
    if not pending:
        return {"error": "No pending recommendation to confirm"}
    is_self_confirm = pending.user_id == confirmer_user_id

    existing = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.event_type.in_(["recommendation_peer_confirmed", "recommendation_self_confirmed"]),
            ContributionEvent.subject_type == "shopping_item",
            ContributionEvent.subject_id == shopping_item_id,
            ContributionEvent.user_id == confirmer_user_id,
            ContributionEvent.status.in_(["finalized", "floating"]),
        )
        .first()
    )
    if existing:
        return {"error": "This recommendation is already confirmed"}

    pending.status = "confirmed"
    if is_self_confirm:
        award_contribution_event(
            session,
            user_id=pending.user_id,
            event_type="recommendation_self_confirmed",
            description=f"Self-confirmed recommendation for {item_name}",
            subject_type="shopping_item",
            subject_id=shopping_item_id,
            status="floating",
            metadata={"role": "self_confirmer"},
        )
        return {"ok": True, "suggested_by": pending.user_id, "status": "self_confirmed"}

    award_contribution_event(
        session,
        user_id=pending.user_id,
        event_type="recommendation_peer_confirmed",
        description=f"Recommendation for {item_name} was confirmed by another household member",
        subject_type="shopping_item",
        subject_id=shopping_item_id,
        status="floating",
        metadata={"role": "suggester", "confirmed_by": confirmer_user_id},
    )
    award_contribution_event(
        session,
        user_id=confirmer_user_id,
        event_type="recommendation_peer_confirmed",
        description=f"Confirmed recommendation for {item_name}",
        subject_type="shopping_item",
        subject_id=shopping_item_id,
        status="floating",
        metadata={"role": "confirmer", "suggested_by": pending.user_id},
    )
    return {"ok": True, "suggested_by": pending.user_id, "status": "peer_confirmed"}


def finalize_recommendation_confirmation(session, *, shopping_item_id: int | None):
    """Convert floating recommendation confirmation points into real score after purchase."""
    if not shopping_item_id:
        return []
    events = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.subject_type == "shopping_item",
            ContributionEvent.subject_id == shopping_item_id,
            ContributionEvent.event_type.in_(["recommendation_peer_confirmed", "recommendation_self_confirmed"]),
            ContributionEvent.status == "floating",
        )
        .all()
    )
    for event in events:
        event.status = "finalized"

    accepted = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.subject_type == "shopping_item",
            ContributionEvent.subject_id == shopping_item_id,
            ContributionEvent.event_type == "recommendation_accepted",
            ContributionEvent.status.in_(["pending_confirmation", "confirmed"]),
        )
        .all()
    )
    for event in accepted:
        event.status = "validated"
    return events


def unfinalize_recommendation_confirmation(session, *, shopping_item_id: int | None):
    """Move recommendation confirmation points back to floating when purchase is reopened."""
    if not shopping_item_id:
        return []
    events = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.subject_type == "shopping_item",
            ContributionEvent.subject_id == shopping_item_id,
            ContributionEvent.event_type.in_(["recommendation_peer_confirmed", "recommendation_self_confirmed"]),
            ContributionEvent.status == "finalized",
        )
        .all()
    )
    for event in events:
        event.status = "floating"

    accepted = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.subject_type == "shopping_item",
            ContributionEvent.subject_id == shopping_item_id,
            ContributionEvent.event_type == "recommendation_accepted",
            ContributionEvent.status == "validated",
        )
        .all()
    )
    for event in accepted:
        event.status = "confirmed"
    return events


def reverse_shopping_item_contributions(session, *, shopping_item_id: int | None):
    """Reverse or cancel shopping-item contribution events when the item is removed."""
    if not shopping_item_id:
        return []
    events = (
        session.query(ContributionEvent)
        .filter(
            ContributionEvent.subject_type == "shopping_item",
            ContributionEvent.subject_id == shopping_item_id,
            ContributionEvent.event_type.in_([
                "shopping_item_added",
                "shopping_item_purchased",
                "shopping_item_validated",
                "recommendation_accepted",
                "recommendation_peer_confirmed",
                "recommendation_self_confirmed",
            ]),
            ContributionEvent.status.in_(["finalized", "pending_confirmation", "confirmed", "validated", "floating"]),
        )
        .all()
    )
    for event in events:
        event.status = "reversed" if event.status == "finalized" else "cancelled"
    return events
