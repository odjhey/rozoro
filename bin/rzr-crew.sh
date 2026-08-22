#!/usr/bin/env bash
# rzr-crew.sh - inspect crewmember presets (spawn profiles).
#
# Usage:
#   rzr-crew.sh list            list preset names + a one-line summary
#   rzr-crew.sh show <name>     print a preset's JSON
#   rzr-crew.sh path <name>     print the file path of a preset
#
# A preset bundles HOW a crew agent is booted (harness, model, effort, fast,
# permission mode, standing rules) - never WHAT its task is. Presets are plain
# JSON files under $ROZORO_HOME/crew/<name>.json; create or edit them by hand.
# `default` resolves from default.json when present. Without that file it falls
# back to sonnet/Claude, gpt-5.6-sol/low for Codex, or auto/yolo for Copilot.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

print_row() {  # <name>
  local name="$1" json harness perm
  rzr_crew_validate "$name" || rzr_die "crew preset '$name' has invalid JSON or known field types"
  json="$(rzr_crew_json "$name")"
  harness="$(printf '%s' "$json" | jq -r '.harness // "-"' 2>/dev/null)"
  if [ "$harness" = codex ] || [ "$harness" = copilot ]; then
    perm="yolo"
  else
    perm="$(printf '%s' "$json" | jq -r 'if (.permission_mode // "") == "" then "-" else .permission_mode end' 2>/dev/null)"
  fi
  printf '%-14s %-8s %-12s %-6s %-5s %-6s %s\n' \
    "$name" \
    "$harness" \
    "$(printf '%s' "$json" | jq -r '.model // "-"' 2>/dev/null)" \
    "$(printf '%s' "$json" | jq -r 'if (.effort // "") == "" then "-" else .effort end' 2>/dev/null)" \
    "$(printf '%s' "$json" | jq -r 'if .fast == true then "yes" else "no" end' 2>/dev/null)" \
    "$perm" \
    "$(printf '%s' "$json" | jq -r '(.rules // []) | length' 2>/dev/null)"
}

cmd="${1:-list}"
case "$cmd" in
  list)
    printf '%-14s %-8s %-12s %-6s %-5s %-6s %s\n' NAME HARNESS MODEL EFFORT FAST PERM RULES
    rzr_crew_exists default || print_row default
    for f in "$RZR_CREW"/*.json; do
      [ -e "$f" ] || continue
      name=$(basename "$f" .json)
      print_row "$name"
    done
    ;;
  show)
    [ $# -ge 2 ] || rzr_die "usage: rzr-crew.sh show <name>"
    rzr_crew_resolves "$2" || rzr_die "no such preset '$2' (rzr-crew.sh list)"
    rzr_crew_validate "$2" || rzr_die "crew preset '$2' has invalid JSON or known field types"
    rzr_crew_json "$2" | jq .
    ;;
  path)
    [ $# -ge 2 ] || rzr_die "usage: rzr-crew.sh path <name>"
    rzr_crew_resolves "$2" || rzr_die "no such preset '$2'"
    rzr_crew_path "$2"
    ;;
  -h|--help) sed -n '2,13p' "$0" ;;
  *) rzr_die "unknown command '$cmd' (list | show <name> | path <name>)" ;;
esac
