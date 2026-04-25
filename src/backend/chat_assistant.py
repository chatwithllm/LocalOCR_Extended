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
    Product,
    Purchase,
    ReceiptItem,
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

When the user asks about a specific item (e.g. "how many times did
we buy tomatoes", "how much do we spend on milk"), check the
``item_search_results`` array. Each row carries
``purchase_count``, ``total_quantity``, ``total_spent``,
``first_bought``, ``last_bought``. Multiple rows may match because
products are stored at variant granularity ("Roma Tomatoes",
"Tomato Paste") — sum across the relevant rows when the user means
the whole category. If ``item_search_results`` is empty but the
question clearly named an item, say so rather than inventing a
number; suggest checking the Inventory or Receipts page.
"""


def _month_range(anchor: datetime) -> tuple[datetime, datetime]:
    start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _category_totals(session, start: datetime, end: datetime) -> dict[str, float]:
    """Sum per-category spend for a month, excluding refunds.

    Household-wide aggregate (matches the dashboard's
    ``/analytics/spending-by-category``). The chat endpoint is
    admin-only in v1, so leaking household totals to the admin is
    intentional — it keeps the assistant's numbers in sync with what
    the admin sees on the Dashboard card.
    """
    import sqlalchemy as _sa

    rows = (
        session.query(
            Purchase.default_budget_category,
            _sa.func.sum(Purchase.total_amount),
        )
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


def _top_stores(session, start: datetime, end: datetime, limit: int = 5) -> list[dict[str, Any]]:
    import sqlalchemy as _sa

    rows = (
        session.query(
            Store.name,
            _sa.func.count(Purchase.id),
            _sa.func.sum(Purchase.total_amount),
        )
        .join(Store, Store.id == Purchase.store_id)
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


def _uncategorized_count(session, start: datetime, end: datetime) -> int:
    import sqlalchemy as _sa

    return int(
        session.query(_sa.func.count(Purchase.id))
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


# Cheap-and-dirty stop-word list used to extract candidate item terms
# from a free-text question. We keep this list short on purpose —
# false positives just mean the LIKE search returns nothing, which is
# fine. The aim is to cover the common shape "how many times did we
# buy <thing>" / "how much did we spend on <thing>".
_CHAT_STOPWORDS: set[str] = {
    "the", "and", "for", "with", "from", "this", "that", "those", "these",
    "how", "much", "many", "times", "did", "have", "has", "had", "was",
    "were", "are", "buy", "bought", "buying", "purchase", "purchased",
    "spend", "spent", "spending", "money", "total", "totals", "all",
    "ever", "year", "month", "week", "day", "today", "yesterday", "last",
    "ago", "since", "what", "where", "when", "why", "who", "which",
    "our", "out", "any", "some", "more", "less", "than", "very", "just",
    "show", "give", "tell", "list", "find", "count", "us", "we", "you",
    "i", "me", "my", "mine", "ours", "his", "her", "their", "them",
    "of", "on", "in", "at", "to", "by", "as", "is", "be", "or", "an",
    "a", "do", "does", "got", "get", "into", "about", "over", "under",
    "much",
}


def _extract_item_query_terms(message: str, max_terms: int = 4) -> list[str]:
    """Pull plausible product nouns out of a free-text question.

    Returns up to ``max_terms`` lowercase tokens of length >= 3 that
    aren't in the stop-word list. Order is preserved (first mention
    wins) so a user typing "tomatoes and onions" gets [tomatoes,
    onions] rather than alphabetical.
    """
    import re

    tokens: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z'\-]+", str(message or "")):
        token = raw.lower().strip("-'")
        if len(token) < 3:
            continue
        if token in _CHAT_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= max_terms:
            break
    return tokens


def _search_items(session, terms: list[str], limit: int = 15) -> list[dict[str, Any]]:
    """Return per-product purchase stats for products whose name
    matches any of the supplied terms (case-insensitive substring).

    Joined to Purchase so we can return last-bought date and exclude
    refund rows; household-wide for parity with the rest of the
    context. Each row carries enough data for the model to answer
    "how many times did we buy X" plus a price summary.
    """
    if not terms:
        return []
    import sqlalchemy as _sa

    likes = [_sa.func.lower(Product.name).like(f"%{t}%") for t in terms]
    rows = (
        session.query(
            Product.id,
            Product.name,
            _sa.func.count(ReceiptItem.id),
            _sa.func.sum(ReceiptItem.quantity),
            _sa.func.sum(ReceiptItem.unit_price * ReceiptItem.quantity),
            _sa.func.min(Purchase.date),
            _sa.func.max(Purchase.date),
        )
        .join(ReceiptItem, ReceiptItem.product_id == Product.id)
        .join(Purchase, Purchase.id == ReceiptItem.purchase_id)
        .filter(_sa.or_(*likes))
        .filter(
            _sa.or_(
                Purchase.transaction_type.is_(None),
                Purchase.transaction_type != "refund",
            )
        )
        .group_by(Product.id, Product.name)
        .order_by(_sa.func.count(ReceiptItem.id).desc())
        .limit(limit)
        .all()
    )

    out: list[dict[str, Any]] = []
    for product_id, name, count, qty, total, first_dt, last_dt in rows:
        out.append({
            "product_id": int(product_id),
            "product_name": name,
            "purchase_count": int(count or 0),
            "total_quantity": round(float(qty or 0.0), 2),
            "total_spent": round(float(total or 0.0), 2),
            "first_bought": first_dt.strftime("%Y-%m-%d") if first_dt else None,
            "last_bought": last_dt.strftime("%Y-%m-%d") if last_dt else None,
        })
    return out


def build_data_context(
    session,
    user: User,
    user_message: str | None = None,
) -> dict[str, Any]:
    """Pre-aggregated context that the assistant reasons over.

    Household-wide aggregates + an opportunistic item-search keyed off
    nouns extracted from ``user_message``. The item-search lets the
    assistant answer "how many times did we buy tomatoes" without
    needing real tool-calling — when the user's question mentions
    plausible product names the resulting per-product stats land in
    ``item_search_results`` and the model is told to use them.
    """
    now = datetime.now(timezone.utc)
    cur_start, cur_end = _month_range(now)
    prev_start, _ = _month_range(cur_start - timedelta(days=1))

    cur = _category_totals(session, cur_start, cur_end)
    prev = _category_totals(session, prev_start, cur_start)

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

    item_terms = _extract_item_query_terms(user_message or "")
    item_results = _search_items(session, item_terms) if item_terms else []

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
        "top_stores_current_month": _top_stores(session, cur_start, cur_end),
        "uncategorized_count_current_month": _uncategorized_count(session, cur_start, cur_end),
        "item_search_terms": item_terms,
        "item_search_results": item_results,
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


def _openai_chat(
    api_key: str,
    model_string: str,
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
    base_url: str | None = None,
) -> str:
    """Backup chat path using the OpenAI Chat Completions API.

    Used when the primary Gemini call hits a quota / rate-limit /
    transient error. Re-uses the same system prompt + history so the
    user sees a continuous conversation. Model name defaults to a
    cheap GPT-4o variant via the ``OPENAI_CHAT_MODEL`` env var.
    """
    from openai import OpenAI  # local import — heavy module

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in history:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": turn.get("text") or ""})
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=model_string,
        messages=messages,
        temperature=0.2,
        max_tokens=600,
    )
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("OpenAI returned an empty response")
    return text


def _resolve_openai_fallback(session) -> tuple[str | None, str, str | None]:
    """Return (api_key, model_string, base_url) for the OpenAI fallback path.

    Order of preference:
      1. An enabled OpenAI ``AIModelConfig`` with a stored key —
         lets admins curate the fallback model in Settings.
      2. ``OPENAI_API_KEY`` env var with model from
         ``OPENAI_CHAT_MODEL`` (default ``gpt-4o-mini``).

    Returns ``(None, "", None)`` when no fallback is configured so
    the caller can surface a clear error.
    """
    candidate = (
        session.query(AIModelConfig)
        .filter(AIModelConfig.is_enabled == True)  # noqa: E712
        .filter(_lower_provider() == "openai")
        .order_by(AIModelConfig.id.asc())
        .first()
    )
    if candidate is not None:
        try:
            api_key = _resolve_api_key(candidate)
        except Exception:  # noqa: BLE001
            api_key = None
        if api_key:
            return (
                api_key,
                (candidate.model_string or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")).strip(),
                (candidate.base_url or "").strip() or None,
            )

    env_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if env_key:
        return (
            env_key,
            (os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini").strip(),
            None,
        )
    return None, "", None


def _lower_provider():
    """SQLAlchemy expression: lower(AIModelConfig.provider)."""
    import sqlalchemy as _sa
    return _sa.func.lower(AIModelConfig.provider)


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
    data_context = build_data_context(session, user, user_message=user_message)
    system_prompt = (
        f"{SYSTEM_PROMPT.strip()}\n\n"
        f"Today's date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
        f"data_context = {json.dumps(data_context, default=str)}\n"
    )
    formatted_history = _format_history(history)

    model = _resolve_chat_model(session, user)
    primary_provider = (model.provider or "").strip().lower() if model else ""

    reply: str | None = None
    used_provider: str | None = None
    used_model: str | None = None
    fallback_used = False
    primary_error: str | None = None

    if model and primary_provider == "gemini":
        try:
            api_key = _resolve_api_key(model)
            if not api_key:
                raise RuntimeError(
                    "Gemini API key is missing. Add a stored key for this "
                    "model or set GEMINI_API_KEY in the environment."
                )
            reply = _gemini_chat(
                api_key=api_key,
                model_string=(model.model_string or "gemini-2.5-flash").strip(),
                system_prompt=system_prompt,
                history=formatted_history,
                user_message=user_message,
            )
            used_provider = "gemini"
            used_model = (model.model_string or "gemini-2.5-flash").strip()
        except Exception as exc:  # noqa: BLE001 — broad on purpose; we fall back
            primary_error = str(exc)
            logger.warning(
                "Gemini chat failed for user=%s, attempting OpenAI fallback: %s",
                user.id, exc,
            )

    if reply is None:
        # Primary unavailable (no model, wrong provider, or hard error).
        # Try OpenAI as a backup so the user still gets an answer.
        fb_key, fb_model, fb_base_url = _resolve_openai_fallback(session)
        if not fb_key:
            if model is None:
                raise RuntimeError(
                    "No AI model is enabled and no OPENAI_API_KEY is set. "
                    "Pick a model in Settings → AI Models or configure an "
                    "OpenAI fallback to use the assistant."
                )
            if primary_provider not in {"gemini", "openai"}:
                return {
                    "reply": (
                        f"Chat supports Gemini (primary) and OpenAI (fallback). "
                        f"Your active model is '{model.name}' ({primary_provider}). "
                        f"Switch in Settings → AI Models to use the assistant."
                    ),
                    "model": model.model_string,
                    "provider": primary_provider,
                    "context_summary": "skipped — provider unsupported",
                }
            # Gemini failed and there's no fallback configured — re-raise.
            raise RuntimeError(
                primary_error or "Chat provider is unavailable and no fallback is configured."
            )

        try:
            reply = _openai_chat(
                api_key=fb_key,
                model_string=fb_model,
                system_prompt=system_prompt,
                history=formatted_history,
                user_message=user_message,
                base_url=fb_base_url,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("OpenAI fallback failed for user=%s", user.id)
            if primary_error:
                raise RuntimeError(
                    f"Both providers failed. Gemini: {primary_error}. OpenAI: {exc}"
                ) from exc
            raise

        used_provider = "openai"
        used_model = fb_model
        fallback_used = bool(model and primary_provider == "gemini")

    summary_parts = [
        f"totals for {data_context['current_month']}",
        f"{data_context['uncategorized_count_current_month']} uncategorized",
    ]
    if data_context.get("item_search_terms"):
        terms = ", ".join(data_context["item_search_terms"])
        hits = len(data_context.get("item_search_results") or [])
        summary_parts.append(
            f"item search: {terms} → {hits} match{'es' if hits != 1 else ''}"
        )
    if fallback_used:
        summary_parts.append("⚠️ fell back to OpenAI (Gemini unavailable)")
    summary = "Used " + " · ".join(summary_parts) + "."

    return {
        "reply": reply,
        "model": used_model,
        "provider": used_provider,
        "context_summary": summary,
        "fallback_used": fallback_used,
        "primary_error": primary_error,
    }
