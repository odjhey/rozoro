#!/usr/bin/env bash
# fl-crew.sh - inspect crewmember presets (spawn profiles).
#
# Usage:
#   fl-crew.sh list            list preset names + a one-line summary
#   fl-crew.sh show <name>     print a preset's JSON
#   fl-crew.sh path <name>     print the file path of a preset
#
# A preset bundles HOW a crew agent is booted (harness, model, effort,
# permission mode, standing rules) - never WHAT its task is. Presets are plain
# JSON files under $ROZORO_HOME/crew/<name>.json; create or edit them by hand.
# The built-in `default` (sonnet claude, auto permission, no rules) is written
# on first use. See fl-spawn.sh --crew.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

fl_crew_ensure_default

cmd="${1:-list}"
case "$cmd" in
  list)
    printf '%-14s %-8s %-10s %-6s %-6s %s\n' NAME HARNESS MODEL EFFORT PERM RULES
    for f in "$FL_CREW"/*.json; do
      [ -e "$f" ] || continue
      name=$(basename "$f" .json)
      printf '%-14s %-8s %-10s %-6s %-6s %s\n' \
        "$name" \
        "$(jq -r '.harness // "-"' "$f" 2>/dev/null)" \
        "$(jq -r '.model // "-"' "$f" 2>/dev/null)" \
        "$(jq -r 'if (.effort // "") == "" then "-" else .effort end' "$f" 2>/dev/null)" \
        "$(jq -r 'if (.permission_mode // "") == "" then "-" else .permission_mode end' "$f" 2>/dev/null)" \
        "$(jq -r '(.rules // []) | length' "$f" 2>/dev/null)"
    done
    ;;
  show)
    [ $# -ge 2 ] || fl_die "usage: fl-crew.sh show <name>"
    fl_crew_exists "$2" || fl_die "no such preset '$2' (fl-crew.sh list)"
    jq . "$(fl_crew_path "$2")"
    ;;
  path)
    [ $# -ge 2 ] || fl_die "usage: fl-crew.sh path <name>"
    fl_crew_exists "$2" || fl_die "no such preset '$2'"
    fl_crew_path "$2"
    ;;
  -h|--help) sed -n '2,13p' "$0" ;;
  *) fl_die "unknown command '$cmd' (list | show <name> | path <name>)" ;;
esac
