# Complete Product Specification

> Purpose: this is the rebuild-grade specification for `LocalOCR Extended`. It inherits the working grocery baseline and defines how the Extended repo should evolve into a modular household receipts platform.

## 1. Product Summary

`LocalOCR Extended` is the experimental successor to the stable grocery app.

It must support:

- safe side-by-side deployment with the grocery app
- a shared receipt/OCR/auth core
- a working Grocery module inherited from the current baseline
- a future Restaurant module built in this repo

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

Planned in this repo:

- restaurant receipt history
- exact restaurant line-item retention
- subtotal/tax/tip/total tracking
- dining analytics
- dining budget

Restaurant items must never affect grocery inventory.

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
5. add combined/separate user presentation options
