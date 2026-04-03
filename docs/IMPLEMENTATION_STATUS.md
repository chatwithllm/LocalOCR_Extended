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
- receipt detail can now edit and resave:
  - receipt type
  - store
  - date/time
  - totals
  - line items
- existing processed receipts can be rebuilt from corrected structured payloads
- first restaurant receipt has been verified as a corrected `restaurant` purchase with exact line items

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

- robust restaurant-first OCR extraction for difficult phone photos
- restaurant-specific analytics/detail polish beyond the initial summary + corrected receipt support
- module selection UI/runtime behavior
- clean-machine validation of the full Extended stack
- broader docs refresh beyond the core operator/handoff/product files

## Resume Priority

1. verify Extended boots on `8090`
2. verify it can run beside grocery on `8080`
3. verify MQTT and Home Assistant topics do not collide
4. continue restaurant/module architecture in this repo only
5. improve restaurant OCR quality and review ergonomics
