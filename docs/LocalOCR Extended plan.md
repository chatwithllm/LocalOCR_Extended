# LocalOCR_Extended — Recurring Household Bills: Product & Technical Plan

---

## 1. Executive Summary

The existing app has solid bones: a receipt-based data model, bill metadata fields, budget and recurring obligation views, and provider tracking. The gap is that these pieces don't yet form a coherent monthly planning system. Bills are entered but not predicted. Providers exist but can't hold multiple services. Paid status is manual and fragile. The extraction layer pulls data but doesn't drive automation.

This plan closes those gaps incrementally without a rewrite. The core changes are: a richer provider model that supports multiple services per provider, a deterministic "planning month" rule, a status lifecycle for each bill obligation, and an LLM extraction split where Gemini handles raw facts and the app handles all planning logic.

---

## 2. Recommended Conceptual Model

The mental model shift is from **"receipts for bills"** to **"monthly obligation slots that bills fill."** Each recurring service generates a predictable slot for every month. When a bill arrives, it fills the slot. If no bill arrives, the slot shows as missing or estimated. The receipt/document remains the evidentiary artifact; the obligation slot is the planning unit.

Three main entities emerge:

- **Provider** — holds identity information (name, account number, contact info) and owns one or more Service Lines. This separates the company from the services it delivers, which is the core fix for the Citizens Energy Group problem.
- **Service Line** — the recurring obligation unit. It knows its billing cycle, typical amount range, and which planning month rule applies. One provider can have three service lines; each generates independent monthly slots.
- **Bill Record** — the document artifact (what currently exists as a household bill receipt) that resolves a service line slot for a given month. It carries raw extracted data, user-confirmed values, and derived planning fields.

### Slot Statuses

| Status | Meaning |
|---|---|
| Paid | Bill received and payment confirmed |
| Upcoming | Bill received, due date in the future |
| Overdue | Due date passed, not marked paid |
| Estimated | No bill yet, amount estimated from history |
| Missing | Expected bill window passed, nothing uploaded |
| Not yet entered | Future slot, no action needed yet |

---

## 3. Extraction vs App Logic Split

**Your proposed split is correct.** It is the right architecture.

### Gemini extracts raw bill facts

Things that are literally printed on the document and require no inference beyond reading:

- Provider name
- Account number
- Service address
- Statement date
- Service period start and end
- Due date
- Total amount due
- Itemized line items (each service charge separately)
- Previous balance
- Payment received
- Penalty amounts
- Service type classification from bill header (gas, electric, water, etc.)

### The app derives everything else

- Which Provider record to match or create
- Which Service Line to associate
- Which planning month the bill belongs to
- What the status is (upcoming, overdue, etc.)
- Whether the amount is higher or lower than the running average for this service line
- Whether this fills an existing slot or creates a new one
- All historical context (prior bills, configured rules, payment records)

### Why this split is correct

If planning logic lived in the Gemini prompt, a user correction to a misread date would require a full re-extraction round-trip. Keeping derivation in app code means it is **deterministic, testable, and auditable**. When a user corrects a raw extracted field, the app re-derives all planning values automatically.

---

## 4. Recommended Data Model

These are **additive changes** to your existing schema. Nothing below requires dropping or migrating existing bill receipt records.

### New: `providers` table

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| display_name | string | required |
| account_number | string | nullable |
| website | string | nullable |
| phone | string | nullable |
| notes | text | nullable |
| created_at | timestamp | |

The existing provider name field on bill receipts becomes a foreign key into this table.

### New: `service_lines` table

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| provider_id | UUID FK → providers | |
| service_type | enum | see section 6 |
| account_label | string | nullable — per-service account numbers |
| billing_cycle | enum | monthly \| bimonthly \| quarterly \| annual |
| planning_month_rule | enum | due_date_month \| statement_month \| service_end_month |
| typical_amount_min | decimal | nullable, derived from history |
| typical_amount_max | decimal | nullable, derived from history |
| is_active | boolean | default true |
| autopay_enabled | boolean | default false |
| notes | text | nullable |
| created_at | timestamp | |

### Modified: existing `bill_receipts` table

Add the following columns:

| Field | Type | Notes |
|---|---|---|
| service_line_id | UUID FK → service_lines | nullable |
| planning_month | string YYYY-MM | derived and stored |
| extraction_raw | JSON | full Gemini response before edits |
| extraction_confidence | enum | low \| medium \| high |
| paid_date | date | actual payment date |
| paid_amount | decimal | may differ from amount due |
| status | enum | estimated \| not_entered \| upcoming \| overdue \| paid |
| is_manual_entry | boolean | default false |

### New: `monthly_obligation_slots` table (recommended)

A lightweight projection table, not a source of truth. Regenerated from service lines and bills. Powers the planning calendar view without complex queries.

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| service_line_id | UUID FK | |
| planning_month | string YYYY-MM | |
| bill_receipt_id | UUID FK | nullable until filled |
| status | enum | mirrors bill status values |
| estimated_amount | decimal | nullable |

---

## 5. Monthly Obligation Logic

### Recommended rule

> **Default: use due date month.** Due date reflects when the user's cash actually needs to be available.

**Priority order for deriving planning month:**

1. Due date month — if a due date is present and within 45 days of statement date
2. Service period end month — if no due date is available
3. Statement date month — fallback of last resort

**Your example resolved:**
Bill issued late March, due April → counts toward **April**. The rule handles this naturally.

### Per-line override

Each service line has its own `planning_month_rule` setting. Default is `due_date_month`. Users can override per line (e.g. rent that should count toward the month it covers rather than the due date month).

### Edge case to watch

If a bill is issued December 28 and due January 3, it belongs in January. The rule handles this correctly, but display the planning month prominently in the UI so users can spot and correct misclassifications.

---

## 6. Provider / Service Modeling

### Service type is single-select on the Service Line, not the Provider

Each service line has exactly one service type. A provider with three services simply has three service line records. Billing, cycle, amount, and status are independent per service.

### Service type enum

```
electricity | gas | water | sewer | trash | internet | phone |
insurance_home | insurance_auto | insurance_health | insurance_life |
mortgage | rent | daycare | gym | hoa | streaming | other
```

### Combined bills (one document, multiple services)

For a Citizens Energy Group bill covering gas, water, and sewer on one statement:

- Use a `bill_service_lines` junction table
- One uploaded document links to multiple service line slots
- Gemini identifies individual service charges as separate line items
- The app suggests the mapping; user confirms
- **Phase 1 simplification:** link one bill to multiple service lines without distributing amounts. Amount distribution comes in a later phase.

---

## 7. UI / UX Recommendations

### Bill planning dashboard (new view)

A monthly grid where rows are service lines and columns are months (6 months back, 3 forward). Each cell shows a color-coded status chip. Tapping a cell opens the bill record or prompts to add one. This is the primary planning surface.

### Provider management screen (new view)

A list of providers, each expandable to show its service lines. Users add new service lines here, not on the bill form. The bill form then links to an existing service line.

### Revised bill upload flow

Two-panel review screen after upload:
- Left: extracted fields with confidence indicators (low-confidence fields highlighted)
- Right: document image
- Planning month shown prominently with explanation ("Due date is April 12 → counts toward April")
- Single "looks good" action saves and closes the slot

### Status chips

Consistent color-coded status chips everywhere a bill appears: budget view, provider summary, obligation view.

| Status | Color |
|---|---|
| Paid | Green |
| Upcoming | Blue |
| Overdue | Red |
| Estimated | Amber |
| Missing | Gray |

### Manual entry

Same form as upload flow but all fields blank. `is_manual_entry` flag set. For autopay bills, user can enter the confirmed amount after the charge hits their account.

### Estimation display

Estimated amounts shown with tilde prefix: **~$142**. Small info icon explains the calculation (average of last N bills for this service). Replaced by actual amount when the bill arrives.

### Overdue handling

If today is past the due date and the bill is not marked paid, status transitions to overdue automatically. Show a dashboard banner for any overdue items.

---

## 8. Edge Cases and Risks

**Provider name matching on extraction.** Gemini may return "Citizens Energy" while the database has "Citizens Energy Group." Use fuzzy matching on provider name during the save flow. Show the candidate match and let the user confirm or create new. Never silently create duplicate providers.

**Bills uploaded after due date.** Do not assume a late-uploaded bill is paid. Default status to overdue and prompt: "This bill was due April 5. Have you paid it?"

**Autopay bills.** Support PDF confirmation uploads. If Gemini detects a payment confirmation document (vs. a statement), mark status as paid on import using the confirmation date as `paid_date`.

**First bill for a new service line.** No history means no estimate. Show a placeholder: "First bill — no estimate available." Estimates activate after the first bill is saved.

**Irregular billing cycles.** Quarterly and annual service lines (insurance, HOA) only generate slots for months where a bill is actually expected. Non-billing months show as blank, not as missing.

**Amount variability.** Electricity can vary 3× between summer and winter. Use a rolling 12-month average rather than last-3. Show the min/max range alongside the estimate.

**Gemini extraction failures.** When confidence is low on critical fields (due date, amount), do not auto-save. Require user review before the record is committed.

**Duplicate uploads.** If the same provider, statement date, and amount combination already exists, warn before creating a second record.

---

## 9. Phase Plan

| Phase | Scope | Estimated Effort |
|---|---|---|
| **1** | Provider + service line data model. Migration from existing provider name field. Provider management screen. | 2–3 weeks |
| **2** | Planning month derivation. `monthly_obligation_slots` projection. Planning month display on bill detail. | 2–3 weeks |
| **3** | Enhanced Gemini extraction prompt. Two-panel review screen. Confidence indicators. `extraction_raw` storage. | 2–3 weeks |
| **4** | Bill planning dashboard (monthly grid). Status lifecycle. Overdue banner. Status chips across all views. | 3–4 weeks |
| **5** | Rolling average estimator. Phantom future slots for active service lines. Estimated amount display. | 2–3 weeks |
| **6** | Multi-service bill linking. Amount distribution UI for combined bills. | 2–3 weeks |

Each phase ships to production independently. Users gain value at every step.

---

## 10. Final Implementation Prompt

> Hand this prompt directly to a coding model to begin Phase 1.

---

You are working on an existing production app called **LocalOCR_Extended**. This is an incremental enhancement — do not rewrite or replace any existing functionality. Read and understand the existing data model and UI patterns before making any changes.

**Context:** The app already supports household bill receipts with fields for provider name, provider type, account label, billing cycle month, service period start/end, due date, and a recurring monthly flag. There are existing views for budgets, recurring obligations, provider summaries, and month-based bill views. The goal is to extend this system to support proper recurring bill planning without disrupting what already works.

---

### Phase 1 task — Provider and service line model

**Add a `providers` table** with fields:
- `id` (UUID PK)
- `display_name` (string, required)
- `account_number` (string, nullable)
- `website` (string, nullable)
- `phone` (string, nullable)
- `notes` (text, nullable)
- `created_at` (timestamp)

**Add a `service_lines` table** with fields:
- `id` (UUID PK)
- `provider_id` (UUID FK → providers)
- `service_type` (enum: `electricity | gas | water | sewer | trash | internet | phone | insurance_home | insurance_auto | insurance_health | insurance_life | mortgage | rent | daycare | gym | hoa | streaming | other`)
- `account_label` (string, nullable — for per-service account numbers)
- `billing_cycle` (enum: `monthly | bimonthly | quarterly | annual`, default `monthly`)
- `planning_month_rule` (enum: `due_date_month | statement_month | service_end_month`, default `due_date_month`)
- `typical_amount_min` (decimal, nullable)
- `typical_amount_max` (decimal, nullable)
- `is_active` (boolean, default true)
- `autopay_enabled` (boolean, default false)
- `notes` (text, nullable)
- `created_at` (timestamp)

**Add to the existing bill receipts table:**
- `service_line_id` (UUID FK → service_lines, nullable)
- `planning_month` (string YYYY-MM format, nullable)
- `extraction_raw` (JSON, nullable)
- `paid_date` (date, nullable)
- `paid_amount` (decimal, nullable)
- `status` (enum: `not_entered | estimated | upcoming | overdue | paid`, default `upcoming`)
- `is_manual_entry` (boolean, default false)

**Write a migration** that reads the existing `provider_name` field on bill receipts and creates a corresponding `providers` row (deduplicating by normalized name). Then create a `service_lines` row using the existing `provider_type` field to set `service_type`. Link each bill receipt to its new `service_line_id`. Preserve all existing data.

**Build a provider management screen** that lists all providers. Each provider row is expandable to show its service lines. Include add/edit/deactivate for both providers and service lines. Service type is a single-select dropdown using the enum above.

**On the existing bill receipt edit form,** replace the free-text provider name field with a provider + service line selector (search-as-you-type for provider, then a secondary selector for the service line within that provider). Keep all other existing fields unchanged.

**Write a `derivePlanningMonth(bill)` function** that:
1. Reads the service line's `planning_month_rule`
2. Applies it to the bill's available dates (due date, service period end, statement date) in that priority order
3. Returns a YYYY-MM string

Call this function on save and store the result in `planning_month`. Expose it so it can be called again whenever the user corrects a date field.

**Do not build the planning dashboard yet.** That is Phase 4. For now, display the `planning_month` field prominently on the bill detail view with the label "Counts toward" and a small note showing which rule was applied (e.g., "Based on due date").

Match the existing visual style of the app exactly. Use the same component library, spacing, typography, and color conventions already in use. Do not introduce new design patterns.

**Write unit tests for `derivePlanningMonth`** covering:
- Due date present
- No due date (falls back to service period end)
- No due date and no service period end (falls back to statement date)
- Cross-month case where statement is late in one month and due date is in the following month