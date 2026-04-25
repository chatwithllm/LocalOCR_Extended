# Chat Assistant: Temporal & Consumption Questions

**Date**: 2026-04-25
**Status**: approved (pending implementation)
**Owner**: chat-assistant

## Goal

Extend the in-app chat assistant so it can answer behavioural / temporal
questions about household shopping that today's `build_data_context`
does not cover:

- "When did we shop lately?"
- "How frequently do we shop?"
- "How much are we consuming?"

## Non-goals

- Predicting future spend.
- Building a tool-calling architecture (deferred — see Alternatives).
- New UI in the chat panel — the panel already renders markdown bullets.

## Decisions captured during brainstorming

| # | Question | Decision |
|---|----------|----------|
| 1 | Framing of "consuming" — $, items, or category? | Bot picks from question phrasing; expose all three signals. |
| 2 | Scope — household vs per-person? | Both. Per-person breakdown returned alongside household roll-up. |
| 3 | Time windows for cadence/trend? | Last 7, 30, and 90 days. |
| 4 | Recent-receipt count for "when did we shop lately"? | Top 5 across household. |
| 5 | Always-on vs lazy-load? | Lazy — only when a temporal-intent regex hits the user message. Mirrors the existing `item_search_results` lazy pattern. |

## Architecture

Single new block — `shopping_activity` — added to the dict returned by
`build_data_context` in `src/backend/chat_assistant.py`. Two new helpers:

1. `_extract_temporal_intent(message: str) -> bool`
2. `_compute_shopping_activity(session, user, now) -> dict | None`

Wire-up at the tail of `build_data_context`, after the existing
item-search block:

```python
shopping_activity = None
if _extract_temporal_intent(user_message or ""):
    shopping_activity = _compute_shopping_activity(session, user, now)
return {
    ...,
    "shopping_activity": shopping_activity,
}
```

When the extractor returns False the key is `None` and no DB queries
fire — zero token / latency cost on unrelated turns.

### Temporal-intent extractor

Regex on the lower-cased user message:

```
\b(when|lately|recent(ly)?|last\s+(time|visit|trip|shop)|frequent(ly)?|often|trend|rate|consumption|consum(e|ing))\b
| how\s+(much|many|fast)\s+(do\s+)?(we|i)\s+(shop|consum|buy)
| how\s+often
```

Triggers True if any branch matches. Conservative; false positives just
add ~1 KB to the context.

### Aggregator output shape

All counts/sums use `Purchase` rows where `transaction_type ==
"purchase"` (refunds excluded). Per-person attribution mirrors the
existing `_spend_by_person` semantics: `attribution_kind == "split"`
rows count toward each listed person but contribute their full
`total_amount` to the household roll-up only once.

```json
{
  "recent_receipts": [
    {"date": "2026-04-25", "store": "Costco",
     "amount": 142.30, "attribution": "Mom"}
  ],
  "windows": {
    "last_7d":  {"trips": 4,  "spend": 312.10,  "items_count": 38},
    "last_30d": {"trips": 18, "spend": 1432.40, "items_count": 156},
    "last_90d": {"trips": 52, "spend": 4120.55, "items_count": 480}
  },
  "cadence": {
    "avg_gap_days_30d":   1.6,
    "avg_gap_days_90d":   1.7,
    "trips_per_week_30d": 4.2,
    "trips_per_week_90d": 4.0,
    "trend": "steady"
  },
  "per_person": [
    {
      "name": "Mom",
      "windows":  { /* same shape */ },
      "cadence":  { /* same shape minus trend */ },
      "last_trip": {"date": "...", "store": "...", "amount": ...}
    }
  ],
  "top_items_30d": [
    {"name": "milk", "qty": 8, "spend": 32.40}
  ]
}
```

- `recent_receipts` — last 5 household-wide receipts, descending by
  date. Answers "when did we shop". `attribution` resolves to the
  display name when `attribution_user_id` is set, "Mom & Dad" style
  comma-joined names for split rows, or `null` for unattributed rows.
- `windows.items_count` — count of `ReceiptItem` rows joined to
  Purchases inside the window (not summed quantities — counting line
  items is cheaper and roughly tracks shopping basket size).
- `windows.spend` — answers "how much did we spend last week / month /
  quarter" framings.
- `windows.trips` + `cadence` — answer "how often do we shop".
- `top_items_30d` — top 5 product names by purchase-count over the last
  30 days (joined via `ReceiptItem`). Answers "what are we consuming
  most" framings.
- `cadence.trend` — derived: compare `trips_per_week_30d` vs
  `trips_per_week_90d`. `up` if 30d > 90d × 1.15, `down` if 30d < 90d ×
  0.85, else `steady`.

### Empty-data short-circuit

If `windows.last_90d.trips == 0` the aggregator returns `None`. The
system prompt instructs the bot to fall back to its standard "I don't
have enough data" phrasing (already part of the guardrail prompt).

### System-prompt addendum

Append to the data-context instructions in `chat_complete`:

> When `shopping_activity` is present, use it to answer recency,
> frequency, and consumption questions. Pick framing from the user's
> wording: phrases mentioning *spending / budget / cost* → use
> `windows.spend`; *items / products / buying X* → use
> `top_items_30d`; *visits / trips / often* → use
> `cadence`/`windows.trips`. Cite specific dates and stores from
> `recent_receipts` when answering "when did we shop". Never invent
> dates — only quote what's in `recent_receipts` or
> `per_person.last_trip`.

## Alternatives considered

- **Two separate blocks** (`recent_activity` + `consumption_stats`).
  Rejected — extra extractor branches and two functions for one
  conceptual feature; doesn't pay back the maintenance cost.
- **Tool-calling refactor** — every data block becomes a model-driven
  JSON tool call. Rejected for now: huge refactor across all four
  provider chat helpers (Ollama, Anthropic, OpenAI, Gemini), and the
  current zero-tool design is working. Worth revisiting if a third or
  fourth temporal block lands.

## Edge cases

- Refunds excluded via `transaction_type` filter.
- Mixed-currency rows: out of scope (project assumes single currency).
- Time zone: all aggregations use `datetime.now(timezone.utc)` like the
  rest of the file. The user-visible date strings are ISO `YYYY-MM-DD`
  (UTC-anchored) — matches existing item-search output.
- Per-person attribution: shares `_spend_by_person`'s `_ids` helper to
  parse `attribution_user_ids` JSON.
- Multi-person split refunds: skipped because refunds are filtered out.

## Testing

**Unit** — extend `tests/test_chat_assistant.py` (or create if missing):

- `_extract_temporal_intent` — six positive cases ("when did we shop",
  "how often do we go", "consumption rate", "recent shopping", "last
  trip", "frequent visits") + four negative cases ("how much did we
  spend on milk last month", "where do property taxes belong", "list
  uncategorized receipts", "show me top stores").
- `_compute_shopping_activity` — synthetic Purchase rows across 90
  days with mixed attribution. Assert window counts, gap math, trend
  calculation, and per-person breakdown.
- Empty-data path: zero rows → returns `None`.
- Refund row included in DB → not counted in trips/spend.

**Smoke (manual)** — live chat panel as the admin user:

1. "When did we shop lately?" → reply names dates + stores from
   `recent_receipts`.
2. "How often do we shop?" → reply uses cadence numbers.
3. "How much are we consuming?" → reply picks framing based on phrasing
   variants.
4. Ask an unrelated question ("how much did we spend on groceries this
   month?") → trace shows `shopping_activity: null`, no extra latency.

## Files touched

- `src/backend/chat_assistant.py` — two new helpers (~120 lines), wire
  into `build_data_context`, system-prompt addendum.
- `tests/test_chat_assistant.py` — new tests for extractor + aggregator
  + empty-data short-circuit.

## Out of scope

- Background pre-aggregation / caching. The query volume is small
  (single admin, lazy-loaded) so per-turn computation is fine.
- Item-name normalisation across stores — `top_items_30d` uses the raw
  `ReceiptItem.name` as it stands. Improving normalisation is a
  separate ticket.
- Frontend changes — answers render via the existing chat-bubble
  markdown pipeline.
