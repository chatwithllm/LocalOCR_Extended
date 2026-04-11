# CONTINUITY.md — LocalOCR Extended Restart Guide

> Read this first when resuming work in `LocalOCR Extended`.

## 1. What This Repo Is

`LocalOCR Extended` is the experimental successor to the stable grocery app.

Relationship to the stable repo:

- stable grocery repo stays the clean production fallback
- Extended is where restaurant and broader modular work will happen
- Extended starts from the working grocery baseline and preserves git ancestry for selective merge-back later

## 2. Parallel Runtime Baseline

The current intended operating model is side-by-side local deployment:

- grocery app on `8080`
- Extended on `8090`

Extended defaults:

- service name: `localocr-extended-backend`
- database: `sqlite:////data/db/localocr_extended.db`
- receipt storage: `/data/receipts`
- backups: `/data/backups`
- backup prefix: `localocr_extended`
- MQTT client id: `localocr-extended`
- MQTT topic prefix: `home/localocr_extended`
- Home Assistant discovery ids derived from `APP_SLUG=localocr_extended`

Shared infrastructure defaults:

- Ollama reused from the grocery stack via `host.docker.internal:11434`
- MQTT reused from the grocery stack via `host.docker.internal:1883`

Extended can also start its own optional `local-infra` profile for MQTT and Ollama, but the default assumption is shared services plus isolated app state.

## 3. Why This Matters

This split gives you a clean safety net:

- if Extended works, it can become the future deployment
- if Extended is abandoned, grocery remains intact
- no rollback on the grocery repo is required

## 4. Completed / Verified

- Dockerfile default port changed to `8090`
- compose backend now binds `8090:8090`
- Extended has its own container, volume, and backup naming
- compose backend resolves `host.docker.internal` for shared-service access
- MQTT topics are now prefixed from `MQTT_TOPIC_PREFIX`
- Home Assistant discovery identifiers are now derived from `APP_SLUG`
- `/health` now returns the env-driven Extended service name
- receipt image storage helper now respects `RECEIPTS_DIR`
- backup and restore scripts now use env-driven DB path, receipts path, and backup prefix
- operator docs now describe parallel local deployment explicitly
- receipt OCR fallback no longer incorrectly marks successful Ollama runs as failed
- image orientation is normalized before OCR for landscape phone photos
- upload now supports explicit receipt intent:
  - auto
  - grocery
  - restaurant
  - general expense
- receipt detail now supports structured editing for:
  - receipt type
  - store
  - date/time
  - subtotal/tax/tip/total
  - line items
- receipt detail now also supports:
  - rotate left/right
  - mark as restaurant
  - safer re-run OCR on already-processed receipts
- restaurant-first OCR now runs a multi-candidate assist for hard restaurant photos
  - compares rotated candidates
  - scores them using restaurant signals like totals, store/date quality, and line-item quality
  - prefills review with the strongest candidate automatically
- processed receipts can now be rebuilt safely from corrected review data
- first restaurant receipt was manually corrected through the new review path and now persists as `domain=restaurant`
- general-expense receipts now persist as `domain=general_expense`
- general-expense receipts do not create inventory or catalog side effects
- Extended now includes an `Expenses` workspace with:
  - expense budget card
  - merchant summary
  - category breakdown
  - recent expense receipts
  - selected receipt detail
- OCR placeholder/template echoes are now treated as invalid instead of looking like a real processed receipt
- upload status now reflects `review` vs `processed` truthfully after upload
- placeholder session/bootstrap secrets are now rejected instead of being trusted silently
- seasonal recommendation date math now tolerates mixed naive/aware timestamps
- placeholder OCR junk receipts/products copied into Extended were cleaned out without touching valid grocery history
- signed-out visitors now get a meaningful read-only demo mode with realistic sample data across dashboard, grocery, restaurant, expenses, receipts, and contribution views
- shopping and inventory mobile surfaces were then compacted further:
  - shopping summary strip now uses `Open / Estimate / Close`
  - Quick Find and Recommendations moved behind header toggles
  - Open and Close summary pills now act as remembered Current List filters
  - Current List now uses lighter inline controls and compact expandable rows
  - inventory add/search/sort clutter was reduced on phones
  - inventory mobile rows now expand on demand instead of showing every action at once
- inventory and products now share the same workspace shell instead of feeling like separate pages
- inventory/product search and category toggles now work on larger screens too, not just mobile
- grouped inventory rows now prefer the current primary location in the summary instead of falling back to `Mixed`
- inventory location actions now display the actual current place, for example `📍 Pantry`, and the picker supports both preset and custom locations
- inventory manual-add now supports smart no-result fallback from search plus optional progressive details
- mobile inventory now hides helper copy and keeps search/categories behind a page-header magnifier until needed
- mobile dashboard now trims explanatory copy, compresses grocery stats into two compact cards, and uses a long-press top-three ranking reveal
- desktop sidebar can now be hidden on larger screens and remembered across refreshes
- household-style display names are now used across recommendations, low-stock, shopping, and inventory
- duplicate household items in inventory are now grouped in the display layer so the list reads as unique household needs instead of repeated package variants
- product rename now uses an in-app text modal instead of browser-native prompt
- login password now supports an eye toggle and resets to hidden after successful sign-in
- trusted-device pairing Phase 1 is now stable on the feature branch:
- trusted-device pairing Phase 2 polish is now layered on top:
  - QR scan works end to end when started from a fresh pairing session
  - device can start a short-lived pairing QR session
  - admin can approve or reject from the scanned link flow
  - approved shared screens now authenticate with a trusted-device token instead of relying only on fragile browser sessions
  - paired fridge/tablet screens stay signed in across refresh
  - trusted devices can be listed, renamed, rescoped, and revoked in Settings
  - Settings now shows:
    - linked user
    - created by
    - relative last seen
    - clearer scope descriptions
  - duplicate same-name pairings for the same linked user are consolidated on future approvals and revoked together
  - stale trusted-device tokens are now ignored for admin QR-approval login/approve/reject flows so the scan browser can authenticate cleanly as admin
  - expired or revoked scanned pairing links now prefer a single inline terminal state instead of leaving a stale approval modal fighting the page
  - revoke-vs-approve timestamp comparisons now use real UTC datetime comparison instead of SQLite string ordering, so fresh QR approvals are not falsely rejected as stale
- Settings user edit/reset password flows now use in-app modals instead of browser-native prompts
- Budget now supports manual entry creation for:
  - grocery
  - restaurant
  - general expense
- manual entries create real purchase + manual receipt history so budget and analytics stay accurate even when the image is missing
- budget updates are now enforced as admin-only on the backend and disabled in the frontend for non-admin users
- trusted-device management remains environment-specific unless multiple hosts share the same backend/database
- trusted-device pairing now supports explicit linked-user selection during admin approval, so a fridge/tablet can be paired to a lower-privilege household user instead of silently inheriting the approving admin account
- Settings now shows session auth source more clearly:
  - browser session
  - trusted device
  - API token
- trusted-device sessions are now bound to trusted-device auth and no longer silently degrade into a normal browser session after revoke
- trusted-device revoke now removes matching cards from Settings immediately with a quick exit animation instead of waiting for a full page refresh
- trusted-device scopes now affect runtime in the main app flow:
  - `Read Only` blocks the main mutating inventory, shopping, product, receipt, and budget actions in both frontend and backend
  - `Kitchen Display` now defaults to a tighter dashboard/shopping/inventory navigation set instead of exposing the full admin-heavy workspace shell
- legacy absolute receipt image paths from earlier local-machine runs can now be remapped into the current `/data/receipts` container root when the underlying file still exists there
- receipts mobile has now been compacted substantially:
  - receipt detail image uses a constrained mobile preview instead of overflowing the screen
  - filters are collapsed behind a header toggle on phones
  - `Purchases By Month` keeps a compact mobile bar graph plus lighter month summary text
  - mobile receipt lists now use compact two-row rows instead of desktop tables
  - extracted item cards and receipt edit line items now use tighter two-row mobile summaries
  - receipt edit metadata fields now use grouped mobile rows instead of a long single-column form
- quick-find and manual shopping entry have been cleaned up further:
  - duplicate manual-add CTAs were removed from Quick Find
  - manual shopping add now supports:
    - category dropdown
    - estimated price
    - quantity
    - note
  - manual shopping add now creates a real product when no matching catalog item exists, so future Quick Find and Products searches can find it
  - manual shopping estimate fallback now uses the saved manual estimate when no price history exists yet
- shopping store-group headers now show richer summary context:
  - store name
  - store-group estimated total
  - grouped item count
- dashboard summary stat routing is now explicit:
  - `Low` opens the low-stock inventory view
  - `INV` opens the Inventory workspace
  - `PROD` opens the Products workspace
- dashboard summary cards were tightened further:
  - recommendation tile label is now `Top Picks`
  - shopping summary tile uses the compact `Shopping List | count | estimate` pattern
  - low stock / top picks / shopping tiles now expand more safely on mobile instead of squeezing content into half-width cards
- shopping naming and recommendation behavior is now more buyer-friendly:
  - shopping rows prefer the explicit renamed/display name instead of awkward shortened family labels
  - expanded shopping rows can show the fuller/original product name as muted context when it differs from the shopper-facing short name
  - recommendation-backed items fall out of active `Top Picks` after they are added to shopping and confirmed, allowing the next best item to surface
- shopping list row interactions were refined:
  - web and mobile recommendation cards were compacted and cleaned up
  - web and mobile shopping rows now support:
    - inline preferred-store updates
    - inline unit / size-label updates
    - inline unit-price updates
    - direct rename from the shopping workflow
  - swipe-right on mobile now marks an item bought and shows a short undo countdown
  - action rows were simplified for usability:
    - visible actions now favor `-1`, `Bought`, and `More`
    - `More` now carries:
      - low / clear-low
      - out-of-stock / reopen
      - rename
      - delete
  - shopping rows now support explicit `out_of_stock` state in addition to `open` and `purchased`
  - shopping rows can now be renamed directly from the shopping workflow
  - compact store selection for shopping rows is now being used so store, unit, and size information fit more cleanly in expanded controls
- README now has a screenshots section backed by committed repo images
- future-enhancement planning docs now exist in-repo:
  - `future enhancements/multi household.md`
  - `future enhancements/budget domains.md`
  - `future enhancements/units and size labels.md`
- budgeting Phase 1 foundation is now implemented:
  - purchases now persist:
    - `default_spending_domain`
    - `default_budget_category`
  - receipt items now persist optional overrides:
    - `spending_domain`
    - `budget_category`
  - OCR/manual/edit receipt save paths now preserve these fields
  - schema migration backfills legacy purchases from the existing `domain` field so old grocery / restaurant / general expense history starts with meaningful defaults
- budgeting Phase 2 receipt review wiring is now implemented:
  - shared receipt editor now exposes:
    - receipt default spending domain
    - receipt default budget category
    - line-item spending-domain override
    - line-item budget-category override
  - line-item overrides support `Use receipt default`
  - editor helpers auto-fill budget categories from selected spending domains to reduce correction work on mixed receipts
- budgeting Phase 3 backend rollup foundation is now implemented:
  - effective line-item allocations are now calculated in backend helpers
  - receipt-level remainder between line subtotals and receipt total is allocated proportionally across effective buckets
  - additive endpoint now exists:
    - `/budget/allocation-summary`
  - current domain-based budget endpoints remain available for compatibility
- budgeting Phase 4 budget-page redesign is now implemented:
  - `Budget` now stores optional category targets via:
    - `budget_category`
    - storage keys like `category:grocery` in the legacy `domain` column for safe coexistence
  - new additive endpoint now exists:
    - `/budget/category-summary`
  - the main `Budget` page now edits monthly targets by budget category instead of by domain
  - the main `Budget` page now renders active and inactive category cards from effective line-item rollups
  - legacy budget consumers like Restaurant / Expenses / Grocery still work through the old domain endpoint, with category-target fallback where that mapping is meaningful
- budgeting follow-up UX/data work is now implemented on the feature branch:
  - saves now append to a real `budget_change_log`
  - the Budget page now shows:
    - compact active-category rows with collapsed summaries
    - expandable category details
    - current budget targets
    - budget change history
    - contributing receipt breakdowns when a category is expanded
  - inactive and zero categories are now grouped under `Other Categories`
  - `Set Monthly Budget`, `Current Budget Targets`, and `Budget Change History` now default to collapsed on mobile-first layouts
  - category target saves now preload the current saved amount back into the editor
  - repeated receipt updates now preserve the existing linked purchase instead of creating duplicate purchases
  - budget contribution rows now use real receipt/store/item naming instead of `Unknown` fallbacks
- budgeting receipt editor cleanup is now implemented:
  - visible `Default Spending Domain` was removed from the shared editor
  - `Default Budget Category` now reads simply as `Budget Category`
- units / size labels rollout is now substantially complete in the active workflows:
  - product catalog rows now expose editable default:
    - unit
    - size label
  - shopping rows now expose editable:
    - preferred store
    - unit
    - size label
    - price
  - product and shopping displays now use the richer unit/size metadata in buyer-facing summaries where available

## 5. Active Next Feature: Receipt Refunds

Branch now reserved for this work:

- `feature_receipt_refunds`

Why this feature matters:

- households sometimes return grocery, restaurant, pharmacy, or general-expense items
- today those receipts can only look like normal purchases, which makes:
  - budgets incorrect
  - analytics overstated
  - merchant/category reporting misleading

### Phase 1 Refund Scope

Phase 1 should treat refunds as a receipt-level transaction type, not as mixed purchase/refund line items.

Recommended model:

- keep existing receipt/spending domain:
  - grocery
  - restaurant
  - general expense
  - event
- add a separate purchase transaction flag:
  - `purchase`
  - `refund`

Phase 1 behavior:

- receipt editor can mark a receipt as `Refund`
- receipt list/detail clearly shows refund state
- budgeting rollups treat refund purchases as negative spend
- analytics totals/net spend treat refund purchases as negative spend
- refund receipts do not create inventory additions
- refund receipts do not act like normal shopping/recommendation purchases
- price-history writes should not blindly learn from refund values

Phase 1 intentionally does not include:

- mixed purchase + refund lines on the same receipt
- automatic inventory reversal/removal
- advanced refund-only analytics screens

### Implementation Notes For Phase 1

Backend:

- add `transaction_type` to `purchases`
- default existing rows to `purchase`
- preserve this field through:
  - OCR ingest
  - receipt rebuild/update
  - receipt detail serialization
- budget/allocation helpers should invert sign for refund purchases
- any spend-summary analytics that total purchases should also net refund rows

Frontend:

- receipt editor should expose:
  - `Transaction`
    - `Purchase`
    - `Refund`
- receipt rows/detail should display refund badge/state clearly
- refund totals should render meaningfully, ideally as a refund rather than looking like a broken normal purchase

Smoke-test target after Phase 1:

- mark one existing receipt as `Refund`
- verify:
  - receipt saves
  - receipt reopens with refund state preserved
  - monthly budget totals decrease appropriately
  - receipt/merchant views no longer overstate spend
  - line-item `Category` now reads as `Item Group`
  - visible line-item `Spending Domain` control was removed from the main editing flow
- unit/size-label enhancement is now implemented through Phase 2:
  - schema/runtime migration now supports:
    - `products.default_unit`
    - `products.default_size_label`
    - `receipt_items.unit`
    - `receipt_items.size_label`
    - `shopping_list_items.unit`
    - `shopping_list_items.size_label`
  - legacy receipt and shopping rows are backfilled to `unit = each`
  - receipt editor and manual entry now expose:
    - `Unit`
    - `Size Label`
  - payload serialization now preserves the new fields through receipt edits and shopping/manual flows
- receipts desktop inline workflow was refined further:
  - desktop Receipts now uses a single-column inline-detail mode instead of reserving the old dead right-hand pane
  - opened inline receipts now include a `Close Receipt` action inside the expanded shell
  - extracted-items rows are denser on web
  - the web receipt editor now uses a split action lane for `Remove` instead of treating it like a full data column
- refund Phase 2 presentation polish is now layered on top of the accounting foundation:
  - Budget category contribution rows now show an explicit refund/purchase badge
  - Restaurant recent-receipt cards now show refund state and signed totals instead of looking like normal visits
  - Expense recent-receipt cards now show refund state and signed totals
  - Expense selected-receipt detail now shows refund state and uses the signed total treatment consistently
- refund Phase 3 summary accuracy is now in progress on the branch:
  - restaurant and general-expense summaries now track:
    - purchase-count
    - refund-count
    - net spend
    - purchase-only average ticket
  - top restaurant / top merchant summaries now stop treating refunds as normal visits
  - budget status domain endpoints now expose:
    - purchase_count
    - refund_count
    - receipt_count
  - frontend summary cards now surface refund counts so users can tell the difference between real visits and return activity
- refund Phase 4 operational safeguards are now being layered in:
  - active inventory rebuild now nets grocery refund quantities back out instead of treating them like normal purchases
  - seasonal recommendation timing now ignores refund receipts so returns do not look like fresh restock activity
- refund Phase 5 editor/manual-entry UX is now being layered in:
  - manual receipt entry now supports explicit `Purchase` vs `Refund`
  - manual refund entry tells the user to enter positive amounts while the app handles the negative-spend treatment
  - the shared receipt editor now shows a refund-mode warning so refund side effects are explicit before saving
  - receipt image weight was reduced slightly so the editor gets more usable width

## 5. Pending / Needs More Work

Operational and product items that are not fully closed yet:

- trusted-device management still needs clearer separation between:
  - trusted-device access
  - normal browser sessions
  - API-token usage
- admin-side "log out all sessions" or "invalidate all browser sessions" does not exist yet
- trusted-device revoke currently removes trusted-device access, but it is still possible for a screen to remain logged in if it separately has a normal browser session
- trusted-device lifecycle needs one more cleanup pass around:
  - expired pairing-session cleanup
  - duplicate historical pairing-session pruning
  - more explicit live/device state in Settings
- trusted-device list behavior is only reliable when pairing, viewing, and revoking are done against the same host/runtime
- deployment/runtime notes should continue to assume:
  - domain and LAN host are different environments unless proven to share the same backend + DB
- some product surfaces still have remaining compactness/polish opportunities:
  - expanded inventory mobile actions
  - device-mode UI differences by scope
  - better read-only affordances
- receipt detail mobile can still benefit from a dedicated full-screen image viewer for long receipts instead of relying only on the shortened inline preview
- some older receipt rows can still reference image files that are no longer physically present in `/data/receipts`
  - those purchases still exist
  - the image cannot be recovered automatically without restoring the missing file from backup/source
- historical receipt images were restored once by copying legacy receipt files back into the live `/data/receipts` store
  - this fixed the current broken-image state
  - it also proved we still need a first-class full-environment backup/restore plan instead of ad-hoc file recovery
- the full-environment backup/restore system is now built, but it still needs one clean-machine drill to be considered production-closed:
  - backup bundle creation script exists
  - restore script exists
  - verification script exists
  - admin Settings UI now supports create / upload / download / verify / restore
  - fresh-machine bootstrap script now exists for first restore before the UI is available
  - bootstrap can now prompt for:
    - `PUBLIC_BASE_URL`
    - `GEMINI_API_KEY`
    - `GEMINI_MODEL`
    - `INITIAL_ADMIN_EMAIL`
  - backup manifests now carry:
    - user count
    - purchase count
    - receipt-row count
    - receipt file count
    - active trusted-device count
    - trusted-device row count
    - receipt bytes
    - DB fingerprint
    - UTC creation timestamp
  - backup cards now display timestamps in the viewer's local timezone instead of raw container-style UTC naming only
- trusted-device scope behavior is now only partially differentiated:
  - `Read Only` is enforced for the main write paths
  - `Kitchen Display` now has a lighter default shell
  - deeper page-level kiosk behavior still needs a follow-up pass
- restaurant and expenses have improved mobile compactness, but they still need one more convergence pass toward the shared Receipts review/edit experience instead of carrying bespoke receipt-detail shells
- the budgeting redesign is now partially implemented:
  - `budget domains.md` reflects the stronger model of:
    - `Spending Domain` for workflow defaults and overrides
    - `Budget Category` for meaningful household budgeting
  - Phases 1-4 are now in code:
    - schema foundations
    - receipt review/edit wiring
    - backend line-item rollups
    - category-based budget page and targets
  - still pending:
    - event naming/reporting
    - migration quality/cleanup passes
- the unit/size-label enhancement is now through Phase 2:
  - planning doc exists in `future enhancements/units and size labels.md`
  - implemented:
    - schema/runtime migration
    - receipt editor controls
    - manual-entry support
    - payload serialization
  - still pending for the unit/size stream:
    - shopping display formatting
    - product-level defaults in the UI

## 6. Planned Next

High-value next work from the current state:

- make trusted-device scopes affect runtime behavior:
  - deepen `Kitchen Display` beyond nav/default-page behavior into a more purpose-built fridge/tablet mode
  - expand `Read Only` affordances so mutating controls are visually disabled/hidden more consistently instead of only being blocked on click/request
- add a visible device-mode badge in the app shell so shared screens are obviously in device mode
- add admin-driven session invalidation for household users and shared screens
- add trusted-device home/default-route behavior, for example:
  - kiosk/dashboard-only
- continue reducing vertical clutter on mobile after row expansion
- keep strengthening structured edit flows so browser-native prompts disappear entirely
- finish validating the backup/restore workflow with a clean-machine restore drill:
  - run `bootstrap_from_backup.sh` on a clean machine or clean Docker host
  - verify the restored environment reaches healthy state without manual DB/receipt copying
  - confirm prompt-mode overrides for base URL and Gemini settings behave correctly
  - document the exact operator checklist from empty host to healthy app
  - optionally add a restore smoke-test checklist to the UI/reporting surface
- start phased budgeting implementation from the design now captured in `future enhancements/budget domains.md`:
  - Phase 5: event naming/reporting support
  - Phase 6: migration quality, recategorization helpers, and cleanup passes
- continue the unit-and-size enhancement from `future enhancements/units and size labels.md`:
  - Phase 3: shopping/product display updates that use those fields
## 7. What Still Belongs To Extended Next

Primary product direction:

- modular Grocery / Restaurant deployment choices
- general expense tracking for non-grocery, non-restaurant receipts
- restaurant receipt tracking with exact line items
- restaurant budget and analytics
- user-selectable combined vs separate presentation when multiple modules are enabled

Current restaurant workflow baseline:

- restaurant receipts can now be corrected after upload instead of being accepted as bad OCR
- corrected restaurant receipts stay out of grocery inventory logic when saved as `restaurant`
- restaurant-specific analytics/detail views can now be built on top of corrected structured receipt data
- restaurant OCR is now stronger for difficult phone photos before the user even opens review
- non-grocery, non-restaurant receipts now have a clean third lane instead of polluting grocery or restaurant
- general-expense line items can now be categorized for better spending analytics
- Restaurant workspace is now moving toward summary-first behavior:
  - dining budget card
  - recent restaurant receipt preview
  - top-ordered-item reporting
  - top-restaurant summary
  - receipt inspection/editing is increasingly handed off to the shared `Receipts` workspace instead of maintaining a second cramped receipt-inspector UI

Current rule:

- do not destabilize the stable grocery repo for this work
- new module and restaurant work should happen here

## 8. Resume Order

Read these in order:

1. [README.md](README.md)
2. [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
3. [PRD.md](PRD.md)
4. [docs/COMPLETE_PRODUCT_SPEC.md](docs/COMPLETE_PRODUCT_SPEC.md)
5. [docs/APP_SETUP_GUIDE.md](docs/APP_SETUP_GUIDE.md)
6. [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)
7. [docs/BACKUP_RESTORE_RUNBOOK.md](docs/BACKUP_RESTORE_RUNBOOK.md)

Then inspect:

- [docker-compose.yml](docker-compose.yml)
- [Dockerfile](Dockerfile)
- [src/backend/create_flask_application.py](src/backend/create_flask_application.py)
- [src/backend/setup_mqtt_connection.py](src/backend/setup_mqtt_connection.py)
- [scripts/backup_database_and_volumes.sh](scripts/backup_database_and_volumes.sh)
- [scripts/restore_from_backup.sh](scripts/restore_from_backup.sh)
- [scripts/verify_restored_environment.sh](scripts/verify_restored_environment.sh)
- [scripts/bootstrap_from_backup.sh](scripts/bootstrap_from_backup.sh)
- [src/backend/manage_environment_ops.py](src/backend/manage_environment_ops.py)
- [src/backend/publish_mqtt_events.py](src/backend/publish_mqtt_events.py)

## 9. Safety Rules

- keep grocery repo `main` as the stable baseline
- keep Extended changes additive and modular where possible
- if a feature is worth bringing back later, prefer cherry-picking focused commits instead of wholesale repo merging
- preserve separate MQTT identifiers and topic namespaces so Home Assistant can ingest both apps cleanly

## 10. Local Verification Targets

When resuming, verify:

```bash
curl http://localhost:8080/health
curl http://localhost:8090/health
```

Then confirm:

- grocery and Extended are both reachable
- their DBs differ
- their receipt storage differs
- their backups differ
- their MQTT namespaces differ
