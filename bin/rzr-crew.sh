#!/usr/bin/env bash
# rzr-crew.sh - inspect crewmember presets (spawn profiles) and roles.
#
# Usage:
#   rzr-crew.sh list             list preset names + a one-line summary
#   rzr-crew.sh show <name>      print a preset's JSON
#   rzr-crew.sh path <name>      print the file path of a preset
#   rzr-crew.sh roles            list role names + their resolved summary
#   rzr-crew.sh role-show <role> print a role's resolved JSON
#   rzr-crew.sh role-path <role> print the file path of a role (need not exist)
#
# A preset bundles HOW a crew agent is booted (harness, model, effort, fast,
# permission mode, standing rules) - never WHAT its task is. Presets are plain
# JSON files under $ROZORO_HOME/crew/<name>.json; create or edit them by hand.
# `default` resolves from default.json when present. Without that file it falls
# back to sonnet/Claude, gpt-5.6-sol/low for Codex, or auto/yolo for Copilot.
#
# A role is a MACHINE-LOCAL preference for who plays a given part (e.g.
# "coder", "planner"), since different machines have different harness
# binaries installed. Role files live under $ROZORO_HOME/crew/roles/<role>.json
# (same shape as a preset). Unconfigured, `coder` falls back to Claude Sonnet
# and `planner` to Claude Opus. Spawn from one with `--role <role>` (mutually
# exclusive with `--crew`).
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

print_role_row() {  # <role>
  local role="$1" json harness perm source
  rzr_role_validate "$role" || rzr_die "role '$role' has invalid JSON or known field types"
  json="$(rzr_role_json "$role")"
  harness="$(printf '%s' "$json" | jq -r '.harness // "-"' 2>/dev/null)"
  if [ "$harness" = codex ] || [ "$harness" = copilot ]; then
    perm="yolo"
  else
    perm="$(printf '%s' "$json" | jq -r 'if (.permission_mode // "") == "" then "-" else .permission_mode end' 2>/dev/null)"
  fi
  rzr_role_exists "$role" && source=host-local || source=built-in
  printf '%-14s %-8s %-12s %-6s %-5s %-6s %-9s %s\n' \
    "$role" \
    "$harness" \
    "$(printf '%s' "$json" | jq -r '.model // "-"' 2>/dev/null)" \
    "$(printf '%s' "$json" | jq -r 'if (.effort // "") == "" then "-" else .effort end' 2>/dev/null)" \
    "$(printf '%s' "$json" | jq -r 'if .fast == true then "yes" else "no" end' 2>/dev/null)" \
    "$perm" \
    "$source" \
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
  roles)
    printf '%-14s %-8s %-12s %-6s %-5s %-6s %-9s %s\n' ROLE HARNESS MODEL EFFORT FAST PERM SOURCE RULES
    for role in $(rzr_role_names); do print_role_row "$role"; done
    ;;
  role-show)
    [ $# -ge 2 ] || rzr_die "usage: rzr-crew.sh role-show <role>"
    rzr_role_resolves "$2" || rzr_die "no such role '$2' (rzr-crew.sh roles)"
    rzr_role_validate "$2" || rzr_die "role '$2' has invalid JSON or known field types"
    rzr_role_json "$2" | jq .
    ;;
  role-path)
    [ $# -ge 2 ] || rzr_die "usage: rzr-crew.sh role-path <role>"
    rzr_role_path "$2"
    ;;
  -h|--help) sed -n '2,23p' "$0" ;;
  *) rzr_die "unknown command '$cmd' (list | show <name> | path <name> | roles | role-show <role> | role-path <role>)" ;;
esac
