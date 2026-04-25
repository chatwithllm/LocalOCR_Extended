"""In-app assistant that answers questions about the user's own data.

v1 design notes:

  * Pre-aggregates a small data context (per-category totals current vs
    prev month, top stores, count of uncategorized) before each turn.
    The assistant model receives the context as a JSON blob in the
    system prompt and answers from it. This is simpler and cheaper
    than full tool-calling, and avoids leaking other users' data
    because every aggregate query is scoped by ``user_id``.
  * Provider: re-uses the user's selected ``AIModelConfig`` when it's
    Gemini (vision and text share the SDK). For other providers the
    endpoint returns a friendly fallback message instead of guessing
    with another SDK.
  * Admin-only at the endpoint layer in v1; non-admins get a static
    "demo" view rendered entirely client-side.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from src.backend.budgeting_domains import BUDGET_CATEGORIES
from src.backend.initialize_database_schema import (
    AIModelConfig,
    ChatMessage,
    Purchase,
    Store,
    User,
)
from src.backend.route_ai_inference import _resolve_api_key

logger = logging.getLogger(__name__)


CATEGORY_RULES: dict[str, str] = {
    "grocery": "Auto-routed when the receipt is grocery-domain.",
    "dining": "Auto-routed when the receipt is restaurant-domain.",
    "utilities": "Auto-routed for electricity/water/gas/sewage/trash/internet/phone/cable bills.",
    "housing": "Auto-routed for rent / mortgage / HOA bills. Property taxes typically belong here.",
    "insurance": "Auto-routed when the household-bill provider type is insurance. Includes home, auto, life, health premiums.",
    "childcare": "Auto-routed for daycare / school bills.",
    "health": "Auto-routed for health-provider bills. Pharmacy receipts are typically retail or health depending on intent.",
    "subscriptions": "Auto-routed for streaming / software / gym / general subscription bills.",
    "household": "Manual category for general household supplies that aren't grocery.",
    "retail": "Manual category for retail / clothing / general goods receipts.",
    "events": "Auto-routed when the receipt is event-domain (tickets, party expenses).",
    "entertainment": "Manual only — no auto-route. Use for movies, games, hobbies that aren't recurring streaming.",
    "other_recurring": "Auto-routed for utility/household bills with an unknown provider type.",
    "other": "Fallback bucket. Anything in 'other' is a candidate for re-categorization.",
}


SYSTEM_PROMPT = """You are the in-app assistant for the LocalOCR Extended household-finance app.

You answer ONLY using the user's own data, supplied to you in the
``data_context`` JSON below the rules. Never invent stores, totals,
amounts, or dates that are not present in the context.

When the user asks where something belongs (for example "where do
property taxes go?"), look at the budget-category rules below and
recommend the best fit, briefly explaining why. If the user asks a
question that requires data not in the context (a specific receipt,
a store the context doesn't mention, an item-level detail), say so
plainly and suggest where in the app they can find it (Receipts page,
Accounts page, etc.) instead of guessing.

Style: short, direct, no filler. Money in USD with two decimals. Use
the categories' canonical labels (Grocery, Dining, Utilities, ...).
Never reveal another user's data; if the question seems to be about
someone else, answer only about the current user.

If the user asks about uncategorized items, point them at the
Receipts page filter ``Budget category = Other`` for a manual review.
"""


def _month_range(anchor: datetime) -> tuple[datetime, datetime]:
    start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _category_totals(session, user_id: int, start: datetime, end: datetime) -> dict[str, float]:
    """Sum per-category spend for the given user/month, excluding refunds.

    Filters by ``Purchase.user_id`` so cross-user data can't leak. NULL
    or empty category falls into ``other`` to match the dashboard.
    """
    import sqlalchemy as _sa

    rows = (
        session.query(
            Purchase.default_budget_category,
            _sa.func.sum(Purchase.total_amount),
        )
        .filter(Purchase.user_id == user_id)
        .filter(Purchase.date >= start, Purchase.date < end)
        .filter(
            _sa.or_(
                Purchase.transaction_type.is_(None),
                Purchase.transaction_type != "refund",
            )
        )
        .group_by(Purchase.default_budget_category)
        .all()
    )
    out: dict[str, float] = {}
    for cat, amt in rows:
        key = (cat or "other").strip().lower() or "other"
        out[key] = round(float(amt or 0.0), 2)
    return out


def _top_stores(session, user_id: int, start: datetime, end: datetime, limit: int = 5) -> list[dict[str, Any]]:
    import sqlalchemy as _sa

    rows = (
        session.query(
            Store.name,
            _sa.func.count(Purchase.id),
            _sa.func.sum(Purchase.total_amount),
        )
        .join(Store, Store.id == Purchase.store_id)
        .filter(Purchase.user_id == user_id)
        .filter(Purchase.date >= start, Purchase.date < end)
        .filter(
            _sa.or_(
                Purchase.transaction_type.is_(None),
                Purchase.transaction_type != "refund",
            )
        )
        .group_by(Store.name)
        .order_by(_sa.func.sum(Purchase.total_amount).desc())
        .limit(limit)
        .all()
    )
    return [
        {"store": name or "Unknown", "count": int(count or 0), "total": round(float(total or 0.0), 2)}
        for name, count, total in rows
    ]


def _uncategorized_count(session, user_id: int, start: datetime, end: datetime) -> int:
    import sqlalchemy as _sa

    return int(
        session.query(_sa.func.count(Purchase.id))
        .filter(Purchase.user_id == user_id)
        .filter(Purchase.date >= start, Purchase.date < end)
        .filter(
            _sa.or_(
                Purchase.default_budget_category.is_(None),
                Purchase.default_budget_category == "",
                _sa.func.lower(Purchase.default_budget_category) == "other",
            )
        )
        .scalar()
        or 0
    )


def build_data_context(session, user: User) -> dict[str, Any]:
    """Pre-aggregated, user-scoped context that the assistant reasons over.

    Light by design — three small queries — so the chat call cost stays
    in the cents-per-month range even with daily use.
    """
    now = datetime.now(timezone.utc)
    cur_start, cur_end = _month_range(now)
    prev_start, _ = _month_range(cur_start - timedelta(days=1))

    cur = _category_totals(session, user.id, cur_start, cur_end)
    prev = _category_totals(session, user.id, prev_start, cur_start)

    by_category = []
    for cat in sorted(BUDGET_CATEGORIES):
        cur_amt = cur.get(cat, 0.0)
        prev_amt = prev.get(cat, 0.0)
        delta_pct = None
        if prev_amt > 0:
            delta_pct = int(round(((cur_amt - prev_amt) / prev_amt) * 100))
        by_category.append({
            "category": cat,
            "current_month_total": cur_amt,
            "prev_month_total": prev_amt,
            "delta_pct_vs_prev": delta_pct,
        })

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "role": user.role,
        },
        "current_month": cur_start.strftime("%Y-%m"),
        "previous_month": prev_start.strftime("%Y-%m"),
        "month_total_current": round(sum(cur.values()), 2),
        "month_total_previous": round(sum(prev.values()), 2),
        "by_category": by_category,
        "top_stores_current_month": _top_stores(session, user.id, cur_start, cur_end),
        "uncategorized_count_current_month": _uncategorized_count(session, user.id, cur_start, cur_end),
        "category_rules": CATEGORY_RULES,
    }


def _format_history(history: list[ChatMessage], limit: int = 10) -> list[dict[str, str]]:
    pruned = history[-limit:]
    return [
        {"role": msg.role, "text": msg.content}
        for msg in pruned
        if msg.role in {"user", "assistant"} and (msg.content or "").strip()
    ]


def _resolve_chat_model(session, user: User) -> AIModelConfig | None:
    model_id = getattr(user, "active_ai_model_config_id", None)
    if not model_id:
        return None
    model = session.query(AIModelConfig).filter_by(id=model_id).first()
    if model and model.is_enabled:
        return model
    return None


def _gemini_chat(
    api_key: str | None,
    model_string: str,
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    """One-shot Gemini text completion for the assistant.

    No streaming, no tool-calling — keeps the v1 surface area tiny. A
    later iteration can swap this for true function-calling once we
    decide which tools graduate from "pre-fetched context" to "real
    tool".
    """
    from google import genai  # local import — heavy module
    from google.genai import types

    client = genai.Client(api_key=api_key)
    parts: list[str] = [system_prompt]
    if history:
        parts.append("Previous conversation:")
        for turn in history:
            speaker = "User" if turn["role"] == "user" else "Assistant"
            parts.append(f"{speaker}: {turn['text']}")
    parts.append(f"User: {user_message}")
    parts.append("Assistant:")
    contents = "\n\n".join(parts)

    response = client.models.generate_content(
        model=model_string,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=600,
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response")
    return text


def chat_complete(
    session,
    user: User,
    user_message: str,
    history: list[ChatMessage],
) -> dict[str, Any]:
    """Run a single assistant turn for ``user_message`` + return the reply.

    Returns:
        ``{"reply": str, "model": str | None, "provider": str | None,
            "context_summary": str}``.

    The reply is the user-visible text. ``context_summary`` is a short
    string the UI can show as an inline chip ("looked at category
    totals for April 2026"). Raises on hard failures so the endpoint
    can decide how to surface them.
    """
    model = _resolve_chat_model(session, user)
    if model is None:
        raise RuntimeError(
            "No AI model is enabled for this account. "
            "Pick one in Settings → AI Models before chatting."
        )

    provider = (model.provider or "").strip().lower()
    if provider != "gemini":
        return {
            "reply": (
                f"Chat is currently Gemini-only. Your active model is "
                f"'{model.name}' ({provider}). Switch to a Gemini model "
                f"in Settings → AI Models to use the assistant."
            ),
            "model": model.model_string,
            "provider": provider,
            "context_summary": "skipped — provider unsupported",
        }

    api_key = _resolve_api_key(model)
    if not api_key:
        raise RuntimeError(
            "Gemini API key is missing. Add a stored key for this "
            "model or set GEMINI_API_KEY in the environment."
        )

    data_context = build_data_context(session, user)
    system_prompt = (
        f"{SYSTEM_PROMPT.strip()}\n\n"
        f"Today's date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
        f"data_context = {json.dumps(data_context, default=str)}\n"
    )

    reply = _gemini_chat(
        api_key=api_key,
        model_string=(model.model_string or "gemini-2.5-flash").strip(),
        system_prompt=system_prompt,
        history=_format_history(history),
        user_message=user_message,
    )

    summary = (
        f"Used totals for {data_context['current_month']} "
        f"({len(data_context['by_category'])} categories, "
        f"{data_context['uncategorized_count_current_month']} uncategorized)."
    )
    return {
        "reply": reply,
        "model": model.model_string,
        "provider": provider,
        "context_summary": summary,
    }
