"""Flask blueprint for shared dining / receipt splitting REST API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, g

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.manage_shared_dining import (
    SplitValidationError,
    create_shared_expense,
    update_split,
    settle_debt,
    settle_all_with_contact,
    get_balance_with_contact,
    get_all_balances,
    merge_contact,
)
from src.backend.initialize_database_schema import DiningContact

shared_dining_bp = Blueprint("shared_dining", __name__, url_prefix="/shared-dining")


@shared_dining_bp.route("/purchases/<int:purchase_id>", methods=["POST"])
@require_write_access
def create_expense(purchase_id: int):
    data = request.get_json(silent=True) or {}
    try:
        expense = create_shared_expense(
            g.db_session,
            purchase_id=purchase_id,
            payment_scenario=data.get("payment_scenario", ""),
            participants=data.get("participants", []),
            notes=data.get("notes"),
        )
    except SplitValidationError as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"id": expense.id, "my_amount": expense.my_amount}), 201


@shared_dining_bp.route("/<int:expense_id>/participants/<int:participant_id>", methods=["PATCH"])
@require_write_access
def patch_participant(expense_id: int, participant_id: int):
    data = request.get_json(silent=True) or {}
    new_amount = data.get("share_amount")
    if new_amount is None:
        return jsonify({"error": "share_amount required"}), 400
    try:
        update_split(g.db_session, expense_id, participant_id, float(new_amount))
    except SplitValidationError as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"ok": True}), 200


@shared_dining_bp.route("/debts/<int:debt_id>/settle", methods=["POST"])
@require_write_access
def settle(debt_id: int):
    data = request.get_json(silent=True) or {}
    try:
        settle_debt(g.db_session, debt_id, note=data.get("note"))
    except SplitValidationError as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"ok": True}), 200


@shared_dining_bp.route("/contacts/<int:contact_id>/settle-all", methods=["POST"])
@require_write_access
def settle_all(contact_id: int):
    count = settle_all_with_contact(g.db_session, contact_id)
    return jsonify({"settled": count}), 200


@shared_dining_bp.route("/balances", methods=["GET"])
@require_auth
def balances():
    return jsonify(get_all_balances(g.db_session)), 200


@shared_dining_bp.route("/balances/<int:contact_id>", methods=["GET"])
@require_auth
def balance_with_contact(contact_id: int):
    amount = get_balance_with_contact(g.db_session, contact_id)
    return jsonify({"contact_id": contact_id, "net_amount": amount}), 200


@shared_dining_bp.route("/contacts", methods=["GET"])
@require_auth
def list_contacts():
    contacts = g.db_session.query(DiningContact).order_by(DiningContact.name).all()
    return jsonify([
        {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email}
        for c in contacts
    ]), 200


@shared_dining_bp.route("/contacts", methods=["POST"])
@require_write_access
def create_contact():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    contact = DiningContact(name=name, phone=data.get("phone"), email=data.get("email"))
    g.db_session.add(contact)
    g.db_session.commit()
    return jsonify({"id": contact.id, "name": contact.name}), 201


@shared_dining_bp.route("/contacts/merge", methods=["POST"])
@require_write_access
def merge():
    data = request.get_json(silent=True) or {}
    try:
        merge_contact(g.db_session, data.get("participant_id"), data.get("contact_id"))
    except (SplitValidationError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"ok": True}), 200
