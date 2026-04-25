"""HTTP endpoints for the in-app assistant.

Admin-only in v1. Non-admins see a static demo panel rendered in the
frontend; this endpoint never returns content for them.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from src.backend.chat_assistant import chat_complete
from src.backend.chat_guardrails import (
    REFUSAL_TEMPLATE,
    check_rate_limit,
    screen_input,
    scrub_output,
)
from src.backend.initialize_database_schema import ChatMessage
from src.backend.manage_authentication import get_authenticated_user, is_admin

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")


_MAX_USER_MESSAGE_CHARS = 2000
_HISTORY_LIMIT = 50


def _serialize_message(msg: ChatMessage) -> dict:
    trace = None
    if msg.tool_trace:
        try:
            trace = json.loads(msg.tool_trace)
        except (TypeError, ValueError):
            trace = None
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "tool_trace": trace,
        "flagged": bool(getattr(msg, "flagged", False)),
        "flag_reason": getattr(msg, "flag_reason", None),
        "created_at": (
            msg.created_at.isoformat() + "Z"
            if msg.created_at and not msg.created_at.isoformat().endswith("Z")
            else (msg.created_at.isoformat() if msg.created_at else None)
        ),
    }


def _require_admin():
    user = get_authenticated_user()
    if not user:
        return None, (jsonify({"error": "Authentication required"}), 401)
    if not is_admin(user):
        return None, (
            jsonify({
                "error": "The in-app assistant is admin-only right now.",
                "scope": "chat_admin_only",
            }),
            403,
        )
    return user, None


@chat_bp.route("/messages", methods=["GET"])
def list_messages():
    """Return the most recent messages for the current admin."""
    user, deny = _require_admin()
    if deny:
        return deny
    rows = (
        g.db_session.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .limit(_HISTORY_LIMIT)
        .all()
    )
    return jsonify({"messages": [_serialize_message(m) for m in rows]}), 200


@chat_bp.route("/messages", methods=["POST"])
def post_message():
    """Append a user message, run the assistant, return both rows."""
    user, deny = _require_admin()
    if deny:
        return deny

    data = request.get_json(silent=True) or {}
    raw = (data.get("content") or "").strip()
    if not raw:
        return jsonify({"error": "Message is empty"}), 400
    if len(raw) > _MAX_USER_MESSAGE_CHARS:
        return jsonify({
            "error": f"Message is too long (max {_MAX_USER_MESSAGE_CHARS} chars)",
        }), 400

    # Per-user rate limit. Denied requests are NOT recorded as a user
    # message so an attacker can't fill someone else's history.
    rate_ok, rate_msg = check_rate_limit(user.id)
    if not rate_ok:
        return jsonify({"error": rate_msg or "Rate limit exceeded"}), 429

    # Input guardrail. Blocked messages are still persisted (with the
    # ``flagged`` column set) so admins can audit attempts later, but
    # we never call the LLM and never build a data context for them.
    allowed, block_reason = screen_input(raw)
    user_msg = ChatMessage(
        user_id=user.id,
        role="user",
        content=raw,
        tool_trace=None,
        flagged=not allowed,
        flag_reason=block_reason if not allowed else None,
        created_at=datetime.now(timezone.utc),
    )
    g.db_session.add(user_msg)
    g.db_session.commit()

    if not allowed:
        refusal = ChatMessage(
            user_id=user.id,
            role="assistant",
            content=REFUSAL_TEMPLATE,
            tool_trace=json.dumps({
                "blocked": True,
                "block_reason": block_reason,
                "context_summary": f"refused — {block_reason}",
            }),
            flagged=True,
            flag_reason=block_reason,
            created_at=datetime.now(timezone.utc),
        )
        g.db_session.add(refusal)
        g.db_session.commit()
        return jsonify({
            "user_message": _serialize_message(user_msg),
            "assistant_message": _serialize_message(refusal),
            "blocked": True,
            "block_reason": block_reason,
        }), 200

    history = (
        g.db_session.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .filter(ChatMessage.id != user_msg.id)
        .filter(ChatMessage.flagged == False)  # noqa: E712 — drop blocked rows from history
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )

    try:
        result = chat_complete(g.db_session, user, raw, history)
    except Exception as exc:  # noqa: BLE001 — surface any provider error
        logger.exception("chat_complete failed for user=%s", user.id)
        # Persist a placeholder assistant row so the user can see we tried,
        # but mark it explicitly so the UI can style it as an error state.
        err_msg = ChatMessage(
            user_id=user.id,
            role="assistant",
            content=f"⚠️ Chat failed: {exc}",
            tool_trace=json.dumps({"error": str(exc)}),
            created_at=datetime.now(timezone.utc),
        )
        g.db_session.add(err_msg)
        g.db_session.commit()
        return jsonify({
            "user_message": _serialize_message(user_msg),
            "assistant_message": _serialize_message(err_msg),
            "error": str(exc),
        }), 502

    raw_reply = result.get("reply") or ""
    safe_reply, leak_reason = scrub_output(raw_reply)
    assistant_msg = ChatMessage(
        user_id=user.id,
        role="assistant",
        content=safe_reply,
        tool_trace=json.dumps({
            "model": result.get("model"),
            "provider": result.get("provider"),
            "context_summary": result.get("context_summary"),
            "fallback_used": bool(result.get("fallback_used")),
            "primary_error": result.get("primary_error"),
            "scrubbed": leak_reason,
        }),
        flagged=bool(leak_reason),
        flag_reason=leak_reason,
        created_at=datetime.now(timezone.utc),
    )
    g.db_session.add(assistant_msg)
    g.db_session.commit()

    return jsonify({
        "user_message": _serialize_message(user_msg),
        "assistant_message": _serialize_message(assistant_msg),
    }), 201


@chat_bp.route("/messages", methods=["DELETE"])
def clear_messages():
    """Wipe the current admin's chat history."""
    user, deny = _require_admin()
    if deny:
        return deny
    deleted = (
        g.db_session.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .delete(synchronize_session=False)
    )
    g.db_session.commit()
    return jsonify({"deleted": int(deleted)}), 200
