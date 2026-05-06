# Loan Progress Pie — Design

**Date:** 2026-05-05
**Status:** Approved (brainstorming)
**Phase:** Follow-on to cards-overview Phase 1.5 (spend pie)

## Goal

Per-loan mini donut showing % paid off vs. unpaid against a user-entered original loan amount. One donut per loan, inline-edit ✏️ to set/update the original amount.

## Scope

**In:**
- New nullable column `original_loan_amount_cents` on `plaid_accounts` (loans only populate it)
- New endpoint `PUT /plaid/accounts/<id>/loan-meta` to set/clear the original amount
- `GET /plaid/cards-overview` extends loan rows with `original_loan_amount_cents` + `paid_off_cents`
- Frontend `Loan Progress` sub-panel inside the existing `#card-usage-card`
- Per-loan mini donut + balance/total + ✏️ inline-edit

**Out (deferred):**
- Plaid Liabilities API integration (Phase 2 of original cards-overview spec — would auto-populate `original_loan_amount`)
- Per-loan APR / next-payment-due (Liabilities)
- Historical paid-off-over-time chart

---

## §1. Architecture

```
Migration 026 → original_loan_amount_cents column
                       ↓
PUT /plaid/accounts/<id>/loan-meta  ← user-entered value
                       ↓
GET /plaid/cards-overview emits original + paid_off per loan row
                       ↓
Frontend renders per-loan mini donuts + inline edit
```

Single new column, single new endpoint, single new sub-panel. Reuses existing visibility filter (`_visible_plaid_item_ids`) and existing donut SVG math.

---

## §2. Data Model

### Migration `026_plaid_account_loan_original_amount`

```python
op.add_column(
    "plaid_accounts",
    sa.Column("original_loan_amount_cents", sa.Integer(), nullable=True),
)
```

Idempotent (PRAGMA-guarded, mirrors 025 pattern). Downgrade is a no-op (additive only).

Loans populate the column when the user sets it; credit/depository accounts always leave it null. The column type is checked nowhere except validation — semantically loan-only by convention.

---

## §3. API

### `PUT /plaid/accounts/<id>/loan-meta`

Auth: `@require_auth` + write_access scope. Body:

```json
{ "original_loan_amount_cents": 18500000 }   // or null to clear
```

**Validation:**
- `original_loan_amount_cents` must be `null` or non-negative integer (`>= 0`)
- The account must exist, belong to a Plaid item visible to the user (via `_visible_plaid_item_ids`), AND have `account_type == "loan"`. Any failure → 404 to avoid leaking existence.

**Response:** updated account dict (same shape as `_serialize_plaid_account` + the new field).

### `GET /plaid/cards-overview` — loan row extension

Each `loan` group row gains:

```json
{
  "...": "...existing fields...",
  "original_loan_amount_cents": 18500000,
  "paid_off_cents": 6260000
}
```

Where `paid_off_cents = max(0, original - balance)` if `original_loan_amount_cents` is non-null, else `null`. Credit rows always emit `original_loan_amount_cents: null` and `paid_off_cents: null`.

Edge cases:
- `balance == 0` AND `original > 0` → `paid_off = original` (fully paid)
- `balance > original` (rare — accrued interest, fees) → `paid_off = original`, frontend treats as 100% but flags the over-balance in tooltip
- `original == null` → frontend shows "Set original amount" CTA, no donut

---

## §4. Frontend

### Panel placement

A third sub-panel `#card-usage-loans-panel` inside `#card-usage-card`, AFTER the existing spend-by-category pie panel and BEFORE the existing per-card group list. Only rendered when ≥1 loan account exists in the cache.

### Layout

```
┌─ Loan Progress ──────────────────────────────────┐
│                                                    │
│   Mortgage ····8821                                │
│   ╭────────╮  Paid off:  $62,600.00 (33.8%)      │
│   │  donut │  Unpaid:    $122,400.00              │
│   │  34%   │  Total:     $185,000.00              │
│   ╰────────╯  ✏️ Edit                              │
│                                                    │
│   Auto Loan ····3344                               │
│   ╭────────╮  Original amount not set.            │
│   │ blank  │  ✏️ Set original amount               │
│   ╰────────╯                                      │
└────────────────────────────────────────────────────┘
```

### Behavior

- For each loan row in `__cardsOverviewCache.groups[loan_group].accounts`:
  - If `original_loan_amount_cents != null`: render mini donut (size 100px, two slices — green `#34c759` paid-off + grey `#8e8e93` unpaid). Center label `XX%` paid-off.
  - If null: render placeholder circle (light grey ring) and a "Set original amount" CTA.
- Right of donut: amount summary (paid off / unpaid / total OR placeholder copy) + `✏️ Edit` button.
- Click `✏️ Edit` → swaps that row's content to inline form: `<input type="number" min="0">` + Save / Cancel buttons. Save → `PUT /plaid/accounts/<id>/loan-meta` → on success, refetch via `loadCardsOverview()`.
- Validation client-side: empty string → null (clears); non-numeric or negative → toast "Invalid amount", abort.
- Inline form pre-populates with current value as dollars (not cents) for easier entry.
- Currency: amounts use `_fmtMoneyCents` with `account.balance_currency`.
- The whole `#card-usage-loans-panel` wraps in a `style="display:none"` and only shown when at least one loan exists in the cache.

### Mini-donut SVG

Reuses `_renderCardUsageDonut`-style math but at 100px outer / 30px inner, two-slice always (or one-slice if 0% or 100%). Center text uses `<text>` element absolutely positioned.

Functions added:

```javascript
function _renderLoanProgressPanel()    // main render — iterates loan accounts
function _renderLoanRow(account)       // one row: donut + summary + edit
function _renderLoanMiniDonut(paidOff, total, currency)  // SVG
function _toggleLoanEditMode(accountId, on)
function _saveLoanOriginal(accountId)
```

### Safety

All amount strings → `textContent`. Account name/mask → `textContent`. No `innerHTML` for API data.

---

## §5. Errors + Edge Cases

| Case | Behavior |
|------|----------|
| `original_loan_amount_cents == null` | Placeholder "Set original amount" CTA, donut shows blank ring |
| `balance == 0` AND original > 0 | 100% paid off, full green ring, "Paid off!" badge |
| `balance > original` | `paid_off = original`, donut 100% green, tooltip notes over-balance |
| `original == 0` (invalid) | Server rejects with 400 |
| Negative `original` | Server rejects with 400 |
| Non-integer / string `original` | Server rejects with 400 |
| User A edits user B's loan | 404 (not found per visibility) |
| Non-loan account given to PUT | 404 |
| Cache stale | Edit triggers `loadCardsOverview()` refresh after save |
| No loan accounts | Whole `#card-usage-loans-panel` hidden |
| Currency != USD | Mini donut still renders; amounts shown in native currency |

---

## §6. Testing

### Backend (pytest, append to `tests/test_cards_overview.py`)

- `test_migration_026_loan_original_amount_column` — schema test for the new column
- `test_put_loan_meta_happy_path` — PUT updates original_loan_amount_cents, returns 200 + updated row
- `test_put_loan_meta_clear_with_null` — PUT `{original_loan_amount_cents: null}` clears the field
- `test_put_loan_meta_rejects_negative` — `-100` → 400
- `test_put_loan_meta_rejects_non_integer` — `"abc"` → 400
- `test_put_loan_meta_rejects_credit_account` — account_type=credit → 404
- `test_put_loan_meta_visibility` — user A can't PUT user B's loan
- `test_cards_overview_loan_paid_off_computed` — original=10000, balance=4000 → paid_off=6000
- `test_cards_overview_loan_paid_off_overbalance` — balance > original → paid_off = original (capped)
- `test_cards_overview_loan_no_original` — original null → paid_off null
- `test_cards_overview_credit_row_no_loan_fields` — credit rows have original=null, paid_off=null

### Frontend (manual smoke)

- Loan with original set → mini donut + percentage center + amounts
- Loan without original → placeholder + "Set original amount" CTA
- ✏️ Edit → inline input pre-filled with dollars; Save → re-renders with new donut
- Invalid input (negative, non-numeric) → toast, no save
- Empty input → clears (null), donut returns to placeholder
- Multiple loans → multiple donuts stacked vertically, each independently editable
- Mobile width → donut + summary stack vertically

---

## Open questions / explicit non-decisions

- Phase 2 will populate `original_loan_amount_cents` automatically from Plaid Liabilities API. The user-entered value will be preserved — Liabilities will only fill nulls (UPSERT-on-null).
- APR and next-payment-due display deferred to Phase 2.
- Multi-currency loan amounts entered through this form assume the same currency as the loan's `balance_iso_currency_code`. No currency picker.
