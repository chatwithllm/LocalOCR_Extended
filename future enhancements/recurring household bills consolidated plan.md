# LocalOCR Extended — Recurring Household Bills Consolidated Plan

This document is the current restart point for recurring household bills and obligation forecasting.

It consolidates:
- what is already implemented in `LocalOCR_Extended`
- what we should adopt from the external planning response
- what should be adjusted before development
- the phased path we should actually execute in this codebase

## 1. Current State In LocalOCR_Extended

As of the current `codex/household-bills` work, the app already supports:

- `Household Bill` as a receipt type
- household-bill manual entry
- household-bill editing in the receipt editor
- bill metadata capture and persistence for:
  - provider name
  - provider type
  - account label
  - billing cycle month
  - service period start
  - service period end
  - due date
  - recurring flag
- a dedicated spend domain for household obligations
- budget category integration for household-bill style spending
- a budget-page Household Obligations panel
- analytics support for:
  - recurring vs one-off obligation totals
  - provider-level totals
  - monthly obligation trend views
- a Bills-page recurring-obligations section with month picker
- derived recurring-obligation grouping from bill history
- provider-name normalization to reduce duplicate rows caused by OCR / casing variation
- combined-provider metadata support where bill services can already be represented as multiple service types while preserving the primary provider-type field for compatibility

What is still missing from a full recurring-bill planning system:

- canonical provider records
- canonical service-line records
- a deterministic obligation/planning month model that is visible everywhere
- explicit paid vs bill-received lifecycle
- predicted future obligation slots
- estimated / missing / overdue logic that is reliable
- Gemini extraction designed specifically for household-bill automation
- multi-service bill allocation and reconciliation

## 2. What We Should Adopt From The External Plan

The external plan is directionally strong. We should adopt these ideas:

### A. Keep receipts as the source document

We should not build a separate bills app or parallel data-entry system.

The uploaded or manually entered household bill receipt remains the source artifact. Planning should be layered on top of receipts rather than replacing them.

### B. Separate provider identity from service obligation

This is the most important architectural improvement.

We should distinguish:
- `Provider`
  - the company, such as Citizens Energy Group
- `Service Line`
  - the recurring obligation under that provider, such as water, sewer, gas, internet, or insurance_auto

This solves the current limitation where one provider can appear to mean multiple different obligations.

### C. Use deterministic planning-month logic

We should derive a single `planning_month` for each bill.

Recommended default:
- use the bill's `due_date` month

Fallbacks:
- `service_period_end` month
- then receipt / statement date month

This matches the practical budgeting question the user actually cares about:
- "which month do I need money available for this bill?"

### D. Keep Gemini focused on raw document facts

Gemini should extract:
- provider name
- account number / account label hints
- service address if visible
- statement date
- due date
- service period start/end
- total amount due
- fees / taxes / prior balance if visible
- likely service type(s)

The app should derive:
- provider match or create flow
- service-line association
- planning month
- lifecycle status
- estimate vs actual behavior
- duplicate detection
- obligation-slot fill behavior

This split is correct because it keeps business rules deterministic and re-runnable after user edits.

### E. Add a bill / obligation lifecycle

The statuses proposed in the external plan are useful:
- `Paid`
- `Upcoming`
- `Overdue`
- `Estimated`
- `Missing`
- `Not Yet Entered`

We should adopt those, but only after clarifying what "paid" means in our system.

## 3. Where The External Plan Needs Refinement

Before implementation, we should tighten four areas.

### A. "Bill uploaded" is not the same as "bill paid"

Today, the app can store a bill receipt. That only proves:
- the bill exists
- the amount and dates are known

It does not prove payment happened.

We should model these separately:
- bill received
- payment confirmed

Recommended rule:
- if the bill exists and due date is in the future:
  - status = `Upcoming`
- if the bill exists, due date passed, and no payment confirmation is recorded:
  - status = `Overdue`
- if payment date is recorded or a confirmation-type workflow is used:
  - status = `Paid`

### B. Monthly obligation slots should be generated, not edited directly

If we introduce `monthly_obligation_slots`, it should be a projection / planning table, not a user-maintained source of truth.

It should be regenerated from:
- service lines
- recurring rules
- uploaded bill receipts
- payment state

That keeps the system auditable and reduces drift.

### C. Multi-service provider support should evolve in two layers

We already have compatibility-oriented multi-service metadata. The next clean step should be:

1. canonical provider
2. canonical service line
3. optional multi-link bill-to-service allocation later

We should avoid jumping directly into full amount allocation before service-line identity is stable.

### D. We should track four different month concepts explicitly

To avoid confusion later, we should consistently reason about:

- `statement_month`
- `service_month`
- `planning_month`
- `paid_month`

For budget and obligation views, `planning_month` should be the main month surfaced to the user.

## 4. Recommended Product Model For This Codebase

This is the model we should use going forward.

### Core entities

#### Provider
- normalized company identity
- one row per provider
- examples:
  - AES Indiana
  - Citizens Energy Group
  - Comcast
  - State Farm

#### Service Line
- one recurring obligation under a provider
- examples:
  - AES Indiana / electricity
  - Citizens Energy Group / water
  - Citizens Energy Group / sewer
  - Citizens Energy Group / gas
  - State Farm / insurance_auto

#### Bill Receipt
- uploaded or manual receipt/bill record
- already exists in the receipt system
- should eventually point to one primary service line
- may later support multiple service-line allocations

#### Monthly Obligation Slot
- generated planning cell for a service line and month
- may be:
  - filled by an actual bill
  - estimated from history
  - still upcoming
  - missing
  - overdue

## 5. What Already Exists Versus What Still Needs To Be Built

### Already present

- household-bill receipt intake
- bill metadata editing
- recurring-flag capture
- provider-style grouping in analytics and recurring views
- obligation-category summaries
- month-based recurring-obligation display

### Needs to be built

#### Foundation
- canonical `providers`
- canonical `service_lines`
- bill-to-service-line linking
- explicit `planning_month`

#### Statusing
- explicit bill lifecycle
- explicit payment confirmation model
- paid vs upcoming vs overdue rules

#### Forecasting
- generated monthly obligation slots
- expected future recurring obligations
- estimated amount calculation
- missing-bill detection

#### Extraction automation
- dedicated Gemini extraction contract for bills
- confidence handling
- provider matching suggestions
- service-line suggestions

## 6. Consolidated Phase Plan

This is the phased path I recommend for `LocalOCR_Extended`.

### Phase 1 — Canonical Provider / Service-Line Foundation

Goal:
- move from text-only provider grouping to canonical provider and service-line identity

Scope:
- add `providers`
- add `service_lines`
- backfill current household-bill metadata into those records where possible
- keep existing fields for compatibility during migration
- expose provider + service-line linking in bill edit flow

Deliverables:
- one provider can own multiple service lines
- provider and service-line matching survives OCR variation
- groundwork exists for forecasting

### Phase 2 — Planning Month Derivation

Goal:
- make every relevant bill resolve to a deterministic planning month

Scope:
- add `planning_month`
- add rule source display:
  - "Based on due date"
  - "Based on service end"
  - "Based on statement date"
- recompute planning month on bill edits

Default rule:
- due date month
- fallback to service period end month
- fallback to statement/receipt month

### Phase 3 — Bill Lifecycle And Paid-State Model

Goal:
- distinguish bill existence from payment state

Scope:
- add status model:
  - `Upcoming`
  - `Overdue`
  - `Paid`
  - `Estimated`
  - `Missing`
  - `Not Yet Entered`
- add `paid_date`
- optionally add `paid_amount`
- add a clear user action to confirm payment

Important:
- merely uploading a bill must not automatically mean `Paid`

### Phase 4 — Generated Monthly Obligation Slots

Goal:
- turn recurring bills into a predictable monthly planning surface

Scope:
- generate monthly obligation slots per active service line
- fill slot from actual bill when available
- otherwise surface as future / estimated / missing based on timing rules
- expose slots in recurring-obligations and budget views

### Phase 5 — Gemini Extraction Contract For Household Bills

Goal:
- automate household-bill entry as much as possible without hiding logic

Scope:
- define extraction schema for:
  - provider
  - service type
  - account identifiers
  - statement date
  - due date
  - service period
  - total / fees
  - likely recurrence
- store extraction payload
- show confidence and allow correction
- rerun deterministic derivation after edits

### Phase 6 — Estimation, Missing Detection, And Alerts

Goal:
- predict expected recurring bills and show what has not yet arrived

Scope:
- rolling-history estimate per service line
- anomaly flagging for unusual amount jumps
- missing-bill logic
- overdue dashboard surfacing

### Phase 7 — Multi-Service Bill Allocation

Goal:
- support one uploaded bill covering multiple services cleanly

Scope:
- optional bill-to-service-line junctions
- amount allocation UI
- service-level actuals from a shared provider bill

This should stay late in the sequence because it is meaningful but structurally more complex.

## 7. Implementation Guardrails

When we build this, we should preserve these rules:

- do not replace the existing receipt architecture
- do not remove current household-bill metadata during migration
- keep compatibility with current analytics and recurring-obligation views while the new model rolls in
- prefer additive migrations
- keep user correction simple and obvious
- keep planning logic deterministic in app code, not in Gemini prompts
- do not infer `Paid` unless there is actual supporting state

## 8. Recommended Immediate Next Build Order

If we start implementing from here, the next best build order is:

1. canonical providers
2. canonical service lines
3. planning-month derivation
4. paid-state / lifecycle model

That gives us the strongest foundation before we touch prediction.

## 9. Open Questions To Resolve Before Coding

These are the only design questions still worth explicitly confirming:

1. Should service-line `service_type` remain single-select while allowing a bill to touch multiple service lines later?
   - recommended answer: yes

2. Do we want payment confirmation to come from:
   - manual mark-paid
   - imported payment receipt
   - both
   - recommended answer: both

3. Should projected monthly obligation slots live as:
   - generated view only
   - or generated projection table
   - recommended answer: projection table derived from source records

## 10. Final Recommendation

We should adopt the external plan, but in a codebase-aware way:

- keep household bills inside the receipt system
- add canonical provider and service-line identity
- make `planning_month` first-class
- treat payment state separately from bill existence
- let Gemini extract facts, while the app computes planning behavior
- defer multi-service allocation until the provider/service foundation is stable

This gives us a realistic, incremental path to a true recurring-obligations system without rewriting what already works.
