"""
Monthly obligation slot projection engine.

Phase 6 and Phase 7 planning work is service-line aware when canonical bill
service identities are available, while preserving legacy provider-name
grouping for older bill rows.
"""

import logging
import statistics
from datetime import datetime
from typing import Any

from src.backend.bill_cadence import month_matches_billing_cycle, normalize_billing_cycle
from src.backend.initialize_database_schema import BillMeta, BillProvider, BillServiceLine, CashTransaction, Purchase
from src.backend.manage_cash_transactions import reconcile_personal_service_slots

logger = logging.getLogger(__name__)


def generate_monthly_obligation_slots(session, target_month: str, user_id: int | None = None) -> list[dict[str, Any]]:
    """Project recurring obligation slots for a target month (`YYYY-MM`)."""
    recurring_entries = _load_recurring_entries(session, user_id=user_id)
    known_obligations: dict[str, dict[str, Any]] = {}
    for bill, _purchase in recurring_entries:
        obligation = _obligation_descriptor(bill)
        known_obligations.setdefault(obligation["key"], obligation)

    actual_bills = _load_actual_bills(session, target_month, user_id=user_id)
    fulfilled_keys: set[str] = set()
    slots: list[dict[str, Any]] = []

    for bill, amount, date_obj in actual_bills:
        obligation = _obligation_descriptor(bill)
        fulfilled_keys.add(obligation["key"])

        amt_val = float(amount or 0.0)
        rolling_avg = _calculate_rolling_estimate(session, obligation, user_id=user_id)

        anomaly = None
        if rolling_avg > 0:
            diff_pct = abs(amt_val - rolling_avg) / rolling_avg
            if diff_pct > 0.30:
                anomaly = (
                    f"Unusual amount: {int(diff_pct * 100)}% "
                    f"{'higher' if amt_val > rolling_avg else 'lower'} than average"
                )

        slots.append({
            "slot_type": "actual",
            "obligation_key": obligation["key"],
            "service_line_id": obligation["service_line_id"],
            "provider_name": obligation["provider_name"],
            "provider_type": obligation["provider_type"],
            "account_label": obligation["account_label"],
            "billing_cycle": obligation["billing_cycle"],
            "planning_month": bill.planning_month,
            "payment_status": bill.payment_status,
            "due_date": bill.due_date.isoformat() if bill.due_date else None,
            "amount": amt_val,
            "average_amount": rolling_avg,
            "is_anomaly": anomaly is not None,
            "anomaly_reason": anomaly,
            "purchase_date": date_obj.isoformat() if date_obj else None,
            "purchase_id": bill.purchase_id,
            "source_type": "bill_receipt",
        })

    cash_actuals = _load_actual_cash_transactions(session, target_month, user_id=user_id)
    for transaction, service_line, provider in cash_actuals:
        obligation = _personal_service_obligation_descriptor(service_line, provider)
        fulfilled_keys.add(obligation["key"])
        slots.append({
            "slot_type": "actual",
            "obligation_key": obligation["key"],
            "service_line_id": obligation["service_line_id"],
            "provider_name": obligation["provider_name"],
            "provider_type": obligation["provider_type"],
            "provider_category": obligation["provider_category"],
            "account_label": obligation["account_label"],
            "billing_cycle": obligation["billing_cycle"],
            "planning_month": transaction.planning_month,
            "payment_status": transaction.status,
            "due_date": None,
            "amount": float(transaction.amount or 0),
            "average_amount": float(service_line.typical_amount_max or 0),
            "is_anomaly": False,
            "anomaly_reason": None,
            "purchase_date": transaction.transaction_date.isoformat() if transaction.transaction_date else None,
            "purchase_id": transaction.purchase_id,
            "transaction_count": 1,
            "source_type": "cash_transaction",
        })

    for key in sorted(set(known_obligations) - fulfilled_keys):
        obligation = known_obligations[key]
        if not _obligation_is_due_for_month(obligation, target_month):
            continue
        rolling_avg = _calculate_rolling_estimate(session, obligation, user_id=user_id)
        status = "missing" if _is_window_passed(session, obligation, target_month, user_id=user_id) else "not_yet_entered"

        slots.append({
            "slot_type": "projected",
            "obligation_key": obligation["key"],
            "service_line_id": obligation["service_line_id"],
            "provider_name": obligation["provider_name"],
            "provider_type": obligation["provider_type"],
            "account_label": obligation["account_label"],
            "billing_cycle": obligation["billing_cycle"],
            "planning_month": target_month,
            "payment_status": status,
            "due_date": None,
            "amount": rolling_avg,
            "average_amount": rolling_avg,
            "is_anomaly": False,
            "anomaly_reason": None,
            "purchase_date": None,
            "purchase_id": None,
            "source_type": "bill_receipt",
        })

    personal_service_lines = _load_active_personal_service_lines(session)
    personal_status_map = reconcile_personal_service_slots(session, target_month)
    for service_line, provider in personal_service_lines:
        obligation = _personal_service_obligation_descriptor(service_line, provider)
        if obligation["key"] in fulfilled_keys:
            continue
        status_info = personal_status_map.get(service_line.id, {})
        amount = float(service_line.typical_amount_max or 0)
        slots.append({
            "slot_type": "projected",
            "obligation_key": obligation["key"],
            "service_line_id": obligation["service_line_id"],
            "provider_name": obligation["provider_name"],
            "provider_type": obligation["provider_type"],
            "provider_category": obligation["provider_category"],
            "account_label": obligation["account_label"],
            "billing_cycle": obligation["billing_cycle"],
            "planning_month": target_month,
            "payment_status": status_info.get("status", "upcoming"),
            "due_date": (
                f"{target_month}-{int(service_line.expected_payment_day):02d}"
                if service_line.expected_payment_day
                else None
            ),
            "amount": amount,
            "average_amount": amount,
            "is_anomaly": False,
            "anomaly_reason": None,
            "purchase_date": None,
            "purchase_id": None,
            "provider_category": "personal_service",
            "transaction_count": status_info.get("count", 0),
            "source_type": "cash_transaction",
        })

    slots.sort(key=lambda slot: (slot["slot_type"] == "projected", slot["provider_name"], slot["provider_type"] or ""))
    return slots


def _load_recurring_entries(session, user_id: int | None = None):
    query = (
        session.query(BillMeta, Purchase)
        .join(Purchase, Purchase.id == BillMeta.purchase_id)
        .filter(BillMeta.is_recurring.is_(True))
    )
    if user_id is not None:
        query = query.filter(Purchase.user_id == user_id)
    return query.all()


def _load_actual_bills(session, target_month: str, user_id: int | None = None):
    query = (
        session.query(BillMeta, Purchase.total_amount, Purchase.date)
        .join(Purchase, Purchase.id == BillMeta.purchase_id)
        .filter(BillMeta.planning_month == target_month)
    )
    if user_id is not None:
        query = query.filter(Purchase.user_id == user_id)
    return query.all()


def _load_actual_cash_transactions(session, target_month: str, user_id: int | None = None):
    today = datetime.now().date()
    query = (
        session.query(CashTransaction, BillServiceLine, BillProvider)
        .join(BillServiceLine, BillServiceLine.id == CashTransaction.service_line_id)
        .join(BillProvider, BillProvider.id == BillServiceLine.provider_id)
        .join(Purchase, Purchase.id == CashTransaction.purchase_id)
        .filter(
            CashTransaction.planning_month == target_month,
            CashTransaction.status == "paid",
            CashTransaction.transaction_date <= today,
        )
    )
    if user_id is not None:
        query = query.filter(Purchase.user_id == user_id)
    return query.all()


def _load_active_personal_service_lines(session):
    return (
        session.query(BillServiceLine, BillProvider)
        .join(BillProvider, BillProvider.id == BillServiceLine.provider_id)
        .filter(
            BillProvider.provider_category == "personal_service",
            BillServiceLine.is_active.is_(True),
        )
        .all()
    )


def _obligation_descriptor(bill: BillMeta) -> dict[str, Any]:
    provider_name = (bill.provider_name or "Unknown Provider").strip() or "Unknown Provider"
    provider_type = (bill.provider_type or getattr(getattr(bill, "service_line", None), "service_type", None) or "").strip() or None
    account_label = (bill.account_label or "").strip() or None

    if bill.service_line_id:
        key = f"service_line:{bill.service_line_id}"
    else:
        key = f"legacy:{provider_name.lower()}::{(provider_type or '').lower()}::{(account_label or '').lower()}"

    return {
        "key": key,
        "service_line_id": bill.service_line_id,
        "provider_name": provider_name,
        "provider_type": provider_type,
        "provider_category": getattr(getattr(bill, "provider", None), "provider_category", "utility"),
        "account_label": account_label,
        "billing_cycle": normalize_billing_cycle(getattr(bill, "billing_cycle", None)),
        "anchor_month": (bill.planning_month or bill.billing_cycle_month or "").strip() or None,
    }


def _personal_service_obligation_descriptor(service_line: BillServiceLine, provider: BillProvider) -> dict[str, Any]:
    return {
        "key": f"service_line:{service_line.id}",
        "service_line_id": service_line.id,
        "provider_name": provider.canonical_name,
        "provider_type": service_line.service_type or provider.provider_type_hint or "other_personal_service",
        "provider_category": provider.provider_category or "personal_service",
        "account_label": (service_line.account_label or "").strip() or None,
        "billing_cycle": normalize_billing_cycle("monthly"),
        "anchor_month": None,
    }


def _obligation_is_due_for_month(obligation: dict[str, Any], target_month: str) -> bool:
    return month_matches_billing_cycle(
        target_month,
        obligation.get("anchor_month"),
        obligation.get("billing_cycle"),
    )


def _apply_obligation_filter(query, obligation: dict[str, Any]):
    if obligation.get("service_line_id"):
        return query.filter(BillMeta.service_line_id == obligation["service_line_id"])

    query = query.filter(BillMeta.provider_name == obligation["provider_name"])
    if obligation.get("provider_type"):
        query = query.filter(BillMeta.provider_type == obligation["provider_type"])
    else:
        query = query.filter(BillMeta.provider_type.is_(None))

    if obligation.get("account_label"):
        query = query.filter(BillMeta.account_label == obligation["account_label"])
    else:
        query = query.filter(BillMeta.account_label.is_(None))

    return query


def _calculate_rolling_estimate(session, obligation: dict[str, Any], user_id: int | None = None) -> float:
    """Calculate mean amount from the last six matching bill observations."""
    query = (
        session.query(Purchase.total_amount)
        .join(BillMeta, BillMeta.purchase_id == Purchase.id)
    )
    query = _apply_obligation_filter(query, obligation)
    if user_id is not None:
        query = query.filter(Purchase.user_id == user_id)

    historical = query.order_by(BillMeta.planning_month.desc()).limit(6).all()
    amounts = [float(row[0] or 0.0) for row in historical if row[0] is not None]
    if not amounts:
        return 0.0
    return round(statistics.mean(amounts), 2)


def _is_window_passed(session, obligation: dict[str, Any], target_month: str, user_id: int | None = None) -> bool:
    """Determine if the expected arrival window has likely passed."""
    query = (
        session.query(Purchase.date)
        .join(BillMeta, BillMeta.purchase_id == Purchase.id)
    )
    query = _apply_obligation_filter(query, obligation)
    if user_id is not None:
        query = query.filter(Purchase.user_id == user_id)

    historical_dates = query.all()
    days = [row[0].day for row in historical_dates if row[0]]
    if not days:
        return False

    typical_day = round(statistics.mean(days))
    now = datetime.now()
    current_month_str = now.strftime("%Y-%m")

    if target_month < current_month_str:
        return True
    if target_month == current_month_str:
        return now.day > (typical_day + 5)
    return False
