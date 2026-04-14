import logging
from collections import defaultdict
from datetime import datetime, date as date_type, timedelta

from flask import Blueprint, g, jsonify, request

from src.backend.bill_planning import derive_planning_month_for_cash_transaction
from src.backend.budgeting_domains import normalize_budget_category
from src.backend.budgeting_rollups import normalize_transaction_type
from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import (
    BillMeta,
    BillProvider,
    BillServiceLine,
    CashTransaction,
    ProductSnapshot,
    Purchase,
    Store,
)
from src.backend.normalize_store_names import canonicalize_store_name, find_matching_store

logger = logging.getLogger(__name__)

cash_transactions_bp = Blueprint("cash_transactions", __name__, url_prefix="/cash-transactions")

ALLOWED_PROVIDER_CATEGORIES = {"utility", "personal_service", "subscription", "other"}
ALLOWED_CONTACT_METHODS = {"phone", "text", "app", "email", "in_person"}
ALLOWED_PAYMENT_METHODS = {"cash", "bank_transfer", "check", "app_transfer", "autopay", "card", "other"}
ALLOWED_PLANNING_MONTH_RULES = {"due_date_month", "statement_month", "service_end_month", "paid_date_month"}
PERSONAL_SERVICE_TYPES = {
    "tutoring",
    "lessons_music",
    "lessons_dance",
    "lessons_sports",
    "childcare_personal",
    "cleaning",
    "lawn_care",
    "pet_care",
    "personal_training",
    "therapy_personal",
    "other_personal_service",
}


def default_budget_category_for_personal_service(service_type: str | None) -> str:
    normalized = str(service_type or "").strip().lower()
    if normalized == "childcare_personal":
        return "childcare"
    return "other_recurring"


def normalize_provider_category(value: str | None, default: str = "other") -> str:
    normalized = str(value or default).strip().lower() or default
    return normalized if normalized in ALLOWED_PROVIDER_CATEGORIES else default


def normalize_contact_method(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in ALLOWED_CONTACT_METHODS else None


def normalize_payment_method(value: str | None, default: str = "cash") -> str:
    normalized = str(value or default).strip().lower() or default
    return normalized if normalized in ALLOWED_PAYMENT_METHODS else default


def normalize_planning_month_rule(value: str | None, default: str = "paid_date_month") -> str:
    normalized = str(value or default).strip().lower() or default
    return normalized if normalized in ALLOWED_PLANNING_MONTH_RULES else default


def serialize_bill_provider(provider: BillProvider) -> dict:
    return {
        "id": provider.id,
        "canonical_name": provider.canonical_name,
        "provider_type_hint": provider.provider_type_hint,
        "provider_category": provider.provider_category or "other",
        "preferred_contact_method": provider.preferred_contact_method,
        "payment_handle": provider.payment_handle,
        "known_services": sorted(
            {
                str(sl.service_type or "").strip().lower()
                for sl in provider.service_lines
                if sl.is_active and sl.service_type
            }
        ),
        "service_lines": [
            serialize_service_line(service_line)
            for service_line in sorted(
                [sl for sl in provider.service_lines if sl.is_active],
                key=lambda row: ((row.service_type or "").lower(), (row.account_label or "").lower()),
            )
        ],
    }


def serialize_service_line(service_line: BillServiceLine) -> dict:
    return {
        "id": service_line.id,
        "provider_id": service_line.provider_id,
        "service_type": service_line.service_type,
        "account_label": service_line.account_label,
        "preferred_payment_method": service_line.preferred_payment_method,
        "expected_payment_day": service_line.expected_payment_day,
        "planning_month_rule": service_line.planning_month_rule,
        "typical_amount_min": round(float(service_line.typical_amount_min or 0), 2)
        if service_line.typical_amount_min is not None
        else None,
        "typical_amount_max": round(float(service_line.typical_amount_max or 0), 2)
        if service_line.typical_amount_max is not None
        else None,
        "is_active": bool(service_line.is_active),
    }


def _normalized_service_line_key(provider_name: str, service_type: str | None, account_label: str | None) -> str:
    provider_token = canonicalize_store_name(provider_name or "Unknown")
    return f"{provider_token.lower()}::{str(service_type or 'other').strip().lower() or 'other'}::{str(account_label or 'default').strip().lower() or 'default'}"


def _get_or_create_provider(session, payload: dict) -> BillProvider:
    provider_id = payload.get("provider_id")
    if provider_id:
        provider = session.query(BillProvider).filter_by(id=int(provider_id)).first()
        if provider:
            provider.provider_category = normalize_provider_category(
                payload.get("provider_category"),
                default=provider.provider_category or "other",
            )
            provider.preferred_contact_method = normalize_contact_method(
                payload.get("preferred_contact_method")
            ) or provider.preferred_contact_method
            provider.payment_handle = (
                str(payload.get("payment_handle") or "").strip() or provider.payment_handle
            )
            return provider

    provider_name = str(payload.get("canonical_name") or payload.get("provider_name") or "").strip()
    if not provider_name:
        raise ValueError("Provider name is required")

    normalized_key = provider_name.lower()
    provider = (
        session.query(BillProvider)
        .filter(BillProvider.normalized_key == normalized_key)
        .first()
    )
    if not provider:
        provider = BillProvider(
            canonical_name=provider_name,
            normalized_key=normalized_key,
            provider_type_hint=(str(payload.get("provider_type_hint") or "").strip().lower() or None),
            provider_category=normalize_provider_category(payload.get("provider_category"), default="personal_service"),
            preferred_contact_method=normalize_contact_method(payload.get("preferred_contact_method")),
            payment_handle=str(payload.get("payment_handle") or "").strip() or None,
            is_active=True,
        )
        session.add(provider)
        session.flush()
    else:
        if payload.get("provider_type_hint") and not provider.provider_type_hint:
            provider.provider_type_hint = str(payload.get("provider_type_hint")).strip().lower() or None
        provider.provider_category = normalize_provider_category(
            payload.get("provider_category"),
            default=provider.provider_category or "personal_service",
        )
        if payload.get("preferred_contact_method"):
            provider.preferred_contact_method = normalize_contact_method(payload.get("preferred_contact_method"))
        if payload.get("payment_handle"):
            provider.payment_handle = str(payload.get("payment_handle")).strip() or None
    return provider


def _get_or_create_service_line(session, provider: BillProvider, payload: dict) -> BillServiceLine:
    service_line_id = payload.get("service_line_id")
    if service_line_id:
        service_line = session.query(BillServiceLine).filter_by(id=int(service_line_id)).first()
        if service_line:
            return service_line

    service_type = str(payload.get("service_type") or "").strip().lower()
    if not service_type:
        raise ValueError("Service line is required")

    account_label = str(payload.get("account_label") or "").strip() or None
    normalized_key = _normalized_service_line_key(provider.canonical_name, service_type, account_label)

    service_line = (
        session.query(BillServiceLine)
        .filter(BillServiceLine.normalized_key == normalized_key)
        .first()
    )
    if not service_line:
        service_line = BillServiceLine(
            provider_id=provider.id,
            service_type=service_type,
            account_label=account_label,
            preferred_payment_method=normalize_payment_method(payload.get("preferred_payment_method"), default="cash"),
            expected_payment_day=int(payload["expected_payment_day"]) if payload.get("expected_payment_day") else None,
            planning_month_rule=normalize_planning_month_rule(payload.get("planning_month_rule"), default="paid_date_month"),
            typical_amount_min=float(payload["typical_amount"]) if payload.get("typical_amount") not in (None, "") else None,
            typical_amount_max=float(payload["typical_amount"]) if payload.get("typical_amount") not in (None, "") else None,
            normalized_key=normalized_key,
            is_active=True,
        )
        session.add(service_line)
        session.flush()
        if not provider.provider_type_hint:
            provider.provider_type_hint = service_type
    else:
        service_line.preferred_payment_method = normalize_payment_method(
            payload.get("preferred_payment_method"),
            default=service_line.preferred_payment_method or "cash",
        )
        if payload.get("expected_payment_day") not in (None, ""):
            service_line.expected_payment_day = int(payload["expected_payment_day"])
        service_line.planning_month_rule = normalize_planning_month_rule(
            payload.get("planning_month_rule"),
            default=service_line.planning_month_rule or "paid_date_month",
        )
    return service_line


def recalculate_service_line_typical_amounts(session, service_line_id: int):
    today = datetime.now().date()
    rows = (
        session.query(CashTransaction.amount)
        .filter(
            CashTransaction.service_line_id == service_line_id,
            CashTransaction.status == "paid",
            CashTransaction.transaction_date <= today,
        )
        .order_by(CashTransaction.transaction_date.desc(), CashTransaction.id.desc())
        .limit(6)
        .all()
    )
    values = [float(row[0] or 0) for row in rows if row[0] is not None]
    service_line = session.query(BillServiceLine).filter_by(id=service_line_id).first()
    if service_line and values:
        service_line.typical_amount_min = round(min(values), 2)
        service_line.typical_amount_max = round(max(values), 2)
    elif service_line:
        service_line.typical_amount_min = None
        service_line.typical_amount_max = None


def _cleanup_empty_cash_entities(session, service_line_id: int | None):
    if not service_line_id:
        return

    service_line = session.query(BillServiceLine).filter_by(id=service_line_id).first()
    if not service_line:
        return

    remaining_cash_count = (
        session.query(CashTransaction.id)
        .filter(CashTransaction.service_line_id == service_line.id)
        .count()
    )
    remaining_bill_links = (
        session.query(BillMeta.id)
        .filter(BillMeta.service_line_id == service_line.id)
        .count()
    )
    provider_id = service_line.provider_id

    if remaining_cash_count == 0 and remaining_bill_links == 0:
        session.delete(service_line)
        session.flush()

    provider = session.query(BillProvider).filter_by(id=provider_id).first()
    if not provider:
        return

    provider_service_lines = (
        session.query(BillServiceLine.id)
        .filter(BillServiceLine.provider_id == provider.id)
        .count()
    )
    provider_bill_links = (
        session.query(BillMeta.id)
        .filter(BillMeta.provider_id == provider.id)
        .count()
    )

    if provider_service_lines == 0 and provider_bill_links == 0:
        session.delete(provider)


def reconcile_personal_service_slots(session, target_month: str, today: date_type | None = None) -> dict[int, dict]:
    today = today or datetime.now().date()
    year, month = [int(part) for part in target_month.split("-")]
    next_month_date = (datetime(year, month, 28) + timedelta(days=4)).replace(day=1).date()
    previous_month_date = (datetime(year, month, 1) - timedelta(days=1)).replace(day=1).date()
    previous_month = previous_month_date.strftime("%Y-%m")

    paid_rows = (
        session.query(CashTransaction)
        .join(BillServiceLine, BillServiceLine.id == CashTransaction.service_line_id)
        .join(BillProvider, BillProvider.id == BillServiceLine.provider_id)
        .filter(
            BillProvider.provider_category == "personal_service",
            CashTransaction.planning_month.in_([target_month, previous_month]),
            CashTransaction.status == "paid",
            CashTransaction.transaction_date <= today,
        )
        .all()
    )
    future_rows = (
        session.query(CashTransaction)
        .join(BillServiceLine, BillServiceLine.id == CashTransaction.service_line_id)
        .join(BillProvider, BillProvider.id == BillServiceLine.provider_id)
        .filter(
            BillProvider.provider_category == "personal_service",
            CashTransaction.planning_month == target_month,
            CashTransaction.transaction_date > today,
        )
        .all()
    )

    payments_by_line_month: dict[tuple[int, str], list[CashTransaction]] = defaultdict(list)
    for row in paid_rows:
        payments_by_line_month[(row.service_line_id, row.planning_month)].append(row)
    future_by_line: dict[int, list[CashTransaction]] = defaultdict(list)
    for row in future_rows:
        future_by_line[row.service_line_id].append(row)

    status_map: dict[int, dict] = {}
    active_service_lines = (
        session.query(BillServiceLine)
        .join(BillProvider, BillProvider.id == BillServiceLine.provider_id)
        .filter(
            BillProvider.provider_category == "personal_service",
            BillServiceLine.is_active.is_(True),
        )
        .all()
    )
    for line in active_service_lines:
        payments = payments_by_line_month.get((line.id, target_month), [])
        if payments:
            total_paid = round(sum(float(item.amount or 0) for item in payments), 2)
            status_map[line.id] = {
                "status": "paid",
                "amount": total_paid,
                "payments": payments,
                "count": len(payments),
                "latest_transaction": max(payments, key=lambda item: (item.transaction_date, item.id)),
            }
            continue

        future_payments = future_by_line.get(line.id, [])
        if future_payments:
            latest_future = max(future_payments, key=lambda item: (item.transaction_date, item.id))
            status_map[line.id] = {
                "status": "upcoming",
                "amount": float(latest_future.amount or line.typical_amount_max or 0),
                "payments": future_payments,
                "count": len(future_payments),
                "latest_transaction": latest_future,
            }
            continue

        previous_paid = payments_by_line_month.get((line.id, previous_month), [])
        if line.expected_payment_day:
            expected_date = date_type(year, month, int(line.expected_payment_day))
            status = "overdue" if today > expected_date else "upcoming"
        else:
            status = "missing" if today >= next_month_date else "upcoming"
        if not payments and not line.expected_payment_day and previous_paid:
            status = "upcoming"
        status_map[line.id] = {
            "status": status,
            "amount": float(line.typical_amount_max or 0),
            "payments": [],
            "count": 0,
            "latest_transaction": None,
        }
    return status_map


@cash_transactions_bp.route("", methods=["POST"])
@require_auth
@require_write_access
def create_cash_transaction():
    session = g.db_session
    data = request.get_json(silent=True) or {}
    provider_payload = data.get("provider") or {}
    service_line_payload = data.get("service_line") or {}

    amount = data.get("amount")
    transaction_date_raw = data.get("transaction_date")
    if amount in (None, "") or not transaction_date_raw:
        return jsonify({"error": "Amount and transaction date are required"}), 400

    try:
        transaction_date = datetime.strptime(str(transaction_date_raw).strip(), "%Y-%m-%d").date()
        amount_value = round(float(amount), 2)
    except ValueError:
        return jsonify({"error": "Invalid date or amount"}), 400

    try:
        provider = _get_or_create_provider(session, provider_payload)
        service_line = _get_or_create_service_line(
            session,
            provider,
            {
                **service_line_payload,
                "typical_amount": amount_value,
                "preferred_payment_method": data.get("payment_method") or service_line_payload.get("preferred_payment_method"),
            },
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    planning_month = derive_planning_month_for_cash_transaction(transaction_date.isoformat(), service_line)
    if not planning_month:
        return jsonify({"error": "Could not derive planning month"}), 400

    store_name = canonicalize_store_name(provider.canonical_name)
    store = find_matching_store(session, store_name)
    if not store:
        store = Store(name=store_name)
        session.add(store)
        session.flush()

    purchase = Purchase(
        store_id=store.id,
        total_amount=amount_value,
        date=datetime.combine(transaction_date, datetime.min.time()),
        domain="household_obligations",
        transaction_type=normalize_transaction_type("purchase", default="purchase"),
        default_spending_domain="household_obligations",
        default_budget_category=normalize_budget_category(
            data.get("budget_category"),
            default=default_budget_category_for_personal_service(service_line.service_type),
        ),
        user_id=getattr(getattr(g, "current_user", None), "id", None),
    )
    session.add(purchase)
    session.flush()

    snapshot_id = data.get("snapshot_id")
    if snapshot_id:
        snapshot = session.query(ProductSnapshot).filter_by(id=int(snapshot_id)).first()
        if snapshot:
            snapshot.purchase_id = purchase.id

    cash_transaction = CashTransaction(
        purchase_id=purchase.id,
        service_line_id=service_line.id,
        planning_month=planning_month,
        transaction_date=transaction_date,
        amount=amount_value,
        payment_method=normalize_payment_method(data.get("payment_method"), default=service_line.preferred_payment_method or "cash"),
        transfer_reference=str(data.get("transfer_reference") or "").strip() or None,
        notes=str(data.get("notes") or "").strip() or None,
        snapshot_id=int(snapshot_id) if snapshot_id not in (None, "") else None,
        status="paid" if transaction_date <= datetime.now().date() else "upcoming",
        created_by_id=getattr(getattr(g, "current_user", None), "id", None),
    )
    session.add(cash_transaction)
    session.flush()

    service_line.preferred_payment_method = cash_transaction.payment_method
    recalculate_service_line_typical_amounts(session, service_line.id)
    session.commit()

    return jsonify(
        {
            "transaction": {
                "id": cash_transaction.id,
                "purchase_id": purchase.id,
                "service_line_id": service_line.id,
                "provider_id": provider.id,
                "provider_name": provider.canonical_name,
                "planning_month": planning_month,
                "transaction_date": transaction_date.isoformat(),
                "amount": amount_value,
                "payment_method": cash_transaction.payment_method,
                "status": cash_transaction.status,
                "snapshot_id": cash_transaction.snapshot_id,
            },
            "provider": serialize_bill_provider(provider),
            "service_line": serialize_service_line(service_line),
        }
    ), 201


@cash_transactions_bp.route("", methods=["GET"])
@require_auth
def list_cash_transactions():
    session = g.db_session
    query = (
        session.query(CashTransaction, BillServiceLine, BillProvider)
        .join(BillServiceLine, BillServiceLine.id == CashTransaction.service_line_id)
        .join(BillProvider, BillProvider.id == BillServiceLine.provider_id)
    )
    service_line_id = request.args.get("service_line_id", type=int)
    month = (request.args.get("month") or "").strip()
    if service_line_id:
        query = query.filter(CashTransaction.service_line_id == service_line_id)
    if month:
        query = query.filter(CashTransaction.planning_month == month)

    rows = query.order_by(CashTransaction.transaction_date.desc(), CashTransaction.id.desc()).all()
    return jsonify(
        {
            "transactions": [
                {
                    "id": tx.id,
                    "purchase_id": tx.purchase_id,
                    "service_line_id": tx.service_line_id,
                    "provider_id": provider.id,
                    "provider_name": provider.canonical_name,
                    "service_type": service_line.service_type,
                    "account_label": service_line.account_label,
                    "planning_month": tx.planning_month,
                    "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
                    "amount": round(float(tx.amount or 0), 2),
                    "payment_method": tx.payment_method,
                    "transfer_reference": tx.transfer_reference,
                    "notes": tx.notes,
                    "snapshot_id": tx.snapshot_id,
                    "status": tx.status,
                }
                for tx, service_line, provider in rows
            ]
        }
    ), 200


@cash_transactions_bp.route("/<int:transaction_id>", methods=["DELETE"])
@require_auth
@require_write_access
def delete_cash_transaction(transaction_id: int):
    session = g.db_session
    cash_transaction = session.query(CashTransaction).filter_by(id=transaction_id).first()
    if not cash_transaction:
        return jsonify({"error": "Cash transaction not found"}), 404

    service_line_id = cash_transaction.service_line_id
    purchase_id = cash_transaction.purchase_id
    snapshot_id = cash_transaction.snapshot_id

    if snapshot_id:
        snapshot = session.query(ProductSnapshot).filter_by(id=snapshot_id).first()
        if snapshot and snapshot.purchase_id == purchase_id:
            snapshot.purchase_id = None

    purchase = session.query(Purchase).filter_by(id=purchase_id).first()

    session.delete(cash_transaction)
    session.flush()

    if purchase:
        session.delete(purchase)

    recalculate_service_line_typical_amounts(session, service_line_id)
    _cleanup_empty_cash_entities(session, service_line_id)
    session.commit()

    return jsonify(
        {
            "deleted": True,
            "transaction_id": transaction_id,
            "purchase_id": purchase_id,
        }
    ), 200
