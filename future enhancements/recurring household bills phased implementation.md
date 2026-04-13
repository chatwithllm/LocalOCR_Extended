# LocalOCR Extended — Recurring Household Bills Phased Implementation

This document turns the consolidated recurring-bills plan into an execution sequence for the new implementation branch.

Current implementation branch:
- `codex/recurring-bills-foundation`

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

## 5. Phase 1 Scope We Are Starting Now

Phase 1 is officially:
- **Canonical Provider And Service-Line Foundation**

### In scope now

- add canonical provider records
- add canonical service-line records
- keep current bill metadata fields for compatibility
- map current provider-related bill metadata toward those canonical records
- document how receipt editing will evolve to use these stable records

### Explicitly not in scope now

- forecasting
- missing-bill detection
- monthly-slot engine
- paid-status lifecycle
- Gemini extraction redesign
- allocation of one bill across multiple services

## 6. Expected Output Of Phase 1

When Phase 1 is complete, we should have:

- a stable provider object
- a stable service-line object
- a migration/backfill approach for current household bills
- a clear compatibility path from current `provider_name` / `provider_type` bill metadata to canonical records
- the codebase ready for `planning_month` work in Phase 2

## 7. Restart Point

If work pauses, restart from:
- this document
- `future enhancements/recurring household bills consolidated plan.md`
- `docs/IMPLEMENTATION_STATUS.md`
