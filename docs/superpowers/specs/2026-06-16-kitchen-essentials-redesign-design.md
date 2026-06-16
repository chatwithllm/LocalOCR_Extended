# Kitchen Tab — Essentials Redesign

**Date:** 2026-06-16
**Status:** Approved (design)

## Summary

Replace the current auto-derived Kitchen tab (frequent grid + browse-by-category
+ running-low wall) with a single, user-curated **Essentials grid**. An essential
is any product the user explicitly tags from the Product view or the Inventory
view. Tapping an essential opens a detail sheet showing current quantity, backup
status, and an Add-to-shopping-list action. When the user has tagged nothing yet,
the tab shows an explanatory prompt plus a "Suggested essentials" row seeded from
their most-frequent purchases.

This is a deliberate decluttering: the kitchen stops guessing what matters and
shows only what the user marked.

## Goals

- Kitchen tab = one grid of user-tagged essential products, nothing else.
- Essentials are taggable from **both** the Product view and the Inventory view.
- Each tile is glanceable (on-list, has-spare hints) and tappable for detail.
- A frictionless empty/seeding state so the tab is useful before manual curation.

## Non-goals

- No per-location or per-household essential scoping (essential is global per product).
- No automatic essential detection — tagging is always an explicit user action.
- No changes to the inventory decay / running-low model itself (that block is simply
  removed from the kitchen surface; the underlying inventory logic is untouched).

## Data model

One migration: `alembic/versions/034_product_essential_backup.py`.

Add two columns to `products`:

| Column         | Type    | Null | Default | Meaning                                  |
| -------------- | ------- | ---- | ------- | ---------------------------------------- |
| `is_essential` | Boolean | not null | False | User has marked this product essential.  |
| `has_backup`   | Boolean | not null | False | User has a spare/backup unit on hand.    |

Both are per-product (global), consistent with the product-level mental model and
with `is_regular_use`. `has_backup` is an explicit user-set bit, not derived from
quantity. Keeping `has_backup` on `Product` (rather than `Inventory`) means a
product can carry the flag even when no inventory row exists yet — required because
essentials can be tagged from the Product view before any stock is logged.

`is_regular_use` is left untouched and remains a separate concept.

## Backend

### `manage_kitchen.py`

Replace `get_kitchen_catalog` with `get_kitchen_essentials(session, *, now=None)`.

Return shape:

```python
{
  "essentials": [
    {
      "product_id": int,
      "name": str,
      "category": str,            # bucket from category_for_product
      "image_url": str | None,
      "fallback_emoji": str,
      "quantity": float,          # summed Inventory.quantity across locations; 0.0 if none
      "has_backup": bool,
      "on_list": bool,            # on an active / ready_to_bill shopping session
      "latest_unit_price": float | None,
    },
    ...
  ],
  "suggested": [ <ProductTile>, ... ]   # only when essentials is empty; else []
}
```

Rules:

- `essentials`: products where `is_essential IS TRUE AND is_non_product IS NOT TRUE`.
  Sorted by `name` (stable, alphabetical) — this is a curated list, **not** frequency
  ranked.
- `quantity`: sum of `Inventory.quantity` over all of the product's inventory rows
  (0.0 if none).
- `on_list`: product id appears in an open/skipped `ShoppingListItem` on an
  `active` or `ready_to_bill` `ShoppingSession` (reuse existing on-list logic).
- `suggested`: returned **only** when `essentials` is empty. Reuses the existing
  frequency query (purchase_count within `FREQUENCY_WINDOW_DAYS`), excludes products
  already `is_essential`, capped at 8, shaped like the old `ProductTile`. Once the
  user has at least one essential, `suggested` is `[]`.
- Keep `category_for_product`, `CATEGORY_EMOJI`, `DEFAULT_CATEGORIES` (used for
  tile emoji/grouping and suggestion tiles).

`get_kitchen_catalog` and its catalog-only return shape are removed. The only
consumer is the kitchen endpoint; tests are updated accordingly.

### Endpoints (`manage_inventory.py`)

Modeled exactly on the existing `PUT /inventory/products/<id>/regular-use` handler:

- `PUT /inventory/products/<int:product_id>/essential` — body `{ "is_essential": bool }`
- `PUT /inventory/products/<int:product_id>/backup` — body `{ "has_backup": bool }`

Both 404 on unknown product, return the updated flag, and are the single write path
used by every tagging surface (inventory row, product detail, kitchen tile, and the
suggestion row).

`manage_kitchen_endpoint.py`: `GET /kitchen` now calls `get_kitchen_essentials`.

Add to shopping list reuses the existing `POST /shopping-list/items`.

## Frontend (`src/frontend/index.html` + `styles/page-shell/kitchen.css`)

### Removed

- Frequent grid markup, JS, and CSS.
- Browse-by-category markup, JS, and CSS.
- Running-low wall markup, JS, and CSS.

(Removed from the **kitchen surface only**; inventory's own running-low/threshold
features stay where they live in the inventory view.)

### Essentials grid

- Renders `essentials` as product tiles: image (or `fallback_emoji`), name.
- Tile face state hints:
  - on-list badge when `on_list`.
  - "spare" dot when `has_backup`.
- Tile sort follows backend order (alphabetical by name).

### Tile detail sheet (on tap)

- **Current quantity**: shows `quantity`, or "Not tracked" when `quantity == 0` /
  no inventory row.
- **Backup**: shows has-spare state with a toggle → `PUT …/backup`.
- **Add to shopping list**: `POST /shopping-list/items` against the current active
  session; button reflects `on_list` (added / already on list).
- **Remove from essentials**: untag → `PUT …/essential {is_essential:false}`; tile
  leaves the grid.

### Empty state (no essentials)

- Prompt: explains essentials are tagged from Products or Inventory.
- "Suggested essentials" row from `suggested`: each suggestion tile has a one-tap
  "Mark essential" → `PUT …/essential {is_essential:true}`; on success it moves into
  the grid and (once the first is added) the empty state / suggestions disappear.

### Tagging entry points

- **Inventory view**: an essential toggle (star) on each inventory row, beside the
  existing low / regular-use controls. Calls `PUT …/essential`.
- **Product view**: an "Essential" toggle in the product detail/edit panel. Calls
  `PUT …/essential`.

## Testing

- `tests/test_manage_kitchen.py`: rewrite catalog-shape assertions to
  `get_kitchen_essentials`. Cover: only `is_essential` products returned;
  `is_non_product` excluded; alphabetical sort; `quantity` summed across multiple
  inventory rows; `on_list` reflects active session; `suggested` populated only when
  essentials empty and excludes already-essential products.
- New tests for the two PUT endpoints (toggle on/off, 404 on unknown product).
- Keep existing `category_for_product` tests.

## Migration / rollout

- Single forward migration; both columns default False, so existing products start
  non-essential and the tab opens in the empty/suggestions state — the intended
  first-run experience. No backfill.

## Open questions

None outstanding. Backup placement (Product vs Inventory), tag source (new column
vs reuse), and block scope (essentials-only) were all resolved during brainstorming.
