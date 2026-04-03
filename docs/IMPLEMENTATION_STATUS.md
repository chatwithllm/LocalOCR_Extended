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

## Verified Working In Code/Config

- Dockerfile now exposes and health-checks `8090`
- compose backend binds `8090:8090`
- backend defaults no longer point at `grocery.db`
- receipt storage helper respects `RECEIPTS_DIR`
- backup/restore scripts no longer use grocery-specific names by default
- MQTT topics now derive from `MQTT_TOPIC_PREFIX`
- MQTT discovery identity now derives from `APP_SLUG`
- setup docs now describe running Extended beside the grocery app

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

- end-to-end restaurant workflow implementation
- module selection UI/runtime behavior
- clean-machine validation of the full Extended stack
- broader docs refresh beyond the core operator/handoff/product files

## Resume Priority

1. verify Extended boots on `8090`
2. verify it can run beside grocery on `8080`
3. verify MQTT and Home Assistant topics do not collide
4. start restaurant/module architecture in this repo only
