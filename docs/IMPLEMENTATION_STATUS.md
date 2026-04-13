# Implementation Status

## Current Snapshot

This repo now represents `LocalOCR Extended`, not the stable grocery deployment.

Inherited from the working grocery baseline:

- household login and admin user management
- receipt upload and OCR pipeline
- inventory and product cleanup tooling
- shopping list, helper QR flow, and contribution ledger
- MQTT/Home Assistant integration

Extended-specific runtime changes now in place:

- backend default port is `8090`
- health endpoint reports `localocr-extended-backend` by default
- Extended uses its own DB path, receipt storage path, and backup prefix
- Extended uses a distinct MQTT client id and topic namespace
- Home Assistant discovery identifiers are separated from the grocery app
- compose defaults are now designed for side-by-side local deployment
- restaurant receipt review/update flow is now available in receipt detail
- general-expense receipts now persist as their own spend domain
- signed-out users now land in a read-only demo mode with seeded sample data across the main workspaces
- shopping and inventory mobile surfaces have been significantly compacted for phone-first use

## Verified Working In Code/Config

- Dockerfile now exposes and health-checks `8090`
- compose backend binds `8090:8090`
- backend defaults no longer point at `grocery.db`
- receipt storage helper respects `RECEIPTS_DIR`
- backup/restore scripts no longer use grocery-specific names by default
- MQTT topics now derive from `MQTT_TOPIC_PREFIX`
- MQTT discovery identity now derives from `APP_SLUG`
- setup docs now describe running Extended beside the grocery app
- successful Ollama fallback is no longer overwritten as failed
- landscape receipt photos are normalized before OCR
- upload page now supports explicit receipt intent:
  - auto
  - grocery
  - restaurant
- receipt detail can now edit and resave:
  - receipt type
  - store
  - date/time
  - totals
  - line items
- receipt detail also includes fast restaurant review actions:
  - rotate left/right
  - mark as restaurant
  - safe re-run OCR for already-processed receipts
- restaurant-first OCR now includes multi-candidate assist for difficult phone photos:
  - rotated candidates are compared
  - restaurant hints are passed into OCR providers
  - the strongest restaurant draft is selected before review is shown
- existing processed receipts can be rebuilt from corrected structured payloads
- first restaurant receipt has been verified as a corrected `restaurant` purchase with exact line items
- general-expense receipts now:
  - save purchase totals without inventory side effects
  - keep reference line items in receipt review/detail
  - appear in a new `Expenses` workspace
  - support category tagging for richer expense analytics
- Restaurant page now includes:
  - monthly dining budget card
  - selected receipt breakdown
  - repeat-order estimate
  - inspect action from recent restaurant receipts
  - top ordered items with average price
- Expenses page now includes:
  - general-expense budget card
  - merchant summary
  - category breakdown
  - recent expense receipts
  - selected receipt detail
- upload flow now shows the real backend status (`review` vs `processed`) instead of treating every 200 response as processed
- Ollama prompt-template echo responses are now rejected as invalid OCR
- placeholder bootstrap/session secrets are now treated as invalid and no longer silently trusted in production-like configs
- seasonal recommendation date math now handles mixed timezone-aware and naive purchase timestamps correctly
- known placeholder OCR junk rows copied into Extended were removed without touching valid grocery-history imports
- demo mode now uses clearly fictional sample household data and compact dashboard previews
- dashboard mobile now trims explanatory copy, uses a top-three ranking surface with long-press reveal, and compresses grocery stats into compact summary cards
- recommendation, shopping, low-stock, and inventory surfaces now use simplified household-style item names
- shopping page now has:
  - compact `Open / Estimate / Close` summary chips
  - header toggles for Quick Find and Recommendations
  - clickable `Open` / `Close` pills that now filter the current list and remember the selected view
  - a lighter Current List with inline sort chips
  - compact expandable mobile rows
  - duplicate household items in Current List now collapse into one row with summed quantity and estimate
  - mobile expanded shopping rows now allow:
    - store updates
    - unit updates
    - size-label updates
    - price updates
  - current shopping actions now use a cleaner visible row plus overflow menu:
    - visible:
      - `-1`
      - `Bought`
      - `More`
    - overflow:
      - `Low`
      - `Out of Stock`
      - `Rename`
      - `Delete`
  - shopping rows now support `out_of_stock` state alongside `open` and `purchased`
  - swipe-right mobile bought flow includes undo feedback
- inventory page now has:
  - a shared Inventory / Products workspace shell
  - magnifier-driven search/sort tools that can now be collapsed on both desktop and mobile
  - category chips hidden behind a dedicated toggle on both desktop and mobile
  - a mobile page-header magnifier that reveals search/category tools only when needed
  - search-assist actions that let the user mark bought, flag low, add to cart, or fall back to manual add
  - manual add with optional progressive details:
    - category
    - unit chips
    - preferred store
    - add-to-shopping
  - smart add-form prefill for strong known-item matches
  - grouped household rows that now show the current primary location instead of generic `Mixed`
  - location edit actions that now display the current location directly and open a preset-or-custom picker
  - mobile-collapsible add form
  - compact expandable mobile rows
  - grouped display rows for duplicate household items
- rename flows now use an in-app text modal instead of browser-native prompt dialogs
- settings user edit and password reset now also use in-app modals instead of browser-native prompt dialogs
- login now supports a password eye toggle and always resets back to hidden after successful sign-in
- desktop users can now hide the left sidebar and keep that preference after refresh
- trusted-device pairing is now working with Phase 2 management polish:
  - QR scan works for fresh pairing sessions on the live host
  - anonymous device can start a short-lived pairing session
  - pairing QR can be scanned by an admin
  - admin can approve or reject the pending device
  - admin can now choose which household user the device should be linked to during approval
  - approved device now authenticates with a trusted-device token on every request
  - paired shared screens stay signed in across refresh
  - admins can list, rename, rescope, and revoke trusted devices from Settings
  - Settings now shows relative last-seen state plus linked-user and created-by metadata
  - Settings now also shows the current auth source for the active screen
  - same-name duplicate pairings for the same linked user are consolidated on future approvals and revoked together
  - trusted-device sessions are now bound to trusted-device auth instead of silently degrading into plain browser sessions after revoke
  - trusted-device cards now disappear immediately on revoke with a quick exit animation
  - scanned approval pages now clear stale revoked/expired messaging when a fresh pairing link is opened
  - admin QR approval flows now ignore any stale trusted-device token so browser admin login/approve/reject requests are evaluated against the real admin session
  - stale revoke checks during approval now use real UTC datetime comparison instead of SQLite string ordering
- receipts page now has a phone-first mobile layout:
  - constrained receipt-image preview that stays inside the screen width
  - collapsible filters behind a header toggle
  - compact `Purchases By Month` mobile graph + summary
  - compact two-row receipt rows for recent receipts and selected-month receipts
  - tighter extracted-item cards and receipt edit line-item cards
  - grouped mobile rows for receipt editor metadata fields
- live receipt assets were restored into `/data/receipts`, so DB-linked receipt images are currently available again on the running environment
  - trusted-device scopes now affect runtime:
    - `Read Only` blocks the main mutating inventory, shopping, product, receipt, and budget actions in both frontend and backend
    - `Kitchen Display` defaults to a lighter dashboard/shopping/inventory navigation set instead of the full workspace shell
- budgeting redesign is now substantially in place on the feature branch:
  - purchases persist:
    - `default_spending_domain`
    - `default_budget_category`
  - receipt items persist optional overrides:
    - `spending_domain`
    - `budget_category`
  - backend rollups now allocate by effective line-item category
  - `Budget` now uses category targets plus:
    - current targets
    - change history
    - contributing receipt breakdowns
  - repeated receipt updates now preserve the existing purchase instead of duplicating it
  - receipt-edit budgeting UI is simplified around:
    - `Receipt Type`
    - `Budget Category`
    - line-item `Item Group`
    - line-item `Budget Category`
- unit / size-label enhancement is now through Phase 2 on the feature branch:
  - schema/runtime migration support exists for product, receipt-item, and shopping-item unit metadata
  - legacy rows backfill to `unit = each`
  - receipt editor and manual entry now expose:
    - `Unit`
    - `Size Label`
  - product catalog now exposes editable product defaults for:
    - `default_unit`
    - `default_size_label`
  - shopping rows now expose inline edits for:
    - preferred store
    - unit
    - size label
    - price
  - shopping and product display layers now surface unit/size context in buyer-facing summaries where available
- product snapshot capture is now implemented on the current branch:
  - new `ProductSnapshot` persistence exists for shopping items, receipt items, purchases, stores, and optional product linkage
  - shopping rows now support:
    - `Add Photo`
    - `View Photo` after a snapshot exists
    - inline thumbnail preview of the latest saved photo
  - receipt extracted items now support:
    - `Add Photo`
    - `View Photo`
  - Settings now includes an admin snapshot review queue
  - a dedicated `/data/product_snapshots` Docker volume persists uploaded item images
- desktop Receipts inline review flow is now cleaner on the feature branch:
  - old dead right-hand detail column is removed during inline mode
  - inline receipts include an in-panel `Close Receipt` action
  - extracted items and the web receipt editor use denser row layouts and a separate remove-action lane
- full environment backup/restore is now implemented:
  - backup bundle creation script
  - restore script
  - verification script
  - fresh-machine bootstrap script
  - admin Settings UI for:
    - create backup
    - upload backup
    - download backup
    - verify environment
    - restore selected backup
  - backup manifests now include:
    - archive size
    - user count
    - purchase count
    - receipt-row count
    - receipt file count
    - active trusted-device count
    - total trusted-device row count
    - total receipt bytes
    - DB checksum/fingerprint
    - UTC creation timestamp
  - backup cards now render legacy timestamps in the browser's local timezone for clearer operator display
- Budget page now supports manual entry creation for missing receipts:
  - grocery
  - restaurant
  - general expense
- manual entries now persist as real purchases plus `manual` receipt records, so:
  - budget totals stay accurate
  - analytics include the spend
  - receipts history can later delete the entry to remove the amount
- budget target changes are now admin-only in both backend enforcement and frontend controls
- receipt image serving now remaps legacy absolute local-machine receipt paths into the current receipts root when the underlying file still exists there
- recurring bills / household obligations Phase 1 is now in progress on:
  - Phase 2 budget integration is now also active on the same branch
  - `codex/household-bills-phase1`
  - planning doc:
    - `future enhancements/localocr_extended_recurring_bills_plan.md`
  - current Phase 1 implementation now includes:
    - `Household Bill` intake intent on upload
    - manual entry type:
      - `🏠 Household Bill`
    - receipt editor type:
      - `🏠 Household Bill`
    - bill metadata capture and persistence:
      - provider name
      - provider type
      - account label
      - billing cycle month
      - service period start/end
      - due date
      - recurring flag
    - new spending-domain mapping:
      - `household_obligations`
    - new budget categories:
      - `utilities`
      - `other_recurring`
    - bill receipts can now validate and save without line items
    - bills analytics now include both:
      - legacy `utility` domain records
      - new `household_obligations` domain records
  - compatibility strategy:
    - legacy `utility_bill` values are still accepted by the backend
    - legacy `utility` spend domain normalizes into Household Obligations behavior
  - next verification step:
    - smoke-test upload, manual entry, receipt edit, receipts filtering, and bills analytics on local `8090`
  - current Phase 2 implementation now includes:
    - a dedicated `Household Obligations` panel on the Budget page
    - domain-level actuals-vs-target display for household bills
    - `Committed This Month` from entered recurring household bills
    - separation of recurring vs one-off household-bill spend
    - fast jump buttons from the Household Obligations panel into the detailed obligation budget categories
  - current Phase 3 analytics implementation now includes:
    - a dedicated Household Obligations view on the shared Analytics page
    - monthly obligation spend trends using the standard spending analytics feed
    - bill budget-category breakdown from household bill receipts
    - provider-level totals plus recent monthly trend chips
    - recurring vs one-off obligation totals surfaced inside Analytics
    - recent household bill activity embedded inside the analytics view
  - intentionally deferred to later phases:
    - missing / outstanding recurring-bill detection
    - canonical recurring-obligation records
    - expected-vs-actual for obligations not yet entered this month

## Intended Parallel Deployment Shape

- stable grocery app:
  - port `8080`
  - existing data untouched
- Extended:
  - port `8090`
  - `sqlite:////data/db/localocr_extended.db`
  - separate receipts and backups
  - shared MQTT and Ollama by default

## Planned Next Work

This is the repo where the following should happen next:

- restaurant receipt handling
- restaurant line-item expense history
- modular deployment options:
  - grocery only
  - restaurant only
  - all
- user-selectable combined vs separate grocery/restaurant presentation

## Not Yet Completed

- full admin invalidation of regular browser sessions across devices
- restaurant-specific analytics/detail polish beyond the current summary, budget, and receipt-detail baseline
- module selection UI/runtime behavior
- clean-machine validation of the full Extended stack
- broader docs refresh beyond the core operator/handoff/product files
- optional deeper backend deduplication/merge rules beyond the current grouped display behavior
- stronger receipt/source affordances around manual entries versus uploaded receipts
- AI-assisted extraction / suggestion from uploaded product photos
- product-level snapshot history UI beyond the latest-photo shortcut in shopping and receipt review
- recovery of receipt images that are physically missing from `/data/receipts`; those purchases still exist, but the image cannot be shown until the file is restored
- the backup/restore workflow still has one major validation gap:
  - clean-machine restore drill from backup to healthy app
  - final operator checklist validation on a truly new environment
  - explicit documented recovery steps for:
    - rotating environment secrets after restore
    - changing domain/base URL after restore
    - verifying restored receipt-file completeness before operators cut over traffic
- a dedicated operator runbook now exists for this area:
  - [BACKUP_RESTORE_RUNBOOK.md](BACKUP_RESTORE_RUNBOOK.md)
- trusted-device scope-specific runtime behavior:
  - deeper `Kitchen Display` kiosk behavior beyond the lighter default nav set
  - stronger `Read Only` visual affordances so controls look disabled/hidden before click
  - device-specific home pages / kiosk behavior

## Resume Priority

1. verify Extended boots on `8090`
2. verify it can run beside grocery on `8080`
3. verify MQTT and Home Assistant topics do not collide
4. continue restaurant/module architecture in this repo only
5. improve category autofill for general expenses and restaurant line-item editing speed
6. decide whether grouped inventory rows should remain display-only or evolve into true backend merge behavior
7. replace any remaining browser-native edit flows with the same in-app modal/sheet pattern
