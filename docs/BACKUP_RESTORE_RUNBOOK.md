# Backup & Restore Runbook

This runbook is the operator guide for moving `LocalOCR Extended` to a new machine or recovering an existing environment from a backup bundle.

## 1. What A Backup Contains

A full environment backup bundle includes:

- SQLite database snapshot
- full receipts file tree
- full product snapshot file tree
- env snapshot
- manifest metadata
- compose snapshot when available

Typical archive name:

- `localocr_extended_backup_YYYYMMDD_HHMMSS.tar.gz`

## 2. Two Restore Paths

Use the correct restore path for the situation.

### A. Fresh-Machine Restore

Use this when the target machine does not have a working app yet.

Command:

```bash
./scripts/bootstrap_from_backup.sh /absolute/path/to/localocr_extended_backup_YYYYMMDD_HHMMSS.tar.gz
```

What bootstrap does:

1. restores env snapshot into `.env` unless skipped
2. optionally prompts for machine-specific overrides
3. builds and starts the backend
4. restores database and receipts from the bundle
5. restores product snapshots from the bundle
6. restarts the backend
7. runs validation automatically

### B. In-App Restore

Use this when the app is already running and admins are restoring from `Settings -> Environment Backup & Restore`.

Current behavior:

1. admin selects a backup
2. admin chooses restore scope:
   - Database
   - Receipts / Files
   - Environment Config
3. app creates a safety backup of the current environment first
4. app restores selected sections
5. backend restarts
6. restore report shows resulting counts

## 3. Fresh-Machine Migration Checklist

Use these steps on a clean target machine.

### Step 1: Install prerequisites

Required:

- Docker
- Docker Compose support
- access to the backup bundle
- access to repo source

### Step 2: Clone the repo

```bash
git clone https://github.com/chatwithllm/LocalOCR_Extended.git
cd LocalOCR_Extended
git checkout <desired-branch-or-main>
```

### Step 3: Copy the backup bundle to the machine

Example:

```bash
scp localocr_extended_backup_YYYYMMDD_HHMMSS.tar.gz user@target:/path/to/backups/
```

### Step 4: Run bootstrap restore

Interactive prompt mode:

```bash
./scripts/bootstrap_from_backup.sh /path/to/localocr_extended_backup_YYYYMMDD_HHMMSS.tar.gz
```

Non-interactive mode:

```bash
./scripts/bootstrap_from_backup.sh /path/to/localocr_extended_backup_YYYYMMDD_HHMMSS.tar.gz --yes --no-prompt-config
```

Prompt overrides currently supported:

- `PUBLIC_BASE_URL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `INITIAL_ADMIN_EMAIL`

### Step 5: Verify the restored environment

Bootstrap already runs verification, but operators should also confirm:

```bash
docker compose ps
curl http://localhost:8090/health
docker exec -it localocr-extended-backend /app/scripts/verify_restored_environment.sh
```

Expected validation areas:

- users count
- purchases count
- active trusted-device count
- receipt rows
- receipt files
- missing receipt images

### Step 6: Perform app-level checks

Open the app and verify:

- admin login works
- expected users exist
- receipts list loads
- receipt images open
- inventory loads
- shopping list loads
- budget loads
- Settings shows backup/restore section

## 4. In-App Restore Checklist

When restoring from the UI:

1. verify you are on the correct host/environment
2. verify the selected backup timestamp and counts
3. choose restore scope carefully
4. confirm restore
5. wait for:
   - safety backup creation
   - restore progress stages
   - backend restart
6. after reload, verify:
   - users
   - purchases
   - receipt files
   - product snapshot files
   - receipt images

Important:

- every UI restore creates a safety backup first
- if the latest backup is marked as a safety backup, it was auto-created by a restore
- local backup creation now keeps the newest 3 backup archives by default
- increase `KEEP_BACKUP_COUNT` in env if you want to keep more than 3 locally

## 5. Post-Restore Checks

After any restore, confirm:

- health endpoint returns healthy
- latest restore report looks reasonable
- restored sections match what was requested
- users count matches expectation
- purchases count matches expectation
- receipt rows and files look correct
- product snapshot rows and files look correct
- missing image count is acceptable or zero

If `Environment Config` was restored, also verify:

- public base URL
- Gemini key/model
- bootstrap admin email
- other environment-specific settings

## 6. Cutover Checklist

Before declaring the target machine production-ready:

- restore verification passes
- app login works
- receipt images resolve
- product/item photos resolve
- budget and analytics load
- backup creation still works on the restored machine
- DNS / reverse proxy points at the correct host
- operators know where the latest safety backup is stored

## 7. Known Limitations

Current scoped restore supports:

- Database
- Receipts / Files
- Environment Config

It does **not** yet support true row-level restore such as:

- only users
- only trusted devices
- only purchases

`Database` currently means the full DB-backed application state.

## 8. Best Practices

- always keep the newest backup archive off-machine too
- treat local retention as convenience, not disaster recovery
- do not rely only on Docker volumes as “the backup”
- prefer fresh backups before risky changes
- keep LAN/domain hosts pointed at the same backend/DB only if you truly want shared state
- after major restore work, create a new backup from the restored environment so the recovery chain stays current
