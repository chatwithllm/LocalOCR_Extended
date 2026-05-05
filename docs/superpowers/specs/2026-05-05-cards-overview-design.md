# Cards Overview — Design

**Date:** 2026-05-05
**Status:** Approved (brainstorming)
**Phase:** 1 of 2 (Phase 2 = Plaid Liabilities API)

## Goal

Single page that shows current usage (balance, credit limit, utilization %, month-to-date spend, transaction count) for every credit-card and loan account the user has linked via Plaid.

## Scope

**In:** Plaid-linked credit cards (`account_type == "credit"`) and loans (`account_type == "loan"`). Read-only view, fed by existing Plaid balance cache. New columns added to `plaid_accounts` for credit limit and available credit (Plaid Balance API already returns these — currently discarded).

**Out (Phase 2):** Plaid Liabilities API integration (statement balance, APR, next payment due, minimum payment). Statement-cycle period spend (vs calendar month). Re-link required because `liabilities` is not in the existing product scope.

**Out (always):** Depository / checking / savings / investment accounts.

---

## §1. Architecture

```
Plaid /accounts/balance/get  →  plaid_accounts (cache w/ new cols)
                                       ↓
                              GET /plaid/cards-overview
                                       ↓
                              Cards page (frontend)
```

- One new read endpoint `GET /plaid/cards-overview` joins `plaid_accounts` (cached balances + new credit-limit columns) with `plaid_staged_transactions` (period spend).
- No new Plaid API calls. The existing `POST /plaid/accounts/refresh-balances` is reused for the refresh button; it already pulls `balances.limit` and `balances.available` — we just stop discarding them.

---

## §2. Data Model

### Migration `025_plaid_account_credit_limits`

```python
op.add_column("plaid_accounts", sa.Column("credit_limit_cents", sa.Integer(), nullable=True))
op.add_column("plaid_accounts", sa.Column("available_credit_cents", sa.Integer(), nullable=True))
```

Both nullable. Debit / checking / loan accounts have no `limit`. Loans use `balance` only.

### `refresh_balances()` change

When iterating `bal_res["accounts"]`, persist:

- `balances.limit` (dollars, float) → `credit_limit_cents = int(round(limit * 100))`
- `balances.available` (dollars, float) → `available_credit_cents = int(round(available * 100))`

No backfill needed — populated on next refresh. UI shows `—` for nulls until refreshed.

### Period-spend join

```sql
SELECT plaid_account_id,
       SUM(amount) AS net_amount,
       COUNT(*) FILTER (WHERE amount > 0) AS debit_count
FROM plaid_staged_transactions
WHERE user_id = :user_id
  AND transaction_date >= :month_start
  AND status != 'dismissed'
GROUP BY plaid_account_id
```

- Refunds (negative `amount`) net out — matches statement convention.
- `txn_count_mtd` is debit-only (refunds excluded).
- `status` filter: keeps `ready_to_import`, `duplicate_flagged`, `skipped_pending`, `confirmed`. Excludes `dismissed`.

---

## §3. API

### `GET /plaid/cards-overview`

Auth: `@require_auth`. Read-only. No throttle (cache-only read; no Plaid call). Existing `_visible_plaid_item_ids` filter applied.

**Response:**

```json
{
  "as_of": "2026-05-05T17:30:00Z",
  "month_start": "2026-05-01",
  "groups": [
    {
      "type": "credit_card",
      "label": "Credit Cards",
      "accounts": [
        {
          "id": 12,
          "plaid_item_id": 3,
          "name": "Sapphire Preferred",
          "mask": "4521",
          "subtype": "credit card",
          "balance_cents": 124300,
          "credit_limit_cents": 500000,
          "available_credit_cents": 375700,
          "utilization_pct": 24.86,
          "spend_mtd_cents": 41250,
          "txn_count_mtd": 17,
          "balance_updated_at": "2026-05-05T16:12:03Z",
          "currency": "USD"
        }
      ]
    },
    {
      "type": "loan",
      "label": "Loans",
      "accounts": [...]
    }
  ],
  "totals": {
    "credit_balance_cents": 124300,
    "credit_limit_cents": 500000,
    "overall_utilization_pct": 24.86,
    "credit_spend_mtd_cents": 41250,
    "loan_balance_cents": 0
  }
}
```

**Type bucketing:**

- `account_type == "credit"` → `credit_card` group
- `account_type == "loan"` → `loan` group
- All others (depository / investment) → excluded from response

**Compute rules:**

- `utilization_pct` = `balance_cents / credit_limit_cents * 100` (rounded to 2 decimals; `null` if limit null or zero)
- `spend_mtd_cents` = `int(round(net_amount * 100))` from the join above
- `txn_count_mtd` = debit count (excludes refunds)
- `totals.overall_utilization_pct` = sum(balance) / sum(limit) across all credit accounts that have a limit
- `totals.credit_spend_mtd_cents` = sum across credit accounts only
- Currency aggregation: only USD accounts contribute to `totals`. Non-USD accounts appear in groups but with their native `currency` field; frontend shows footer note.

---

## §4. Frontend

New page route `#cards`, registered in router and main nav. Visibility gated by existing `allowed_pages` mechanism (default-on for admins, opt-in for members).

### Layout

```
┌─ Cards ────────────────────── [↻ Refresh] ─┐
│                                              │
│  ┌─ Summary ──────────────────────────────┐ │
│  │ Total credit balance   $1,243.00       │ │
│  │ Total credit limit     $5,000.00       │ │
│  │ Overall utilization    24.9%   [bar]   │ │
│  │ Credit spend (May)     $412.50         │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  Credit Cards                                │
│  ┌──────────────────────────────────────┐  │
│  │ 💳 Sapphire ····4521                 │  │
│  │ $1,243 / $5,000           [████░] 25%│  │
│  │ This month: $412.50 · 17 txns        │  │
│  │ Available: $3,757                    │  │
│  │ Updated 18 min ago                   │  │
│  └──────────────────────────────────────┘  │
│                                              │
│  Loans                                       │
│  ┌──────────────────────────────────────┐  │
│  │ 🏠 Mortgage ····8821                 │  │
│  │ Balance: $182,400                    │  │
│  │ This month: $0 · 0 txns              │  │
│  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### Behavior

- On mount: `GET /plaid/cards-overview` → render.
- If newest `balance_updated_at` across all accounts > 1hr stale → auto-trigger `POST /plaid/accounts/refresh-balances` once, swallow 429, re-fetch overview.
- Refresh button: `POST /plaid/accounts/refresh-balances`. On 200 or 429, re-fetch overview. On 429 surface a toast.
- Util bar color: `<30%` green (`util-good`), `30–70%` amber (`util-warn`), `>70%` red (`util-bad`).
- Util > 100% (over limit) → bar clamped to 100% width, numeric value shown unclamped, red.
- Net-refund row (`spend_mtd_cents < 0`) → "−$23.40 (net refund)" in muted neutral.
- Empty state: "No linked accounts. Link via Settings → Plaid." with deep link to existing Plaid Link flow.
- Tap a card row → drill into existing transactions UI filtered by that `plaid_account_id`.
- Mobile: single column, sticky summary at top, full-width rows.

### Defaults baked

| Decision | Value |
|----------|-------|
| Display | New top-nav page **"Cards"** |
| Spend window | Calendar month-to-date |
| Refresh | Manual button + auto-refresh on open if cache > 1hr |
| Grouping | Credit Cards (sorted by util% desc), Loans (sorted by balance desc) |
| Util% color | green <30, amber 30–70, red >70 |
| Privacy | Existing `_visible_plaid_item_ids` filter respected |

---

## §5. Errors + Edge Cases

| Case | Behavior |
|------|----------|
| No Plaid linked | Empty state with link to Settings → Plaid. |
| Plaid not configured (`is_plaid_configured() == False`) | Page hides Refresh button. Shows cached data only. |
| `credit_limit_cents` null (never refreshed since migration) | Util%, available, limit shown as `—`. Row still renders balance + spend. |
| Refresh 429 (throttle) | Toast: "Refreshed recently. Try again in Xs." Keeps existing data. |
| Refresh fails (Plaid 5xx) | Per-item error logged; cached data still shown. |
| `ITEM_LOGIN_REQUIRED` on any item | Banner: "1 institution needs reconnect" → links to existing reconnect flow. |
| Loan account with no Plaid transactions | `spend_mtd_cents = 0`, `txn_count_mtd = 0`. |
| Net refund (refunds > debits MTD) | Negative spend value, muted styling. |
| Util > 100% | Bar clamped to 100%, value shown unclamped, red. |
| Non-USD account | Row shows native currency; excluded from `totals`; footer note "1 account in CAD excluded from totals." |
| Cache > 24hr stale | Banner: "Balances may be outdated. Refresh." |
| User without write_access scope | Refresh button hidden (existing `@require_write_access` returns 403). |

---

## §6. Testing

### Backend (pytest)

- `test_cards_overview_empty` — no Plaid items → empty groups + zero totals.
- `test_cards_overview_credit_card_with_limit` — fixture: 1 credit account, limit set, 3 staged txns (2 debits + 1 refund) MTD → util%, spend net, count excludes refund.
- `test_cards_overview_credit_card_no_limit` — null `credit_limit_cents` → `utilization_pct: null`, `available_credit_cents: null`.
- `test_cards_overview_loan_excludes_util` — loan account → no util%, just balance.
- `test_cards_overview_excludes_depository` — checking account never appears in groups.
- `test_cards_overview_visibility_filter` — user A cannot see user B's accounts.
- `test_cards_overview_mtd_boundary` — txn dated last day of prev month excluded; first day of current month included.
- `test_cards_overview_dismissed_excluded` — staged txn with `status='dismissed'` not counted in spend.
- `test_refresh_balances_persists_limit_and_available` — mocked Plaid response with `balances.limit` and `balances.available` → row updated.
- `test_migration_025_add_credit_columns` — alembic upgrade adds nullable columns; downgrade drops them.

### Frontend (manual smoke)

- Open `#cards` → renders summary + groups.
- Empty Plaid state → empty card + Settings link.
- Refresh button → toast on 429.
- Stale-cache auto-refresh on mount.
- Util bar colors at boundary values (29%, 30%, 69%, 70%, 101%).

### Fixtures

Reuse `tests/fixtures/plaid_*.py` if it exists; else add a minimal one alongside Phase 1.

---

## Open questions / explicit non-decisions

- **Statement balance vs current balance.** Phase 1 uses `current` from Plaid Balance API (matches what other endpoints already store). Phase 2 (Liabilities API) will add `last_statement_balance` and split the display.
- **Period choice.** Calendar month-to-date is hardcoded. Phase 2 will offer "since last statement close" once Liabilities provides statement dates.
- **Cross-currency totals.** Phase 1 only aggregates USD. A multi-currency household will see partial totals + a note. Revisit when more than one user has non-USD accounts.

## Phase 2 preview (not in this spec)

- New Plaid product: `liabilities`. Existing users must re-link to grant the scope.
- New endpoint `GET /plaid/liabilities` exposing APR, statement balance, last statement date, next payment due, minimum payment.
- Cards page gains optional "next payment due" column and statement-cycle spend mode.
