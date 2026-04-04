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
- recommendation, shopping, low-stock, and inventory surfaces now use simplified household-style item names
- shopping page now has:
  - compact `Open / Estimate / Close` summary chips
  - header toggles for Quick Find and Recommendations
  - clickable `Open` / `Close` pills that now filter the current list and remember the selected view
  - a lighter Current List with inline sort chips
  - compact expandable mobile rows
- inventory page now has:
  - mobile-collapsible add form
  - magnifier-driven search/sort tools
  - compact expandable mobile rows
  - grouped display rows for duplicate household items
- rename flows now use an in-app text modal instead of browser-native prompt dialogs
- settings user edit and password reset now also use in-app modals instead of browser-native prompt dialogs
- login now supports a password eye toggle and always resets back to hidden after successful sign-in
- desktop users can now hide the left sidebar and keep that preference after refresh
- Budget page now supports manual entry creation for missing receipts:
  - grocery
  - restaurant
  - general expense
- manual entries now persist as real purchases plus `manual` receipt records, so:
  - budget totals stay accurate
  - analytics include the spend
  - receipts history can later delete the entry to remove the amount

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

- restaurant-specific analytics/detail polish beyond the current summary, budget, and receipt-detail baseline
- module selection UI/runtime behavior
- clean-machine validation of the full Extended stack
- broader docs refresh beyond the core operator/handoff/product files
- optional deeper backend deduplication/merge rules beyond the current grouped display behavior
- stronger receipt/source affordances around manual entries versus uploaded receipts

## Resume Priority

1. verify Extended boots on `8090`
2. verify it can run beside grocery on `8080`
3. verify MQTT and Home Assistant topics do not collide
4. continue restaurant/module architecture in this repo only
5. improve category autofill for general expenses and restaurant line-item editing speed
6. decide whether grouped inventory rows should remain display-only or evolve into true backend merge behavior
7. replace any remaining browser-native edit flows with the same in-app modal/sheet pattern
