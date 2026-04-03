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

## 4. Current Verified Extended Changes

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

## 5. What Still Belongs To Extended Next

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
- Restaurant workspace now includes:
  - dining budget card
  - selected receipt detail panel
  - repeat-order estimate from the chosen receipt
  - recent receipt inspect action
  - stronger top-ordered-item reporting

Current rule:

- do not destabilize the stable grocery repo for this work
- new module and restaurant work should happen here

## 6. Resume Order

Read these in order:

1. [README.md](README.md)
2. [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
3. [PRD.md](PRD.md)
4. [docs/COMPLETE_PRODUCT_SPEC.md](docs/COMPLETE_PRODUCT_SPEC.md)
5. [docs/APP_SETUP_GUIDE.md](docs/APP_SETUP_GUIDE.md)
6. [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)

Then inspect:

- [docker-compose.yml](docker-compose.yml)
- [Dockerfile](Dockerfile)
- [src/backend/create_flask_application.py](src/backend/create_flask_application.py)
- [src/backend/setup_mqtt_connection.py](src/backend/setup_mqtt_connection.py)
- [src/backend/publish_mqtt_events.py](src/backend/publish_mqtt_events.py)

## 7. Safety Rules

- keep grocery repo `main` as the stable baseline
- keep Extended changes additive and modular where possible
- if a feature is worth bringing back later, prefer cherry-picking focused commits instead of wholesale repo merging
- preserve separate MQTT identifiers and topic namespaces so Home Assistant can ingest both apps cleanly

## 8. Local Verification Targets

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
