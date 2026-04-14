# LocalOCR Extended — Recurring Household Bills Phased Implementation

This document turns the consolidated recurring-bills plan into an execution sequence for the new implementation branch.

Current implementation branch:
- `codex/planning-month-foundation`

This document is the working phase guide for the next build cycle.

## 1. Goal Of This Implementation Track

We are evolving recurring household bills from:
- receipt capture with basic bill metadata

into:
- a real monthly obligation planning system

without replacing the existing receipt-based architecture.

## 2. What Already Exists Before This Track

Already in `main`:
- `Household Bill` receipt type
- bill metadata capture
- recurring flag
- household-obligations budget support
- bills analytics and recurring-obligation summaries
- provider-name normalization
- combined-provider metadata compatibility support

Still missing:
- canonical providers
- canonical service lines
- planning month derivation
- paid vs unpaid lifecycle
- generated obligation slots
- estimation / missing detection
- Gemini-specific household-bill extraction flow

## 3. Phase Overview

### Phase 1 — Canonical Provider And Service-Line Foundation

What this phase will complete:
- introduce canonical provider identity
- introduce canonical service-line identity
- preserve compatibility with current provider-name / provider-type metadata
- prepare the receipt system to link a household bill to a stable provider/service record

Expected deliverables:
- new provider model in backend schema
- new service-line model in backend schema
- migration/backfill logic for existing household bills
- initial provider/service lookup behavior in the bill edit flow
- no forecasting yet
- no obligation-slot generation yet

Expected user-visible outcome:
- providers stop being only text labels
- one provider can cleanly support multiple services
- future recurring logic will have a stable base

### Phase 2 — Planning Month Foundation

What this phase will complete:
- derive and store `planning_month`
- show users what month a bill counts toward
- explain the rule used to derive that month

Expected deliverables:
- deterministic planning-month function
- fallback order:
  - due date month
  - service period end month
  - statement/receipt month
- persistence on save
- recompute on edit
- visible "Counts toward" UI

Expected user-visible outcome:
- bills can be reasoned about by the month they belong to for planning

### Phase 3 — Bill Lifecycle And Paid-State Model

What this phase will complete:
- separate "bill exists" from "bill is paid"
- introduce a lifecycle users can trust

Expected deliverables:
- explicit statuses:
  - upcoming
  - overdue
  - paid
  - estimated
  - missing
  - not_yet_entered
- payment confirmation fields
- UI to mark payment confirmed
- rules that do not auto-mark uploaded bills as paid

Expected user-visible outcome:
- users can distinguish entered bills from actually paid obligations

### Phase 4 — Monthly Obligation Slots

What this phase will complete:
- generate predictable recurring obligation slots
- let each month show what is filled vs missing

Expected deliverables:
- generated monthly obligation projection
- actual bill linked to slot when available
- support for future and unfilled slots

Expected user-visible outcome:
- users can see what recurring bills are expected for a month even before upload

### Phase 5 — Gemini Household-Bill Extraction Contract

What this phase will complete:
- automate household-bill extraction more deeply

Expected deliverables:
- dedicated extraction contract for bill documents
- extraction of:
  - provider
  - likely service type
  - statement date
  - due date
  - service period
  - account hints
  - totals and fees
- confidence-aware review behavior
- deterministic post-processing after user corrections

Expected user-visible outcome:
- uploading a bill should prefill most fields correctly

### Phase 6 — Estimation And Missing Detection

What this phase will complete:
- predict expected bills for a month
- detect when an expected bill has not arrived

Expected deliverables:
- rolling-history estimate per service line
- expected recurring slot generation for future/current months
- missing detection when expected window passes
- anomaly surfacing for unusual bill amounts

Expected user-visible outcome:
- the app starts acting like a planning assistant, not just a receipt archive

### Phase 7 — Multi-Service Bill Allocation

What this phase will complete:
- support one bill funding multiple service lines cleanly

Expected deliverables:
- one-to-many bill/service linking
- optional per-service amount allocation
- combined-bill reconciliation UI

Expected user-visible outcome:
- providers like Citizens Energy Group can be represented correctly without awkward workarounds

## 4. Recommended Immediate Sequence

The execution order should be:

1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4
5. Phase 5
6. Phase 6
7. Phase 7

This keeps the highest-risk forecasting work off the table until the underlying records are stable.

## 5. Current Branch Progress

This branch has moved beyond the original Phase 1-only starting point.

### Phase 1 — Canonical Provider And Service-Line Foundation

Completed in the current implementation pass:
- restored BillMeta save/load wiring in the receipt editor and manual entry flow
- restored household-bill budget-domain helpers that were missing from the branch
- added canonical `bill_providers` records
- added canonical `bill_service_lines` records
- added compatibility linkage from `bill_meta` into provider/service-line identities
- added runtime backfill so existing bill metadata can attach to canonical provider/service-line rows

Verified in the current implementation pass:
- stronger provider/service lookup behavior in the bill edit flow
- operator smoke test of bill edit/save against a live local database

### Phase 2 — Planning Month Foundation

Completed in the current implementation pass:
- deterministic planning-month derivation is implemented
- fallback order is now:
  - due date month
  - service period end month
  - legacy stored billing-cycle month
  - receipt month fallback
- planning month persists through upload, manual entry, and receipt edit flows
- receipt detail shows a visible `Counts toward` explanation in Bill Planning

### Phase 3 — Bill Lifecycle And Paid-State Model

Completed in the current implementation pass:
- receipt detail now supports bill payment-status actions
- analytics distinguish entered obligations from outstanding ones
- Bills workspace can show `Not Due` for obligations outside the selected cadence month

Still remaining inside Phase 3:
- richer overdue/upcoming lifecycle states
- explicit payment-confirmation timestamp/history

### Phase 4 — Monthly Obligation Slots

Completed in the current implementation pass:
- Bills workspace renders recurring obligations against the selected month
- obligation cards support direct receipt jump-through
- lower Bills sections remain available:
  - Providers
  - Month-over-Month
  - Recent Bills

### Phase 6 — Estimation And Missing Detection

Completed in the current implementation pass:
- projection logic now respects non-monthly bill cadence
- supported billing cycles now include:
  - monthly
  - every 2 months
  - quarterly
  - every 6 months
  - annual
- recurring-obligation status now distinguishes:
  - entered
  - outstanding
  - not due
- Bills workspace carries cadence through:
  - obligation cards
  - manual-entry shortcuts
  - receipt detail summaries
- projection logic uses cadence-aware month matching before surfacing missing/outstanding bills
- Progressive insurance was verified locally as a semiannual recurring bill example

Additional operator fixes completed alongside these phases:
- store canonicalization now merges duplicate provider/store variants such as:
  - AES Indiana / Aes Indiana
  - McDonald's receipt-number variants
  - India Bazar naming variants
- `Receipts By Store` cards are clickable and open filtered Receipts results
- Bills-to-Receipts jump-through now bypasses the default last-60-days receipt filter once, so older bills like `2026-01-19` Progressive can still open from the Bills workspace

## 6. Personal-Service Cash / Transfer Track

This implementation branch also moved beyond receipt-only household obligations and now supports recurring personal-service payments inside the same Bills + Budget surfaces.

Completed in the current implementation pass:
- added personal-service metadata on canonical bill providers and service lines
- added `cash_transactions` as the manual-payment persistence layer
- linked each saved cash / transfer payment to a lightweight `Purchase` for budget/reporting compatibility
- added planning-month derivation for manual cash / transfer entries
- extended recurring-obligation generation to include personal-service lines
- added month-state reconciliation for personal-service obligations:
  - upcoming
  - overdue
  - missing
  - paid
- added Bills entry points for:
  - `Log Cash / Transfer`
  - `Mark Paid` on personal-service obligations
- added provider payment-history detail for personal-service providers
- added delete support for mistaken manual cash / transfer entries

Important implementation notes:
- future-dated manual payments are now treated as upcoming instead of immediately counting as paid
- personal-service cash rows now route to payment history rather than the receipt viewer
- deleting the last orphaned test payment also removes the now-empty provider/service-line records when they are not linked to real bill metadata
- the cash / transfer modal has been restyled into a darker, cleaner, mobile-safer form to match the app shell

### Explicitly not in scope now

- forecasting
- missing-bill detection
- monthly-slot engine
- paid-status lifecycle
- Gemini extraction redesign
- allocation of one bill across multiple services

## 6. Expected Output Of This Branch Track

This branch now provides:

- a stable provider object
- a stable service-line object
- a migration/backfill approach for current household bills
- a clear compatibility path from current `provider_name` / `provider_type` bill metadata to canonical records
- planning-month derivation and persistence
- cadence-aware recurring-obligation projections
- a Bills workspace that supports drill-down into matching receipt history

## 7. Restart Point

If work pauses, restart from:
- this document
- `future enhancements/recurring household bills consolidated plan.md`
- `docs/IMPLEMENTATION_STATUS.md`
