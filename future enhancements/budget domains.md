# Budget Domains Plan

## Status

Current implementation state:

- Phase 1 foundation is complete in code:
  - purchases now persist:
    - `default_spending_domain`
    - `default_budget_category`
  - receipt items now persist optional overrides:
    - `spending_domain`
    - `budget_category`
  - OCR/manual/edit receipt save paths now preserve these fields
  - existing purchases backfill from legacy `domain` values during schema migration
- Phase 2 review/edit UI is complete in code:
  - shared receipt editor now exposes:
    - receipt default spending domain
    - receipt default budget category
    - line-item spending-domain override
    - line-item budget-category override
  - line-item overrides support `Use receipt default`
  - the editor gently auto-fills budget categories from selected spending domains to reduce correction friction
- Phase 3 budget engine foundation is complete in code:
  - effective line-item allocations now exist in backend rollup logic
  - receipt-level remainder (tax/fees/tip/delta between line subtotal and receipt total) is allocated proportionally across effective line-item buckets
  - additive backend endpoint now exists:
    - `/budget/allocation-summary`
  - current domain-based budget endpoints remain intact for compatibility
- Phase 4 budget page redesign is complete in code:
  - `Budget` now stores optional category targets via:
    - `budget_category`
    - storage keys like `category:grocery` in the legacy `domain` column so category targets can coexist with old domain rows
  - additive backend endpoint now exists:
    - `/budget/category-summary`
  - the main Budget page now:
    - edits targets by budget category
    - preloads the selected category's saved target
    - renders active and inactive category cards from effective line-item rollups
  - legacy domain budget views can fall back to category targets where that mapping is meaningful
- Still pending:
  - event naming/reporting
  - migration quality / cleanup

## Purpose

This document is the restart point for redesigning budgets so they reflect real household spending more accurately.

The current budget model is too coarse for mixed receipts. A single Costco, Walmart, or Target receipt can contain:

- home groceries
- event supplies
- general household / personal expenses

If budgeting happens only at the whole-receipt level, totals will be wrong.

The recommended design is:

- a workflow-level `spending domain`
- a budgeting-level `budget category`
- receipt-level defaults
- line-item level overrides
- budget totals calculated from line items, not just receipt headers


## Two-Layer Model

The cleanest serious solution is to separate:

1. **Spending Domain**
- how the app should treat the receipt / workflow

2. **Budget Category**
- where the money belongs in the household budget

This prevents `General Expense` from becoming an unhelpful catch-all in budgeting while still keeping receipt workflows simple.


## Spending Domains

Recommended top-level budget domains:

1. `grocery`
- household groceries and normal home essentials

2. `restaurant`
- dining out, takeout, cafes

3. `general_expense`
- non-grocery, non-restaurant purchases
- pharmacy, retail, services, fees, personal care, etc.

4. `event`
- birthdays, parties, hosting, celebrations, household gatherings

5. `other`
- fallback bucket for unclear or temporary classification


## Budget Categories

Recommended budgeting categories:

1. `grocery`
2. `dining`
3. `housing`
4. `insurance`
5. `childcare`
6. `health`
7. `subscriptions`
8. `household`
9. `retail`
10. `events`
11. `other`

These should drive monthly budget reporting.


## Core Design Principle

Budgets should be computed from **line items**.

Each receipt should have:

- `default_spending_domain`
- `default_budget_category`

Each line item should have:

- `spending_domain_override` or equivalent item-level domain field
- `budget_category_override` or equivalent item-level category field
- optional `event_name`

Effective values for a line item:

1. use line item override if set
2. otherwise use receipt default

For spending domain:

- line item override domain
- else receipt default domain

For budget category:

- line item override category
- else receipt default category

This keeps normal receipts simple while still allowing mixed receipts to be split correctly.


## Why Receipt-Level Budgeting Is Not Enough

Example receipt:

- Milk -> Grocery
- Paper plates for birthday -> Event
- Shampoo -> General Expense

One receipt, multiple budget buckets.

If the whole receipt is assigned to only one budget:

- Grocery will be overstated
- Event budget will miss real spend
- General Expenses will be understated


## Recommended Product Behavior

### 1. Receipt Defaults

Every receipt gets:

- a default spending domain
- a default budget category

Default suggestions:

- grocery receipt
  - spending domain -> `grocery`
  - budget category -> `grocery`
- restaurant receipt
  - spending domain -> `restaurant`
  - budget category -> `dining`
- general expense receipt
  - spending domain -> `general_expense`
  - budget category -> user-selected or inferred from known merchant/item patterns
- unknown receipt
  - spending domain -> `other`
  - budget category -> `other`

This makes most receipts quick to process.


### 2. Line Item Overrides

Each line item in receipt review can optionally override:

- spending domain
- budget category

Recommended options in the line-item editor:

For spending domain:

- `Use Receipt Default`
- `Grocery`
- `Restaurant`
- `General Expenses`
- `Events`
- `Other`

For budget category:

- `Use Receipt Default`
- `Grocery`
- `Dining`
- `Housing`
- `Insurance`
- `Childcare`
- `Health`
- `Subscriptions`
- `Household`
- `Retail`
- `Events`
- `Other`

This means:

- simple receipts can be reviewed with one receipt-level choice
- mixed receipts can be split accurately without forcing every line item to be manually classified


### 3. Event Support

If a line item is assigned to `event`, optionally allow:

- `event_name`

Examples:

- `Aarav Birthday`
- `Housewarming`
- `Diwali Dinner`

This can come after the basic domain model is working.


## Budget Calculation Rules

### Item Totals

Each line item contributes its line total to exactly one effective budget category.

Spending domain remains useful for workflow and page behavior, but **budget totals should roll up by budget category**.

### Tax / Fees / Discounts

Receipt-level tax and similar totals should be allocated proportionally across domains using the share of item subtotals.

Example:

- Grocery line subtotal: $60
- Event line subtotal: $40
- Tax: $7

Allocation:

- Grocery gets 60% of tax -> $4.20
- Event gets 40% of tax -> $2.80

Result:

- Grocery total = $64.20
- Event total = $42.80

### Tip

Mostly relevant for restaurant.

Recommended rule:

- restaurant receipts: tip follows restaurant domain
- non-restaurant receipts: tip usually zero, but if present can be allocated proportionally or follow receipt default


## Data Model Proposal

### Receipt / Purchase Level

Add fields such as:

- `default_spending_domain`
- `default_budget_category`
- optional `default_event_name`

### Line Item Level

Add fields such as:

- `spending_domain`
- `budget_category`
- optional `event_name`

Notes:

- If `spending_domain` is null, use the receipt default spending domain
- If `budget_category` is null, use the receipt default budget category
- If `event_name` is null, no event labeling is applied


## UI Plan

### Budget Page

Budget page should show monthly cards / sections for budget categories such as:

- Grocery
- Dining
- Housing
- Insurance
- Childcare
- Health
- Subscriptions
- Household
- Retail
- Events
- Other

Each shows:

- budget amount
- actual spent
- remaining
- percent used

### Receipt Review

At receipt level:

- `Default Spending Domain`
- `Default Budget Category`

At line-item level:

- `Spending Domain`
- `Budget Category`
- optional `Event Name` when domain is `Events`

### Manual Entry

Manual entry must support:

- default spending domain
- default budget category
- optional event name
- line-item-level override later if entry supports multiple items


## Migration Plan

### Phase 1: Foundation

Add new fields:

- receipt default spending domain
- receipt default budget category
- line-item spending domain override
- line-item budget category override

Backfill existing data using current receipt type:

- restaurant
  - spending domain -> `restaurant`
  - budget category -> `dining`
- general expense
  - spending domain -> `general_expense`
  - budget category -> `other` initially, then improve later
- grocery
  - spending domain -> `grocery`
  - budget category -> `grocery`
- unknown
  - spending domain -> `other`
  - budget category -> `other`

### Phase 2: Review UI

Expose:

- receipt default spending domain selector
- receipt default budget category selector
- line-item spending domain override selector
- line-item budget category override selector

### Phase 3: Budget Calculation

Change budget totals to use:

- line-item totals
- proportional tax allocation
- budget category rollups

### Phase 4: Budget Page Redesign

Redesign the main Budget page to use:

- monthly budget targets by `budget category`
- category-level cards for:
  - target
  - spent
  - remaining
  - percentage used
- prefilled budget editor values when a category is selected

Compatibility rules:

- old `/budget/status?domain=...` consumers remain available
- category targets are stored alongside legacy domain rows
- restaurant / expense budget views can fall back to mapped category targets while their page-level redesign catches up

### Phase 5: Events

Add:

- `event_name`
- event-specific reporting


## Open Questions

These should be answered before implementation starts:

1. Should home essentials bought at grocery stores always stay in `grocery`, or should some map to `general_expense`?

2. Should `event` exist only as an item override, or also as a receipt default spending domain for fully event-focused receipts?

3. Should `other` be user-selectable, or only a fallback bucket used when classification is unclear?

4. Which categories should we support in V1 vs later:
- insurance
- housing
- childcare
- subscriptions
- health
- retail

5. Should tax allocation happen immediately in Phase 1, or can Phase 1 use a simpler temporary rule and improve later?


## Recommendation

Implement in this order:

1. add spending domain + budget category at receipt + line-item level
2. backfill existing data from receipt types
3. expose editing in receipt review
4. update Budget page to summarize categories
5. add event naming and event-specific reporting

This is the cleanest serious solution because it supports:

- simple receipts
- mixed receipts
- future event planning
- future multi-household expansion
- real household budgeting beyond grocery vs restaurant


## Restart Notes

When work resumes, start here:

1. confirm final spending domain names
2. confirm final budget category list for V1
3. decide exact schema fields
4. map which tables currently store editable line items
5. design proportional tax allocation implementation
6. update receipt review UI before changing budget summaries
