# Kitchen View — design

**Date:** 2026-04-30
**Status:** Draft, awaiting user review.

## Problem

Shopping list page is a dense table designed for desktop browsing. The user
keeps a tablet in the kitchen, mounted ~3 ft from where they stand. From that
distance the current rows are too small to scan, and the per-row controls
(Update / Rename / Photo / Low / No Stock / Delete + qty input + size label
fields) are too small to tap reliably with wet or floured hands.

The user wants a kitchen-first surface that:

1. **Shows what's planned to buy** as a glance-ably big image grid.
2. **Lets the user act on each item** (qty +/-, mark bought, mark low, skip,
   delete) via tap on the image — no precision pointing.
3. **Lets the user add new items by category** (tap "Produce" → grid of
   produce images sorted by purchase frequency → tap to add). Typing is a
   last resort behind a 🔍 icon.
4. **Lets the user stamp a quick comment** when bought / low / skipped, from
   a small set of presets ("paid more", "out of stock", etc.) without
   having to type.

Existing shopping-list page stays as the desktop authoring surface; kitchen
view is an additive read-and-act layer over the same data.

## Solution overview

Add a new top-level route `/kitchen` (sidebar entry "👨‍🍳 Kitchen"). The page
has two stacked sections:

- **Top: Catalog grid (add)** — ⭐ Frequent + category chips
  (Produce / Meat / Dairy / Bakery / Pantry / Other). Tap chip → 4–6 col
  image-tile grid below, sorted by purchase frequency in last 90 days.
  Tap tile = adds product to active shopping session (qty 1). Already-on-list
  tiles dim and show "✓ on list".
- **Bottom: Current list (manage)** — image tiles for each open
  ShoppingListItem in the active session. Tap tile → bottom sheet with
  qty ± / Bought / Low / Skip / Delete + preset comment chips.

Image source per tile: latest `ProductSnapshot.image_url` for the product if
present, otherwise category emoji (🥬 🥩 🥛 🍞 🥫 🧴) on a gradient background.

All mutations route through existing shopping-list and inventory-low
endpoints. The single new backend endpoint is a read aggregator that
returns the catalog grid in one fetch.

## Architecture

### Data model

One new value on existing `ShoppingListItem.status` enum: `"skipped"`. The
column is `String(20)` already, so no schema change is needed — only a
documentation update + endpoint validation extension. No Alembic migration
because the column shape is unchanged.

`Product.category` is already populated by the enrichment pipeline. No new
column is added for category.

### Catalog aggregator

`src/backend/manage_kitchen.py` (new module, pure functions only):

```python
FREQUENCY_WINDOW_DAYS = 90
FREQUENT_LIMIT = 12
CATEGORY_LIMIT = 50  # max products per category chip

DEFAULT_CATEGORIES = ["Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other"]

CATEGORY_EMOJI = {
    "Produce": "🥬", "Meat": "🥩", "Dairy": "🥛",
    "Bakery": "🍞", "Pantry": "🥫", "Other": "🧴",
    # additional Product.category values map to "Other" emoji
}

def category_for_product(product) -> str:
    """Map raw Product.category to one of DEFAULT_CATEGORIES."""

def get_kitchen_catalog(session, *, now=None) -> dict:
    """Return {
      'frequent': [<ProductTile>, ...],   # top FREQUENT_LIMIT by recent count
      'categories': {
        'Produce': [<ProductTile>, ...],  # sorted by recent count desc
        'Meat': [...],
        ...
      },
      'on_list_product_ids': [<int>, ...]  # products already in active session
    }"""
```

`ProductTile` shape:
```python
{
    "product_id": int,
    "name": str,                 # display name
    "category": str,             # one of DEFAULT_CATEGORIES
    "image_url": str | None,     # latest ProductSnapshot, else None
    "fallback_emoji": str,       # category emoji
    "purchase_count": int,       # purchases within window
}
```

The aggregator runs one query per shape:

- A subquery selects `MAX(ProductSnapshot.id) AS latest_snapshot_id`
  grouped by `ProductSnapshot.product_id` (any snapshot whose
  `product_id` matches, regardless of which shopping_list_item it was
  attached to).
- A second subquery selects `COUNT(Purchase.id) AS purchase_count`
  grouped by `Purchase.product_id` filtered by
  `Purchase.date >= now - 90d` joined through `ReceiptItem`.
- Outer query joins `Product LEFT JOIN snapshot_subq LEFT JOIN
  count_subq`, returns rows. Python categorizes via
  `category_for_product` and emits `image_url` as
  `f"/product-snapshots/{latest_snapshot_id}/image"` when present, else
  `None`.
- `on_list_product_ids` is a plain `SELECT product_id FROM
  shopping_list_items WHERE shopping_session_id = active_session_id
  AND product_id IS NOT NULL`.

SQLite is fine at this scale (~hundreds of products per user).

### Read endpoint

`src/backend/manage_kitchen_endpoint.py`:

- `GET /api/kitchen/catalog` — returns the aggregator dict. `@require_auth`.
- (No write endpoints — all mutations reuse existing shopping-list /
  inventory routes.)

### Status validation extension

`src/backend/manage_shopping_list.py:744` currently accepts any string for
`status`. Tighten to a known-set check that includes `"skipped"`:

```python
_VALID_ITEM_STATUSES = {"open", "purchased", "skipped"}
if "status" in data:
    next_status = str(data["status"]).strip().lower()
    if next_status and next_status not in _VALID_ITEM_STATUSES:
        return jsonify({"error": "invalid status"}), 400
    item.status = next_status or item.status
```

`finalize_session()` already filters to only `purchased` for billing.
Behaviour for `"skipped"` items:

- **Excluded from "open count" / Estimated remaining total** in the
  shopping-list page header (i.e., counted as resolved like `purchased`).
- **Excluded from ready-to-bill totals** (no actual_price needed).
- **Excluded from `finalize_session()` billing rows** (only purchased
  produces a Purchase row, unchanged).
- **Visible in the kitchen-view current-list grid as a dimmed tile with
  a "skipped" badge** so the user can un-skip via reopening the sheet
  and tapping `Open` (which we add as a sheet action only when current
  status is `skipped`).
- **Visible in the existing shopping-list page** under a new "Skipped"
  collapsible group, ordered after Purchased.

### Predefined comment presets

Pure-frontend constant table (no DB), keyed by action:

```js
const KITCHEN_COMMENT_PRESETS = {
  bought:  ["Paid more", "Paid less", "Different brand", "Different size"],
  low:     ["Almost out", "Restock soon"],
  skipped: ["Too expensive", "Out of stock", "Changed mind", "Got from elsewhere"],
};
```

When the user taps a preset, it's stamped into `note` and submitted with
the status update PUT call. Tapping a preset twice toggles it off (sets
note to null). A "✏️ custom" chip opens a text input for free-form note.

### Frontend layout

New `<section id="kitchen-view" class="page-section">` in
`src/frontend/index.html`. Contains:

```
┌─────────────────────────────────────────────────────────────┐
│  👨‍🍳 Kitchen                          [⚙ open shopping list] │
├─────────────────────────────────────────────────────────────┤
│ [⭐ Frequent] [🥬 Produce] [🥩 Meat] [🥛 Dairy] …  [🔍]      │
├─────────────────────────────────────────────────────────────┤
│ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐                              │
│ │🍅│ │🥬│ │🥕│ │🍌│ │🥒│ │🌶│                              │
│ └──┘ └──┘ └──┘ └──┘ └──┘ └──┘                              │
│  Tomatoes     12×    (already-on-list dimmed)              │
├─────────────────────────────────────────────────────────────┤
│ Current List (3)                              $46.90        │
│                                                             │
│ ┌──────┐ ┌──────┐ ┌──────┐                                 │
│ │ 🥛 2 │ │ 🍅 1 │ │ 🥚 2 │                                 │
│ │ Milk │ │Tomato│ │ Eggs │                                 │
│ └──────┘ └──────┘ └──────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

Tap a current-list tile → bottom sheet covers lower half:

```
┌─────────────────────────────────────────────────────────────┐
│ (grid dimmed)                                               │
├─────────────────────────────────────────────────────────────┤
│ 🍅 Cocktail Tomatoes                                  ✕    │
│ $11.98 · Costco · Produce                                   │
│                                                             │
│  [−] 1 [+]   [✓ Bought]  [📝 Low]  [⏭ Skip]  [🗑 Delete]  │
│                                                             │
│  Notes: [ Paid more ] [ Paid less ] [ Different brand ]    │
│         [ Different size ] [ ✏️ custom ]                    │
└─────────────────────────────────────────────────────────────┘
```

Tap an action button → optimistic UI update + endpoint PUT/POST/DELETE.
On error: toast + rollback state.

**Action commit semantics — one-step with optional follow-up note:**

Tapping `✓ Bought` / `📝 Low` / `⏭ Skip` immediately commits the status
change with `note=null`. The action button remains highlighted in the
sheet for ~3 seconds with the action's preset chip row revealed
underneath (e.g., after Bought, the chips "Paid more / Paid less /
Different brand / Different size / ✏️ custom" appear). Tapping a preset
fires a second `PUT` setting only `note`. The chip row auto-hides on
sheet close or after the 3 s window.

Rationale: keeps the common path single-tap (tap Bought → done) while
making the comment a non-blocking optional refinement. No "Confirm"
button needed.

`🗑 Delete` shows an inline `Are you sure? [Yes]` confirmation that
replaces the button row for one tap, then commits.

### Files

**Backend:**
- New: `src/backend/manage_kitchen.py` — pure aggregator
  (`get_kitchen_catalog`, `category_for_product`, constants).
- New: `src/backend/manage_kitchen_endpoint.py` — Flask blueprint
  (`/api/kitchen/catalog`).
- Modify: `src/backend/manage_shopping_list.py` — `_VALID_ITEM_STATUSES`
  set + 400 on bogus status; verify `skipped` exclusion in
  `_build_shopping_list_payload` open-count + `mark_session_ready_to_bill`.
- Modify: `src/backend/create_flask_application.py` — register
  `kitchen_bp` after `stores_bp`.

**Frontend:**
- Modify: `src/frontend/index.html`:
  - Add sidebar nav entry "👨‍🍳 Kitchen" → `showSection("kitchen-view")`.
  - Add `<section id="kitchen-view">` markup with chip bar + grids.
  - Add JS: `loadKitchen()`, `renderKitchenCatalog()`, `renderKitchenList()`,
    `openKitchenSheet(itemId)`, `closeKitchenSheet()`,
    `addProductToList(productId)`, `kitchenSetActiveCategory(name)`,
    `kitchenStampNote(action, presetText)`.
  - Module-level: `let kitchenCatalog = {frequent:[], categories:{}};`,
    `let kitchenActiveCategory = "frequent";`,
    `let kitchenSheetState = null;`.
- New: `src/frontend/styles/page-shell/kitchen.css` — chip bar, tile grid,
  bottom sheet, action button styling. All theme-token-driven (matches the
  Manage Stores fix pattern).

**Tests:**
- New: `tests/test_manage_kitchen.py`:
  - `category_for_product` truth table (raw category → bucket).
  - `get_kitchen_catalog` aggregator: empty DB returns empty buckets;
    products with snapshots return `image_url`; products without snapshots
    return `image_url=None` and emoji fallback; frequency window respects
    cutoff (purchase 91d ago not counted); already-on-list product ids
    surface in `on_list_product_ids`; sort within bucket by purchase count
    desc.
- New: `tests/test_manage_kitchen_endpoint.py`:
  - `GET /api/kitchen/catalog` unauth → 401 (existing pattern).
  - Authed → 200 + shape contract (frequent / categories /
    on_list_product_ids keys).
- Modify: `tests/test_manage_shopping_list*.py`:
  - PUT with `status: "skipped"` → 200 + persists.
  - PUT with `status: "garbage"` → 400.
  - `_build_shopping_list_payload` excludes `skipped` from open count.
  - `mark_session_ready_to_bill` with mix of open/purchased/skipped:
    skipped not flagged as a billing concern.

## Data flow

```
[Page load: /kitchen]
   ↓
[GET /api/kitchen/catalog]  ← single fetch
   ↓ {frequent, categories, on_list_product_ids}
[GET /shopping-list]        ← existing fetch
   ↓ {items: [...]}
[Render]
   - chip bar from DEFAULT_CATEGORIES
   - active grid = catalog[activeCategory or 'frequent']
   - current-list grid = items where status='open' or 'skipped'

[User tap on catalog tile]
   ↓
[POST /shopping-list/items {product_id, quantity:1}]
   ↓ optimistic add to in-memory list
[Refresh kitchen via single GET /shopping-list]

[User tap on current-list tile]
   ↓
[Open bottom sheet for itemId]

[User tap ± in sheet]
   ↓
[PUT /shopping-list/items/{id} {quantity}]
   ↓ refresh local state

[User tap "Bought" + preset chip]
   ↓
[PUT /shopping-list/items/{id} {status:"purchased", note:"Paid more"}]
   ↓ tile leaves current-list grid, returns to catalog (dim cleared)

[User tap "Low" + preset chip]
   ↓
[POST /inventory/products/{product_id}/low {manual_low:true}]
[PUT /shopping-list/items/{id} {note:"Almost out"}]  (note only)
   ↓ tile stays on list, low badge appears

[User tap "Skip" + preset chip]
   ↓
[PUT /shopping-list/items/{id} {status:"skipped", note:"Too expensive"}]
   ↓ tile dims with "skipped" badge, stays in current-list grid

[User tap "Delete"]
   ↓
[DELETE /shopping-list/items/{id}]
   ↓ tile removed
```

## Error handling

- **Catalog endpoint fails:** show toast, render empty grid with retry button.
- **Mutation fails:** toast + rollback the optimistic state.
- **Unauthenticated GET catalog:** 401 (existing pattern).
- **Bogus status in PUT:** 400 with `{"error": "invalid status"}`.
- **No active shopping session:** kitchen view shows empty current list +
  a "Start a shopping session" pill that links to `/shopping-list`.
- **Product has no category set:** falls into `"Other"` bucket.
- **Product has no ProductSnapshot:** category emoji on gradient background.

## Backup / restore safety

- **No new DB columns.** `ShoppingListItem.status` already accepts strings;
  we add `"skipped"` as a recognized value at the application layer only.
- **No volume changes.** No new files outside source tree.
- **Backwards-compatible status enum:** restore from a pre-feature backup
  has no rows with `status="skipped"`, so the status filter logic
  (`status='open'` vs `'purchased'`) continues to behave identically.
  Forward-compatible: a pre-feature build encountering a `"skipped"` row
  ignores the value (treated as not "open" and not "purchased" — invisible
  in legacy filters), which is acceptable because legacy is read-only at
  that point.
- **No Alembic migration needed.** The migration counter does not advance.

## Testing

### Unit (`tests/test_manage_kitchen.py`)

`category_for_product` truth table:

| Raw category   | Mapped to  |
|----------------|------------|
| "Produce"      | "Produce"  |
| "produce"      | "Produce"  |
| "Vegetables"   | "Produce"  |
| "Fruit"        | "Produce"  |
| "Meat"         | "Meat"     |
| "Poultry"      | "Meat"     |
| "Seafood"      | "Meat"     |
| "Dairy"        | "Dairy"    |
| "Cheese"       | "Dairy"    |
| "Bakery"       | "Bakery"   |
| "Bread"        | "Bakery"   |
| "Pantry"       | "Pantry"   |
| "Snacks"       | "Pantry"   |
| "Beverages"    | "Pantry"   |
| None           | "Other"    |
| ""             | "Other"    |
| "weird"        | "Other"    |

`get_kitchen_catalog`:

- Empty DB → all category lists empty, frequent empty.
- 5 products in Produce, varying purchase counts in last 90d → returned
  sorted desc by count.
- 1 product with 3 purchases at day 1, day 50, day 100 → count = 2 (one
  outside window).
- Product with 2 ProductSnapshots → uses latest by id.
- Product with no snapshot → `image_url=None`, emoji set to category emoji.
- Product currently on active session → product_id in `on_list_product_ids`.
- Product on a finalized old session → product_id NOT in
  `on_list_product_ids`.

### Integration (`tests/test_manage_kitchen_endpoint.py`)

- GET unauth → 401.
- GET authed → 200 + JSON has keys `frequent`, `categories`,
  `on_list_product_ids`. `categories` keys are exactly `DEFAULT_CATEGORIES`.
- (Tighter shape contracts deferred to later — initial coverage is auth +
  shape, not full data assertions.)

### Status validation (`tests/test_manage_shopping_list_status.py`)

- PUT `{status: "skipped"}` → 200, persists.
- PUT `{status: "purchased"}` → 200 (existing).
- PUT `{status: "garbage"}` → 400.
- Empty / missing status → no-op (existing).

### Smoke checklist (post-deploy)

- [ ] Sidebar shows "👨‍🍳 Kitchen" entry; clicking lands on /kitchen.
- [ ] Page loads with category chips + frequent + 6-column grid.
- [ ] Tap "Produce" → grid filters; "Meat" → swaps; chip active state correct.
- [ ] Tap a tile not on list → toast "added", tile dims with "✓ on list".
- [ ] Current-list section renders open items with image / name / qty.
- [ ] Tap a current-list tile → bottom sheet slides up with item info.
- [ ] ± buttons in sheet update qty (PUT call, persists on reload).
- [ ] Tap "Bought" + "Paid more" → item leaves list, note saved (verify in
      shopping-list page).
- [ ] Tap "Low" → item shows low badge, low flag set on product (verify in
      inventory).
- [ ] Tap "Skip" + "Out of stock" → item dims with "skipped" badge, doesn't
      appear in ready-to-bill flow.
- [ ] Tap "Delete" → confirm prompt → item removed.
- [ ] No active session → "Start a shopping session" CTA shown.
- [ ] Product without ProductSnapshot → category emoji shown.
- [ ] Backup → restore on dev → /kitchen still loads + works.

## YAGNI removed

- **Voice input** — typing is last resort but not required to be voice.
- **Offline / PWA shell** — kitchen tablet has Wi-Fi.
- **Drag-to-reorder** — frequency sort is enough.
- **Custom category creation** — DEFAULT_CATEGORIES is fixed for v1.
- **Per-product image upload from kitchen** — use existing Photo flow on
  shopping-list page.
- **Multi-user concurrent state** — single-user-at-a-time pattern stands.
- **Animation polish** — minimal CSS transitions, no library imports.

## Out of scope

- Recipe / meal-plan integration (stays in restaurant module).
- Inventory grid view (separate page).
- Bill totals integration (stays on shopping-list page).
- Receipt scanning from kitchen view.
