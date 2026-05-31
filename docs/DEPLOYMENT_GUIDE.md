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
- product snapshot storage: `/data/product_snapshots`
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
PRODUCT_SNAPSHOTS_DIR=/data/product_snapshots
BACKUP_DIR=/data/backups
BACKUP_PREFIX=localocr_extended
KEEP_BACKUP_COUNT=3
```

These live inside Extended's own volumes when you use the provided compose file.

Backup retention note:

- backup creation now keeps the newest `KEEP_BACKUP_COUNT` archives automatically
- default local retention is `3`
- set `KEEP_BACKUP_COUNT` higher if you want a deeper local history

Snapshot note:

- shopping-item and receipt-item supporting photos now persist separately from receipt images
- keep the product snapshot volume with the rest of the environment when backing up or migrating this stack

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

## Enabling Google Sign-In

The backend already implements every Google OAuth route
(`/auth/oauth/google`, `/callback`, `/status`, `/link`, `/unlink`) in
`src/backend/manage_authentication.py`. It stays disabled until both
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are present in the
environment. This section walks through enabling it on
`https://extended.npalakurla.com`.

### Prerequisites

- A Google Cloud project with the OAuth consent screen configured
  (External or Internal — both work).
- If the consent screen is in **Testing** mode, your sign-in email must
  be added as a test user, otherwise you will hit
  `Error 403: access_denied`.

### Step 1 — Create the OAuth 2.0 Web Client in GCP

1. Open Google Cloud Console → **APIs & Services** → **Credentials**.
2. Click **Create Credentials** → **OAuth client ID**.
3. Application type: **Web application**.
4. Authorized redirect URIs — add exactly:

   ```
   https://extended.npalakurla.com/auth/oauth/google/callback
   ```

   No trailing slash. Scheme must be `https`. Host without `www`.
5. Click **Create**. Copy the **Client ID** and **Client secret**.

### Step 2 — Edit prod `.env`

```bash
ssh UDImmich
cd /opt/extended/LocalOCR_Extended
cp .env .env.backup-$(date +%Y%m%d-%H%M%S)   # safety copy
nano .env
```

Add or update these four lines (paste the values from Step 1):

```
GOOGLE_CLIENT_ID=<paste from GCP>
GOOGLE_CLIENT_SECRET=<paste from GCP>
GOOGLE_OAUTH_ENABLED=true
PUBLIC_BASE_URL=https://extended.npalakurla.com
```

Save and exit. `.env` is gitignored, so the secrets stay on the host.

### Step 3 — Restart the backend

```bash
docker compose restart backend
```

> Use `restart`, **not** `up -d`. `up -d` is a no-op when the image is
> unchanged and will not pick up the new env vars.

### Step 4 — Verify

From any machine:

```bash
curl -s https://extended.npalakurla.com/auth/oauth/google/status
```

Expected:
```json
{"enabled": true}
```

If you see `{"enabled": false}`:
- check `docker compose exec backend env | grep GOOGLE`
- check `docker compose logs backend --tail 50` for missing-config warnings.

Then run the full browser round trip:

1. Open `https://extended.npalakurla.com/app` in a browser.
2. The Google sign-in button should be visible
   (`#auth-google-btn` un-hidden by the SPA reading `app-config`).
3. Click it → Google consent screen → consent → back to `/app`
   authenticated.
4. `docker compose logs backend --tail 100` shows the callback
   succeeding (no `redirect_uri_mismatch`, no `state` errors).

### Rollback

```bash
ssh UDImmich
cd /opt/extended/LocalOCR_Extended
# Comment out or blank the two credentials in .env:
sed -i 's/^GOOGLE_CLIENT_ID=.*/GOOGLE_CLIENT_ID=/' .env
sed -i 's/^GOOGLE_CLIENT_SECRET=.*/GOOGLE_CLIENT_SECRET=/' .env
docker compose restart backend
```

`_is_google_oauth_configured()` returns `False`, the SPA hides the
button, and existing users with linked `google_sub` fall back to
password login. No database changes need reverting.

### Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `Error 400: redirect_uri_mismatch` | URI in GCP doesn't match what backend sent | Compare GCP URI with `_get_oauth_redirect_uri()` output — usually a trailing slash or `http` vs `https`. |
| `Error 403: access_denied` | Consent screen in Testing mode, signing-in email not added as test user | Add the email under **OAuth consent screen → Test users**, or publish the consent screen. |
| `/auth/oauth/google/status` still `{"enabled": false}` after restart | Env not actually reloaded | `docker compose down && docker compose up -d backend` to force a recreate. |
| `Error: invalid_client` on callback | Wrong `GOOGLE_CLIENT_SECRET` | Re-copy the secret from GCP — they look similar but include subtle characters. |
