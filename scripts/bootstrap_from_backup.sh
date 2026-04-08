#!/bin/bash
set -euo pipefail

BACKUP_FILE="${1:-}"
shift || true

TARGET_ENV_FILE=".env"
SKIP_BUILD="0"
SKIP_ENV_RESTORE="0"
ASSUME_YES="0"
PROMPT_CONFIG="auto"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      TARGET_ENV_FILE="${2:-.env}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD="1"
      shift
      ;;
    --skip-env-restore)
      SKIP_ENV_RESTORE="1"
      shift
      ;;
    --yes)
      ASSUME_YES="1"
      shift
      ;;
    --prompt-config)
      PROMPT_CONFIG="yes"
      shift
      ;;
    --no-prompt-config)
      PROMPT_CONFIG="no"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [ -z "${BACKUP_FILE}" ]; then
  echo "Usage: $0 <backup.tar.gz> [--env-file <path>] [--skip-build] [--skip-env-restore] [--prompt-config|--no-prompt-config] [--yes]"
  exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "❌ Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Docker is required but not installed."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "❌ Docker daemon is not running."
  exit 1
fi

if [ ! -f "docker-compose.yml" ]; then
  echo "❌ Run this script from the project root containing docker-compose.yml."
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

BACKUP_ABS="$(cd "$(dirname "${BACKUP_FILE}")" && pwd)/$(basename "${BACKUP_FILE}")"
CONTAINER_NAME="localocr-extended-backend"
CONTAINER_BACKUP_PATH="/tmp/$(basename "${BACKUP_FILE}")"

extract_backup_entry() {
  local entry_path="$1"
  tar -xOf "${BACKUP_ABS}" "${entry_path}" 2>/dev/null || true
}

should_prompt_config() {
  case "${PROMPT_CONFIG}" in
    yes) return 0 ;;
    no) return 1 ;;
    auto)
      if [ -t 0 ] && [ "${ASSUME_YES}" != "1" ]; then
        return 0
      fi
      return 1
      ;;
  esac
  return 1
}

get_env_value() {
  local key="$1"
  local env_file="$2"
  if [ ! -f "${env_file}" ]; then
    return 0
  fi
  grep -E "^${key}=" "${env_file}" | tail -n 1 | cut -d= -f2- || true
}

set_env_value() {
  local key="$1"
  local value="$2"
  local env_file="$3"
  touch "${env_file}"
  if grep -qE "^${key}=" "${env_file}"; then
    python3 - <<'PY' "${env_file}" "${key}" "${value}"
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = env_path.read_text(encoding="utf-8").splitlines()
updated = []
replaced = False
for line in lines:
    if line.startswith(f"{key}="):
        updated.append(f"{key}={value}")
        replaced = True
    else:
        updated.append(line)
if not replaced:
    updated.append(f"{key}={value}")
env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${env_file}"
  fi
}

prompt_override() {
  local label="$1"
  local key="$2"
  local env_file="$3"
  local secret="${4:-0}"
  local current
  current="$(get_env_value "${key}" "${env_file}")"
  local prompt_suffix=""
  if [ -n "${current}" ]; then
    if [ "${secret}" = "1" ]; then
      prompt_suffix=" [currently set]"
    else
      prompt_suffix=" [${current}]"
    fi
  fi
  local response=""
  if [ "${secret}" = "1" ]; then
    read -r -s -p "${label}${prompt_suffix} (press Enter to keep current): " response
    echo
  else
    read -r -p "${label}${prompt_suffix} (press Enter to keep current): " response
  fi
  if [ -n "${response}" ]; then
    set_env_value "${key}" "${response}" "${env_file}"
    echo "✅ Updated ${key}"
  fi
}

wait_for_backend_health() {
  local attempts="${1:-60}"
  local sleep_seconds="${2:-2}"
  local i
  for ((i=1; i<=attempts; i++)); do
    local status
    status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
    if [ "${status}" = "healthy" ] || [ "${status}" = "running" ]; then
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  return 1
}

echo "═══════════════════════════════════════════"
echo "🚀 LocalOCR Extended Bootstrap Restore"
echo "═══════════════════════════════════════════"
echo "Backup: ${BACKUP_ABS}"
echo "Target env file: ${TARGET_ENV_FILE}"

if [ "${ASSUME_YES}" != "1" ]; then
  echo
  echo "This will:"
  echo "  1. Optionally restore the backed-up env file"
  echo "  2. Build/start the backend container"
  echo "  3. Restore database and receipts from the backup bundle"
  echo "  4. Restart the backend"
  echo "  5. Verify the restored environment"
  echo
  read -p "Continue? (y/N) " -n 1 -r
  echo
  if [[ ! ${REPLY} =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

if [ "${SKIP_ENV_RESTORE}" != "1" ]; then
  ENV_CONTENT="$(extract_backup_entry "./meta/env.snapshot")"
  if [ -n "${ENV_CONTENT}" ]; then
    printf '%s\n' "${ENV_CONTENT}" > "${TARGET_ENV_FILE}"
    echo "✅ Restored env snapshot to ${TARGET_ENV_FILE}"
  else
    echo "ℹ️  No env snapshot found in backup; keeping current ${TARGET_ENV_FILE}"
  fi
else
  echo "ℹ️  Skipping env snapshot restore"
fi

if should_prompt_config; then
  echo
  echo "⚙️  Override deployment values for this environment"
  echo "    Press Enter to keep the restored value."
  prompt_override "Public base URL / domain" "PUBLIC_BASE_URL" "${TARGET_ENV_FILE}" 0
  prompt_override "Gemini API key" "GEMINI_API_KEY" "${TARGET_ENV_FILE}" 1
  prompt_override "Gemini model" "GEMINI_MODEL" "${TARGET_ENV_FILE}" 0
  prompt_override "Initial admin email" "INITIAL_ADMIN_EMAIL" "${TARGET_ENV_FILE}" 0
fi

if [ "${SKIP_BUILD}" = "1" ]; then
  echo "ℹ️  Starting backend without rebuild"
  docker compose up -d backend
else
  echo "🔧 Building and starting backend"
  docker compose up -d --build backend
fi

echo "⏳ Waiting for backend container to become healthy..."
if ! wait_for_backend_health 90 2; then
  echo "❌ Backend did not become healthy in time."
  docker compose ps
  exit 1
fi

echo "📦 Copying backup into container..."
docker cp "${BACKUP_ABS}" "${CONTAINER_NAME}:${CONTAINER_BACKUP_PATH}"

echo "🔄 Restoring backup contents inside container..."
docker exec "${CONTAINER_NAME}" sh -lc "/app/scripts/restore_from_backup.sh '${CONTAINER_BACKUP_PATH}' --yes --no-restart --target-env-file /data/backups/restored_env.snapshot"
docker exec "${CONTAINER_NAME}" rm -f "${CONTAINER_BACKUP_PATH}"

echo "♻️  Restarting backend to apply restored state..."
docker compose restart backend

echo "⏳ Waiting for restarted backend to become healthy..."
if ! wait_for_backend_health 90 2; then
  echo "❌ Backend did not become healthy after restore."
  docker compose ps
  exit 1
fi

echo "🔍 Running post-restore verification..."
VERIFY_OUTPUT="$(docker exec "${CONTAINER_NAME}" sh -lc '/app/scripts/verify_restored_environment.sh /data/backups/last_verify_report.json')"
printf '%s\n' "${VERIFY_OUTPUT}"

echo "═══════════════════════════════════════════"
echo "✅ Bootstrap restore complete"
echo "═══════════════════════════════════════════"
