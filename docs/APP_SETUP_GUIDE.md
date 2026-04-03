# App Setup Guide

Use this guide when setting up `LocalOCR Extended` as an actual app, not just a development workspace.

## What This Repo Assumes

This repo is meant to run beside the stable grocery deployment:

- stable grocery app: `http://localhost:8080`
- Extended app: `http://localhost:8090`

Extended uses separate app state so it is safe to test in parallel.

## 1. Clone Extended

```bash
git clone https://github.com/chatwithllm/LocalOCR_Extended.git
cd LocalOCR_Extended
cp .env.example .env
```

## 2. Fill In `.env`

Start with these:

```dotenv
INITIAL_ADMIN_TOKEN=replace_with_a_long_random_token
INITIAL_ADMIN_EMAIL=admin@localhost
INITIAL_ADMIN_PASSWORD=replace_with_a_strong_password
SESSION_SECRET=replace_with_another_long_random_secret
GEMINI_API_KEY=replace_with_your_gemini_api_key
```

Recommended Extended runtime defaults:

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

## 3. Shared Service Defaults

Extended is configured to reuse the stable grocery app's support services by default:

```dotenv
MQTT_BROKER=host.docker.internal
MQTT_PORT=1883
OLLAMA_ENDPOINT=http://host.docker.internal:11434
```

That is the right setup when the grocery stack is already running and publishing:

- MQTT on `1883`
- Ollama on `11434`

If your machine does not support `host.docker.internal`, replace those with your host LAN IP.

## 4. Start Extended

```bash
docker compose up -d --build
```

Verify:

```bash
curl http://localhost:8090/health
docker compose ps
```

Open:

- [http://localhost:8090](http://localhost:8090)

## 5. Optional: Run Dedicated MQTT + Ollama For Extended

If you do not want to share the grocery stack's MQTT and Ollama, start the optional infra profile:

```bash
docker compose --profile local-infra up -d --build
```

Then set:

```dotenv
MQTT_BROKER=mqtt
OLLAMA_ENDPOINT=http://ollama:11434
```

Use this mode only if you intentionally want Extended to have its own local support services. For parallel day-to-day testing, shared services are the simpler choice.

## 6. Open The App

Log in with:

- email: `INITIAL_ADMIN_EMAIL`
- password: `INITIAL_ADMIN_PASSWORD`

If `INITIAL_ADMIN_PASSWORD` is blank, the first browser login falls back to `INITIAL_ADMIN_TOKEN`.

## 7. Parallel Deployment Notes

The stable grocery repo remains independent:

- grocery backend stays on `8080`
- Extended stays on `8090`
- grocery DB and volumes remain untouched
- Extended writes to its own DB, receipts volume, and backup archives

This is intentional so the Extended idea can be abandoned later with no rollback required on the grocery app.

## 8. Day-To-Day Operations

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

## 9. Backup And Restore

Manual backup:

```bash
docker exec localocr-extended-backend /app/scripts/backup_database_and_volumes.sh
```

Restore:

```bash
docker exec -it localocr-extended-backend /app/scripts/restore_from_backup.sh /data/backups/localocr_extended_backup_YYYYMMDD.tar.gz
```
