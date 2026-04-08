# Deployment Guide

This guide explains how to run `LocalOCR Extended` safely beside the stable grocery app.

## Deployment Goal

Run both products at the same time:

- stable grocery app on `8080`
- Extended on `8090`

Keep them isolated for app state:

- separate database
- separate receipt files
- separate backups

Reuse infrastructure where practical:

- shared MQTT broker
- shared Ollama endpoint

## Recommended Parallel Layout

### Stable Grocery Repo

- port: `8080`
- existing DB and receipt storage stay untouched
- remains the fallback deployment

### LocalOCR Extended

- port: `8090`
- DB: `sqlite:////data/db/localocr_extended.db`
- receipt storage: `/data/receipts`
- backups: `/data/backups`
- service label: `localocr-extended-backend`
- MQTT client id: `localocr-extended`
- MQTT topic prefix: `home/localocr_extended`

## Step 1: Clone And Configure Extended

```bash
git clone https://github.com/chatwithllm/LocalOCR_Extended.git
cd LocalOCR_Extended
cp .env.example .env
```

Minimum required secrets:

```dotenv
GEMINI_API_KEY=your_actual_key_here
INITIAL_ADMIN_TOKEN=generate_a_secure_token
INITIAL_ADMIN_EMAIL=admin@localhost
INITIAL_ADMIN_PASSWORD=choose_a_strong_password
SESSION_SECRET=generate_another_secure_secret
```

Do not leave placeholder secrets in place. Extended now treats placeholder bootstrap/session secrets as invalid and will fall back to a generated process-local secret, which is safer but will rotate on restart.

## Step 2: Keep The Port Split

Extended should stay on:

```dotenv
FLASK_PORT=8090
```

Do not point Extended at `8080`. That port belongs to the stable grocery app.

## Step 3: Use Separate App State

Extended defaults already separate storage:

```dotenv
DATABASE_URL=sqlite:////data/db/localocr_extended.db
RECEIPTS_DIR=/data/receipts
BACKUP_DIR=/data/backups
BACKUP_PREFIX=localocr_extended
```

These live inside Extended's own volumes when you use the provided compose file.

## Step 4: Reuse Shared MQTT + Ollama

When the grocery stack is already running, keep these defaults:

```dotenv
MQTT_BROKER=host.docker.internal
MQTT_PORT=1883
OLLAMA_ENDPOINT=http://host.docker.internal:11434
```

This lets Extended share the already-running support services instead of starting conflicting duplicates.

## Step 5: Prevent Home Assistant Collisions

Extended uses separate identifiers by default:

```dotenv
MQTT_CLIENT_ID=localocr-extended
MQTT_TOPIC_PREFIX=home/localocr_extended
APP_SLUG=localocr_extended
APP_DISPLAY_NAME="LocalOCR Extended"
HOME_ASSISTANT_DISCOVERY_PREFIX=homeassistant
```

That means:

- MQTT topics do not overlap with grocery topics
- Home Assistant discovery objects do not reuse grocery ids
- both apps can publish to the same broker without stomping each other

## Step 6: Start Extended

```bash
docker compose up -d --build
```

Check:

```bash
curl http://localhost:8090/health
docker compose ps
```

Expected Extended backend result:

```json
{"status":"healthy","service":"localocr-extended-backend"}
```

## Environment Migration / Recovery

If you are restoring a full production copy onto a new machine, use the backup bootstrap flow instead of manually creating volumes and copying files.

Runbook:

- [BACKUP_RESTORE_RUNBOOK.md](BACKUP_RESTORE_RUNBOOK.md)

Fresh-machine bootstrap example:

```bash
./scripts/bootstrap_from_backup.sh /absolute/path/to/localocr_extended_backup_YYYYMMDD_HHMMSS.tar.gz
```

That flow restores:

- database
- receipt files
- env snapshot

and then verifies the resulting environment automatically.

## Step 7: Optional Dedicated Infra Profile

If you want Extended to run with its own bundled MQTT and Ollama, start:

```bash
docker compose --profile local-infra up -d --build
```

Then set:

```dotenv
MQTT_BROKER=mqtt
OLLAMA_ENDPOINT=http://ollama:11434
```

This is not the recommended default for side-by-side testing, because the shared-service setup is simpler and avoids extra local ports.

## Verification Checklist

Verify grocery still works:

```bash
curl http://localhost:8080/health
```

Verify Extended works:

```bash
curl http://localhost:8090/health
```

Then verify:

- the two apps do not share DB rows
- the two apps do not share receipt files
- the two apps do not share backup archives
- both apps can reach Ollama
- both apps can reach MQTT
- Home Assistant entities from Extended are distinct from grocery entities

## Why This Split Matters

This repo is allowed to move fast and experiment.

If Extended succeeds:

- it can become the long-term deployment target

If Extended is abandoned:

- the grocery repo remains clean
- the grocery deployment keeps running
- no rollback of grocery data or runtime is required
