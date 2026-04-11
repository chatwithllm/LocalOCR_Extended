"""
Helpers for maintaining the app's active inventory window.

Active inventory is defined as:
- products purchased on receipts in the current month or previous month
- plus manual inventory adjustments made in that same rolling window
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from src.backend.budgeting_rollups import purchase_amount_sign
from src.backend.initialize_database_schema import (
    Inventory,
    InventoryAdjustment,
    Product,
    Purchase,
    ReceiptItem,
    TelegramReceipt,
)


ACTIVE_RECEIPT_TYPES = {"grocery", "retail_items"}


def get_active_inventory_cutoff(now: datetime | None = None) -> datetime:
    """Return the first moment of the previous calendar month."""
    reference = now or datetime.now()
    first_of_current_month = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if first_of_current_month.month == 1:
        return first_of_current_month.replace(year=first_of_current_month.year - 1, month=12)
    return first_of_current_month.replace(month=first_of_current_month.month - 1)


def record_inventory_adjustment(session, product_id: int, quantity_delta: float, user_id: int | None, reason: str):
    """Persist a manual adjustment that should be folded into active inventory."""
    adjustment = InventoryAdjustment(
        product_id=product_id,
        quantity_delta=quantity_delta,
        user_id=user_id,
        reason=reason,
    )
    session.add(adjustment)
    return adjustment


def rebuild_active_inventory(session):
    """Recompute inventory from recent receipts plus recent manual adjustments."""
    cutoff = get_active_inventory_cutoff()
    now = datetime.now()

    eligible_purchase_ids = (
        session.query(TelegramReceipt.purchase_id)
        .filter(TelegramReceipt.purchase_id.isnot(None))
        .filter(TelegramReceipt.receipt_type.in_(ACTIVE_RECEIPT_TYPES))
        .distinct()
        .subquery()
    )

    baseline_rows = (
        session.query(
            ReceiptItem.product_id.label("product_id"),
            ReceiptItem.quantity.label("quantity"),
            Purchase.id.label("purchase_id"),
            Purchase.transaction_type.label("transaction_type"),
        )
        .join(Purchase, ReceiptItem.purchase_id == Purchase.id)
        .join(eligible_purchase_ids, eligible_purchase_ids.c.purchase_id == Purchase.id)
        .filter(Purchase.date >= cutoff)
        .all()
    )
    baseline_map = {}
    for row in baseline_rows:
        baseline_map[row.product_id] = float(baseline_map.get(row.product_id, 0) or 0) + (
            float(row.quantity or 0) * purchase_amount_sign(row)
        )

    adjustment_rows = (
        session.query(
            InventoryAdjustment.product_id.label("product_id"),
            func.coalesce(func.sum(InventoryAdjustment.quantity_delta), 0).label("quantity_delta"),
        )
        .filter(InventoryAdjustment.created_at >= cutoff)
        .group_by(InventoryAdjustment.product_id)
        .all()
    )
    adjustment_map = {row.product_id: float(row.quantity_delta or 0) for row in adjustment_rows}

    inventory_rows = {
        item.product_id: item
        for item in session.query(Inventory).all()
    }

    active_product_ids = set(baseline_map) | set(adjustment_map) | set(inventory_rows)
    if not active_product_ids:
        return

    existing_products = {
        product.id: product
        for product in session.query(Product).filter(Product.id.in_(active_product_ids)).all()
    }

    for product_id in active_product_ids:
        if product_id not in existing_products:
            continue

        item = inventory_rows.get(product_id)
        if not item:
            item = Inventory(
                product_id=product_id,
                quantity=0,
                location="Pantry",
                is_active_window=False,
            )
            session.add(item)
            inventory_rows[product_id] = item

        computed_quantity = max(0, round(baseline_map.get(product_id, 0) + adjustment_map.get(product_id, 0), 3))
        item.quantity = computed_quantity
        item.is_active_window = computed_quantity > 0 or bool(item.manual_low)
        item.last_updated = now
        if not item.location:
            item.location = "Pantry"
