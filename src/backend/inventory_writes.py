"""Pure inventory write helpers — no HTTP, no Flask, no transactions.

Three writers:
  upsert_inventory_for_receipt_item  — receipt-finalize side effect.
  apply_manual_patch                 — PATCH endpoint side effect.
  reset_expiry_to_system             — DELETE expiry-override side effect.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

from src.backend.category_shelf_life import get_category_default
from src.backend.initialize_database_schema import (
    Inventory, InventoryAdjustment, Product, Purchase, ReceiptItem,
)


logger = logging.getLogger(__name__)


def _purchase_sign(purchase: Purchase) -> int:
    txn = (getattr(purchase, "transaction_type", None) or "purchase").lower()
    return -1 if txn == "refund" else 1


def upsert_inventory_for_receipt_item(session, product: Product, item: ReceiptItem, purchase: Purchase) -> Inventory:
    """Mutates ``session``. Caller commits."""
    if product is None:
        return None  # type: ignore[return-value]
    defaults = get_category_default(session, product.category)
    inv = session.query(Inventory).filter_by(product_id=product.id).first()
    if inv is None:
        inv = Inventory(product_id=product.id, quantity=0,
                        location=defaults.location_default,
                        expires_source="system", is_active_window=True)
        session.add(inv); session.flush()

    sign = _purchase_sign(purchase)
    delta = float(item.quantity or 0) * sign
    inv.quantity = max(0.0, float(inv.quantity or 0) + delta)

    pdate = getattr(purchase, "date", None)
    if pdate is not None:
        # Normalise to offset-aware UTC for comparison so naive and aware datetimes don't clash.
        def _as_utc(d):
            if isinstance(d, datetime):
                return d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        pdate_utc = _as_utc(pdate)
        prior_utc = _as_utc(inv.last_purchased_at) if inv.last_purchased_at is not None else None
        if prior_utc is None or pdate_utc > prior_utc:
            inv.last_purchased_at = pdate

    if defaults.shelf_life_days > 0 and pdate is not None and sign > 0:
        purchase_date = pdate.date() if isinstance(pdate, datetime) else pdate
        new_system = purchase_date + timedelta(days=defaults.shelf_life_days)
        prior_system = inv.expires_at_system or date.min
        inv.expires_at_system = max(new_system, prior_system)
        if inv.expires_source == "system":
            inv.expires_at = inv.expires_at_system

    inv.last_updated = datetime.now(timezone.utc)
    return inv


def _audit(session, product_id: int, delta: float, reason: str, user_id: int | None) -> None:
    session.add(InventoryAdjustment(product_id=product_id, quantity_delta=delta,
                                    reason=reason, user_id=user_id))


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"unsupported date value: {value!r}")


def apply_manual_patch(session, inv: Inventory, patch: dict, user_id: int | None) -> Inventory | None:
    """Apply a partial update to ``inv``. Returns the row, or ``None`` when
    the row was deleted (used-up transition: quantity 0 from a positive value).
    The audit InventoryAdjustment row is preserved either way so history
    survives the deletion.
    """
    deleted = False
    if "quantity" in patch:
        new_qty = max(0.0, float(patch["quantity"]))
        delta = new_qty - float(inv.quantity or 0)
        if new_qty == 0:
            # Any patch landing at qty=0 means "remove from inventory" —
            # delete the row regardless of the prior quantity. Idempotent:
            # repeated 0-patches on a zero row still delete cleanly.
            reason = "consumed_all"
            deleted = True
        else:
            reason = "manual_edit"
        inv.quantity = new_qty
        _audit(session, inv.product_id, delta, reason, user_id)

    if "location" in patch and patch["location"]:
        new_loc = str(patch["location"]).strip()
        if new_loc and new_loc != (inv.location or ""):
            inv.location = new_loc
            _audit(session, inv.product_id, 0, "moved", user_id)

    if "expires_at" in patch:
        inv.expires_at = _coerce_date(patch["expires_at"])
        inv.expires_source = "user"
        _audit(session, inv.product_id, 0, "edit_expiry", user_id)

    if "defer_days" in patch and patch["defer_days"]:
        days = int(patch["defer_days"])
        base = inv.expires_at or inv.expires_at_system or date.today()
        inv.expires_at = base + timedelta(days=days)
        inv.expires_source = "defer"
        _audit(session, inv.product_id, 0, f"defer_expiry_+{days}d", user_id)

    inv.last_updated = datetime.now(timezone.utc)

    if deleted:
        # Used-up: drop the row entirely. Next receipt for this product
        # will upsert a fresh Inventory row via receipt finalize.
        session.delete(inv)
        return None
    return inv


def reset_expiry_to_system(session, inv: Inventory, user_id: int | None) -> Inventory:
    inv.expires_at = inv.expires_at_system
    inv.expires_source = "system"
    _audit(session, inv.product_id, 0, "reset_expiry_to_system", user_id)
    inv.last_updated = datetime.now(timezone.utc)
    return inv
