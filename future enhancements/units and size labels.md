# Units And Size Labels

## Goal

Make quantities and prices meaningful for real shopping and receipt review.

Today the app treats many items as simple numeric quantities, which is not enough for:

- milk by bottle or gallon
- eggs by dozen or count
- meat by pound
- produce by pound, bag, bunch, or each
- household products by pack, box, roll, or ounce

This plan introduces explicit units and shopper-friendly size labels so item meaning stays clear across:

- receipts
- shopping list
- product catalog
- pricing

## Status

Current implementation state:

- Phase 1 foundation is complete in code:
  - schema support exists for:
    - `products.default_unit`
    - `products.default_size_label`
    - `receipt_items.unit`
    - `receipt_items.size_label`
    - `shopping_list_items.unit`
    - `shopping_list_items.size_label`
  - runtime SQLite migration backfills legacy receipt/shopping rows to `unit = each`
  - receipt/shopping/manual-entry payload plumbing now preserves the new fields
- Phase 2 editor wiring is complete in code:
  - shared receipt editor now exposes:
    - `Unit`
    - `Size Label`
  - manual entry now uses the same fields
  - mobile receipt editor layout was adjusted so:
    - `Qty` and `Line Total` are balanced
    - `Item Group` and `Budget Category` stay side by side
- Phase 3 display rollout is now substantially complete:
  - Products/Catalog now exposes inline default editing for:
    - `Unit`
    - `Size Label`
  - Shopping rows now expose inline editing for:
    - preferred store
    - `Unit`
    - `Size Label`
    - unit price
  - shopper-facing summaries in Products and Shopping now use unit/size context when available
- Still pending:
  - stronger price-basis logic beyond current shopper/unit totals
  - optional future analytics around price-per-pound / price-per-ounce

## Problem Summary

Current quantity handling is too generic.

Examples of ambiguity:

- `Milk x1` does not tell us whether that means a gallon, half gallon, or bottle
- `Eggs x1` does not tell us whether that is 12 count, 18 count, or 5 dozen
- `Chicken Breast x2` may actually mean 2.4 lb instead of 2 pieces
- shopping estimates become harder to trust when the item shape is unclear

## Recommended Model

Use 3 layers:

1. `quantity`
- numeric amount
- examples:
  - `1`
  - `2`
  - `2.4`

2. `unit`
- normalized unit used for logic
- examples:
  - `each`
  - `bottle`
  - `gal`
  - `dozen`
  - `count`
  - `lb`
  - `oz`
  - `bag`
  - `box`
  - `pack`
  - `roll`
  - `bunch`

3. `size_label`
- shopper-facing size text when needed
- examples:
  - `18 count`
  - `12 count`
  - `1 gal`
  - `64 oz`
  - `5 dozen`

This gives us both:

- normalized logic
- readable display

## Example Outcomes

### Milk

- quantity: `1`
- unit: `gal`
- size_label: `1 gal`

Display:

- `Milk x1 gal`

### Eggs

- quantity: `1`
- unit: `count`
- size_label: `18 count`

Display:

- `Eggs x1 (18 count)`

Or:

- quantity: `1`
- unit: `dozen`
- size_label: `5 dozen`

Display:

- `Eggs x1 (5 dozen)`

### Chicken Breast

- quantity: `2.4`
- unit: `lb`
- size_label: `2.4 lb`

Display:

- `Chicken Breast 2.4 lb`

### Water

- quantity: `1`
- unit: `pack`
- size_label: `40 pack`

Display:

- `Water x1 (40 pack)`

## Data Model Proposal

### Product

Add:

- `default_unit`
- `default_size_label`

Use:

- to inform shopping display
- to help manual entry defaults

### Receipt Item

Add:

- `unit`
- `size_label`

Use:

- receipt review
- budgeting and shopping corrections
- future price intelligence

### Shopping Item

Add:

- `unit`
- `size_label`

Use:

- current trip clarity
- better item display while shopping

## Pricing Guidance

We should keep line totals and shopper-visible totals simple, but still leave room for future unit pricing.

Recommended V1:

- keep `line_total`
- keep normalized per-item price logic already used today
- do not force price-per-ounce or price-per-pound yet

Possible later addition:

- `price_basis_unit`
- `price_basis_quantity`

Examples:

- `$3.99 / lb`
- `$0.22 / count`
- `$5.49 / gal`

That should be a later phase, not part of the first unit rollout.

## UI Proposal

### Receipt Editor

For each line item:

- Name
- Qty
- Unit
- Size Label
- Line Total
- Item Group
- Budget Category

Best UX:

- default unit to `each`
- let user override when needed
- keep size label optional

### Shopping List

Collapsed row display should use the best readable version:

- `Avocado Oil x2`
- `Milk x1 gal`

Current practical implementation:

- shopping rows now keep the richer unit/size context in expanded controls
- shopping/product defaults can be corrected inline instead of only at receipt-edit time
- manual price edits in shopping can now coexist with unit/size corrections, which makes live trip correction more useful
- `Eggs x1 (18 count)`
- `Chicken Breast 2.4 lb`

Expanded row should show:

- unit
- size label
- price
- preferred store

### Products / Catalog

Product variants should be clearer when units differ.

Examples:

- `Eggs (18 count)`
- `Eggs (5 dozen)`
- `Milk (1 gal)`

This helps prevent confusion and duplicate products that are really different pack sizes.

## Migration Plan

### Phase 1: Schema

Add:

- `unit`
- `size_label`

to receipt items and shopping items

Add:

- `default_unit`
- `default_size_label`

to products

### Phase 2: Backfill

Backfill old rows with:

- `unit = each`
- `size_label = null`

### Phase 3: Editor Support

Add `Unit` and `Size Label` to:

- receipt review / edit
- manual entry

### Phase 4: Display Rollout

Use the new fields in:

- shopping list rows
- product/catalog labels
- future receipt summaries where helpful

That keeps existing behavior stable.

### Phase 3: Receipt Review Support

Let users correct unit and size on receipt lines.

Examples:

- ORGAVOOIL -> `1 bottle`
- eggs -> `18 count`
- chicken -> `2.4 lb`

### Phase 4: Shopping Display

Use unit and size in shopping labels and expanded details.

### Phase 5: Product Intelligence

Use saved units and size labels to improve:

- duplicate prevention
- product matching
- future estimates

## Important Product Rules

1. Default old data to `each`
- safe fallback

2. Do not try to infer everything forever
- OCR names are too messy
- users need explicit control

3. Keep size label optional
- not every item needs it

4. Keep display shopper-friendly
- normalized logic should not make the UI harder to read

## Open Questions

1. Should `unit` and `size_label` live at product level, line-item level, or both?

Recommendation:

- both
- product provides default
- receipt/shopping line can override

2. Should eggs be modeled as `dozen` or `count`?

Recommendation:

- use whichever is most shopper-friendly on that product
- keep `size_label` flexible enough to show exact packaging

3. Should price-per-unit be part of V1?

Recommendation:

- no
- keep first rollout focused on clarity, not advanced price math

## Restart Notes

If this work resumes later, start with:

1. add `unit` and `size_label` fields to schema
2. backfill legacy rows to `each`
3. add receipt editor controls
4. update shopping display formatting
5. then evaluate product matching improvements

This should be treated as a separate enhancement stream from budget classification, but it complements:

- shopping usability
- receipt editing clarity
- product normalization

## Implementation Status

Current branch progress:

- Phase 1 has started
- schema/runtime migration work is in progress:
  - `products.default_unit`
  - `products.default_size_label`
  - `receipt_items.unit`
  - `receipt_items.size_label`
  - `shopping_list_items.unit`
  - `shopping_list_items.size_label`
- legacy shopping and receipt rows backfill to `unit = each`
- receipt and shopping payload serialization now carries these fields

Still pending in the active implementation stream:

- receipt editor controls for unit and size label
- shopping display formatting that uses unit and size label
- product catalog/default editing for unit and size label
