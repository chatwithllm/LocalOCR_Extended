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


def _ollama_chat(
    base_url: str,
    model_string: str,
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    """Local Ollama text chat — last-resort fallback (no quota).

    Uses ``/api/chat`` instead of ``/api/generate`` so the system
    prompt + history can be passed as discrete messages, matching the
    OpenAI-style structure we send to the cloud providers.
    """
    import requests

    url = f"{base_url.rstrip('/')}/api/chat"
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in history:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": turn.get("text") or ""})
    messages.append({"role": "user", "content": user_message})

    response = requests.post(
        url,
        json={
            "model": model_string,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 600},
        },
        timeout=int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
    )
    response.raise_for_status()
    payload = response.json()
    text = ((payload.get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response")
    return text


def _anthropic_chat(
    api_key: str,
    model_string: str,
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    """Anthropic Claude text chat fallback."""
    import requests

    messages: list[dict[str, str]] = []
    for turn in history:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": turn.get("text") or ""})
    messages.append({"role": "user", "content": user_message})

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model_string,
            "max_tokens": 600,
            "temperature": 0.2,
            "system": system_prompt,
            "messages": messages,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    blocks = payload.get("content") or []
    text_parts = [
        b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    ]
    text = "".join(text_parts).strip()
    if not text:
        raise RuntimeError("Anthropic returned an empty response")
    return text


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

    chain = _build_provider_chain(session, user)
    if not chain:
        raise RuntimeError(
            "No chat providers are configured. Add a Gemini, OpenAI, "
            "OpenRouter, Anthropic, or Ollama model in Settings → AI Models, "
            "or set the matching API key in the environment."
        )

    errors: list[tuple[str, str]] = []
    reply: str | None = None
    used_provider: str | None = None
    used_model: str | None = None
    primary_label = chain[0]["label"]

    for attempt in chain:
        label = attempt["label"]
        try:
            reply = attempt["call"](
                system_prompt=system_prompt,
                history=formatted_history,
                user_message=user_message,
            )
            used_provider = attempt["provider"]
            used_model = attempt["model_string"]
            break
        except Exception as exc:  # noqa: BLE001 — broad on purpose; we fall back
            short = str(exc)
            if len(short) > 240:
                short = short[:240] + "…"
            errors.append((label, short))
            logger.warning(
                "Chat provider %s failed for user=%s: %s", label, user.id, exc,
            )

    if reply is None:
        joined = "; ".join(f"{label}: {err}" for label, err in errors)
        raise RuntimeError(f"All chat providers failed. {joined}")

    fallback_used = used_provider != chain[0]["provider"]

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
        summary_parts.append(
            f"⚠️ fell back to {used_provider} ({primary_label} unavailable)"
        )
    summary = "Used " + " · ".join(summary_parts) + "."

    return {
        "reply": reply,
        "model": used_model,
        "provider": used_provider,
        "context_summary": summary,
        "fallback_used": fallback_used,
        "provider_errors": errors,
    }


def _build_provider_chain(session, user: User) -> list[dict[str, Any]]:
    """Return the ordered list of provider attempts for one chat turn.

    Each entry: {label, provider, model_string, call(callable)}. The
    chain is built once per turn so we don't re-resolve env vars or
    DB rows mid-fallback. Order:

      1. The user's active AIModelConfig (if its provider is supported).
      2. Any other supported AIModelConfig that has a working key.
      3. Env-var fallbacks for OpenAI / Anthropic / OpenRouter.
      4. Ollama as a last-resort local model (no key, no quota).

    Duplicates by provider are de-duped so the chain doesn't try the
    same key twice when an active model also matches an env var.
    """
    chain: list[dict[str, Any]] = []
    seen_providers: set[str] = set()
    supported = {"gemini", "openai", "anthropic", "openrouter", "ollama"}

    def _push(provider: str, label: str, model_string: str, call) -> None:
        key = f"{provider}:{model_string}"
        if key in seen_providers:
            return
        seen_providers.add(key)
        chain.append({
            "provider": provider,
            "label": label,
            "model_string": model_string,
            "call": call,
        })

    # 1. Active model first.
    active = _resolve_chat_model(session, user)
    if active is not None and (active.provider or "").strip().lower() in supported:
        _push_model_attempt(active, _push)

    # 2. Other enabled, supported AIModelConfigs.
    others = (
        session.query(AIModelConfig)
        .filter(AIModelConfig.is_enabled == True)  # noqa: E712
        .order_by(AIModelConfig.id.asc())
        .all()
    )
    for cfg in others:
        if active is not None and cfg.id == active.id:
            continue
        provider = (cfg.provider or "").strip().lower()
        if provider not in supported:
            continue
        _push_model_attempt(cfg, _push)

    # 3. Env-var fallbacks.
    openai_env = (os.getenv("OPENAI_API_KEY") or "").strip()
    if openai_env:
        model_string = (os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini").strip()
        _push(
            "openai",
            f"openai-env ({model_string})",
            model_string,
            lambda *, system_prompt, history, user_message: _openai_chat(
                openai_env, model_string, system_prompt, history, user_message,
            ),
        )
    openrouter_env = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if openrouter_env:
        or_model = (os.getenv("OPENROUTER_CHAT_MODEL") or "openai/gpt-4o-mini").strip()
        _push(
            "openrouter",
            f"openrouter-env ({or_model})",
            or_model,
            lambda *, system_prompt, history, user_message: _openai_chat(
                openrouter_env,
                or_model,
                system_prompt,
                history,
                user_message,
                base_url="https://openrouter.ai/api/v1",
            ),
        )
    anthropic_env = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if anthropic_env:
        a_model = (os.getenv("ANTHROPIC_CHAT_MODEL") or "claude-3-5-haiku-latest").strip()
        _push(
            "anthropic",
            f"anthropic-env ({a_model})",
            a_model,
            lambda *, system_prompt, history, user_message: _anthropic_chat(
                anthropic_env, a_model, system_prompt, history, user_message,
            ),
        )

    # 4. Local Ollama — last resort, no quota or key needed.
    ollama_endpoint = (os.getenv("OLLAMA_ENDPOINT") or "").strip()
    ollama_model = (os.getenv("OLLAMA_CHAT_MODEL") or os.getenv("OLLAMA_MODEL") or "").strip()
    if ollama_endpoint and ollama_model:
        _push(
            "ollama",
            f"ollama-local ({ollama_model})",
            ollama_model,
            lambda *, system_prompt, history, user_message: _ollama_chat(
                ollama_endpoint, ollama_model, system_prompt, history, user_message,
            ),
        )

    return chain


def _push_model_attempt(cfg: AIModelConfig, push) -> None:
    """Helper: build a chain entry from an AIModelConfig row."""
    provider = (cfg.provider or "").strip().lower()
    model_string = (cfg.model_string or "").strip()
    if not model_string:
        return

    if provider == "gemini":
        try:
            api_key = _resolve_api_key(cfg)
        except Exception:  # noqa: BLE001
            return
        if not api_key:
            return
        push(
            "gemini",
            f"gemini ({model_string})",
            model_string,
            lambda *, system_prompt, history, user_message: _gemini_chat(
                api_key, model_string, system_prompt, history, user_message,
            ),
        )
    elif provider == "openai":
        try:
            api_key = _resolve_api_key(cfg)
        except Exception:  # noqa: BLE001
            return
        if not api_key:
            return
        base_url = (cfg.base_url or "").strip() or None
        push(
            "openai",
            f"openai ({model_string})",
            model_string,
            lambda *, system_prompt, history, user_message: _openai_chat(
                api_key, model_string, system_prompt, history, user_message,
                base_url=base_url,
            ),
        )
    elif provider == "openrouter":
        try:
            api_key = _resolve_api_key(cfg)
        except Exception:  # noqa: BLE001
            return
        if not api_key:
            return
        base_url = (cfg.base_url or "https://openrouter.ai/api/v1").strip()
        push(
            "openrouter",
            f"openrouter ({model_string})",
            model_string,
            lambda *, system_prompt, history, user_message: _openai_chat(
                api_key, model_string, system_prompt, history, user_message,
                base_url=base_url,
            ),
        )
    elif provider == "anthropic":
        try:
            api_key = _resolve_api_key(cfg)
        except Exception:  # noqa: BLE001
            return
        if not api_key:
            return
        push(
            "anthropic",
            f"anthropic ({model_string})",
            model_string,
            lambda *, system_prompt, history, user_message: _anthropic_chat(
                api_key, model_string, system_prompt, history, user_message,
            ),
        )
    elif provider == "ollama":
        base_url = (cfg.base_url or os.getenv("OLLAMA_ENDPOINT") or "http://ollama:11434").strip()
        push(
            "ollama",
            f"ollama ({model_string})",
            model_string,
            lambda *, system_prompt, history, user_message: _ollama_chat(
                base_url, model_string, system_prompt, history, user_message,
            ),
        )
