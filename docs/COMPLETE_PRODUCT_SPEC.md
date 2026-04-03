# Complete Product Specification

> Purpose: this is the rebuild-grade specification for `LocalOCR Extended`. It inherits the working grocery baseline and defines how the Extended repo should evolve into a modular household receipts platform.

## 1. Product Summary

`LocalOCR Extended` is the experimental successor to the stable grocery app.

It must support:

- safe side-by-side deployment with the grocery app
- a shared receipt/OCR/auth core
- a working Grocery module inherited from the current baseline
- a future Restaurant module built in this repo
- a General Expense domain for non-grocery, non-restaurant receipts

Primary runtime defaults:

- Extended app on `8090`
- separate DB, receipts, and backups
- shared MQTT and Ollama by default
- isolated MQTT/Home Assistant identities

## 2. Parallel Deployment Contract

The Extended repo must be safe to run beside the stable grocery repo.

Required behavior:

- grocery app remains on `8080`
- Extended runs on `8090`
- Extended does not reuse grocery DB paths
- Extended does not reuse grocery backup names
- Extended does not reuse grocery MQTT client ids
- Extended does not reuse grocery MQTT topic prefixes
- Extended does not reuse grocery Home Assistant discovery identifiers

If Extended is abandoned later, the grocery deployment must remain unaffected.

## 3. Product Architecture

### Shared Core

- browser auth and household users
- receipt upload and OCR
- upload-time receipt intent selection
- review queue
- local file storage
- Telegram intake
- contribution ledger
- MQTT/Home Assistant plumbing

### Grocery Module

- inventory
- product cleanup
- shopping list
- grocery recommendations
- grocery analytics
- grocery budget

### Restaurant Module

Implemented baseline in this repo:

- restaurant receipt history
- exact restaurant line-item retention
- subtotal/tax/tip/total tracking
- structured restaurant receipt correction in receipt detail
- ability to resave corrected receipt type, store, date/time, totals, and items
- quick restaurant review actions:
  - rotate image
  - mark as restaurant
  - safe OCR rerun
- restaurant OCR assist for hard phone photos:
  - upload-time restaurant intent
  - restaurant-specific OCR prompt hints
  - rotated candidate comparison
  - strongest candidate chosen before review
- restaurant workspace budget/status card
- selected restaurant receipt detail panel
- repeat-order estimate from a selected receipt
- dining analytics
- dining budget

### General Expense Domain

Implemented baseline in this repo:

- upload-time `general_expense` intent
- auto-classification of retail/service-style receipts into `general_expense`
- purchase totals saved under `domain=general_expense`
- reference line items preserved in receipt review/detail
- no grocery inventory or catalog side effects
- `Expenses` workspace with:
  - spend summary
  - top merchants
  - top reference items
  - budget card
  - selected receipt detail

Restaurant items must never affect grocery inventory.
General-expense receipts must never affect grocery inventory.

Current expectation:

- difficult restaurant OCR should be fixable in the UI after upload
- difficult restaurant OCR should start from the best available candidate, not always the first OCR pass
- restaurant correction should not require raw JSON editing
- corrected receipts should rebuild their purchase cleanly and preserve receipt image linkage
- general-expense receipts should be tracked without being forced into grocery or dining flows

## 4. Deployment Modes

Target deploy-time choices:

- Grocery only
- Restaurant only
- All

If both modules are enabled, future user preference should allow:

- separate views
- combined expenses-style view

## 5. Extended Runtime Defaults

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

## 6. Operator Expectations

Extended docs and setup must clearly explain:

- it is derived from the stable grocery baseline
- it can run in parallel with grocery
- it is the right place for restaurant/module experimentation
- it is safe to abandon later without rollback in grocery

## 7. Implementation Priority

1. keep Extended parallel-safe and isolated
2. preserve inherited grocery behavior
3. add modular runtime scaffolding
4. add restaurant receipt workflows
5. deepen general-expense categorization and restaurant planning ergonomics
6. add combined/separate user presentation options
