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
from src.backend.chat_guardrails import GUARDRAIL_PROMPT
from src.backend.initialize_database_schema import (
    AIModelConfig,
    ChatMessage,
    Product,
    Purchase,
    ReceiptItem,
    Store,
    User,
)
# noqa: F401 — Store imported for the join in _search_items below.
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
``item_search_results`` array. Each row is ONE product variant
(e.g. "Roma Tomato", "Vine Tomato", "Cocktail Tomatoes"). If the
user's question is about the general item, you MUST sum
``purchase_count`` across every variant row before answering.

When the user asks about purchase HISTORY for an item — "when did
we buy", "what dates", "prices", "where did we buy", "from which
store", "how much per unit" — use the ``purchase_history`` array on
each item_search_results row. Each entry is one purchase line and
carries ``date`` (YYYY-MM-DD), ``store``, ``unit_price``, and
``line_total``. Up to 25 most-recent rows per product. Render the
history as a bullet list grouped by product, never as a long inline
comma-separated string. Pick which fields to include based on the
question: dates only → "- 2026-04-09"; with prices → "- 2026-04-09
@ Costco — $6.89"; with totals → append " (×qty = $X.XX)" only when
the user asked for totals.

For analytical questions ("anything interesting", "any patterns",
"trends", "buying habits", "where do we buy X most/least", "how
often", "are we paying more"), DO NOT refuse — read the
``insights`` block on each item_search_results row instead. It
already contains ``store_breakdown`` (count + spend per store, sorted
by count desc), ``top_store_share_pct``, ``avg_days_between_purchases``,
``cadence_change_pct_recent_vs_older`` (negative = buying more often
recently), ``unit_price_min/max/avg/last``, and
``unit_price_volatility_pct``. Translate those numbers into plain
English observations. Pick the 2–3 most interesting ones; don't
recite every field.

If ``item_search_topic_carried_from_history`` is true, the user's
current message had no explicit product name and we reused the term
from a previous turn — acknowledge briefly ("for tomatoes...") so
they know which item the answer covers.

If ``item_search_results`` is empty but the question clearly named
an item, say so rather than inventing a number; suggest checking the
Inventory or Receipts page. NEVER invent a store name that isn't in
``store_breakdown`` — if the user asks about a store you don't see
there, say so.

FORMATTING (the UI renders a small subset of markdown — use it):

  * Lead with a one-line headline using **bold** for the headline
    label and the answer.
  * When you have several matching products / categories / months,
    follow the headline with a short bullet list using "- " for each
    item. Format each bullet as "- ProductName — N" or
    "- Category — $X.XX (Δ%)".
  * Separate independent answers with a blank line.
  * Do NOT use tables, code blocks, or "###" headings unless the user
    explicitly asks for them.
  * Never include the data_context JSON, raw user_id values, or any
    field the user wouldn't recognise.

Example for "how many times did we buy tomatoes":

    **Tomatoes:** 12 times.
    - Vine Tomato — 10
    - Roma Tomato — 1
    - Cocktail Tomatoes — 1

Example for "what dates did we buy tomatoes":

    **Tomato purchase history (12 receipts):**

    *Vine Tomato (10):*
    - 2026-04-09
    - 2026-03-30
    - 2026-03-06
    - …

    *Roma Tomato (1):*
    - 2026-02-03

Example for "what dates and prices for tomatoes":

    **Tomato purchase history with prices:**

    *Vine Tomato:*
    - 2026-04-09 @ Costco Wholesale — $6.89
    - 2026-03-30 @ Costco Wholesale — $13.78
    - 2026-03-06 @ Costco Wholesale — $13.98

    *Roma Tomato:*
    - 2026-02-03 @ Costco Wholesale — $17.97

Example for "how much did we spend on groceries this month":

    **Grocery (2026-04):** $626.47 (↓37% vs last month).

Example for "do you see anything interesting in tomato buying pattern?":

    **Tomato buying pattern (12 receipts):**
    - All purchases at Costco Wholesale (100% concentration).
    - Buying on average every 22 days — fairly consistent cadence.
    - Unit price ranged $6.39 – $17.97 (≈180% volatility); the
      $17.97 one is an outlier worth a glance.
    - Most-recent price ($6.89) is about half the average — likely a
      promo run.

Example for "which store did we visit least for tomatoes?":

    **Tomatoes by store:**
    - Costco Wholesale — 12 purchases ($122.52)

    Only one store in the data, so there is no "least visited" to
    compare. Try a different item or expand the date range.

Keep answers terse — one headline + at most a short list. Skip
filler ("Sure!", "Of course!", "Here is..."). USD totals always show
two decimals.
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
    # Calendar / history words — without these the message "what dates
    # did we buy tomatoes" matches the product "Organic Dates" and the
    # bot answers about the wrong thing. Users searching for the fruit
    # can use a more specific term (e.g. "medjool dates").
    "date", "dates", "history", "tracking", "track", "log", "logs",
    "schedule", "schedules", "calendar",
    "before", "after", "between", "during", "around", "near",
    "first", "earliest", "recent", "latest", "previous", "next",
    # Conversational filler that slips through the noun extractor.
    "can", "could", "would", "should", "may", "might", "will", "won't",
    "please", "also", "too", "now", "then", "here", "there", "still",
    "yet", "mean", "means", "meant", "really", "actually", "maybe",
    "though", "either", "neither", "rather", "quite", "kind", "sort",
    "way", "thing", "stuff",
    # Analytical / pattern-question vocabulary that should never be
    # treated as a product name. Keeps "do you see anything
    # interesting in tomato pattern" from triggering false-positive
    # ILIKE searches for "see", "anything", "interesting", "pattern".
    "store", "stores", "visited", "visit", "shop", "shopping",
    "most", "least", "best", "worst", "common", "rare", "rarely",
    "often", "usual", "usually",
    "trend", "trends", "pattern", "patterns", "insight", "insights",
    "interesting", "notable", "notice", "noticed", "anything",
    "something", "nothing", "see", "anymore", "ever", "never",
    "seem", "seems", "looks", "look", "looking",
    "compare", "comparing", "comparison", "vs", "versus", "between",
    # Money/measurement words that aren't products themselves.
    "price", "prices", "cost", "costs", "amount", "amounts", "value",
    "values", "quantity", "qty", "unit", "units", "size", "weight",
    "average", "median", "mean", "min", "minimum", "max", "maximum",
    "sum", "summary", "report", "reports", "stat", "stats",
    "statistic", "statistics",
}


def _extract_item_query_terms(message: str, max_terms: int = 2) -> list[str]:
    """Pull plausible product nouns out of a free-text question.

    Heuristic — keeps lowercase non-stopword tokens of length >= 3,
    then ranks them so the longest (most specific) tokens survive the
    ``max_terms`` cap. "tomatoes and onions" still produces both,
    but a noisy "do you see anything interesting in tomato pattern"
    yields just ["tomato"] instead of dragging "see"/"anything"/etc.
    along into ILIKE searches.
    """
    import re

    candidates: list[str] = []
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
        candidates.append(token)

    # Rank by length descending — long words tend to be specific
    # product nouns, short ones tend to be filler that slipped past
    # the stoplist. Tie-break by original order so "tomato" beats
    # "onion" when both are equally specific.
    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda pair: (-len(pair[1]), pair[0]))
    return [tok for _, tok in indexed[:max_terms]]


def _compute_item_insights(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Pre-compute the analysis the bot used to make up.

    Given the per-product purchase history (date / store / unit_price
    / line_total), return a small JSON-friendly insights blob the
    model can read off directly when the user asks about patterns,
    cadence, store concentration, or price changes. Without this the
    model would either hallucinate or refuse to analyse.
    """
    if not history:
        return {}

    # Store breakdown — count + spend per store, sorted by count desc.
    store_stats: dict[str, dict[str, float]] = {}
    for h in history:
        store = h.get("store") or "Unknown"
        st = store_stats.setdefault(store, {"count": 0, "total_spent": 0.0})
        st["count"] += 1
        st["total_spent"] += float(h.get("line_total") or 0.0)
    store_breakdown = [
        {"store": s, "count": int(v["count"]), "total_spent": round(v["total_spent"], 2)}
        for s, v in store_stats.items()
    ]
    store_breakdown.sort(key=lambda x: (-x["count"], -x["total_spent"]))
    top_store_pct = (
        int(round(store_breakdown[0]["count"] / len(history) * 100))
        if store_breakdown else 0
    )

    # Cadence — average days between consecutive purchases. History is
    # already sorted desc; flip to chronological for the diff.
    from datetime import datetime as _dt
    dates: list[_dt] = []
    for h in history:
        ds = h.get("date")
        if ds:
            try:
                dates.append(_dt.strptime(ds, "%Y-%m-%d"))
            except ValueError:
                continue
    dates.sort()
    avg_days_between: float | None = None
    if len(dates) >= 2:
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        avg_days_between = round(sum(gaps) / len(gaps), 1)

    # Cadence trend — recent half vs older half. Negative pct = buying
    # more often, positive = buying less often.
    cadence_change_pct: int | None = None
    if len(dates) >= 6:
        mid = len(dates) // 2
        old_gaps = [(dates[i] - dates[i - 1]).days for i in range(1, mid)]
        new_gaps = [(dates[i] - dates[i - 1]).days for i in range(mid + 1, len(dates))]
        if old_gaps and new_gaps:
            old_avg = sum(old_gaps) / len(old_gaps)
            new_avg = sum(new_gaps) / len(new_gaps)
            if old_avg > 0:
                cadence_change_pct = int(round(((new_avg - old_avg) / old_avg) * 100))

    # Price stats.
    prices = [float(h.get("unit_price") or 0.0) for h in history if (h.get("unit_price") or 0.0) > 0]
    price_min = round(min(prices), 2) if prices else None
    price_max = round(max(prices), 2) if prices else None
    price_avg = round(sum(prices) / len(prices), 2) if prices else None
    price_last = round(float(history[0].get("unit_price") or 0.0), 2) if history else None
    price_change_pct: int | None = None
    if price_min is not None and price_max is not None and price_min > 0:
        # Volatility as a simple max/min ratio in percent.
        price_change_pct = int(round((price_max - price_min) / price_min * 100))

    return {
        "store_breakdown": store_breakdown,
        "top_store_share_pct": top_store_pct,
        "avg_days_between_purchases": avg_days_between,
        "cadence_change_pct_recent_vs_older": cadence_change_pct,
        "unit_price_min": price_min,
        "unit_price_max": price_max,
        "unit_price_avg": price_avg,
        "unit_price_last": price_last,
        "unit_price_volatility_pct": price_change_pct,
    }


def _expand_term_variants(term: str) -> list[str]:
    """Produce singular/plural variants of a search term so a query for
    "tomatoes" still matches products named "Tomato" / "Vine Tomato".

    Cheap heuristic — generates a small superset of variants and lets
    the ILIKE substring match do the rest. Order doesn't matter; the
    caller dedupes.
    """
    base = term.lower().strip()
    if not base:
        return []
    variants = {base}
    # Trailing-plural strip.
    if base.endswith("ies") and len(base) > 4:
        variants.add(base[:-3] + "y")          # companies -> company
    if base.endswith("es") and len(base) > 3:
        variants.add(base[:-2])                # tomatoes -> tomato, dishes -> dish
    if base.endswith("s") and len(base) > 3 and not base.endswith("ss"):
        variants.add(base[:-1])                # carrots -> carrot
    # Pluralisation in case the user typed singular but products are plural.
    if not base.endswith("s"):
        variants.add(base + "s")               # tomato -> tomatos? loose match
    if base.endswith("y") and len(base) > 3:
        variants.add(base[:-1] + "ies")        # company -> companies
    return [v for v in variants if len(v) >= 3]


def _search_items(session, terms: list[str], limit: int = 15) -> list[dict[str, Any]]:
    """Return per-product purchase stats for products whose name
    matches any of the supplied terms (case-insensitive substring).

    Each input term is expanded into singular/plural variants so a
    user query for "tomatoes" still hits products named "Tomato",
    "Roma Tomato", and "Vine Tomato". Joined to Purchase so we can
    return last-bought date and exclude refund rows; household-wide
    for parity with the rest of the context.
    """
    if not terms:
        return []
    import sqlalchemy as _sa

    expanded: list[str] = []
    seen: set[str] = set()
    for t in terms:
        for v in _expand_term_variants(t):
            if v not in seen:
                seen.add(v)
                expanded.append(v)
    if not expanded:
        return []

    likes = [_sa.func.lower(Product.name).like(f"%{t}%") for t in expanded]
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

    # Pull the per-product purchase history (date + store + price)
    # so the bot can answer "what dates did we buy X", "and prices
    # too", or "from which store" without inventing data. Capped at 25
    # most-recent rows per product. Single follow-up query keyed on
    # the ids we already fetched — household-wide, refunds excluded.
    product_ids = [int(r[0]) for r in rows]
    history_by_product: dict[int, list[dict[str, Any]]] = {pid: [] for pid in product_ids}
    if product_ids:
        history_rows = (
            session.query(
                ReceiptItem.product_id,
                Purchase.date,
                Store.name,
                ReceiptItem.unit_price,
                ReceiptItem.quantity,
            )
            .join(Purchase, Purchase.id == ReceiptItem.purchase_id)
            .outerjoin(Store, Store.id == Purchase.store_id)
            .filter(ReceiptItem.product_id.in_(product_ids))
            .filter(
                _sa.or_(
                    Purchase.transaction_type.is_(None),
                    Purchase.transaction_type != "refund",
                )
            )
            .order_by(Purchase.date.desc(), ReceiptItem.id.desc())
            .all()
        )
        for pid, dt, store_name, unit_price, qty in history_rows:
            bucket = history_by_product.get(int(pid))
            if bucket is None or len(bucket) >= 25:
                continue
            unit_p = float(unit_price or 0.0)
            line_q = float(qty or 0.0)
            bucket.append({
                "date": dt.strftime("%Y-%m-%d") if dt else None,
                "store": store_name or "Unknown",
                "unit_price": round(unit_p, 2),
                "line_total": round(unit_p * line_q, 2),
            })

    out: list[dict[str, Any]] = []
    for product_id, name, count, qty, total, first_dt, last_dt in rows:
        history = history_by_product.get(int(product_id), [])
        out.append({
            "product_id": int(product_id),
            "product_name": name,
            "purchase_count": int(count or 0),
            "total_quantity": round(float(qty or 0.0), 2),
            "total_spent": round(float(total or 0.0), 2),
            "first_bought": first_dt.strftime("%Y-%m-%d") if first_dt else None,
            "last_bought": last_dt.strftime("%Y-%m-%d") if last_dt else None,
            "purchase_history": history,
            "insights": _compute_item_insights(history),
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
    carried_from_history = False
    # Topic carry-over — if the user's current message has no item
    # term but they're clearly continuing a thread ("anything
    # interesting?", "and prices too", "from which store"), reuse the
    # most recent terms we successfully extracted from a prior user
    # turn. Walk back at most 5 turns so a long unrelated history
    # doesn't drag stale topics back in.
    if not item_terms:
        history_walked = 0
        # ``user_message`` is THIS turn — walk only the previously
        # persisted user messages stored in g.db_session before the
        # caller. Since ``build_data_context`` doesn't have direct
        # access to the chat-message history, we rely on the
        # session-attached query.
        try:
            recent_user_msgs = (
                session.query(ChatMessage)
                .filter(ChatMessage.user_id == user.id)
                .filter(ChatMessage.role == "user")
                .filter(ChatMessage.flagged == False)  # noqa: E712
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(6)
                .all()
            )
        except Exception:  # noqa: BLE001
            recent_user_msgs = []
        for past in recent_user_msgs:
            if past.content == user_message:
                # Skip the row we just persisted for this turn.
                continue
            past_terms = _extract_item_query_terms(past.content)
            if past_terms:
                item_terms = past_terms
                carried_from_history = True
                break
            history_walked += 1
            if history_walked >= 5:
                break
    item_results = _search_items(session, item_terms) if item_terms else []

    return {
        # Intentionally minimal user identity — no email, no FK ids
        # the model could try to leak. Just the display name so it can
        # address the admin politely.
        "user": {"name": user.name},
        "current_month": cur_start.strftime("%Y-%m"),
        "previous_month": prev_start.strftime("%Y-%m"),
        "month_total_current": round(sum(cur.values()), 2),
        "month_total_previous": round(sum(prev.values()), 2),
        "by_category": by_category,
        "top_stores_current_month": _top_stores(session, cur_start, cur_end),
        "uncategorized_count_current_month": _uncategorized_count(session, cur_start, cur_end),
        "item_search_terms": item_terms,
        "item_search_results": item_results,
        "item_search_topic_carried_from_history": carried_from_history,
        "categories_supported": sorted(BUDGET_CATEGORIES),
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
    rules_compact = "; ".join(f"{k}: {v}" for k, v in CATEGORY_RULES.items())
    system_prompt = (
        f"{GUARDRAIL_PROMPT.strip()}\n\n"
        f"{SYSTEM_PROMPT.strip()}\n\n"
        f"Today's date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
        f"category_rules: {rules_compact}\n\n"
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
    cloud = {"gemini", "openai", "anthropic", "openrouter"}
    supported = cloud | {"ollama"}

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

    # 1. Active model first — but only if it's a cloud provider.
    #    The user's "active model" for OCR is sometimes Ollama, and we
    #    don't want a slow local model to take precedence over the cloud
    #    fallbacks for the chat path. Ollama is reserved for the final
    #    safety-net slot below.
    active = _resolve_chat_model(session, user)
    if active is not None and (active.provider or "").strip().lower() in cloud:
        _push_model_attempt(active, _push)

    # 2. Other enabled cloud AIModelConfigs (skip ollama here).
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
        if provider not in cloud:
            continue
        _push_model_attempt(cfg, _push)

    # 3. Env-var fallbacks. Chat-specific keys take priority over the
    #    OCR keys so the operator can attribute spend separately on the
    #    provider's billing console (e.g. one OpenRouter key for receipt
    #    OCR, a different one for the assistant). Placeholder values
    #    starting with "your_" are treated as unset.
    def _chat_key(*names: str) -> str:
        for name in names:
            value = (os.getenv(name) or "").strip()
            if value and not value.startswith("your_"):
                return value
        return ""

    openai_env = _chat_key("OPENAI_CHAT_API_KEY", "OPENAI_API_KEY")
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
    openrouter_env = _chat_key("OPENROUTER_CHAT_API_KEY", "OPENROUTER_API_KEY")
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
    anthropic_env = _chat_key("ANTHROPIC_CHAT_API_KEY", "ANTHROPIC_API_KEY")
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
