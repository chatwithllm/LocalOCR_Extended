# LocalOCR Extended — Recurring Bills & Utilities Enhancement Plan

---

## 1. Current-State Summary

The system is a functional receipt capture and review platform supporting five receipt types (Grocery, Restaurant, General Expense, Event, Unknown), two transaction types (Purchase/Refund), and four intake methods. It has a mature review/edit workflow covering all major receipt fields, line items, and budget allocation. Downstream behavior is already differentiated by receipt type — grocery receipts feed inventory and price history, restaurant receipts feed dining analytics, and general expense receipts feed expense tracking. Refunds are properly handled across budgets and analytics. The system is intentionally evolving from grocery-first toward a broader household planning platform, which is what motivates this enhancement.

The core gap: recurring household bills (rent, utilities, insurance, subscriptions) have no natural home. They get absorbed into General Expense, which conflates one-time discretionary spending with fixed predictable obligations — making budget forecasting and recurring-obligations visibility nearly impossible.

---

## 2. Recommended Model

### Receipt Type Strategy

Introduce **one new receipt type: `Household Bill`**.

Do not create separate receipt types for each bill category (electricity, rent, insurance, etc.). That would balloon the type list and create maintenance overhead. Instead, `Household Bill` becomes a single receipt type with an internal **bill category** that carries the semantic distinction.

The full receipt type list becomes:

| Type | Status |
|---|---|
| Grocery | Existing |
| Restaurant | Existing |
| General Expense | Existing |
| **Household Bill** | **New** |
| Event | Existing |
| Unknown | Existing |

This preserves all existing types exactly. `Household Bill` is intentionally distinct from `General Expense` because the downstream planning behavior is fundamentally different: bills are recurring, often fixed or predictable, tied to a provider and billing period, and need to surface in forecasting. General Expense remains for one-off discretionary or work-related purchases.

### Spending Domain Strategy

Introduce a new top-level spending domain: **`Household Obligations`**.

Existing domains (Grocery, Dining, General) remain unchanged. `Household Obligations` becomes a first-class domain that budget and analytics pages can query independently. Within it, introduce **domain subcategories** that organize bill types meaningfully:

| Subcategory | Examples |
|---|---|
| Utilities | Electricity, water, gas, sewage, trash, internet, phone |
| Housing | Rent, mortgage, HOA |
| Insurance | Home, auto, health, life premiums |
| Childcare & Education | Daycare, tuition, tutoring |
| Subscriptions & Memberships | Gym, streaming, software, club dues |
| Other Recurring | Catch-all for bills that don't fit above |

This structure answers real planning questions ("how much do I spend on utilities vs. housing costs?") without polluting the grocery or general expense domains.

### Budget Category Strategy

Budget categories under `Household Obligations` should mirror the domain subcategories above, but remain user-adjustable at review time (same pattern as existing budget allocation). The budget system should support both:

- **Fixed budget targets** — user declares an expected monthly amount (e.g., rent is always $1,800)
- **Variable tracking** — user tracks actuals for variable bills (e.g., electricity varies seasonally)

This distinction between fixed and variable is new and meaningful. It enables the forecasting goal: "what do I already know this month will cost, before I've paid it?"

### Recurring Bill Modeling Strategy

Recurring bills should be modeled as a **property of the receipt/bill record**, not as a separate object type. Specifically, a `Household Bill` receipt gains a set of bill-specific fields (detailed in Section 5) that enable recurrence tracking. The system does not need a full subscription management engine in Phase 1. What it needs is:

1. The ability to mark a bill as recurring and capture its cadence
2. The ability to link a new receipt to a known recurring obligation (provider + bill type)
3. The ability to surface expected-vs-actual on the budget page

A lightweight "known recurring obligations" list can be derived from past `Household Bill` receipts where `is_recurring = true`, rather than requiring a separate obligations table at first. This keeps the data model additive rather than requiring a parallel system.

---

## 3. Alternatives Considered

### Alternative A: Subtype under General Expense

Add a `bill_subtype` field to General Expense receipts to distinguish recurring bills. Simple to implement, but fundamentally wrong for the long-term goal. General Expense would carry two very different behavioral intents (one-time spending vs. recurring obligations), making it impossible to give each its own analytics treatment, budget behavior, or UI without ugly conditional logic everywhere. This is the "rename General Expense and call it done" path — explicitly ruled out in the problem statement.

### Alternative B: One receipt type per bill category

Create separate types for Utilities, Housing, Insurance, Subscriptions, etc. This gives maximum semantic clarity per type but creates an explosion of receipt types (8–10+), complicates the intake picker, and doesn't actually need type-level separation since the bill category field inside `Household Bill` carries that meaning. The review and budget pages would also need to handle each type individually.

### Alternative C: A fully separate recurring obligations module

Build a stand-alone bill-management system (like a bills calendar or subscription tracker) entirely separate from the receipt flow. This could be powerful eventually, but it is the wrong Phase 1 choice because it creates a parallel data model that must eventually reconcile with receipts anyway. It also abandons the existing receipt intake infrastructure that already handles image upload, OCR, PDF, and manual entry — all of which are directly applicable to bill receipts. Start with receipts; a dedicated obligations view can be a later layer on top.

### Alternative D: Spending domain only, no new receipt type

Keep receipt types as-is, but add `Household Obligations` as a new spending domain that General Expense receipts can be assigned to. This is superficially appealing but leaves all the bill-specific fields (billing period, provider, due date, recurrence) with no natural home. The review form would need awkward conditional fields inside General Expense, and analytics could not cleanly separate bills from discretionary spending by type.

---

## 4. User Flow Proposal

### Upload Flow

The upload screen adds `Household Bill` to the intent picker alongside Grocery, Restaurant, General Expense, and Auto. If the user selects `Household Bill`, the OCR/review form that follows shows the bill-specific field set rather than the grocery or restaurant field set. If Auto is selected and the OCR result suggests a utility or bill, the system proposes `Household Bill` as the inferred type, which the user can accept or change.

### OCR / Review Flow

After OCR on a `Household Bill`, the review screen presents:

- **Standard fields:** store/provider name, date, total, tax
- **Bill-specific fields:** bill category (dropdown from the subcategory list), billing period (start/end), due date, service account label, autopay indicator, recurring flag and cadence
- **Budget allocation:** domain pre-set to `Household Obligations`, subcategory selectable
- If OCR extracts a billing period or due date from the document, those fields are pre-filled and user-confirmable

The review screen should also offer a "link to existing recurring obligation" prompt if a bill from the same provider has been entered before. This is low-friction: *"We've seen a bill from Vectren Energy before — is this the same recurring bill? Yes / No."*

### Manual Entry Flow

Manual entry adds `Household Bill` as a receipt type option. The form mirrors the review screen above. Because many bills arrive as paper statements or emails rather than uploadable images, manual entry for bills is an important first-class path. The user fills in provider, bill category, period, total, and optionally marks it recurring.

### Budgeting Flow

The budget page gains a `Household Obligations` section. Within it, users can:

- Set a fixed monthly target per bill category (or per specific provider)
- See actuals from entered receipts vs. target
- See which recurring obligations have been entered for the current period and which are still outstanding
- View a simple "committed spend" number representing fixed obligations already known for the month

### Analytics Flow

The analytics page gains a `Household Obligations` domain view showing:

- Monthly totals by subcategory (utilities vs. housing vs. insurance, etc.)
- Trend over time per provider or category
- Variable vs. fixed split
- Year-over-year comparison for seasonal bills (e.g., electricity in summer vs. winter)

Existing Grocery, Dining, and General Expense analytics are completely unaffected.

### Correction of a Misclassified Bill

If a user entered an electricity bill as General Expense and later wants to reclassify it: the existing receipt type edit capability already supports changing receipt type. The system should, after the user changes type to `Household Bill`, prompt them to fill in the bill-specific fields that are now relevant (billing period, provider, etc.) without requiring them to re-enter anything already captured. The budget and analytics systems should reprocess that receipt under its new type on save.

---

## 5. Data Model Changes

### Required

| Field | Type | Notes |
|---|---|---|
| `receipt_type` enum value | `household_bill` | New value added to existing type enum |
| `bill_category` | string enum | Utilities, Housing, Insurance, Childcare & Education, Subscriptions & Memberships, Other Recurring. Required when type is `household_bill` |
| `bill_type` | string | Specific label within the category (electricity, water, rent, gym, etc.). Freeform or from a suggested list. Required when type is `household_bill` |
| `provider_name` | string | The biller/company name. Analogous to store name but semantically distinct for bills |
| `billing_period_start` | date | Start of the service period covered by the bill |
| `billing_period_end` | date | End of the service period covered by the bill |
| `is_recurring` | boolean | Marks this as a known recurring obligation |
| `household_obligations` domain value | — | New value added to existing spending domain enum |
| Budget subcategories | — | New subcategory group under `household_obligations` matching the bill_category list |

### Optional (useful but not blocking Phase 1)

| Field | Type | Notes |
|---|---|---|
| `due_date` | date | When payment is due, separate from the statement/receipt date |
| `autopay` | boolean | Whether payment is automated |
| `cadence` | enum | Monthly, quarterly, annually, irregular — meaningful for forecasting |
| `service_account_label` | string | User-defined label (e.g., "Main house electric", "Mom's phone line") — useful in multi-property or multi-account households |
| `statement_date` | date | Date the bill was issued, if different from receipt capture date |

### Future-Only (defer until recurring obligations module exists)

| Field | Type | Notes |
|---|---|---|
| `recurring_obligation_id` | foreign key | Links a bill receipt to a canonical recurring-obligation record |
| `expected_amount` | decimal | Known fixed amount for a recurring bill, enabling expected-vs-actual variance tracking per obligation |
| `payment_date` | date | Date payment was actually made — relevant once payment tracking is a goal |
| `billing_address` / `service_address` | string | For multi-property households |

---

## 6. UI / Page Changes

### Upload / Intake Screen
Add `Household Bill` to the intent type picker. Low-effort change; the picker already supports multiple types.

### OCR Review / Edit Screen
Add a conditional bill-specific field section that appears when receipt type is `household_bill`. This section shows `bill_category`, `bill_type`, `provider_name`, `billing_period_start/end`, `due_date`, `autopay`, `is_recurring`, and `cadence`. All other existing fields (date, total, tax, budget allocation) remain and behave identically. The conditional display pattern likely already exists in the codebase given that grocery-specific fields (line items, unit, size label) already differ from restaurant-specific fields.

### Manual Entry Form
Add `Household Bill` as a type option with the same conditional field section as the review screen.

### Budget Page
Add a `Household Obligations` budget section. Within it, allow per-subcategory and per-provider budget targets. Add a "committed this month" summary showing total from recurring bills already entered for the period. This is a new section; existing budget sections are untouched.

### Analytics Page
Add a `Household Obligations` analytics domain view. Charts for monthly trends, subcategory breakdown, and provider-level history. Existing domain views (Grocery, Dining, General) are untouched.

### Receipts List / Review Page
Add `Household Bill` as a filter option in the receipt type filter. No structural change needed beyond adding the new type to the filter list.

### New: Recurring Obligations Summary View *(Phase 2+)*
A dedicated page or section that lists known recurring obligations, their last-seen amounts, expected next billing dates, and whether they've been entered for the current period. This is not required in Phase 1 but is the natural home for the planning value the enhancement is targeting. It is built on top of existing `household_bill` receipts where `is_recurring = true` rather than requiring a new data store.

---

## 7. Phase Plan

### Phase 1 — Foundation: New Type, Fields, and Intake

**Goal:** Make it possible to correctly capture and classify a household bill without forcing it into General Expense.

**Scope:**
- Add `household_bill` receipt type
- Add bill-specific fields to the data model (required set only)
- Update the intake intent picker to include Household Bill
- Update the OCR review and manual entry forms with conditional bill-specific fields
- Add `household_obligations` spending domain
- Add bill subcategories to budget category options
- Add Household Bill to the receipts list filter

**Why first:** Everything else depends on having the data correctly captured. Analytics and forecasting are meaningless without clean data going in. This phase is also the lowest risk — it is purely additive, touches no existing receipt type logic, and introduces no breaking changes.

**Main risk:** OCR accuracy on utility bills. Utility bill layouts vary widely across providers. The billing period and due date fields may often need manual correction. The review step mitigates this, but user friction in correcting OCR output is real and should be monitored.

---

### Phase 2 — Budget Integration

**Goal:** Surface household obligations meaningfully on the budget page.

**Scope:**
- `Household Obligations` section on the budget page
- Per-subcategory budget targets
- Actuals-vs-target display for the domain
- "Committed this month" calculation from entered recurring bills
- Fixed vs. variable bill indicator in the budget view

**Why second:** Budget value is the primary stated goal of the enhancement. Once Phase 1 data exists, Phase 2 turns it into planning utility. This phase is also self-contained — it adds a new section to the budget page without touching existing budget sections.

**Main risk:** The definition of "committed this month" requires logic to identify which recurring bills have been entered for the current billing period and which are outstanding. This logic must handle cadence, billing period dates, and the fact that some bills arrive mid-month. Getting this right requires careful definition before implementation begins.

---

### Phase 3 — Analytics Integration

**Goal:** Make household bill trends visible and comparable over time.

**Scope:**
- `Household Obligations` domain view on the analytics page
- Monthly totals by subcategory and provider
- Trend charts per provider (e.g., electricity cost over 12 months)
- Variable vs. fixed split visualization
- Year-over-year comparison

**Why third:** Analytics require historical data to be meaningful. Running Phase 1 and 2 first allows several months of clean data to accumulate before the analytics view is valuable to users. Building analytics on a sparse dataset produces charts that look incomplete and may discourage adoption.

**Main risk:** If `provider_name` or `bill_type` was entered inconsistently in Phase 1 (e.g., "Vectren" vs. "Vectren Energy" vs. "VECTREN ENERGY DELIVERY"), provider-level trend charts will be fragmented. A light normalization or alias mechanism for provider names should be considered alongside this phase.

---

### Phase 4 — Recurring Obligations Module

**Goal:** Give users a proactive, forward-looking view of their recurring obligations — not just a history of what was entered.

**Scope:**
- Recurring Obligations summary view (new page or section)
- Derived "known obligations" list from past recurring bills
- Expected-vs-actual for the current period
- Outstanding obligations indicator ("Your internet bill hasn't been entered yet this month")
- Optional: `recurring_obligation_id` linking receipts to canonical obligations
- Optional: `expected_amount` for fixed-amount obligations

**Why fourth:** This is the most complex phase and depends on having sufficient historical data and stable data quality from Phases 1–3. It also introduces the closest thing to a new data concept (the canonical recurring obligation) that could require a schema change beyond additive fields. Deferring this keeps Phases 1–3 low-risk and ensures the foundation is solid before building the forecasting layer.

**Main risk:** This phase risks scope creep into full subscription management or bill payment tracking, which is out of scope for the current enhancement. Strict scope discipline is needed. The goal is visibility and planning, not payment orchestration.

### Phase 4 Follow-Through: Combined Providers

Some real-world providers issue a single statement that covers multiple services. Example: one provider may cover water, sewage, and gas on the same bill. That should not force the system to pretend there are multiple providers.

Recommended refinement:
- keep `Provider Name` as a single biller
- keep the existing single `Provider Type` as the primary compatibility field
- add `Service Types` as multi-select metadata for combined providers
- defer true amount-splitting across multiple services unless a later planning need proves it is worth the added complexity

This preserves compatibility with current budget logic while making combined-utility providers representable without data loss.

---

## 8. Backward Compatibility / Migration

**No existing data changes are required for Phase 1.** The new receipt type, fields, and spending domain are purely additive. Existing Grocery, Restaurant, General Expense, Event, and Unknown receipts continue to behave exactly as they do today. No migration script is needed.

**General Expense receipts that were previously used to capture bills** do not need to be automatically reclassified. The system should not attempt bulk reclassification of historical data — it cannot know which General Expense receipts represent utility bills without human review. Instead, the receipt type edit capability (which already exists) allows users to reclassify individual receipts when they choose. This should be surfaced as a gentle user prompt, not an automated migration.

**Budget and analytics calculations for existing domains** are unaffected. The `Household Obligations` domain is additive. No existing budget targets, category allocations, or analytics views change.

**The refund flow is unaffected.** If a user ever needs to enter a utility refund or billing credit, the existing refund transaction type applies to `Household Bill` receipts the same way it applies to other types. No special handling is needed.

**OCR field mappings** for existing receipt types should not be touched. The new bill-specific fields are only populated when the type is `household_bill`, so there is no risk of polluting existing receipt extraction logic.

---

## 9. Recommendation

**Build Phase 1 first, with deliberate restraint.**

The most important thing to get right is the data model and intake experience — specifically, the `Household Bill` receipt type, the bill-specific fields (billing period, provider, bill category, recurring flag), and the review/manual-entry form changes. This is unglamorous foundational work, but everything valuable downstream (forecasting, analytics, obligation tracking) is only as good as the data quality established here.

**Defer the Recurring Obligations Module (Phase 4) intentionally.** It is the most architecturally interesting part of the enhancement, which also makes it the most dangerous to rush. Build it only after several months of clean Phase 1 data demonstrates what the real patterns and pain points are. The temptation to design a full obligations engine up front should be resisted — the receipt-based model of Phase 1 and 2 will answer the majority of the stated planning questions and will reveal what Phase 4 actually needs to look like.

**Do not rename or split General Expense.** It is working correctly for its purpose. The right fix is giving bills their own home, not restructuring the bucket that everything else currently lives in.

The immediate deliverable that will make users feel the value of this enhancement is simple: a budget page that shows "here are your known household obligations for this month, and here is how much of that you've already accounted for." Phase 1 + Phase 2 together deliver that. That is the right first milestone.
