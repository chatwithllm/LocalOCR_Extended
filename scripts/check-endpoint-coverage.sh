#!/usr/bin/env bash
# V-6 RESOLVED — per-screen Dart remote_source coverage audit.
#
# Extracts every `Method | Path` row from ANDROID_APP_PLAN.md §4 endpoint inventory
# and confirms each appears in at least one `dio.<verb>(...)` call inside lib/features/.
# Fails (exit 1) if any endpoint is missing a corresponding Dart caller.
#
# Pre-conditions:
#   - ANDROID_APP_PLAN.md present at repo root.
#   - lib/features/ present (created by `flutter create` + scaffold step).
#
# Usage: scripts/check-endpoint-coverage.sh
set -euo pipefail

PLAN="${1:-ANDROID_APP_PLAN.md}"
LIB="${2:-lib/features}"

if [ ! -f "$PLAN" ]; then
  echo "ERROR: $PLAN not found" >&2
  exit 2
fi

if [ ! -d "$LIB" ]; then
  echo "ERROR: $LIB not found (run after \`flutter create\` + scaffold)" >&2
  exit 2
fi

tmp_endpoints="$(mktemp)"
trap 'rm -f "$tmp_endpoints"' EXIT

# Pull endpoint rows from §4 markdown tables: `| METHOD | /path | source | notes |`.
# Strip backticks, query strings, and `<int:foo>` placeholders so we can grep for
# the literal path stem in dio call strings.
awk -F'|' '
  /^\| (GET|POST|PUT|DELETE|PATCH) +\|/ {
    method=$2; gsub(/[ `]/, "", method);
    path=$3;   gsub(/[ `]/, "", path);
    gsub(/<[^>]*>/, "<>", path);
    sub(/\?.*$/, "", path);
    print method " " path;
  }
' "$PLAN" | sort -u > "$tmp_endpoints"

total=$(wc -l < "$tmp_endpoints" | tr -d ' ')
missing=0

while IFS=' ' read -r method path; do
  stem=$(echo "$path" | sed 's|/<>|/|g' | awk -F'/<>' '{print $1}')
  # Match dio.<verb>('...stem...') or dio.<verb>("...stem...") in lib/features/
  verb=$(echo "$method" | tr '[:upper:]' '[:lower:]')
  if ! grep -rqE "dio\.${verb}\(\s*['\"][^'\"]*${stem}" "$LIB" 2>/dev/null; then
    echo "MISSING: $method $path"
    missing=$((missing + 1))
  fi
done < "$tmp_endpoints"

echo "---"
echo "checked: $total endpoints"
echo "missing: $missing"

if [ "$missing" -gt 0 ]; then
  exit 1
fi
exit 0
