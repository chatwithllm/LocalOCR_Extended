# Telegram Inventory Walk — Design Spec

**Date:** 2026-05-13
**Status:** Draft — pending user approval
**Authors:** Assistant + user

## 1. Goal

Let users keep `Inventory` accurate by chatting with the Telegram bot instead of opening the Extended web UI. Bot walks the user through stale items one at a time, captures how much is left via quantized buttons, and offers to add empty items to the shopping list.

## 2. Why

- Web UI requires login + page nav + per-item slider. Friction → users skip updates → inventory drifts.
- Telegram bot already handles receipts; users have it on their lock screen.
- Quantized "Empty / ¼ / ½ / ¾ / Full" answers match the existing green-fill slider on the inventory tile — same mental model, two taps instead of one slider gesture in a browser.
- Closes the loop between "I'm out of this" and "buy this" without context-switching to another screen.

## 3. Scope

**In scope (v1):**
- `/inventory` slash command in Telegram → category picker → per-item walk.
- Per-item answer via 5 quantized buttons, writes `consumed_pct_override`.
- `manual_low=True` set automatically when Empty is tapped.
- "No longer have this" button → `is_active_window=False`.
- Empty → ask "Add to shopping list?" → inserts `ShoppingListItem` into active `ShoppingSession`.
- Stale-first filter: only items with `last_updated < now() - 14 days` and `is_active_window=True`.
- Walk capped at 10 items per page, "Continue?" prompt after each page.
- Mid-walk controls: Skip, No-longer-have, Done.
- Resume offer if active session exists at next `/inventory` invocation.
- Proactive daily nudge for chats with ≥3 stale items, with Later/Mute controls.
- Feature flag for safe rollout, pilot-chat allowlist.

**Out of scope (v1):**
- Adding net-new products via Telegram.
- Editing category/name/threshold via Telegram.
- Snapshot photo capture during walk.
- Expiry-date editing during walk.
- Web parity for nudge prefs UI (env-driven for v1).
- Multi-language / locale.

## 4. User flow (happy path)

```
User: /inventory
Bot:  📦 Update inventory

      3 categories have stale items (>14 days):
      [Pantry · 8]    [Fridge · 4]
      [Bathroom · 2]
      [Cancel]

User: taps [Pantry · 8]
Bot:  Pantry · 1/8

      🫒 Olive Oil
      Last updated 23 days ago

      How much left?
      [Empty] [¼] [½] [¾] [Full]
      [Skip] [No longer have]
      [✓ Done for now]

User: taps [Empty]
Bot:  🫒 Olive Oil → empty.

      Add to shopping list?
      [✓ Yes] [✗ No] [Already have it]

User: taps [Yes]
Bot:  (edits message) → Pantry · 2/8 [next item …]

… loop until cursor reaches 8 …

Bot:  ✅ Walk complete · Pantry

      Updated: 6   Skipped: 1   Removed: 1
      Added to shopping list: 2

      [📦 Another category]  [📋 View shopping list]
```

### Resume flow

```
User: /inventory   (during active session)
Bot:  You have a walk in progress.
      Pantry · 3/8 done.
      [▶ Resume]  [↻ Start over]
```

### Nudge flow

```
Bot:  📦 8 items haven't been counted in 2+ weeks. Update now?
      [▶ Yes, walk me through]  [⏰ Later]  [🔕 Mute 7d]
```

## 5. Data model

### New table — migration `031_telegram_inventory_session.py`

```python
class TelegramInventorySession(Base):
    __tablename__ = "telegram_inventory_session"

    chat_id              = Column(String(64), primary_key=True)
    user_id              = Column(Integer, ForeignKey("users.id"), nullable=True)
    status               = Column(String(20), nullable=False, default="active")
                           # active | paused | done | abandoned
    current_category     = Column(String(40), nullable=True)
    item_queue           = Column(JSON, nullable=False, default=list)
                           # ordered list[int] of inventory.id for current page
    cursor               = Column(Integer, nullable=False, default=0)
    page                 = Column(Integer, nullable=False, default=1)
    pending_prompt       = Column(String(30), nullable=True)
                           # 'category' | 'level' | 'cart' | 'continue' | 'resume'
    last_item_id         = Column(Integer, nullable=True)
    stats                = Column(JSON, nullable=False, default=dict)
                           # {'updated': int, 'skipped': int, 'removed': int, 'cart_added': int}
    nudge_muted_until    = Column(DateTime, nullable=True)
    last_nudge_sent_at   = Column(DateTime, nullable=True)
    started_at           = Column(DateTime, default=utcnow)
    last_action_at       = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_tg_inv_status", "status"),
        Index("ix_tg_inv_last_action", "last_action_at"),
    )
```

**Invariants:**
- Exactly one row per `chat_id` (PK). A "Start over" mutates the existing row in place: reset `status='active'`, `current_category=NULL`, `item_queue=[]`, `cursor=0`, `page=1`, `pending_prompt='category'`, `stats={}`. Nudge-preference fields (`nudge_muted_until`, `last_nudge_sent_at`) are preserved across resets.
- `pending_prompt` reflects which callback is expected next. Mismatched callbacks are rejected and the current prompt is re-rendered.
- Idle timeout: if `last_action_at < now() - 30 min` on next callback arrival, session auto-abandoned (`status='abandoned'`) with reply `Session timed out. /inventory to restart.`
- Audit trail of past walks lives in `InventoryAdjustment` rows (`reason='telegram_walk'`), not in the session table itself — single-row-per-chat keeps the session table small.

### Inventory mutations (per button)

| Button       | `consumed_pct_override` | `manual_low` | Other                                | InventoryAdjustment? |
|--------------|-------------------------|--------------|--------------------------------------|----------------------|
| Empty        | 1.0                     | True         | `last_updated=now()`                 | yes, reason=`telegram_walk` |
| ¼            | 0.75                    | False        | `last_updated=now()`                 | yes |
| ½            | 0.50                    | False        | `last_updated=now()`                 | yes |
| ¾            | 0.25                    | False        | `last_updated=now()`                 | yes |
| Full         | 0.00                    | False        | `last_updated=now()`                 | yes |
| Skip         | —                       | —            | no write                             | no |
| No longer have | —                     | —            | `is_active_window=False`             | yes, reason=`telegram_walk_remove` |

### Shopping list insert (on Empty → Yes)

Reuses `manage_shopping_list._ensure_current_session(session)` to fetch active `ShoppingSession`, then inserts:

```python
ShoppingListItem(
    session_id=active.id,
    product_id=inv.product_id,
    name=inv.product.name,
    category=inv.product.category,
    quantity=1,
    source="telegram_walk",
)
```

No new API surface; reuses existing helper.

### Stale-item SQL (category screen)

```sql
SELECT product.category, COUNT(*) AS n
FROM inventory
JOIN product ON product.id = inventory.product_id
WHERE inventory.is_active_window = 1
  AND inventory.last_updated < datetime('now', '-14 days')
GROUP BY product.category
HAVING n > 0
ORDER BY n DESC;
```

Within a chosen category, item queue is built as:

```sql
SELECT inventory.id
FROM inventory
JOIN product ON product.id = inventory.product_id
WHERE inventory.is_active_window = 1
  AND inventory.last_updated < datetime('now', '-14 days')
  AND product.category = :category
ORDER BY inventory.last_updated ASC
LIMIT 10 OFFSET (:page - 1) * 10;
```

## 6. State machine

```
                    ┌─────────────┐
   /inventory ────► │  CATEGORY   │ ◄────── Resume → "start over"
                    └──────┬──────┘
                           │ tap [<category>]
                           ▼
                    ┌─────────────┐
                    │   LEVEL     │ ◄─── after non-empty button (cursor+1)
                    │  (item i/N) │ ◄─── after cart answer
                    └──────┬──────┘
        ┌─────────┬───────┬───────────────┬───────────┐
        │ Empty   │ ¼-Full│ Skip          │ No-have   │ Done
        ▼         ▼       ▼               ▼           ▼
     ┌──────┐  write,   write,        deactivate,    END
     │ CART │  cursor+1 cursor+1      cursor+1
     └──┬───┘
        │ Yes/No/Already
        ▼ back to LEVEL (cursor+1)

   When cursor == len(item_queue):
        more pages? ──► CONTINUE [Continue][Done]
                              Continue → page+1, reload queue → LEVEL
                              Done     → END (summary)
        else        ──► END (summary)
```

**Invariants:**
- Each transition runs in a single DB transaction: session state + inventory mutation + optional ShoppingListItem insert, atomic.
- Stale-callback handling: any callback whose verb doesn't match `pending_prompt` is rejected with `"That button is stale. Showing current step:"` and the current prompt is re-rendered.

### Callback_data format

Compact, fits Telegram 64-byte cap.

| Verb           | Example                | Meaning                       |
|----------------|------------------------|-------------------------------|
| `inv:cat:<C>`  | `inv:cat:Pantry`       | category chosen               |
| `inv:lvl:<n>`  | `inv:lvl:0` (Empty) … `inv:lvl:4` (Full) | level button |
| `inv:skip`     |                        | skip current item             |
| `inv:nohave`   |                        | no longer have current item   |
| `inv:done`     |                        | end walk                      |
| `inv:cont`     |                        | next page                     |
| `inv:cart:y`   |                        | add to shopping list          |
| `inv:cart:n`   |                        | don't add                     |
| `inv:cart:a`   |                        | already have it               |
| `inv:resume`   |                        | resume in-progress walk       |
| `inv:restart`  |                        | abandon + new walk            |
| `inv:cancel`   |                        | abandon w/o walking           |
| `nudge:yes`    |                        | nudge → start walk            |
| `nudge:later`  |                        | nudge → suppress 3d           |
| `nudge:mute`   |                        | nudge → mute 7d               |

Verb dispatch lives in new module `src/backend/handle_inventory_walk.py`. Existing `handle_telegram_messages._handle_callback_query` is extended to route `data.startswith(("inv:", "nudge:"))` to the new handler. Webhook command router adds `/inventory` → `_start_inventory_walk(chat_id)`.

## 7. Telegram UI copy

Defined in section 4 (User flow). Implementation notes:

- All step transitions use `editMessageText` (not new messages) so chat stays clean.
- Item emoji pulled from a category → emoji map; fallback `📦`.
- "Last updated N days ago" computed from `inventory.last_updated`. Anything > 60 days reads "2+ months ago" to avoid scary numbers.
- End-summary "View shopping list" button: links to `${PUBLIC_BASE_URL}/shopping/list` if env set; otherwise text-only `Open Extended → Shopping`.

### Error copy

| Scenario                                | Message |
|-----------------------------------------|---------|
| Callback verb mismatch                  | `That button is stale. Showing current step:` + re-render |
| DB error during write                   | `Couldn't save that — try again.` (state unchanged) |
| Inventory row vanished mid-walk         | Silent skip + advance + log |
| All items walked, no stale left at all  | `🎉 All caught up — nothing stale.` |
| Idle timeout next callback              | `Session timed out. /inventory to restart.` |

## 8. Proactive nudge

**Scheduler:** APScheduler job in `check_inventory_thresholds.start_threshold_checker()` (or sibling). Runs daily at 09:00 server local time.

**Eligibility per chat_id:**
- chat_id is in allowlist (env `TELEGRAM_AUTHORIZED_CHAT_IDS`, falling back to distinct `chat_id` in `TelegramReceipt`).
- `nudge_muted_until` is NULL or in the past.
- No `status='active'` session row.
- `stale_item_count >= 3` (same 14-day filter).
- `last_nudge_sent_at` is NULL or older than 5 days.

**Reaction handling:**
- `nudge:yes` → identical to `/inventory` entry.
- `nudge:later` → `nudge_muted_until = now() + 3d`. Reply: `OK, I'll ask again in a few days.`
- `nudge:mute` → `nudge_muted_until = now() + 7d`. Reply: `Muted for a week.`

**Anti-spam:**
- Min 5 days between nudges, always.
- Two consecutive ignored nudges (no callback within 24h) → suppress for 14 days.
- Telegram API failure → do not record `last_nudge_sent_at` so job retries next run.

**Manual disable:** env `INVENTORY_NUDGES_ENABLED=0` short-circuits the job. Default off in dev, on in prod.

**Stale threshold:** `INVENTORY_STALE_DAYS` is read from env at process start with default `14`. Not exposed in user-facing UI in v1. Operators can override via env (see flag table below).

## 9. Module layout

```
src/backend/
├── handle_telegram_messages.py    (existing — extend routing only)
├── handle_inventory_walk.py        (NEW — walk state machine + UI rendering)
├── inventory_nudge_job.py          (NEW — APScheduler-driven daily nudge)
├── manage_shopping_list.py         (existing — reuse _ensure_current_session)
├── active_inventory.py             (existing — reuse for stale-item queries)
└── check_inventory_thresholds.py   (existing — extend to schedule nudge job)

alembic/versions/
└── 031_telegram_inventory_session.py   (NEW migration)

tests/
├── test_telegram_inventory_walk.py     (NEW — state machine + handlers)
├── test_telegram_inventory_e2e.py      (NEW — webhook flow)
├── test_inventory_nudge_job.py         (NEW — eligibility + send)
└── test_migration_031.py               (NEW — additive + idempotent)
```

## 10. Feature flags & rollout

| Flag                                    | Purpose                                 | Default |
|-----------------------------------------|-----------------------------------------|---------|
| `TELEGRAM_INVENTORY_WALK_ENABLED`       | Gates `/inventory` command + callbacks  | `0`     |
| `TELEGRAM_INVENTORY_WALK_PILOT_CHATS`   | Comma-list of chat_ids for pilot phase  | empty   |
| `INVENTORY_NUDGES_ENABLED`              | Gates daily nudge cron                  | `0`     |
| `INVENTORY_STALE_DAYS`                  | Override default 14-day threshold       | `14`    |

**Rollout order:**

1. Migration 031 applied (additive, no breakage).
2. Code deployed with all flags off.
3. Smoke-test on dev with prod data pulled.
4. Flip `TELEGRAM_INVENTORY_WALK_ENABLED=1` + set `_PILOT_CHATS` to one chat.
5. After 3 stable days, unset `_PILOT_CHATS` (open to all allowlisted chats).
6. Flip `INVENTORY_NUDGES_ENABLED=1`.

## 11. Testing strategy

### Unit — state machine (`tests/test_telegram_inventory_walk.py`)

- Fresh `/inventory`, no stale items → "All caught up" reply, no session row.
- Fresh `/inventory`, stale items present → CATEGORY screen, session row created with `pending_prompt='category'`.
- Category tap → LEVEL prompt, `item_queue` has up to 10 ids, `pending_prompt='level'`.
- Each level button (Empty/¼/½/¾/Full) writes correct `consumed_pct_override` + `manual_low`, creates `InventoryAdjustment` row.
- Empty → `pending_prompt='cart'`. Cart Yes inserts `ShoppingListItem`; No/Already advance without insert.
- Skip → cursor advances, no inventory write.
- No-longer-have → `is_active_window=False`, advance.
- Done → `status='done'`, summary message.
- Cursor reaches page end, more pages exist → CONTINUE prompt.
- Cursor reaches end, last page → END summary.
- Stale callback (verb mismatch) → rejected with re-render.
- Idle > 30 min → auto-abandoned on next callback.

### Unit — resume

- `/inventory` with active session → resume offer rendered.
- Resume re-renders current prompt from state.
- Start-over resets the existing row in place (preserving `nudge_muted_until` and `last_nudge_sent_at`); `current_category`, `item_queue`, `cursor`, `page`, `stats`, and `pending_prompt` are cleared.

### Unit — nudge (`tests/test_inventory_nudge_job.py`)

- Under 3 stale → no nudge.
- Muted (future `nudge_muted_until`) → no nudge.
- `last_nudge_sent_at` within 5 days → no nudge.
- Eligible → telegram POST called once, `last_nudge_sent_at` set.
- Mute 7d → `nudge_muted_until = now+7d`.
- Telegram API failure → no `last_nudge_sent_at` write.
- `INVENTORY_NUDGES_ENABLED=0` → job no-ops.

### Integration (`tests/test_telegram_inventory_e2e.py`)

- Simulate full Telegram webhook JSON sequence → assert state row, inventory mutations, shopping list insert.
- Two chat_ids walking simultaneously → no state bleed.

### Migration test (`tests/test_migration_031.py`)

- Apply on clean DB → table + indexes exist with expected columns.
- Apply on populated DB → no data loss, idempotent.
- Downgrade drops only the new table.

### Smoke-test checklist

- [ ] Send `/inventory` from authorized chat → category screen appears.
- [ ] Tap a category → first item shown with correct staleness.
- [ ] Tap each level button → web UI green-fill % matches button choice.
- [ ] Mark Empty → tap Yes → item appears in shopping list page.
- [ ] Mark No-longer-have → item disappears from web inventory.
- [ ] Tap Done mid-walk → summary shows correct counts.
- [ ] `/inventory` again within 1h → Resume offered.
- [ ] Run nudge job manually (dry-run then real) → message arrives once.
- [ ] Tap Mute 7d → next nudge run skips chat.
- [ ] Container restart mid-walk → next tap shows "stale button" + re-rendered prompt.
- [ ] Backup → restore round-trip preserves session table, no orphan FKs.

## 12. Risks & open questions

| Risk | Mitigation |
|------|------------|
| Long stale-item lists (50+) fatigue users | 10-per-page cap + Done button + sort by staleness desc |
| User loses progress on deploy | DB-backed session table (chose option A in brainstorm) |
| Stale callback after webhook redelivery | Verb-vs-`pending_prompt` check; idempotent rejection w/ re-render |
| Nudge spam | 5-day floor, two-ignored backoff, mute controls |
| Category list explodes from free-text variants | v1 accepts as-is; future work: normalize categories before category-screen render |
| Inventory row removed mid-walk by another user | Silent skip + log |
| Telegram API outage during walk | Each callback returns 200 to Telegram so it doesn't retry; user simply re-taps |

**Open questions deferred to impl (safe to defer — none blocks v1):**
- Public shopping list URL: if `PUBLIC_BASE_URL` is set, the end-summary "View shopping list" button is a link; otherwise the summary message says `Open Extended → Shopping` as plain text. Real share-link integration revisited in v2.
- Multi-household scoping: codebase is single-household self-hosted. If a second household is added later, session table needs `household_id`. v1 ships without it.

## 13. Non-goals (explicit)

- No new Inventory schema fields. Walk uses existing `consumed_pct_override`, `manual_low`, `is_active_window`, `last_updated`.
- No new ShoppingList schema. Walk reuses `ShoppingSession` + `ShoppingListItem`.
- No web UI changes for v1 (the web slider stays as the primary path).
- No batch operations ("set everything in Pantry to Full") — single-item walk only.
