# Telegram Shopping Walk — Design Spec

**Date:** 2026-05-14
**Status:** Draft — pending user approval
**Authors:** Assistant + user
**Related:** [Telegram Inventory Walk spec](./2026-05-13-telegram-inventory-walk-design.md) — same architectural pattern.

## 1. Goal

Add a `/shopping` Telegram flow that proactively proposes shopping-list items grouped by category (driven by the existing recommendation engine) and lets the user one-tap-add to the active shopping session. Supports both quick-add (qty=1, no store) and detailed-add (qty + store sub-prompts), plus per-category type-add for items not in the recommendation set.

## 2. Why

- Existing recommendation engine (`generate_recommendations.get_recommendations()`) already detects low-inventory, regular-use, seasonal, and price-deal items but only surfaces them on the web shopping page.
- Users (family members) want to plan shopping while doing other things; pushing the same recommendation list to Telegram with one-tap add removes the friction of "open web → click around" for the most common workflow.
- Mirror the just-shipped inventory walk: consistent UX, same state-machine pattern, low cognitive load for users who already know `/inventory`.

## 3. Scope

**In scope (v1):**
- `/shopping` slash command in Telegram.
- Smart-trigger proactive nudge when `len(get_recommendations()) >= 8` and chat is eligible.
- Category-grouped walk: each non-empty recommendation category becomes a step.
- Sequential one-item-at-a-time prompt within a category (matches inventory walk).
- Four action buttons per item: `[+ Add]` (qty=1, no store), `[+ Add w/ qty+store]` (sub-flow), `[Skip]`, `[Already have]`.
- Detailed-add sub-flow: qty picker (1/2/3/4/5/custom) → store picker (top 3 stores by purchase count + Skip + Other typed).
- Per-category `+ Add custom item` button at end of category: typed name → qty → store → insert with `product_id=NULL` and `source='telegram_shopping'`.
- Insert via `manage_shopping_list._ensure_current_session(session)` + `ShoppingListItem`. Reuse existing dedup against same-product OPEN items in same shopping session.
- Resume offer if active mid-walk when user sends `/shopping` again.
- Mid-walk `[✓ Done for now]` ends gracefully with summary.
- End-of-walk summary with view-shopping-list URL + bridge button into inventory walk.
- Daily proactive nudge with Yes/Later/Mute controls.
- Feature flag for safe rollout; pilot-chat allowlist.

**Out of scope (v1):**
- Editing existing shopping list items via Telegram (qty, store, note changes — use web).
- Removing items already on the list (use web).
- Sharing or emailing the shopping list from inside the walk.
- Auto-creating Products from custom typed names (just stores free-text on `ShoppingListItem.name`).
- Cross-household shopping list (single-household model unchanged).
- Price/total estimates in the Telegram summary (web shows them already).

## 4. User flow

### Happy path

```
Bot (nudge): 📋 12 items recommended across 4 categories. Plan shop?
             [▶ Yes] [⏰ Later] [🔕 Mute 7d]

User taps Yes
Bot: 📋 Plan shopping
     12 items recommended across 4 categories:
     [🥫 Pantry · 5]   [🥶 Fridge · 4]
     [🥦 Produce · 2]  [🧴 Bathroom · 1]
     [Cancel]

User taps [🥫 Pantry · 5]
Bot: 🥫 Pantry · 1/5
     🫒 Olive Oil
     Low stock · last bought 22 days ago at Costco
     [+ Add]  [+ Add w/ qty+store]
     [⏭ Skip] [✓ Already have]
     [✓ Done for now]

User taps [+ Add]
Bot edits → Pantry · 2/5 (added: 1) ... next item ...

... (continues 5 items) ...

After last item:
Bot: 🥫 Pantry — done.
     Added 3 · skipped 1 · already had 1
     Anything else for Pantry?
     [+ Add custom item]
     [→ Next: Fridge]  [✓ Done for now]

User taps [+ Add custom item]
Bot: What's the item name?  [← Cancel]
User: (types) Bay Leaves
Bot: Bay Leaves — how many?
     [1] [2] [3] [4] [5] [✏ Custom qty]  [← Back]
User taps [1]
Bot: Bay Leaves × 1 — where?
     [⏭ Skip store]
     [🛒 Costco] [🛒 Sprouts] [🛒 Trader Joe's]
     [✏ Other store]  [← Back]
User taps [Costco]
Bot: ✅ Bay Leaves × 1 → Costco added.
     [+ Add another custom]
     [→ Next: Fridge]  [✓ Done for now]

User taps [→ Next: Fridge] → Fridge walk continues …

End:
Bot: ✅ Shopping plan complete
     Added:        8
     Skipped:      3
     Already had:  1
     Custom added: 2
     [📋 View shopping list]  [📦 Inventory walk]
```

### Resume

```
User: /shopping  (during active session)
Bot:  You have a shopping plan in progress.
      Pantry · 3/5 done.
      [▶ Resume]  [↻ Start over]
```

### Smart-trigger nudge

Daily 09:30 cron checks: any chat with ≥ 8 active recommendations, not muted, no walk in progress, no nudge sent within last 3 days → send nudge.

## 5. Data model

### New table — migration `032_telegram_shopping_session.py`

```python
class TelegramShoppingSession(Base):
    __tablename__ = "telegram_shopping_session"

    chat_id              = Column(String(64), primary_key=True)
    user_id              = Column(Integer, ForeignKey("users.id"), nullable=True)
    status               = Column(String(20), nullable=False, default="active")
                           # active | done | abandoned

    # Walk-by-category state
    category_queue       = Column(JSON, nullable=False, default=list)
                           # ordered list[str] of remaining categories
    current_category     = Column(String(40), nullable=True)
    item_queue           = Column(JSON, nullable=False, default=list)
                           # list[{"product_id": int, "name": str, "category": str,
                           #       "reason_label": str}] for current category page
    cursor               = Column(Integer, nullable=False, default=0)

    # Per-item sub-flow state
    pending_prompt       = Column(String(30), nullable=True)
                           # 'category' | 'item' | 'qty' | 'store'
                           # | 'custom_name' | 'custom_qty' | 'custom_store'
                           # | 'category_end' | 'resume' | None (end)
    pending_action       = Column(String(20), nullable=True)
                           # 'add_detailed' | 'custom_add'

    last_item_id         = Column(Integer, nullable=True)
                           # product_id when adding existing rec
    pending_name         = Column(String(255), nullable=True)
                           # typed name during custom-add
    pending_qty          = Column(Float, nullable=True)
                           # picked qty, waiting on store

    stats                = Column(JSON, nullable=False, default=dict)
                           # {added, skipped, already_have, custom_added}

    # Nudge prefs (per-chat)
    nudge_muted_until    = Column(DateTime, nullable=True)
    last_nudge_sent_at   = Column(DateTime, nullable=True)

    started_at           = Column(DateTime, default=utcnow)
    last_action_at       = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_tg_shop_status", "status"),
        Index("ix_tg_shop_last_action", "last_action_at"),
    )
```

**Invariants:**
- One row per `chat_id` (PK).
- "Start over" mutates in place: clears walk state, preserves `nudge_muted_until` + `last_nudge_sent_at`.
- Idle timeout: if `last_action_at < now - 30 min` on next callback arrival, session is auto-abandoned.

### Migration metadata
- `revision = "032_telegram_shopping_session"`
- `down_revision = "031_telegram_inventory_session"` (the actual revision id from the previously-merged migration file)

### Inventory of writes per action

| Action | DB writes |
|--------|-----------|
| `shop:add` | Insert `ShoppingListItem(qty=1, preferred_store=None, source='telegram_shopping')` if not duplicate. Stats `added++`. |
| `shop:add+` → `qty:n` → `store:S` | Insert `ShoppingListItem(qty=n, preferred_store=S)`. Stats `added++`. |
| `shop:skip` | No DB write. Stats `skipped++`. |
| `shop:have` | No DB write. Stats `already_have++`. |
| `shop:custom` → name → qty → store | Insert `ShoppingListItem(product_id=NULL, name=typed, quantity=picked, preferred_store=picked)`. Stats `custom_added++`. |

### Dedup

Per spec on Telegram Inventory Walk: existing OPEN `ShoppingListItem` for `(shopping_session_id, product_id, status='open')` short-circuits — returns existing row, does NOT bump stats. For custom items (NULL product_id), name-based dedup is out of scope v1 (treat each typed entry as fresh).

### Top-stores query

```sql
SELECT s.name
FROM stores s
JOIN purchases p ON p.store_id = s.id
WHERE COALESCE(s.is_payment_artifact, 0) = 0
  AND COALESCE(s.visibility_override, '') <> 'hidden'
GROUP BY s.id, s.name
ORDER BY COUNT(p.id) DESC
LIMIT 3;
```

Empty result → store picker shows only `[Skip][Other ✏]`.

### Source of recommendations

Single call to `generate_recommendations.get_recommendations()` at walk start, cached in `category_queue` + `item_queue` for the duration. Re-fetched on `shop:restart`. Each rec contributes one `{product_id, name, category, reason_label}` dict in `item_queue`.

`category_queue` is ordered by rec-count descending (most-recommended categories first), matching the order shown on the category screen.

`reason_label` derived from rec kind:
- `low_stock` → `"Low stock · last bought N days ago at <store>"`
- `regular_use` → `"Regular item · N days since last buy"`
- `seasonal` → `"Seasonal pick"`
- `price_deal` → `"Price drop · was $X.XX now $Y.YY"`

## 6. State machine

```
                                 ┌─────────────┐
   /shopping ─────────────────► │  CATEGORY   │ ◄── nudge:shop:yes
                                 │             │ ◄── shop:cat_done after last item if more categories
                                 └──────┬──────┘
                                        │ shop:cat:<C>
                                        ▼
                                 ┌─────────────┐
                                 │    ITEM     │ ◄── cursor+1 after add/skip/have
                                 │  (i/N)      │ ◄── return from qty/store sub-flows
                                 └──────┬──────┘
            ┌─────────┬─────────────┬──────────────┬──────────────┐
        shop:add  shop:add+    shop:skip     shop:have       shop:done
            │         │             │              │              │
            ▼         ▼             ▼              ▼              ▼
        insert    QTY prompt    stats.skipped  stats.have      END
        qty=1     ▼ shop:qty:N  cursor+1       cursor+1
        cursor+1  STORE prompt
                  ▼ shop:store:S
                  insert qty,store
                  cursor+1

   cursor == len(item_queue):
       ┌──────────────────────────┐
       │    CATEGORY_END          │
       │  Anything else?          │
       └──────────────────────────┘
       ├ shop:custom    → CUSTOM_NAME (typed text)
       │                  → CUSTOM_QTY (button)
       │                  → CUSTOM_STORE (button)
       │                  → insert, back to CATEGORY_END
       ├ shop:cat_done  → pop next category from category_queue → ITEM
       │                  if queue empty → END
       └ shop:done      → END (summary)

   END: render summary, status='done', pending_prompt=None.
        [📋 View shopping list]  [📦 Inventory walk]
```

### Verb table (compact callback_data, fits 64-byte cap)

| Verb pattern | Expected `pending_prompt` | Effect |
|---|---|---|
| `shop:cat:<category>` | `category` | Pop category from queue, load `item_queue`, transition to ITEM |
| `shop:add` | `item` | Insert qty=1 + store=NULL, advance |
| `shop:add+` | `item` | `pending_action='add_detailed'`, render qty prompt |
| `shop:qty:<n>` | `qty` or `custom_qty` | Store qty, render store prompt |
| `shop:qty:cu` | `qty` or `custom_qty` | Render "enter qty" text-prompt — next msg text becomes qty |
| `shop:store:<slug>` | `store` or `custom_store` | Insert + advance / commit-custom |
| `shop:store:skip` | `store` or `custom_store` | Insert without store / commit-custom |
| `shop:store:other` | `store` or `custom_store` | "Type a store name" text-prompt |
| `shop:skip` | `item` | stats++, advance |
| `shop:have` | `item` | stats++, advance |
| `shop:done` | `item` or `category_end` | End walk |
| `shop:custom` | `category_end` | Start custom-add: `pending_prompt='custom_name'` |
| `shop:cat_done` | `category_end` | Pop next category, transition to ITEM (or END) |
| `shop:back` | `qty` or `store` or `custom_qty` or `custom_store` | Return to previous sub-prompt |
| `shop:cancel` | `category` | status='abandoned', edit "Cancelled." |
| `shop:resume` | `resume` | Re-render current prompt |
| `shop:restart` | `resume`, `None` | reset_for_start_over, render category screen |
| `nudge:shop:yes` / `:later` / `:mute` | (any) | State-independent; no `pending_prompt` validation |

### Typed-text handling

Three states consume the next inbound `message.text` instead of a callback:
- `pending_prompt == "custom_name"` → text becomes `pending_name`.
- `pending_prompt == "custom_qty"` after `shop:qty:cu` → text parsed as float; non-numeric re-prompts.
- `pending_prompt == "custom_store"` after `shop:store:other` → text becomes free-text store; empty re-prompts.

Webhook handler must check the row's `pending_prompt` BEFORE routing inbound messages to the existing receipt-photo handler — typed text in a shopping-walk state is consumed by the walk, not treated as a new receipt prompt.

### Stale-callback handling

Same as inventory walk: verb-vs-`pending_prompt` mismatch → edit "That button is stale. Showing current step:" + `_rerender_current_prompt(row)` which sends a fresh prompt matching current state.

### Idle timeout

`abandon_if_idle(row)` mirrors the helper from `handle_inventory_walk.py`. 30-min default. Bot replies `Session timed out. /shopping to restart.`

## 7. Telegram UI copy

Defined in section 4 (User flow). Implementation notes:

- All step transitions use `editMessageText` (clean chat history).
- Category emoji map reused from `handle_inventory_walk._CATEGORY_EMOJI`; fallback `📦`.
- Reason label varies per rec kind (see section 5).
- Store-picker button labels include `🛒` prefix; store-slug used as callback arg (URL-safe lowercase, e.g. `trader_joes`).
- Top-of-prompt mini-banner shows running `(added: N)` count from `stats`.

### Error copy

| Scenario | Message |
|---|---|
| Stale callback verb | `That button is stale. Showing current step:` + re-render |
| Idle timeout next callback | `Session timed out. /shopping to restart.` |
| Recommendation row vanished | Silent skip + advance + log |
| Custom-name typed empty | `Name can't be empty. Try again:` (state stays) |
| Custom-qty non-numeric | `Couldn't parse that as a number. Try again:` |
| Empty recommendation set on start | `🎉 Nothing to suggest right now — shopping list looks good.` |

## 8. Proactive nudge

**Scheduler:** APScheduler cron, daily 09:30 server local. Co-located with existing `check_inventory_thresholds.start_threshold_checker()` registration. Runs 30 min after inventory nudge to avoid simultaneous fires.

**Eligibility per chat_id:**
- chat_id allowlisted (env `TELEGRAM_AUTHORIZED_CHAT_IDS` falling back to distinct `TelegramReceipt.telegram_user_id`).
- `nudge_muted_until` NULL or past.
- No `status='active'` row with non-empty `category_queue`.
- `last_nudge_sent_at` NULL or older than `SHOPPING_NUDGE_GAP_DAYS` (default 3).
- `len(get_recommendations()) >= SHOPPING_NUDGE_MIN_RECS` (default 8).

**Reactions:**
- `nudge:shop:yes` → "Starting walk…" edit, then `start_shopping_walk(chat_id)`.
- `nudge:shop:later` → `nudge_muted_until = now + 3d`. Reply: `OK, I'll ask again in a few days.`
- `nudge:shop:mute` → `nudge_muted_until = now + 7d`. Reply: `Muted for a week.`

**Anti-spam:**
- Minimum 3 days between nudges.
- Two consecutive ignored nudges (no callback within 24h of send) → suppress for 14 days.
- Telegram API failure → do not record `last_nudge_sent_at` so next run retries.

**Manual disable:** env `SHOPPING_NUDGE_ENABLED=0` short-circuits the cron job. Default off; flip on after pilot stability.

## 9. Module layout

```
src/backend/
├── handle_telegram_messages.py     (extend: route /shopping + shop:* + nudge:shop:*)
├── handle_inventory_walk.py        (unchanged — sibling module)
├── handle_shopping_walk.py         (NEW — state machine, rendering, dispatch, handlers)
├── shopping_nudge_job.py           (NEW — daily eligibility + send job)
├── generate_recommendations.py     (unchanged — consumed read-only)
├── manage_shopping_list.py         (unchanged — consumed via _ensure_current_session)
└── check_inventory_thresholds.py   (extend: register shopping nudge job)

alembic/versions/
└── 032_telegram_shopping_session.py   (NEW migration)

tests/
├── test_telegram_shopping_walk.py     (NEW unit tests)
├── test_shopping_nudge_job.py         (NEW)
├── test_telegram_shopping_e2e.py      (NEW E2E)
└── test_migration_032.py              (NEW)
```

`handle_shopping_walk.py` is independent from `handle_inventory_walk.py`. Shared utility extraction (env parsers, send/edit wrappers) deferred — if both modules grow further, a `telegram_walk_common.py` is a follow-up refactor, not part of v1.

## 10. Feature flags & rollout

| Flag | Purpose | Default |
|---|---|---|
| `TELEGRAM_SHOPPING_WALK_ENABLED` | Gates `/shopping` command + callbacks | `0` |
| `TELEGRAM_SHOPPING_WALK_PILOT_CHATS` | Comma-list of chat_ids for pilot | empty |
| `SHOPPING_NUDGE_ENABLED` | Gates daily nudge cron | `0` |
| `SHOPPING_NUDGE_MIN_RECS` | Min recommendation count to nudge | `8` |
| `SHOPPING_NUDGE_GAP_DAYS` | Min days between nudges | `3` |

**Rollout order:**

1. Migration 032 (additive, no breakage).
2. Code deployed with all flags off.
3. Smoke-test on dev with prod recommendation data pulled.
4. Flip `TELEGRAM_SHOPPING_WALK_ENABLED=1` + `_PILOT_CHATS=<one-chat>`.
5. After 3 stable days: open to all allowlisted chats, flip `SHOPPING_NUDGE_ENABLED=1`.

## 11. Testing strategy

### Unit — state machine (`tests/test_telegram_shopping_walk.py`)

- Fresh `/shopping` with no recommendations → "Nothing to suggest right now." reply, row left clean.
- Fresh `/shopping` with recommendations → CATEGORY screen, `pending_prompt='category'`.
- Tap category → ITEM prompt, `item_queue` populated for category, `pending_prompt='item'`.
- `shop:add` → insert `ShoppingListItem(qty=1, source='telegram_shopping')`, stats.added++, cursor advances.
- `shop:add+` → render qty sub-screen, `pending_prompt='qty'`, `pending_action='add_detailed'`.
- `shop:qty:3` → render store sub-screen, `pending_qty=3`, `pending_prompt='store'`.
- `shop:store:costco` → insert with qty=3 + store=Costco, advance.
- `shop:store:skip` → insert without store.
- `shop:store:other` → typed-text state, next message text becomes store.
- `shop:skip` / `shop:have` → no DB write, correct stats key incremented.
- End-of-category → CATEGORY_END prompt with `+ Add custom` button.
- `shop:custom` → `pending_prompt='custom_name'`, await message text.
- Custom-name text → `pending_name` set, transition to `custom_qty`.
- Custom-qty button → store sub-screen.
- Custom-store choice → insert with product_id=NULL, stats.custom_added++, back to CATEGORY_END.
- `shop:cat_done` → next category OR END.
- End-of-walk → summary edit + status='done' + pending_prompt=None.
- Stale-verb callback → "That button is stale" edit + re-render.
- Idle 30+ min → auto-abandon on next callback.
- `shop:back` from qty → returns to item prompt; from store → returns to qty prompt.

### Unit — nudge (`tests/test_shopping_nudge_job.py`)

- Under threshold → no nudge sent.
- Muted → no nudge.
- Recently nudged (< 3d) → no nudge.
- Active walk in progress → no nudge.
- Eligible → POST sent, `last_nudge_sent_at` updated.
- Telegram fail → `last_nudge_sent_at` NOT updated.
- `SHOPPING_NUDGE_ENABLED=0` → job no-ops.
- `nudge:shop:later` → `nudge_muted_until = now + 3d`.
- `nudge:shop:mute` → `nudge_muted_until = now + 7d`.

### Migration (`tests/test_migration_032.py`)

- `revision = "032_telegram_shopping_session"`.
- `down_revision = "031_telegram_inventory_session"`.
- Upgrade creates table with expected columns + indexes.
- Idempotent (running twice → no error).
- Downgrade drops table + indexes cleanly; no-op when table absent.

### E2E (`tests/test_telegram_shopping_e2e.py`)

- Full happy-path: `/shopping` → category → 2 quick-adds → 1 detailed-add → custom-add → next category → done. Asserts ShoppingListItem rows (qty, store, source), stats dict, final status='done'.
- Two chats walking simultaneously → no state cross-talk, two separate session rows.

### Smoke-test checklist

- [ ] Send `/shopping` from pilot chat → category screen with stale counts.
- [ ] Tap category → first item rendered with reason label and "last bought" info.
- [ ] `[+ Add]` → ShoppingListItem appears in `/shopping/list` web (source=`telegram_shopping`, qty=1).
- [ ] `[+ Add w/ qty+store]` → pick qty 3 → pick Costco → row has qty=3, preferred_store=Costco.
- [ ] `[+ Add custom item]` → type "Bay Leaves" → qty 1 → Sprouts → row with product_id=NULL, name=Bay Leaves.
- [ ] Skip/Already have → no rows, stats increment.
- [ ] `[✓ Done for now]` → summary with all 4 counts.
- [ ] Run `run_daily_shopping_nudge()` manually → message arrives once on eligible chats.
- [ ] Mute 7d → next run skips chat.
- [ ] Container restart mid-walk → re-tap stale button → "stale" notice + fresh prompt.
- [ ] Backup → restore round-trip preserves `telegram_shopping_session` rows; no orphan FKs.

## 12. Risks & open questions

| Risk | Mitigation |
|------|------------|
| Long category lists overwhelm user | Sequential walk + `[✓ Done for now]` mid-walk; future pagination if a single category has 15+ items |
| Recommendation engine produces noisy items | Reuse existing web filtering; bot just reads what the engine emits |
| Race: same product added on web and via Telegram simultaneously | Dedup query on `(shopping_session_id, product_id, status='open')` makes second insert a no-op (returns existing row) |
| Custom-add typed-text routes wrongly into receipt flow | Webhook handler explicitly checks `pending_prompt in {custom_name, custom_qty, custom_store}` BEFORE existing photo/receipt dispatch |
| Two telegram nudges fire same morning (inventory + shopping) | Stagger schedule: inventory 09:00, shopping 09:30 |
| `get_recommendations()` is slow (synchronous) | Cache result in session row at walk start; only re-fetch on `shop:restart` |
| Store-slug collisions (e.g. "trader_joes" vs "trader_joes_inc") | Pre-slug stores via `canonicalize_store_name`; only top-3 ever appear |

**Open questions deferred to impl (safe to defer — none blocks v1):**
- Whether to upsert a Product row when user custom-adds an item — v1 stores as free-text only.
- Whether the nudge text should preview top 3 items inline (e.g., "...including Olive Oil, Eggs, Bread") — v1 stays brief.
- Whether `shop:restart` should also clear `nudge_muted_until` — v1 preserves it (consistent with inventory walk).

## 13. Non-goals (explicit)

- No schema changes to `Product`, `ShoppingListItem`, or `ShoppingSession`. Walk consumes existing fields (`source`, `preferred_store`, `quantity`).
- No new web UI surfaces. Telegram-only feature.
- No editing/deleting existing list items from Telegram.
- No store auto-creation. Free-text "Other store" stays free-text on `preferred_store`; only known stores produce slugs.
- No analytics or instrumentation beyond existing `stats` JSON for in-walk counts.
