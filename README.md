# LocalOCR Extended

`LocalOCR Extended` is the experimental successor to the stable grocery app. It starts from the working grocery baseline, runs safely beside it, and is the place where restaurant and future module work will happen.

The important operational rule is simple:

- stable grocery app stays on `http://localhost:8080`
- Extended runs on `http://localhost:8090`
- they use separate app state
- they can share infrastructure like MQTT and Ollama

## What Extended Is For

- preserve the current grocery repo as the clean fallback deployment
- let you explore restaurant and modular household-expense features without risking the stable grocery install
- keep full git ancestry so useful work can be cherry-picked back later if needed

## Current Product Baseline

- inherited grocery workflows remain available
- restaurant summary view is live
- restaurant receipts can now be corrected from receipt detail with structured fields
- corrected restaurant receipts can rebuild store, totals, and line items without raw JSON editing
- Restaurant workspace now also includes dining budget status, selected receipt detail, and repeat-order estimate support

## Current Extended Runtime Defaults

- Flask backend: `8090`
- database: `sqlite:////data/db/localocr_extended.db`
- receipt storage: `/data/receipts`
- backups: `/data/backups`
- MQTT client id: `localocr-extended`
- MQTT topic prefix: `home/localocr_extended`
- Home Assistant discovery device id: `localocr_extended`

These defaults intentionally avoid collisions with the stable grocery stack.

## Parallel Local Deployment

Extended is configured to run beside the stable grocery project.

- grocery repo remains the stable baseline on `8080`
- Extended uses `8090`
- both can reuse the same Ollama endpoint
- both can reuse the same MQTT broker
- Extended uses its own MQTT client id, topic namespace, and Home Assistant discovery identifiers so HA entities do not stomp each other
- Extended uses its own DB, receipts volume, and backup naming so abandoning it later does not damage grocery data

This means you can test Extended freely, and if you lose interest, the grocery deployment remains untouched.

## Quick Start

```bash
git clone https://github.com/chatwithllm/LocalOCR_Extended.git
cd LocalOCR_Extended
cp .env.example .env
```

Edit `.env` with at least:

```dotenv
GEMINI_API_KEY=replace_with_your_gemini_api_key
INITIAL_ADMIN_TOKEN=replace_with_a_long_random_token
INITIAL_ADMIN_EMAIL=admin@localhost
INITIAL_ADMIN_PASSWORD=replace_with_a_strong_password
SESSION_SECRET=replace_with_another_long_random_secret
```

Then start Extended:

```bash
docker compose up -d --build
curl http://localhost:8090/health
```

Open:

- [http://localhost:8090](http://localhost:8090)

The stable grocery app can keep running separately on:

- [http://localhost:8080](http://localhost:8080)

## Shared Services

By default, Extended expects to reuse the stable grocery stack's shared services:

- `OLLAMA_ENDPOINT=http://host.docker.internal:11434`
- `MQTT_BROKER=host.docker.internal`

If you want Extended to run with its own local MQTT and Ollama instead, you can start the optional profile:

```bash
docker compose --profile local-infra up -d --build
```

Then point `.env` to:

```dotenv
MQTT_BROKER=mqtt
OLLAMA_ENDPOINT=http://ollama:11434
```

## Documentation

- [docs/APP_SETUP_GUIDE.md](docs/APP_SETUP_GUIDE.md): operator-friendly first-run setup
- [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md): deeper deployment details and parallel-runtime guidance
- [CONTINUITY.md](CONTINUITY.md): restart and handoff context for Extended
- [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md): inherited working baseline vs planned Extended work
- [PRD.md](PRD.md): product direction for the Extended repo
- [docs/COMPLETE_PRODUCT_SPEC.md](docs/COMPLETE_PRODUCT_SPEC.md): detailed rebuild-grade product spec

## Current Product Direction

What is already inherited and working:

- grocery receipt OCR
- web auth and household users
- inventory and product cleanup tools
- shopping list and shopping helper QR
- contribution ledger and collaborative scoring
- MQTT and Home Assistant integration

What Extended is for next:

- modular deployment choices
- restaurant receipts and restaurant expense tracking
- combined vs separate grocery/restaurant user views
- safe experimentation without destabilizing the grocery repo

## License

Private project. All rights reserved.
