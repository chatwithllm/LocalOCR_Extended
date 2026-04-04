# Complete Product Specification

> Purpose: this is the decision-grade specification for `LocalOCR Extended` as it exists today and as it should continue to evolve. It is written as a standalone product spec for the Extended app, not as a thin note about a grocery fork.

## 1. Product Summary

`LocalOCR Extended` is a household operating system for three kinds of receipt-driven behavior:

- grocery operations
- restaurant spend and repeat-order tracking
- general expense tracking

The app combines:

- OCR receipt ingestion
- structured review and correction
- household collaboration
- contribution scoring
- shopping coordination
- budget and analytics views
- guest/demo exploration before login

The product must work for:

- logged-in household members using real data
- admins managing users and reviewing catalog cleanup
- signed-out visitors exploring a realistic, read-only demo
- shared shopping helpers on mobile via QR links

## 2. Runtime and Deployment Contract

`LocalOCR Extended` must be safe to run beside the stable grocery deployment.

Required runtime defaults:

- grocery app remains on `8080`
- Extended runs on `8090`
- Extended uses separate DB, receipts, and backups
- Extended may share MQTT and Ollama infrastructure
- Extended must use distinct MQTT/Home Assistant identity values

Default environment contract:

- `FLASK_PORT=8090`
- `DATABASE_URL=sqlite:////data/db/localocr_extended.db`
- `RECEIPTS_DIR=/data/receipts`
- `BACKUP_DIR=/data/backups`
- `BACKUP_PREFIX=localocr_extended`
- `APP_SERVICE_NAME=localocr-extended-backend`
- `APP_DISPLAY_NAME=LocalOCR Extended`
- `APP_SLUG=localocr_extended`
- `MQTT_CLIENT_ID=localocr-extended`
- `MQTT_TOPIC_PREFIX=home/localocr_extended`

Security/runtime expectations:

- placeholder session/bootstrap secrets must not be silently trusted
- Extended must be deployable independently of the stable grocery app
- abandoning Extended later must not damage grocery data or grocery deployment

## 3. Product Domains

The product currently supports three operational receipt domains.

### Grocery

Grocery is the operational household supply workflow.

It includes:

- product catalog
- inventory tracking
- low-stock detection
- shopping list and helper QR
- grocery recommendations
- grocery analytics
- grocery budget

Grocery receipts may:

- create or update products
- affect inventory
- trigger low-stock logic
- influence recommendations
- feed shopping decisions

### Restaurant

Restaurant is the dining-out workflow.

It includes:

- restaurant receipt history
- exact line-item retention
- subtotal/tax/tip/total tracking
- structured restaurant correction after OCR
- repeat-order estimation
- restaurant budget
- dining analytics

Restaurant receipts must never:

- create grocery inventory
- create grocery products
- affect low-stock logic
- create grocery shopping recommendations

### General Expense

General Expense is the catch-all non-grocery, non-restaurant spend workflow.

Examples:

- Claire's ear piercing
- salon/spa
- gifts
- fees
- service receipts
- health/personal care purchases
- one-off retail receipts

General-expense receipts must:

- preserve merchant/date/totals
- preserve reference line items
- support category tagging
- contribute to budgets and analytics

General-expense receipts must never:

- create grocery inventory
- create grocery products
- create shopping recommendations
- affect restaurant analytics

All three domains must also support manual spend capture when the receipt image is unavailable.

## 4. Shared Core

The shared core spans all domains.

It includes:

- browser auth
- admin-managed household users
- guest demo mode
- receipt upload
- OCR orchestration
- receipt review
- local file storage
- receipts list/detail browsing
- contribution ledger
- optional Telegram ingestion
- optional MQTT/Home Assistant plumbing
- QR-based login/helper flows

Shared-core rules:

- receipt images/files remain available after review edits
- receipt detail must be human-editable without raw JSON editing
- receipts must always remain traceable even when extracted data is weak
- weak OCR must land in review rather than silently polluting downstream workflows

## 5. Authentication, Users, and Identity

The app supports:

- standard login/logout
- admin user creation and editing
- password reset flows
- profile/avatar editing

Authentication UX requirements:

- login password fields may expose an eye toggle for temporary visibility
- after successful login, password fields must clear and reset to hidden mode
- shared devices like a fridge tablet should support QR-based pairing without typing account credentials
- QR pairing must use a short-lived pairing session and require explicit admin approval before persistent access is granted
- once approved, the paired shared screen should authenticate with a durable trusted-device token so it survives refresh without depending only on browser-session cookies
- user-edit and password-reset flows should use in-app modal patterns instead of browser-native prompts where browser popups are unreliable
- compact mobile views should prefer action-first controls over explanatory text blocks

Identity presentation rules:

- users may have emoji avatars
- dashboard household ranking uses avatar identity heavily
- demo mode must use clearly fake fictional users

Current demo household style:

- superhero-style sample users
- no real household names or records exposed

Future expectation:

- emoji/avatar identity should remain unique enough within a household that compact mobile ranking can rely on avatar + score

## 6. Guest Demo Mode

Signed-out visitors must still understand the app.

Demo mode requirements:

- landing on the app while signed out shows a meaningful dashboard
- all demo data is seeded, local, and read-only
- no real household records may leak into demo mode
- upload/edit actions remain gated behind sign-in

Demo mode should cover:

- dashboard
- inventory/products
- shopping
- receipts
- restaurant
- expenses
- budget
- analytics
- contribution

Demo UX expectations:

- landing should be concise and approachable
- demo data should feel fun and intentional
- mobile dashboard should be compact and readable
- demo ranking should adapt to small screens

Current dashboard demo behavior:

- fictional household ranking
- themed low-stock and recommendation examples
- compact mobile ranking preview
- mobile stat cards in a 2x2 layout

Desktop workspace behavior:

- the left sidebar may be hidden on larger screens
- sidebar collapse state should be remembered across refreshes
- mobile hamburger behavior remains separate from desktop sidebar collapse

## 7. Receipt Intake

The upload entrypoint supports intent selection.

Current intent choices:

- `Auto`
- `Grocery`
- `Restaurant`
- `General Expense`

Intent rules:

- explicit user intent should bias OCR/classification
- `Auto` may classify across supported domains
- a user-chosen intent should reduce cleanup effort when they already know the receipt type

Upload workflow requirements:

- successful OCR should produce usable structured data
- weak OCR should go to review, not fail silently
- invalid placeholder OCR values should be rejected
- upload UI must report the real backend state:
  - `processed`
  - `review`
  - failure when truly failed

Manual entry workflow requirements:

- users must be able to create a manual entry when the receipt image is lost or unavailable
- manual entries must support:
  - grocery
  - restaurant
  - general expense
- manual entries must create real spend history, not UI-only placeholders
- manual entries must be deletable later so their amount can be removed from budget and analytics cleanly

## 8. OCR and Review

OCR provider behavior must be resilient.

Current supported behavior:

- OCR provider fallback chain
- placeholder-value rejection
- template-echo rejection from weak local OCR
- restaurant-aware prompt hints
- restaurant-specific rotated candidate comparison
- strongest restaurant candidate selected before review
- orientation normalization for hard receipt photos

Receipt review requirements:

- users can edit:
  - receipt type
  - store
  - date/time
  - subtotal/tax/tip/total
  - line items
- corrected receipts must rebuild purchase data cleanly
- already-processed receipts must not duplicate purchases during re-review

Quick review actions currently supported:

- rotate left
- rotate right
- mark as restaurant
- safe re-run OCR

Review/edit reliability rules:

- browser-native prompts should be avoided for important edit flows where Chrome/Safari may dismiss them unexpectedly
- in-app modal flows are preferred for rename, user edit, password reset, and similar structured edits

Review philosophy:

- structured correction, not raw JSON editing
- preserve receipt image linkage
- prefer human-trustworthy review over questionable automation

## 9. Grocery Workspace

Grocery operations include:

- merged Inventory / Products workspace
- toggle between inventory and products view
- shared search-first shell
- collapsible search and category controls
- category filters
- sort controls
- receipt traceability from inventory rows
- rename and recategorization flows
- normalized product naming

Inventory behavior:

- active inventory window
- low-stock detection
- manual low flagging
- storage locations
- quantity decrement
- receipt source lookup
- grouped household rows
- current location shown directly in row actions and summary snapshots
- no-result search path can open manual add instead of keeping add clutter always visible
- mobile inventory should keep search/category tools behind a single page-header magnifier until requested
- manual add supports progressive optional details:
  - category
  - unit
  - preferred store
  - add to shopping
- strong known-item matches may prefill manual-add defaults, but weak or ambiguous names should stay neutral

Products behavior:

- catalog-style cleanup
- direct rename/category tagging
- latest price/unit context where known
- uses the same shared workspace shell and mobile/desktop interaction model as Inventory

Category system currently includes examples like:

- produce
- dairy
- meat
- seafood
- bakery
- grains
- frozen
- beverages
- snacks
- household
- personal care
- apparel
- restaurant
- beauty
- health
- gift
- fees
- service
- retail
- general_expense
- other

## 10. Shopping Workflow

Shopping is a collaborative operational surface.

Current shopping behavior includes:

- current list
- quick find
- store grouping
- estimated total cost
- recommendation integration
- bought/reopen recovery flow
- mobile helper QR view
- simplified household-style item names instead of package-heavy labels

Shopping requirements:

- store preference can be attached to items
- shopping helper QR must expose scoped, shopping-only access
- helper view must support bought/reopen actions
- bought items must remain recoverable in both helper and full shopping views
- helper view must stay lightweight on phones

Shopping page behavior:

- collapsible sections
- section state remembered
- quick find first, manual add when needed
- helper page simplified for store-and-item execution
- shopping header now acts as a compact tool rail:
  - search icon reveals Quick Find
  - `✨ count` chip reveals recommendations
- top summary strip is compact:
  - Open
  - Estimate
  - Close
- Open and Close summary pills may act as list-view toggles and should remember the chosen view
- Current List is open-focused and visually lighter:
  - compact rows first
  - extra actions/details only when expanded
  - inline sort chips instead of heavier form controls
  - duplicate household items within a store should collapse into one display row with summed quantity and estimate
  - mobile expanded rows should allow store-preference updates without requiring the desktop table view
- closed items remain available in the Close view so `Reopen` can safely undo shopping-only test actions

## 11. Recommendations and Low-Stock

Recommendations and low-stock are collaborative workflows, not just static lists.

Current recommendation/low-stock behavior includes:

- low-stock signals from thresholds and manual flags
- dashboard quick actions
- shopping confirmation pathways
- floating vs finalized contribution scoring
- reversals when actions are undone before real validation

Dashboard behavior:

- low-stock and recommendations show action hints
- mobile dashboard should compress grocery overview into compact summary cards rather than repeating long explanatory text
- score implications use honest labels like:
  - pending
  - unlocks
  - +2

Budget behavior:

- dashboard budget cards should show the saved target amount in the label and current usage in the value
- only admins may change budget targets

Empty-state requirement:

- if low stock is empty, dashboard should use a compact zero-state instead of a large empty card

## 12. Restaurant Workspace

Restaurant is now a first-class workspace in Extended.

Current implemented behavior:

- restaurant receipt list/history
- dining spend summary
- visit count
- average ticket
- top restaurants
- top ordered items with average price
- selected receipt detail panel
- repeat-order estimate from a prior receipt
- dining budget card

Receipt detail should clearly show:

- store/restaurant
- address/location when available
- date/time
- subtotal
- tax
- tip
- total
- exact ordered items

Repeat-order planning expectation:

- restaurant line items are preserved for rough future cost estimation
- exact restaurant item names are more important than forcing grocery-like normalization

## 13. Expenses Workspace

Expenses is the general-expense workspace.

Current implemented behavior:

- spend summary
- top merchants
- average ticket
- category breakdown
- top reference items
- budget card
- selected receipt detail
- recent expense receipts

Expense category behavior:

- categories are human-meaningful
- they improve reporting rather than operational inventory

Examples of expense categories:

- beauty
- health
- gift
- fees
- service
- retail
- other

## 14. Budgets and Analytics

The product supports domain-aware spending visibility.

Current budget domains:

- grocery
- restaurant
- general_expense

Analytics expectations:

- grocery analytics exclude restaurant/general-expense behavior
- restaurant analytics exclude grocery inventory logic
- general-expense analytics focus on merchant/category/spend visibility

Current analytics surfaces include:

- spending by period
- domain-aware totals
- restaurant summary
- expense summary
- deals captured

## 15. Contribution and Household Collaboration

Contribution scoring is meant to reward meaningful household/system help.

Current contribution ideas in the product:

- receipts processed
- OCR cleanup
- meaningful inventory updates
- low-stock collaboration
- recommendation confirmations
- shopping follow-through

Scoring rules must remain fair:

- no-op edits do not score
- some points float until validated
- reversals should remove unearned points

Contribution UI expectations:

- show transparent scoring explanation
- show recent contribution history
- show ways to help right now

Dashboard ranking expectations:

- equal scores share rank
- top contributors are emphasized
- mobile collapsed ranking should be compact
- top 3 preview is acceptable in collapsed mode

## 16. Mobile Expectations

The app must be intentionally usable on phones.

Current and required mobile behaviors:

- mobile menu header
- compact collapsed household ranking preview
- responsive top stat cards
- inventory actions moved into tighter mobile-friendly layout
- helper QR shopping page simplified for touch use
- receipt review and shopping flows must remain readable without desktop assumptions
- shopping current list and recommendations should feel like lightweight execution feeds, not admin tables
- inventory should mirror shopping on mobile:
  - compact rows
  - expandable details
  - hidden search/sort until requested
  - add form collapsed by default when space is tight
- item naming should prefer household-readable names:
  - milk instead of brand-heavy milk labels
  - apples instead of size/store-heavy apple labels
- display-layer grouping is acceptable on mobile and list surfaces when it removes obvious duplicate household items

Mobile design rule:

- if a section does not earn its height, it should collapse or simplify

## 17. QR and Shared Access

Current QR behaviors:

- hidden QR access triggered by long-press on brand text
- login QR for same-user device sign-in
- shopping helper QR for scoped shopping access
- trusted-device pairing and management now support:
  - device can request a short-lived pairing QR
  - admin can approve or reject the pending pairing from the scanned-link flow
  - approved device now keeps a trusted-device token locally and authenticates through that token on future requests
  - trusted devices can be listed, renamed, rescoped, and revoked in Settings
  - Settings should surface:
    - device name
    - scope
    - linked user
    - created by
    - relative last seen
  - duplicate same-name pairings for the same linked user should be consolidated instead of growing indefinitely

QR safety requirements:

- helper links must be scoped
- helper links must not expose full app capabilities
- login links should be short-lived and safer than password sharing
- trusted-device pairing QR must carry only a short-lived pairing session, never the persistent device credential itself
- persistent trusted-device credentials must only be issued after admin approval and must remain revocable from Settings

## 18. Operational Hardening

Extended must remain resilient in production-like use.

Hardening expectations already addressed:

- invalid placeholder secrets should not be trusted
- placeholder OCR scaffolding values should not persist as valid purchases
- timezone issues in recommendation date logic should not break recommendations
- known junk OCR imports should be removable without harming valid imported history

Operational expectation:

- code changes are versioned in git
- live data cleanup may happen in runtime DB when needed
- local secrets remain uncommitted
- trusted-device state is host/environment specific unless multiple hosts share the same backend/database

## 19. Current Branch Workflow

For Extended feature work before landing on `main`:

1. commit to a feature branch with a clear comment
2. update docs when behavior/scope/setup changes
3. state the best next enhancement after the push
4. ask for merge to `main`

## 20. Near-Term Product Priorities

The most likely next-value areas after the current state are:

- merchant/category memory for general expenses
- unique household emoji identity enforcement
- additional restaurant review speed improvements
- cleaner empty/compact dashboard states on mobile
- deploy-time module selection and future combined/separate presentation

## 21. Non-Negotiable Rules

- grocery, restaurant, and general expense must remain distinct domains
- restaurant and general-expense receipts must never pollute grocery inventory
- demo mode must never expose real household data
- weak OCR must go to review instead of silently creating junk
- Extended must remain safe to run beside the stable grocery app
