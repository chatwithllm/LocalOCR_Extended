"""
Medicine Cabinet — Household Members
======================================
CRUD endpoints for managing household members. Each member can be
assigned medications and dosage schedules in the medicine cabinet feature.

Blueprint: household_members_bp
URL prefix: /household-members
"""

import logging
from flask import Blueprint, request, jsonify, g

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import HouseholdMember

logger = logging.getLogger(__name__)

household_members_bp = Blueprint("household_members", __name__, url_prefix="/household-members")

_VALID_AGE_GROUPS = {"adult", "child"}


def _serialize_member(m):
    return {
        "id": m.id,
        "name": m.name,
        "age_group": m.age_group or "adult",
        "avatar_emoji": m.avatar_emoji,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


@household_members_bp.route("", methods=["GET"])
@require_auth
def list_members():
    """List all household members ordered by name."""
    members = (
        g.db_session.query(HouseholdMember)
        .order_by(HouseholdMember.name.asc())
        .all()
    )
    return jsonify({
        "members": [_serialize_member(m) for m in members],
        "count": len(members),
    })


@household_members_bp.route("", methods=["POST"])
@require_auth
@require_write_access
def create_member():
    """Create a new household member."""
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required and must be a non-empty string"}), 400

    age_group = data.get("age_group", "adult")
    if age_group not in _VALID_AGE_GROUPS:
        return jsonify({"error": f"age_group must be one of: {sorted(_VALID_AGE_GROUPS)}"}), 400

    avatar_emoji = data.get("avatar_emoji")
    created_by_id = getattr(g.current_user, "id", None)

    member = HouseholdMember(
        name=name,
        age_group=age_group,
        avatar_emoji=avatar_emoji,
        created_by_id=created_by_id,
    )
    g.db_session.add(member)
    g.db_session.commit()

    logger.info("Created household member id=%s name=%r", member.id, member.name)
    return jsonify({"member": _serialize_member(member)}), 201


@household_members_bp.route("/<int:member_id>", methods=["PUT"])
@require_auth
@require_write_access
def update_member(member_id):
    """Update an existing household member."""
    member = g.db_session.get(HouseholdMember, member_id)
    if member is None:
        return jsonify({"error": "Member not found"}), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify({"error": "name must be a non-empty string"}), 400
        member.name = name

    if "age_group" in data:
        age_group = data["age_group"]
        if age_group not in _VALID_AGE_GROUPS:
            return jsonify({"error": f"age_group must be one of: {sorted(_VALID_AGE_GROUPS)}"}), 400
        member.age_group = age_group

    if "avatar_emoji" in data:
        member.avatar_emoji = data["avatar_emoji"]

    g.db_session.commit()

    logger.info("Updated household member id=%s", member.id)
    return jsonify({"member": _serialize_member(member)})


@household_members_bp.route("/<int:member_id>", methods=["DELETE"])
@require_auth
@require_write_access
def delete_member(member_id):
    """Delete a household member."""
    member = g.db_session.get(HouseholdMember, member_id)
    if member is None:
        return jsonify({"error": "Member not found"}), 404

    g.db_session.delete(member)
    g.db_session.commit()

    logger.info("Deleted household member id=%s", member_id)
    return jsonify({"deleted": True, "id": member_id})
