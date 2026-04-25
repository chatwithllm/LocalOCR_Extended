# Receipt Attribution Tagging — Design

**Date**: 2026-04-25
**Status**: approved (pending implementation)
**Owner**: receipts / chat

## Goal

Make receipt attribution easy to set so the chat assistant's
`shopping_activity.per_person` (built in the
`2026-04-25-chat-temporal-shopping-activity` plan) actually has data
to read. Today 0/169 purchases are tagged, so per-person questions
("when did Mom last shop", "how much does Chamu spend") return
"no purchases tagged" no matter what the user asks.

Two complementary fixes shipped together:

1. **Bulk-tag UI** so the existing 169-receipt backlog can be cleared
   in minutes, not one-row-at-a-time.
2. **Auto-suggest at upload** so new receipts arrive pre-tagged when
   we can confidently predict the attribution from the uploader's
   history at the same store.

## Non-goals

- Schema changes — `Purchase.attribution_user_id`,
  `attribution_user_ids`, and `attribution_kind` already exist and
  are reused as-is.
- Tool-calling chat-driven tagging ("Mom got the Costco one") — the
  cool conversational path needs tool-call infrastructure not yet
  built. Scope-creep risk; defer.
- A new dedicated "Tag review queue" page — Receipts page filter +
  multi-select covers the same workflow inside an interface the user
  already knows.
- Item-level (`ReceiptItem.attribution_user_id`) bulk tagging — the
  bulk endpoint flips items along with the purchase via the existing
  `apply_to_items` flag, but a dedicated per-item bulk UI is out of
  scope for v1.

## Decisions captured during brainstorming

| # | Question | Decision |
|---|----------|----------|
| 1 | Sub-feature scope | E — bulk-tag existing + auto-suggest new (combined plan) |
| 2 | Auto-suggest signal source | B — uploader + per-store history learning |
| 3 | Bulk-tag UX shape | D — Receipts page filter + multi-select + dashboard nudge banner |
| 4 | Auto-suggest behaviour at upload | C — confidence-based: silent auto-apply when habitual, leave untagged + surface suggestion when uncertain |
| 5 | Bills "who pays" semantics | A — reuse `Purchase.attribution_user_id` (Bills are Purchase rows; same picker) |

## Architecture

### Data model

Zero schema changes. The existing columns already cover every
requirement:

- `Purchase.attribution_user_id` — single-person tag (legacy + fast lookup)
- `Purchase.attribution_user_ids` — JSON array for shared
- `Purchase.attribution_kind` — `"personal" | "shared" | "household" | None`

Bills (`Purchase.domain == "bill"`) reuse the same columns. The
`kind=personal` semantic maps to "who is responsible for paying";
`kind=household` means a shared utility; `kind=shared` with multiple
ids means split between named members.

### Backend

**`src/backend/handle_receipt_upload.py`**:

1. **New** `POST /receipts/bulk-attribution`
   ```json
   Body: {
     "purchase_ids": [int, ...],
     "user_ids": [int, ...],
     "kind": "personal" | "shared" | "household" | null,
     "apply_to_items": bool   // default true
   }
   Response: {
     "updated": <int>,
     "skipped": [{ "purchase_id": int, "reason": str }, ...]
   }
   ```
   Reuses `_normalize_attribution_payload`. Loops through
   `purchase_ids` (capped at 200/request), applies attribution.
   Skipped rows include not-found and not-owned-by-household
   reasons (no admin can tag rows belonging to a user outside the
   household — same authorisation rule as the per-row endpoint).

2. **New** `GET /receipts/attribution-stats`
   ```json
   Response: {
     "untagged_count": <int>,
     "tagged_count": <int>,
     "untagged_sample_ids": [int, ... up to 5]
   }
   ```
   Powers the dashboard banner. The sample-ids let the frontend
   pre-load thumbnails without a second round trip.

3. **Modify** the existing receipts list endpoint:
   add `attribution=untagged|tagged|any` query parameter
   (default `"any"`). Untagged filter:
   `attribution_user_id.is_(None) AND attribution_user_ids.is_(None)
   AND attribution_kind.is_(None)`.

4. **New helper** `_suggest_attribution_for_upload(session,
   uploader_id, store_id, store_name) -> dict | None`:
   - Pull last 10 Purchase rows for the same `(uploader_id, store_id)`
     filtered to non-null attribution.
   - Group by `(attribution_user_ids, attribution_kind)` tuple.
   - If the modal group covers ≥3 of the last 5 → return
     `{"user_ids": [...], "kind": "...", "confidence": "high"}`.
   - If the modal group covers 2 of the last 5 → return same shape
     with `confidence: "medium"`.
   - Otherwise return `None`.

5. **Wire-up** in the existing receipt-create / OCR-finalize path:
   after the Purchase row is committed without an attribution, call
   `_suggest_attribution_for_upload`. If `confidence == "high"`,
   apply silently (single follow-up UPDATE). If `confidence ==
   "medium"`, attach the suggestion to the API response under
   `attribution_suggestion` so the upload-review modal can pre-select
   it without committing.

### Frontend

**`src/frontend/index.html`**:

1. **Receipts page** (`#page-receipts`):
   - New filter chip: "🏷 Untagged only" toggle. Adds
     `attribution=untagged` to the existing list query and re-renders.
   - Multi-select: when "Untagged only" is active, render a checkbox
     in the leftmost column of every row. Header checkbox toggles all
     visible rows.
   - Sticky bulk-action toolbar (renders when ≥1 row selected): "Tag
     X selected as…" → opens the existing attribution picker (already
     handles personal / shared / household / multi-select). On
     confirm, POST `/receipts/bulk-attribution`.

2. **Dashboard** (between leaderboard and KPI row):
   - New compact banner card: "💡 N receipts untagged — tag now →".
     Hidden when `untagged_count == 0`. Click navigates to
     `#page-receipts` with `?attribution=untagged` so the filter
     opens pre-active.

3. **Upload review modal** (existing post-OCR review modal):
   - If response carries `attribution_suggestion` with
     `confidence: "medium"`, pre-select it in the picker and label it
     "Suggested: Mom — confirm or change".
   - High-confidence already silently applied: render a small
     "Auto-tagged: Mom — change?" hint above the picker so the user
     sees what happened and can override.

**`src/frontend/styles/design-system.css`**:
- `.attr-bulk-toolbar` (sticky-top, pill-shaped, accent border).
- `.dash-attr-nudge` (compact banner card matching existing
  dashboard tile language).
- `.attr-suggest-pill` (small "Suggested" label inside the picker).

### Auto-suggest confidence rules (precise)

| Modal group support | Confidence | Behaviour |
|---|---|---|
| ≥3 of last 5 attributed receipts at this store by this uploader | high | Silent auto-apply |
| 2 of last 5 | medium | Leave untagged but return suggestion in API |
| <2, or fewer than 3 attributed receipts in the lookback window | none | Return `None`; banner picks it up later |

The lookback window is the last 10 attributed Purchase rows for that
`(uploader_id, store_id)` tuple — order by `Purchase.date desc`.
"Modal group" means most-frequent `(user_ids tuple, kind)` pair.

## Edge cases

- **Bills**: same Purchase row, same picker, same logic. No special
  case in the suggestion helper — it'll learn that "AT&T uploads by
  Dad → personal/Dad" or "Comcast uploads by anyone → household".
- **First-time upload at a new store**: no history → no suggestion →
  receipt stays untagged → banner picks it up.
- **Bulk overwrite of already-tagged rows**: bulk endpoint overwrites
  by default. Frontend shows a confirmation modal when the selection
  contains ≥1 already-tagged row — "3 of these are already tagged —
  overwrite?".
- **Authorization**: `bulk-attribution` calls the same
  `require_write_access` decorator the per-row endpoint uses.
- **Concurrent uploads**: silent auto-apply runs in the same
  request/transaction as the receipt save, so two parallel uploads
  can't race each other into a half-tagged state.
- **Empty `purchase_ids`**: bulk endpoint returns 400.
- **Suggestion when the historical attribution is no longer valid**
  (e.g. user was deleted): suggestion returns `None`; the surviving
  history is irrelevant once one of its user_ids is gone.

## Testing

**Unit (backend)** — new `tests/test_attribution_bulk.py`:

- `_suggest_attribution_for_upload`:
  - 4 of 5 last receipts at Costco by Mom → personal/Mom → high.
  - 2 of 5 split Mom/Dad → shared/[Mom,Dad] → medium.
  - 1 each across 5 different attributions → None.
  - Zero attributed rows in lookback → None.
  - Same store, different uploader → suggestion based on that
    uploader's history only, not the original.
- `POST /receipts/bulk-attribution`:
  - 5 ids, valid kind, valid users → returns `updated: 5`.
  - 1 invalid id mixed in → returns `updated: 4, skipped: [...]`.
  - Empty `purchase_ids` → 400.
  - Caller without write access → 403.
- `GET /receipts/attribution-stats`:
  - Mixed tagged/untagged DB → returns correct counts and ≤5 sample
    ids.

**Smoke (manual)** in dev:

1. Dashboard renders banner "💡 N untagged" with the actual count.
2. Click banner → Receipts page opens with "Untagged only" filter
   active.
3. Select 5 rows → bulk toolbar shows "Tag 5 selected as…".
4. Pick "Mom" + kind=personal + apply-to-items → all 5 update; the
   banner count drops by 5.
5. Upload a new receipt at a store with strong history → confirm
   silent auto-tag (the modal shows the "Auto-tagged: X — change?"
   hint).
6. Upload a new receipt at a store with weak history → modal
   pre-selects the medium-confidence suggestion but does not commit
   until user confirms.
7. Ask chat "who last shopped?" → bot now quotes per-person from real
   attribution data, no longer "no purchases tagged".

## Files touched

| Path | Action |
|---|---|
| `src/backend/handle_receipt_upload.py` | Add bulk-attribution + attribution-stats endpoints, `_suggest_attribution_for_upload` helper, untagged filter on list |
| `src/frontend/index.html` | Receipts page filter chip + multi-select + bulk toolbar; upload-review suggestion hint; dashboard banner |
| `src/frontend/styles/design-system.css` | Bulk toolbar, banner, suggested-pill styles |
| `tests/test_attribution_bulk.py` | New file — unit tests for bulk endpoint, attribution-stats, and auto-suggest helper |

## Out of scope

- Item-level bulk attribution UI.
- Tool-calling conversational tagging from the chat panel.
- Backfilling attribution by parsing receipt text (e.g. "PAID BY
  CARD ENDING IN 4242 → Dad's card").
- Cross-household privacy tags.
- A dedicated "Tag review queue" page (Receipts filter covers it).
