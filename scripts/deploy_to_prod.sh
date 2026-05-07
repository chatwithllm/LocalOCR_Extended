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
#   COMPOSE_PROJECT — project    (auto-detected from running container)
#   BACKEND_SVC     — service    (default backend)
#   PORT            — health     (default 8090)
#   SKIP_BACKUP     — set to 1 to skip pre-deploy backup (NOT recommended)
#   SKIP_PULL       — set to 1 to deploy current working tree only
#   VERBOSE         — set to 1 to stream all command output instead of spinner
#   NO_SPINNER      — set to 1 to disable spinner (e.g. in CI/non-TTY)

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

DEPLOY_LOG="/tmp/deploy_to_prod_$$.log"
trap 'rm -f "${DEPLOY_LOG}"' EXIT

# ---------------------------------------------------------------------
# Spinner helper. Shows an animated braille frame + step label while a
# long-running command executes in the background. Output is captured
# to ${DEPLOY_LOG}; on failure we tail the last 40 lines so the operator
# sees what broke. On success the spinner replaces itself with a ✓ line
# plus elapsed seconds.
#
# Skipped when:
#   - VERBOSE=1            : output streams live, no spinner
#   - NO_SPINNER=1         : use plain "..." dots
#   - stdout is not a TTY  : same as NO_SPINNER (CI / piped to file)
#
# Usage:
#   _run "Building image" docker compose build backend
# ---------------------------------------------------------------------
_run() {
  local label="$1"; shift
  local start=$(date +%s)

  if [ "${VERBOSE:-0}" = "1" ]; then
    echo "▶ ${label}"
    if "$@"; then
      local elapsed=$(( $(date +%s) - start ))
      echo "  ✓ ${label} (${elapsed}s)"
      return 0
    else
      local rc=$?
      echo "  ✗ ${label} (exit ${rc})"
      return $rc
    fi
  fi

  if [ "${NO_SPINNER:-0}" = "1" ] || [ ! -t 1 ]; then
    printf "▶ %s ..." "${label}"
    if "$@" >>"${DEPLOY_LOG}" 2>&1; then
      local elapsed=$(( $(date +%s) - start ))
      printf " ✓ (%ds)\n" "${elapsed}"
      return 0
    else
      local rc=$?
      printf " ✗ (exit %d)\n" "${rc}"
      echo "  Last 40 lines of output:"
      tail -n 40 "${DEPLOY_LOG}" | sed 's/^/    /'
      return $rc
    fi
  fi

  # TTY spinner — braille frames, ~10fps.
  local frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  ( "$@" >>"${DEPLOY_LOG}" 2>&1 ) &
  local pid=$!
  local i=0
  # Hide cursor while spinning.
  tput civis 2>/dev/null || true
  while kill -0 "${pid}" 2>/dev/null; do
    local frame="${frames:i++%${#frames}:1}"
    local elapsed=$(( $(date +%s) - start ))
    printf "\r  %s %s %s(%ds)%s    " \
      "${frame}" "${label}" "$(tput dim 2>/dev/null)" "${elapsed}" "$(tput sgr0 2>/dev/null)"
    sleep 0.1
  done
  tput cnorm 2>/dev/null || true

  if wait "${pid}"; then
    local elapsed=$(( $(date +%s) - start ))
    # \r + clear-line so ✓ replaces spinner cleanly
    printf "\r\033[K  ✓ %s (%ds)\n" "${label}" "${elapsed}"
    return 0
  else
    local rc=$?
    printf "\r\033[K  ✗ %s (exit %d)\n" "${label}" "${rc}"
    echo "  Last 40 lines of output:"
    tail -n 40 "${DEPLOY_LOG}" | sed 's/^/    /'
    return $rc
  fi
}

cd "${PROD_DIR}"

DEPLOY_START=$(date +%s)
echo "═══════════════════════════════════════════"
echo "🚀 LocalOCR_Extended — production deploy"
echo "    repo:    ${PROD_DIR}"
echo "    project: ${COMPOSE_PROJECT}"
echo "    log:     ${DEPLOY_LOG}"
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
  _run "Fetching origin/main" git fetch --prune origin
  _run "Fast-forwarding to origin/main" git merge --ff-only origin/main
fi
POST_SHA="$(git rev-parse --short HEAD)"

if [ "${PRE_SHA}" = "${POST_SHA}" ] && [ "${SKIP_PULL:-0}" != "1" ]; then
  echo "✓ Already at latest (${POST_SHA}). Nothing to deploy."
  echo "  Use SKIP_PULL=1 to force-rebuild current SHA."
  exit 0
fi

echo "▶ Will deploy: ${PRE_SHA} → ${POST_SHA}"
echo
if [ "${PRE_SHA}" != "${POST_SHA}" ]; then
  echo "Commits in this deploy:"
  git log --oneline "${PRE_SHA}..${POST_SHA}" 2>/dev/null | sed 's/^/  /' || true
  echo
fi

# ---------------------------------------------------------------------
# 2. Pre-deploy backup (DB + volumes + .env metadata)
#    Runs INSIDE the live container so the SQLite WAL is consistent.
#    The script `backup_database_and_volumes.sh` is already shipped in
#    the image and writes to /data/backups inside the container, which
#    is mounted on the `extended-backups` volume.
# ---------------------------------------------------------------------
if [ "${SKIP_BACKUP:-0}" != "1" ]; then
  if docker compose -p "${COMPOSE_PROJECT}" ps --status running --services 2>/dev/null \
       | grep -q "^${BACKEND_SVC}$"; then
    _run "Pre-deploy backup (DB + volumes)" \
      docker compose -p "${COMPOSE_PROJECT}" exec -T "${BACKEND_SVC}" \
        bash /app/scripts/backup_database_and_volumes.sh
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
_run "Building backend image" \
  docker compose -p "${COMPOSE_PROJECT}" build "${BACKEND_SVC}"
_run "Recreating ${BACKEND_SVC} container" \
  docker compose -p "${COMPOSE_PROJECT}" up -d --no-deps "${BACKEND_SVC}"

# ---------------------------------------------------------------------
# 4. Apply pending Alembic migrations.
#    The container entrypoint already runs `alembic upgrade head` on
#    boot, but this explicit pass surfaces failures here in the deploy
#    log instead of buried in container output.
# ---------------------------------------------------------------------
_run "Verifying Alembic head" \
  docker compose -p "${COMPOSE_PROJECT}" exec -T "${BACKEND_SVC}" \
    python -m alembic current
_run "Applying pending migrations" \
  docker compose -p "${COMPOSE_PROJECT}" exec -T "${BACKEND_SVC}" \
    python -m alembic upgrade head

# ---------------------------------------------------------------------
# 5. Health check — wait up to HEALTH_TIMEOUT seconds for /health=200.
#    We spin manually here because the wait is a polling loop, not a
#    single command we can wrap in _run.
# ---------------------------------------------------------------------
_health_check() {
  local start=$(date +%s)
  local frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  local can_spin=1
  if [ "${VERBOSE:-0}" = "1" ] || [ "${NO_SPINNER:-0}" = "1" ] || [ ! -t 1 ]; then
    can_spin=0
  fi
  [ "${can_spin}" = "1" ] && tput civis 2>/dev/null || true
  while true; do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      [ "${can_spin}" = "1" ] && tput cnorm 2>/dev/null || true
      local elapsed=$(( $(date +%s) - start ))
      if [ "${can_spin}" = "1" ]; then
        printf "\r\033[K  ✓ Health check passed (%ds)\n" "${elapsed}"
      else
        echo "  ✓ Health check passed (${elapsed}s)"
      fi
      return 0
    fi
    local now=$(date +%s)
    local elapsed=$(( now - start ))
    if [ "${elapsed}" -ge "${HEALTH_TIMEOUT}" ]; then
      [ "${can_spin}" = "1" ] && tput cnorm 2>/dev/null || true
      printf "\r\033[K  ✗ Health check timed out (%ds)\n" "${elapsed}"
      echo "  Last 80 lines of backend logs:"
      docker compose -p "${COMPOSE_PROJECT}" logs --tail 80 "${BACKEND_SVC}" 2>&1 \
        | sed 's/^/    /' || true
      return 2
    fi
    if [ "${can_spin}" = "1" ]; then
      local frame="${frames:i++%${#frames}:1}"
      printf "\r  %s Waiting for /health on :%s %s(%ds / %ds)%s    " \
        "${frame}" "${PORT}" "$(tput dim 2>/dev/null)" "${elapsed}" "${HEALTH_TIMEOUT}" \
        "$(tput sgr0 2>/dev/null)"
      sleep 0.2
    else
      printf "."
      sleep 2
    fi
  done
}
_health_check

# ---------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------
TOTAL_ELAPSED=$(( $(date +%s) - DEPLOY_START ))
echo
echo "═══════════════════════════════════════════"
echo "✅ Deploy complete (${TOTAL_ELAPSED}s total)"
echo "    SHA:     ${PRE_SHA} → ${POST_SHA}"
echo "    health:  http://127.0.0.1:${PORT}/health"
echo "    finished: $(date -Is)"
echo "═══════════════════════════════════════════"
echo
echo "Rollback command (if needed):"
echo "  cd ${PROD_DIR} && git reset --hard ${PRE_SHA} && \\"
echo "  docker compose -p ${COMPOSE_PROJECT} up -d --build --no-deps ${BACKEND_SVC}"
echo
echo "Full deploy log: ${DEPLOY_LOG} (auto-removed on script exit)."
echo "Re-run with VERBOSE=1 to stream output instead of spinner."
