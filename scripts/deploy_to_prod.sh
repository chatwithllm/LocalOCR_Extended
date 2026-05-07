#!/bin/bash
# Production deploy script for LocalOCR_Extended.
#
# Run on the prod host (UDImmich) from /opt/extended/LocalOCR_Extended.
# Pulls latest main, snapshots DB+volumes inside the running container,
# rebuilds the backend image, applies pending Alembic migrations, then
# tails health until /health returns 200.
#
# Safe to re-run. Aborts on any error. Backup is taken BEFORE the
# rebuild so a failed migration leaves a recoverable archive.
#
# Usage:
#   bash scripts/deploy_to_prod.sh
#
# Override knobs (env vars):
#   PROD_DIR        — repo path  (default /opt/extended/LocalOCR_Extended)
#   COMPOSE_PROJECT — project    (default extended)
#   BACKEND_SVC     — service    (default backend)
#   PORT            — health     (default 8090)
#   SKIP_BACKUP     — set to 1 to skip pre-deploy backup (NOT recommended)
#   SKIP_PULL       — set to 1 to deploy current working tree only

set -euo pipefail

PROD_DIR="${PROD_DIR:-/opt/extended/LocalOCR_Extended}"
BACKEND_SVC="${BACKEND_SVC:-backend}"

# Auto-detect compose project name from the running container's labels.
# Compose uses the directory name by default but operators sometimes
# override via COMPOSE_PROJECT_NAME, so we look at the live state first.
# Falls back to "extended" then directory basename.
_DETECTED_PROJECT="$(docker inspect localocr-extended-backend \
  --format '{{ index .Config.Labels "com.docker.compose.project" }}' 2>/dev/null || true)"
if [ -n "${_DETECTED_PROJECT}" ] && [ "${_DETECTED_PROJECT}" != "<no value>" ]; then
  COMPOSE_PROJECT="${COMPOSE_PROJECT:-${_DETECTED_PROJECT}}"
else
  COMPOSE_PROJECT="${COMPOSE_PROJECT:-$(basename "${PROD_DIR}" | tr '[:upper:]' '[:lower:]' | tr -d '_-')}"
fi
PORT="${PORT:-8090}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"

cd "${PROD_DIR}"

echo "═══════════════════════════════════════════"
echo "🚀 LocalOCR_Extended — production deploy"
echo "    repo:    ${PROD_DIR}"
echo "    project: ${COMPOSE_PROJECT}"
echo "    started: $(date -Is)"
echo "═══════════════════════════════════════════"

# ---------------------------------------------------------------------
# 0. Confirm we're on a clean tree on main (warn but don't block —
#    operator may have local hotfixes intentionally).
# ---------------------------------------------------------------------
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "${BRANCH}" != "main" ]; then
  echo "⚠️  Current branch is '${BRANCH}', not 'main'. Continue? [y/N]"
  read -r ans
  [ "${ans}" = "y" ] || [ "${ans}" = "Y" ] || { echo "Aborted."; exit 1; }
fi
if ! git diff-index --quiet HEAD --; then
  echo "⚠️  Working tree has uncommitted changes:"
  git status --short
  echo "Continue anyway? [y/N]"
  read -r ans
  [ "${ans}" = "y" ] || [ "${ans}" = "Y" ] || { echo "Aborted."; exit 1; }
fi

PRE_SHA="$(git rev-parse --short HEAD)"

# ---------------------------------------------------------------------
# 1. Pull latest main (skippable for hotfix deploys)
# ---------------------------------------------------------------------
if [ "${SKIP_PULL:-0}" != "1" ]; then
  echo "▶ Fetching origin/main..."
  git fetch --prune origin
  echo "▶ Fast-forwarding to origin/main..."
  git merge --ff-only origin/main
fi
POST_SHA="$(git rev-parse --short HEAD)"

if [ "${PRE_SHA}" = "${POST_SHA}" ] && [ "${SKIP_PULL:-0}" != "1" ]; then
  echo "✓ Already at latest (${POST_SHA}). Nothing to deploy."
  echo "  Use SKIP_PULL=1 to force-rebuild current SHA."
  exit 0
fi

echo "▶ Will deploy: ${PRE_SHA} → ${POST_SHA}"
echo
echo "Commits in this deploy:"
git log --oneline "${PRE_SHA}..${POST_SHA}" 2>/dev/null | sed 's/^/  /' || true
echo

# ---------------------------------------------------------------------
# 2. Pre-deploy backup (DB + volumes + .env metadata)
#    Runs INSIDE the live container so the SQLite WAL is consistent.
#    The script `backup_database_and_volumes.sh` is already shipped in
#    the image and writes to /data/backups inside the container, which
#    is mounted on the `extended-backups` volume.
# ---------------------------------------------------------------------
if [ "${SKIP_BACKUP:-0}" != "1" ]; then
  echo "▶ Pre-deploy backup (running inside ${BACKEND_SVC} container)..."
  if docker compose -p "${COMPOSE_PROJECT}" ps --status running --services | grep -q "^${BACKEND_SVC}$"; then
    docker compose -p "${COMPOSE_PROJECT}" exec -T "${BACKEND_SVC}" \
      bash /app/scripts/backup_database_and_volumes.sh
    echo "✓ Backup complete (in extended-backups volume)"
  else
    echo "⚠️  ${BACKEND_SVC} not running — skipping in-container backup."
    echo "   First-time deploy on this host? Migration alone is safe (idempotent)."
  fi
else
  echo "⚠️  SKIP_BACKUP=1 — proceeding without backup. Don't say I didn't warn you."
fi

# ---------------------------------------------------------------------
# 3. Build new image + recreate the backend service
# ---------------------------------------------------------------------
echo "▶ Building image..."
docker compose -p "${COMPOSE_PROJECT}" build "${BACKEND_SVC}"

echo "▶ Recreating ${BACKEND_SVC} (other services left untouched)..."
docker compose -p "${COMPOSE_PROJECT}" up -d --no-deps "${BACKEND_SVC}"

# ---------------------------------------------------------------------
# 4. Apply pending Alembic migrations.
#    The container entrypoint already runs `alembic upgrade head` on
#    boot, but this explicit pass surfaces failures here in the deploy
#    log instead of buried in container output.
# ---------------------------------------------------------------------
echo "▶ Verifying Alembic head..."
docker compose -p "${COMPOSE_PROJECT}" exec -T "${BACKEND_SVC}" \
  python -m alembic current

echo "▶ Applying any pending migrations (idempotent)..."
docker compose -p "${COMPOSE_PROJECT}" exec -T "${BACKEND_SVC}" \
  python -m alembic upgrade head

# ---------------------------------------------------------------------
# 5. Health check — wait up to HEALTH_TIMEOUT seconds for /health=200
# ---------------------------------------------------------------------
echo "▶ Waiting for /health on port ${PORT} (timeout ${HEALTH_TIMEOUT}s)..."
start=$(date +%s)
while true; do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "✓ /health OK"
    break
  fi
  now=$(date +%s)
  if [ $((now - start)) -ge "${HEALTH_TIMEOUT}" ]; then
    echo "❌ Health check did not pass within ${HEALTH_TIMEOUT}s."
    echo "   Tailing last 80 lines of backend logs:"
    docker compose -p "${COMPOSE_PROJECT}" logs --tail 80 "${BACKEND_SVC}" || true
    exit 2
  fi
  sleep 2
done

# ---------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------
echo
echo "═══════════════════════════════════════════"
echo "✅ Deploy complete"
echo "    SHA:     ${PRE_SHA} → ${POST_SHA}"
echo "    health:  http://127.0.0.1:${PORT}/health"
echo "    finished: $(date -Is)"
echo "═══════════════════════════════════════════"
echo
echo "Rollback command (if needed):"
echo "  cd ${PROD_DIR} && git reset --hard ${PRE_SHA} && \\"
echo "  docker compose -p ${COMPOSE_PROJECT} up -d --build --no-deps ${BACKEND_SVC}"
