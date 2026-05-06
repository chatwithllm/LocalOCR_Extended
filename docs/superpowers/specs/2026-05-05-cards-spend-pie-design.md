# Cards Overview — Spend-by-Category Pie + Filter (Phase 1.5)

**Date:** 2026-05-05
**Status:** Approved (brainstorming)
**Phase:** Follow-on to `2026-05-05-cards-overview-design.md` (Phase 1)

## Goal

Show how this month's credit-card spend breaks down by Plaid category, with a filter to switch between "All Cards" and a single card. The donut + legend re-render on filter change so the user can see per-card category mix without leaving the page.

## Scope

**In:**
- Per-credit-account `categories_mtd` array on the existing `GET /plaid/cards-overview` response
- New "Spend by Category (this month)" panel inside the existing Card Usage card on the Accounts page
- Filter dropdown: "All Cards" + one option per linked credit account
- Inline-SVG donut + legend table (project pattern — no external chart lib)

**Out (deferred):**
- Loan-account categories (loans don't carry meaningful Plaid categories)
- Drill-down on slice click (Phase 2 — would filter the staged-transactions list)
- Statement-period or rolling-30-day windows (matches existing MTD window per Phase 1 spec)

---

## §1. Architecture

```
GET /plaid/cards-overview response gains per-account `categories_mtd`
                            ↓
       Frontend caches the full response in __cardsOverviewCache
                            ↓
   On filter change: aggregate categories across selected scope (client-side)
                            ↓
           Re-render SVG donut + legend table inside the panel
```

Single round-trip — no new endpoint, no new fetch on filter change. Filter is pure client-side aggregation against the in-memory cache populated by `loadCardsOverview()`.

---

## §2. Data Model — no schema change

The existing `plaid_staged_transactions` table already has `plaid_category_primary` (nullable string). No migration. Loans contribute zero rows because they have no staged transactions.

---

## §3. API

### `GET /plaid/cards-overview` — extended response

Each credit-card account row gains a `categories_mtd` array:

```json
{
  "id": 12,
  "...": "...existing fields unchanged...",
  "categories_mtd": [
    {"category": "FOOD_AND_DRINK", "amount_cents": 12300},
    {"category": "TRANSPORTATION", "amount_cents": 8400},
    {"category": "GENERAL_MERCHANDISE", "amount_cents": 5600}
  ]
}
```

Loan-account rows always emit `categories_mtd: []`.

### Compute rules

```sql
SELECT plaid_account_id, plaid_category_primary, SUM(amount) AS amt
FROM plaid_staged_transactions
WHERE transaction_date >= :month_start
  AND status != 'dismissed'
  AND amount > 0                          -- debits only; refunds excluded from pie
  AND plaid_item_id IN (:visible_ids)     -- existing visibility filter
GROUP BY plaid_account_id, plaid_category_primary
```

- Sorted by `amount_cents` desc on output
- Null `plaid_category_primary` → bucket as `"UNCATEGORIZED"` (server-side, before serialization)
- Cents conversion: `int(round(float(amt) * 100))` — matches existing `spend_mtd_cents` pattern

### Why amount > 0 here when existing `spend_mtd_cents` is net?

`spend_mtd_cents` keeps refunds in the sum so it matches statement convention ("net new charges this period"). The pie answers a different question — *where did money go this month* — which becomes meaningless if a refund cancels out a category. Keeping the two definitions distinct is intentional. The frontend will surface this as "Gross spend $X (excl. refunds)" under the donut.

---

## §4. Frontend

### Panel placement

A new "Spend by Category" sub-panel **inside** the existing `#card-usage-card`, between the summary stats grid and the per-card group list. Hidden entirely if the user has zero credit accounts.

### Layout

```
┌─ Spend by Category (this month) ─────────────────────┐
│  Filter: [ All Cards ▾ ]                              │
│                                                        │
│        ╭─────────╮     Food & Drink   $123.00  35%   │
│       │  donut   │     Transportation  $84.00   24%   │
│        ╰─────────╯     Shopping        $56.00   16%   │
│                        Bills           $42.00   12%   │
│                        Other          $45.00   13%    │
│                        ────────────────────────       │
│                        Gross spend    $350.00         │
└────────────────────────────────────────────────────────┘
```

### Behavior

- Filter `<select>` built on every `loadCardsOverview()` from `__cardsOverviewCache.groups[*].accounts` (credit-card group only)
  - Options: `"All Cards"` (`value="all"`) + one option per credit account (`value=account.plaid_account_id`, label `"💳 " + name + " ····" + mask`)
  - Default selection: `"All Cards"`
  - If the previously selected `plaid_account_id` is no longer in the cache (card removed), fall back to `"All Cards"`
- On filter change: aggregate categories from the relevant subset, re-render donut + legend
- "All Cards" aggregation: sum `amount_cents` across all credit accounts grouped by category name
- Top 6 categories rendered as slices; everything else collapsed into a single grey `Other` slice with combined amount
- Empty selection (zero gross spend on selection): donut hidden; legend area shows `"No spend this month on <selection>."`
- Donut total displayed under legend as `"Gross spend $X.XX"` — explicitly *gross* to disambiguate from `spend_mtd_cents` which is net.

### SVG donut

Plain inline SVG matching the existing pattern in `renderSpendingTrendsChart` and `_renderReceiptsActivityChart`. Computed slice arcs via standard `polar→cartesian` math. Inner radius ≈ 60% of outer for a donut look. ~120 lines total including legend table builder.

Color palette (six fixed accent colors + grey for `Other`):

```
['#2e7d6b', '#0a84ff', '#ff9f0a', '#bf5af2', '#ff453a', '#34c759', '#8e8e93']
```

The grey is reserved exclusively for `Other`. The other six are assigned in legend order.

### Functions

```javascript
function _aggregateCategories(scope, cache) { ... }   // returns {category, amount_cents}[] sorted desc
function _renderCategoryDonut(slices, totalCents) { ... } // SVG path math
function _renderCategoryLegend(slices, totalCents) { ... }
function _onCardUsageFilterChange(e) { ... }
function _categoryLabel(raw) { ... }    // "FOOD_AND_DRINK" → "Food & Drink"
```

### Safety

All category names go through `escHtml` / `textContent` (project's existing escapers) before reaching the DOM. No `innerHTML` interpolation of API data.

---

## §5. Errors + Edge Cases

| Case | Behavior |
|------|----------|
| No credit accounts at all | Whole "Spend by Category" panel hidden |
| Filter = `"All Cards"`, zero gross MTD spend | Donut hidden; legend area shows `"No spend this month."` |
| Filter = single card, zero MTD spend on that card | Same empty message scoped to card name |
| Single category | One full-circle slice; legend shows 1 row at 100% |
| `plaid_category_primary` null | Bucket as `UNCATEGORIZED`; label rendered as `"Uncategorized"` |
| ≤6 categories | Show all; no `Other` row |
| 7+ categories | Top 6 by amount; remainder collapsed into `Other` (always grey) |
| Card removed between renders | Filter rebuilds from latest cache; orphaned selection falls back to `All Cards` |
| Cache stale | Pie reads from cache like the rest of the panel — no extra staleness layer |
| Non-USD account | Excluded from pie aggregation (matches existing `totals` USD-only rule) |

---

## §6. Testing

### Backend (pytest, append to `tests/test_cards_overview.py`)

- `test_cards_overview_categories_basic` — credit card with $50 FOOD_AND_DRINK, $30 TRANSPORTATION, $-10 refund. Expect `categories_mtd == [{FOOD…, 5000}, {TRANSPORTATION…, 3000}]`, sorted desc, refund excluded.
- `test_cards_overview_categories_null_bucket` — txn with `plaid_category_primary=None` appears as `UNCATEGORIZED`.
- `test_cards_overview_categories_dismissed_excluded` — `status='dismissed'` rows do not contribute.
- `test_cards_overview_loans_have_empty_categories` — loan account → `categories_mtd: []`.
- `test_cards_overview_categories_visibility` — user A's categories not visible to user B.

### Frontend (manual smoke)

- "Spend by Category" appears below summary, above per-card list
- Filter dropdown: "All Cards" + each linked credit card
- Selecting a single card re-renders donut + legend
- Top 6 cap: 7+ categories → "Other" slice appears, always grey
- Empty case shows scoped empty message, hides donut, leaves filter functional
- Category names with HTML chars render literally (XSS-safe)
- Gross spend total in legend matches sum of slices

---

## Open questions / explicit non-decisions

- **Slice click drill-down** is deferred. Phase 1.5 is read-only visualization.
- **Statement-cycle period** is still tied to the parent spec's Phase 2 (Plaid Liabilities API). When that lands, the donut's window will track the same toggle as the summary.
- **Color customization / theming** (light/dark mode adjustments to the palette) deferred — initial palette has acceptable contrast on both existing themes.

## Phase 2 preview (not in this spec)

- Slice click → filters the staged-transactions section by category
- Date-range picker (statement vs MTD)
- Subcategory drill-down (`plaid_category_detailed`)
