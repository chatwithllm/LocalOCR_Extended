# Kitchen Tab Revamp — "Running Low" Wall Display

**Date:** 2026-06-15
**Status:** Approved (design), pending implementation plan
**Scope:** Frontend only — the `#page-kitchen` view in `src/frontend/index.html` (markup + its JS) and `src/frontend/styles/page-shell/kitchen.css`. Reuses existing data + actions. No backend changes expected (the plan confirms the exact "mark restocked" call).

## Problem / goal

The Kitchen tab is built for a **kitchen-display tablet**, but today it leads with a "Browse products" carousel and shows the shopping list as tiles — not what a glanceable wall display should foreground. The user wants it to surface **what's running low** first, so anyone walking by sees what needs restocking and taps once to add it to the shopping list.

Decisions captured in brainstorming:
- Primary device: **wall tablet**, glanceable, touch-first, low interaction.
- Primary content: **what's running low**.
- Tap a tile = **one-tap add to the shopping list**; the tile then flips to a dimmed **"✓ On list"** and stays (no double-add).
- Each tile also offers a small **"Got it"** (mark restocked) that clears the low condition so the tile leaves the grid.

## Existing building blocks (reused, not rebuilt)

- `loadKitchen()` → `GET /api/kitchen/catalog` returns products with `is_low` (manual-low OR quantity < threshold), `on_list_product_ids`, `product_id`, name, category, and latest snapshot image.
- `quickAddToShoppingList({product_id, name, category, quantity, source})` — adds to the shopping list (POST `/shopping-list/items`).
- `setProductLowStatus(productId, manualLow)` — toggles `manual_low`.
- Inventory quantity writes (`inventory_writes.py`) — adjust/set `quantity` (used by the restock path).
- `shoppingItemEmoji(name, category)` — the item-aware emoji fallback already added for shopping thumbnails.
- The current catalog overlay (carousel + `kitchen-search` + chips + `toggleKitchenCatalog`) — kept, but demoted to a secondary "Browse" surface.

## Design

### Layout (`#page-kitchen`)
A single glanceable screen:

1. **Slim header** — `🍳 Running Low · N` on the left; weather (`#kitchen-weather`) + a live **clock** + a `🛒 N on list` chip (opens/links to the shopping list) on the right. No toolbar/chip-bar by default.
2. **Hero grid** — a responsive grid of large, image-forward **running-low tiles** filling the screen. This is the primary content.
3. **Trailing "＋ Browse" tile** (and/or a header action) — opens the existing product catalog overlay (carousel + search + store filter) for adding anything not low.
4. **Empty state** — when nothing is low: a calm **"All stocked ✅"** with the Browse affordance.

### Running-low tile
- **Source:** items from the kitchen catalog where `is_low` is true. Sort: out-of-stock (qty 0) first, then most-overdue (lowest quantity / furthest below threshold).
- **Content:** product photo (`latest_snapshot.image_url`) with **`shoppingItemEmoji` fallback**; product name; a low badge — `0 left` / `2 left` / `low`. **Out-of-stock (0) tiles get an urgent (red) treatment.**
- **Already-on-list:** if the product is in `on_list_product_ids`, the tile renders in the dimmed **"✓ On list"** state on load.
- **Whole-tile tap → add:** calls `quickAddToShoppingList({product_id, name, category, quantity: 1, source: 'kitchen_low'})`; on success the tile flips to **"✓ On list"** (dimmed, stays in place). A second tap does not re-add.
- **"Got it" (restocked):** a small secondary control on the tile → mark restocked. Clears the low condition (clear `manual_low`; if low by threshold, restore `quantity` to ≥ threshold), reusing `setProductLowStatus(pid, false)` + the inventory quantity write. On success the tile leaves the grid (refresh from `loadKitchen`). The exact restock endpoint is confirmed in the plan.

### Data flow
`loadKitchen()` already populates the catalog + `on_list_product_ids`. The revamp derives the low set client-side (`catalog products where is_low`), so **no new endpoint**. After add / restock, re-call `loadKitchen()` (and `loadShoppingList()` where relevant) to refresh tile states.

## What changes vs. stays
- **Demoted:** the always-open "Browse products" carousel + chip bar + the shopping-list-as-tiles "Current List" become secondary (Browse overlay; on-list shown via ✓ badges + the header count).
- **Kept:** weather, the catalog overlay internals (carousel/search/chips/sheet), all underlying data + actions.
- **Removed from the default view:** the prominent catalog toolbar and the separate kitchen "Current List" grid as primary elements.

## Success criteria
1. Opening the Kitchen tab shows running-low items as the primary, full-screen tile grid (out-of-stock first), with weather + clock + on-list count in a slim header.
2. Tapping a tile adds it to the shopping list and flips the tile to a persistent dimmed "✓ On list"; items already on the list show that state on load; no double-add.
3. Each tile's "Got it" marks the item restocked, clears the low condition, and removes it from the grid.
4. A Browse affordance still opens the existing catalog to add non-low products.
5. Nothing low → "All stocked ✅" empty state.
6. No backend/API changes (or, if the restock path needs one, it is minimal and identified in the plan); other tabs unaffected.

## Non-goals
Recipes, meal planning, kitchen-display device auth, redesigning the catalog overlay internals.
