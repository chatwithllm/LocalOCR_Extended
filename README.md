# LocalOCR Extended

`LocalOCR Extended` is a household receipt, shopping, inventory, and restaurant-expense platform.

It is designed to help a household:

- capture receipts from web upload, QR helper flow, and optional Telegram intake
- maintain grocery inventory and shopping workflows
- track restaurant spending with exact line items
- correct bad OCR without losing the original receipt image
- keep budgets, analytics, and collaboration visible across users
- publish live updates to MQTT / Home Assistant when configured

## What The Product Does

`LocalOCR Extended` has two main domains:

- `Grocery`
  - receipt OCR
  - active inventory
  - product cleanup and normalization
  - shopping list
  - low-stock workflow
  - grocery budget and analytics

- `Restaurant`
  - restaurant receipt tracking
  - exact menu line items
  - subtotal, tax, tip, total
  - dining budget
  - dining analytics
  - repeat-order estimate from prior receipts

The app also includes a shared collaboration layer:

- household login and user roles
- contribution tracking and scoring
- QR helper access for shopping
- OCR correction and review workflows
- optional MQTT / Home Assistant integration

## Main Workspaces

### Dashboard

- household ranking and contribution scorecards
- grocery status cards
- low-stock and recommendation surfaces
- hidden QR access tools

### Inventory

- current active grocery inventory
- search, category chips, sorting
- rename, recategorize, low/clear-low, location, shopping add
- receipt traceability for confusing items

### Products

- merged into the same workspace as Inventory via toggle
- normalized names and receipt history
- rename, recategorize, add to shopping
- cleanup support for OCR-heavy product names

### Upload Receipt

- upload image or PDF
- choose receipt intent:
  - `Auto`
  - `Grocery`
  - `Restaurant`
- OCR preview/result feedback

### Receipts

- receipt list with filters and sorting
- receipt detail with image/PDF view
- structured editing for:
  - receipt type
  - store
  - date/time
  - subtotal/tax/tip/total
  - line items
- quick actions:
  - rotate left/right
  - mark as restaurant
  - re-run OCR
- safe rebuild of corrected receipts

### Shopping List

- current list, quick find, recommendations, store grouping
- estimated total cost
- estimated store stops
- shopping helper QR for shared trip execution
- bought / reopen handling

### Budget

- grocery monthly budget
- restaurant monthly budget
- budget status and progress

### Analytics

- grocery spending analytics
- restaurant spending analytics
- monthly totals and category/domain breakdowns

### Restaurant

- dining spend summary
- visit count
- average ticket
- top restaurants
- top ordered items
- dining budget card
- selected receipt detail
- repeat-order estimate

### Contribution

- how scoring works
- recent contribution history
- ways users can help improve the system

### Settings

- user profile and avatar
- admin user management
- catalog review queue for OCR-heavy products

## Restaurant Workflow

Restaurant receipts are treated differently from grocery receipts.

Goals:

- keep restaurant spending out of grocery inventory
- preserve exact menu items
- allow correction after OCR
- make prior orders useful for planning future visits

Current restaurant flow:

1. Upload a receipt and choose `Restaurant` when you already know it is dining-related.
2. OCR runs with restaurant-friendly hints.
3. If OCR is imperfect, open the receipt in `Receipts`.
4. Use the structured editor to fix:
   - restaurant name
   - date/time
   - subtotal/tax/tip/total
   - line items
5. Save the corrected receipt.
6. The corrected receipt appears in the `Restaurant` workspace, budget, and analytics.

## Grocery Workflow

Grocery receipts continue to drive the operational household flow:

1. Upload or ingest receipt
2. OCR extracts grocery items
3. Purchase is stored
4. Active inventory is rebuilt
5. Recommendations and shopping flows update
6. Users can clean up names, categories, and low-stock state later

## OCR Review Philosophy

The app is built around the idea that OCR is helpful but not perfect.

So the product supports:

- OCR-first ingestion
- structured correction after upload
- product/category cleanup
- receipt-level rebuilds from corrected data

This is especially important for:

- sideways phone photos
- long restaurant receipts
- OCR-heavy abbreviations
- mixed grocery / discount / restaurant edge cases

## MQTT / Home Assistant

When configured, the app can publish live updates over MQTT for Home Assistant.

Typical uses:

- inventory updates
- low-stock updates
- recommendations
- budget alerts

Recommended defaults in this repo:

- MQTT client id: `localocr-extended`
- MQTT topic prefix: `home/localocr_extended`
- Home Assistant identity derived from `APP_SLUG=localocr_extended`

## Runtime Defaults

Default local runtime:

- backend port: `8090`
- database: `sqlite:////data/db/localocr_extended.db`
- receipt storage: `/data/receipts`
- backups: `/data/backups`

Default service identity:

- app name: `LocalOCR Extended`
- service name: `localocr-extended-backend`
- app slug: `localocr_extended`

## Quick Start

```bash
git clone https://github.com/chatwithllm/LocalOCR_Extended.git
cd LocalOCR_Extended
cp .env.example .env
```

Edit `.env` with at least:

```dotenv
INITIAL_ADMIN_TOKEN=replace_with_a_long_random_token
INITIAL_ADMIN_EMAIL=admin@localhost
INITIAL_ADMIN_PASSWORD=replace_with_a_strong_password
SESSION_SECRET=replace_with_another_long_random_secret
GEMINI_API_KEY=replace_with_your_gemini_api_key
```

Recommended defaults:

```dotenv
FLASK_PORT=8090
APP_SERVICE_NAME=localocr-extended-backend
APP_DISPLAY_NAME=LocalOCR Extended
APP_SLUG=localocr_extended
DATABASE_URL=sqlite:////data/db/localocr_extended.db
RECEIPTS_DIR=/data/receipts
BACKUP_DIR=/data/backups
BACKUP_PREFIX=localocr_extended
MQTT_CLIENT_ID=localocr-extended
MQTT_TOPIC_PREFIX=home/localocr_extended
```

Start the app:

```bash
docker compose up -d --build
curl http://localhost:8090/health
```

Open:

- [http://localhost:8090](http://localhost:8090)

## Shared Infrastructure

By default, this project can reuse existing infrastructure:

- Ollama
- MQTT broker

Example shared-service configuration:

```dotenv
MQTT_BROKER=host.docker.internal
MQTT_PORT=1883
OLLAMA_ENDPOINT=http://host.docker.internal:11434
```

If you want this repo to run with its own local MQTT and Ollama instead:

```bash
docker compose --profile local-infra up -d --build
```

Then set:

```dotenv
MQTT_BROKER=mqtt
OLLAMA_ENDPOINT=http://ollama:11434
```

## Daily Operations

View logs:

```bash
docker compose logs -f backend
```

Update:

```bash
git pull
docker compose up -d --build
```

Stop:

```bash
docker compose down
```

## Backups

Manual backup:

```bash
docker exec localocr-extended-backend /app/scripts/backup_database_and_volumes.sh
```

Restore:

```bash
docker exec -it localocr-extended-backend /app/scripts/restore_from_backup.sh /data/backups/localocr_extended_backup_YYYYMMDD.tar.gz
```

## Documentation

- [docs/APP_SETUP_GUIDE.md](docs/APP_SETUP_GUIDE.md)
- [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)
- [CONTINUITY.md](CONTINUITY.md)
- [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
- [PRD.md](PRD.md)
- [docs/COMPLETE_PRODUCT_SPEC.md](docs/COMPLETE_PRODUCT_SPEC.md)

## Current Product Direction

Near-term focus:

- stronger restaurant OCR assistance
- faster receipt correction on mobile
- modular deployment choices
- user-selectable grocery vs restaurant presentation modes

## License

Private project. All rights reserved.
