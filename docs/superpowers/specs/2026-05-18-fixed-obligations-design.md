# Fixed Obligations Manager + Analytics Widget — Design Spec

## Goal

Let the user curate a list of "cannot-skip" monthly expenses, then show them on the Analytics dashboard with month-over-month comparison and a monthly floor total.

## Architecture

Two independent pieces:

1. **FloorObligation data model + management UI** — a table of active monthly obligations, editable from the Bills page.
2. **Analytics widget** — reads FloorObligation + BillMeta purchase history to render the floor panel above Spending by Category.

---

## Data Model

### New table: `floor_obligations`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `label` | VARCHAR(255) | Display name |
| `expected_monthly_amount` | DECIMAL(10,2) | User's estimate of normal monthly cost |
| `is_active` | BOOLEAN | Whether included in floor calculation; default true |
| `bill_provider_id` | INTEGER FK → bill_providers.id | NULL for manual items |
| `created_at` | DATETIME | |

Constraints:
- `UNIQUE(bill_provider_id)` where bill_provider_id IS NOT NULL — one row per provider
- No FK cascade delete on bill_provider — if a provider is deleted the obligation becomes manual (set bill_provider_id = NULL)

Schema migration: additive `ALTER TABLE` or `CREATE TABLE IF NOT EXISTS` in `initialize_database_schema.py`.

---

## Management UI (Bills Page)

### Location

New collapsible section at the top of the Bills page, above the monthly bill panels. Heading: "Fixed Monthly Obligations".

### Layout

A table with one row per obligation (active + inactive):

| (toggle) | Name | Expected/mo | Source | (delete) |
|----------|------|-------------|--------|----------|
| ✅ | Rocket Mortgage | $2,100 | Bills | — |
| ✅ | Citizens Energy Group | $140 | Bills | — |
| ✅ | Car Loan | $450 | Manual | 🗑 |

- **Toggle**: inline checkbox, saves immediately via `PATCH /bills/floor-obligations/<id>` `{is_active: bool}`
- **Expected/mo**: editable inline (click to edit), saves on blur
- **Source**: "Bills" for bill_provider-linked rows, "Manual" for user-added rows. Bills-source rows cannot be deleted (only toggled off).
- **Delete**: only shown for Manual rows; calls `DELETE /bills/floor-obligations/<id>`
- **Add row**: "＋ Add manual obligation" button at bottom opens an inline form: name input + amount input + Save

### Auto-population

When the Bills page loads for the first time (or on demand via a "Sync from Bills" button), any `BillProvider` that has no corresponding `FloorObligation` row is offered as a candidate. A small banner: "3 bill providers not in your floor list — Add all / Review". Clicking Add All creates active FloorObligation rows for each.

No automatic sync on every load — user controls their list explicitly.

---

## Analytics Widget

### Location

Above "Spending by Category" on the Analytics/Dashboard page. Only renders if ≥1 active FloorObligation exists.

### Layout

```
Fixed Obligations                            Floor: $3,190/mo
─────────────────────────────────────────────────────────────
Rocket Mortgage      $2,100   $2,100   ──    ✅ paid
Citizens Energy      $141     $134     ▲$7   ✅ paid (over)
Car Loan             $450     $450     ──    ✅ paid
Internet (Manual)    $80      —        —     ⚠ not recorded
─────────────────────────────────────────────────────────────
Total this month     $2,691   $2,684   ▲$7
```

Columns: Name | This month | Last month | Delta | Status

**Status logic:**
- Bill-linked items: look for a BillMeta purchase in the current calendar month for that provider.
  - Found + amount ≤ expected: green "✅ paid"
  - Found + amount > expected: yellow "✅ paid (over)"
  - Not found: red "⚠ not recorded"
- Manual items: always show expected amount in "this month" column, status = grey "manual"

**Floor headline**: sum of all active `expected_monthly_amount` values regardless of whether paid yet.

### API endpoint

`GET /analytics/floor-obligations/summary?month=YYYY-MM`

Returns:
```json
{
  "floor_total": 3190.00,
  "month": "2026-05",
  "obligations": [
    {
      "id": 1,
      "label": "Rocket Mortgage",
      "expected_monthly_amount": 2100.00,
      "is_active": true,
      "source": "bill_provider",
      "this_month_actual": 2100.00,
      "last_month_actual": 2100.00,
      "delta": 0.00,
      "status": "paid"
    }
  ]
}
```

For bill-linked items, "actual" = sum of Purchase.total_amount where BillMeta.provider_id matches and purchase date falls in the target month.

---

## API Endpoints

| Method | Path | Action |
|--------|------|--------|
| GET | `/bills/floor-obligations` | List all obligations (active + inactive) |
| POST | `/bills/floor-obligations` | Create manual obligation `{label, expected_monthly_amount}` |
| PATCH | `/bills/floor-obligations/<id>` | Update `is_active` and/or `expected_monthly_amount` |
| DELETE | `/bills/floor-obligations/<id>` | Delete manual obligation only |
| GET | `/analytics/floor-obligations/summary` | Month summary with actuals |

All endpoints: require auth, write endpoints require write access.

---

## Files

| File | Change |
|------|--------|
| `src/backend/initialize_database_schema.py` | Add `FloorObligation` model + migration |
| `src/backend/handle_bills.py` | Add 4 CRUD endpoints for floor-obligations |
| `src/backend/calculate_spending_analytics.py` | Add `floor_obligations_summary()` function + route |
| `src/frontend/index.html` | Management table in Bills page + widget in Analytics page |
| `tests/test_floor_obligations.py` | API tests for CRUD + summary endpoint |

---

## Out of Scope

- Push notifications when a bill is overdue
- Historical trend charts per obligation
- Budget integration (separate Budget feature handles that)
