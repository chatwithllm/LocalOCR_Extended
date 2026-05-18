# Floor Obligations v2 — Design Spec

## Goal

Enhance the Fixed Obligations Manager so users can:
1. See historical average and latest actual amounts alongside the expected amount they set
2. Tune their floor list via a "Selected / Available" tab split — moving items in and out without deleting them
3. Get 6-month average pre-filled when adding a bill provider to the floor

---

## What Is Not Changing

- `floor_obligations` DB table — no schema changes
- `/floor-obligations/summary` endpoint — response shape unchanged
- Dashboard widget — no changes

---

## Data Layer

### Computed fields added to list response

`GET /floor-obligations/` now returns two additional read-only fields per obligation:

| Field | Type | Meaning |
|-------|------|---------|
| `avg_6mo` | FLOAT \| null | Average of `Purchase.total_amount` over the last 6 complete calendar months, via `BillMeta.provider_id` join. `null` for manual obligations or providers with no purchase history. |
| `latest_actual` | FLOAT \| null | Most recent calendar month's payment (sum of purchases in that month). `null` for manual obligations or no history. |

These are computed at query time in Python — no DB columns added.

### New endpoint: `GET /floor-obligations/available`

Returns bill providers that have **no active FloorObligation** (i.e. `bill_provider_id` not present in any active row).

Response:
```json
{
  "available": [
    {
      "bill_provider_id": 7,
      "label": "DIRECTV",
      "avg_6mo": 89.50,
      "latest_actual": 91.00
    }
  ]
}
```

- `avg_6mo` and `latest_actual` computed same way as above
- `label` = `BillProvider.canonical_name` (fallback to `BillProvider.name`)
- Inactive FloorObligation rows (is_active=false) are treated as "available" — they appear here and their existing row is reactivated on Add (PATCH is_active=true + update amount) rather than creating a duplicate

Auth: `@require_auth` (read-only)

---

## Bills Page — Management Table

### Layout

Tabbed panel replacing the current flat table:

```
[ Selected (3) ]  [ Available (2) ]
```

### Selected tab

Table columns: (checkbox) | Name | Expected/mo | Avg (6mo) | Latest | Source | (action)

- **Expected/mo**: editable inline on click, saves on blur via `PATCH /floor-obligations/<id>`
- **Avg (6mo)**: grey read-only hint
- **Latest**: grey read-only hint (most recent month paid)
- **Source**: "Bills" or "Manual" label
- **Action**:
  - Bill-linked rows: "Remove" button → `PATCH is_active=false` (moves to Available tab)
  - Manual rows: 🗑 delete button → `DELETE /floor-obligations/<id>`
- Add manual form at bottom of Selected tab (unchanged from v1)

### Available tab

Table columns: Name | Avg (6mo) | Latest | (add button)

- Each row: bill provider not currently on the floor
- **Add button**: opens a mini inline form inline in the row:
  - Amount input pre-filled with `avg_6mo` (editable)
  - Save → if an inactive FloorObligation exists for this provider: `PATCH is_active=true + expected_monthly_amount=<amount>`; otherwise: `POST /floor-obligations/` with `bill_provider_id` + `label` + `expected_monthly_amount`
  - Cancel → collapses form

### Tab counts

Tab labels show live counts: "Selected (3)" / "Available (2)". Counts update after any add/remove action.

---

## API Endpoints Summary

| Method | Path | Change |
|--------|------|--------|
| GET | `/floor-obligations/` | + `avg_6mo`, `latest_actual` fields in each obligation |
| GET | `/floor-obligations/available` | **New** — available providers with avg/latest |
| PATCH | `/floor-obligations/<id>` | No change (already handles `is_active` + `expected_monthly_amount`) |

---

## Files

| File | Change |
|------|--------|
| `src/backend/handle_floor_obligations.py` | `_compute_history()` helper; enrich list response; add `/available` route |
| `src/frontend/index.html` | Replace flat table with tabbed panel; Selected tab adds Avg/Latest columns; Available tab with inline add form |
| `tests/test_floor_obligations.py` | Tests for `avg_6mo`/`latest_actual` in list; tests for `/available` endpoint |

---

## Out of Scope

- Avg/latest columns in the dashboard widget
- Per-obligation trend charts
- More than 6-month avg window (fixed at 6)
- Avg for manual obligations (no purchase history to draw from)
