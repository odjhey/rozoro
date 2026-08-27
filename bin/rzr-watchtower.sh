#!/usr/bin/env bash
# Inspect named, versioned watchtower presets and active registrations.
set -euo pipefail
# shellcheck disable=SC1091 # The library path is resolved beside this script.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

print_row() {
  local name="$1" json
  rzr_wtpreset_validate "$name" || rzr_die "watchtower preset '$name' has invalid JSON or known field types"
  json="$(rzr_wtpreset_json "$name")"
  printf '%-18s %-8s %-20s %-8s %-12s %s\n' "$name" \
    "$(printf '%s' "$json" | jq -r '.harness // "-"')" \
    "$(printf '%s' "$json" | jq -r '.model // "-"')" \
    "$(printf '%s' "$json" | jq -r 'if (.effort // "") == "" then "-" else .effort end')" \
    "$(printf '%s' "$json" | jq -r 'if (.mission // "") == "" then "delivery" else .mission end')" \
    "$(printf '%s' "$json" | jq -r '.version // 0')"
}

cmd="${1:-list}"
case "$cmd" in
  list)
    printf '%-18s %-8s %-20s %-8s %-12s %s\n' NAME HARNESS MODEL EFFORT MISSION VERSION
    for f in "$RZR_WT_PRESETS"/*.json; do [ -e "$f" ] || continue; print_row "$(basename "$f" .json)"; done ;;
  show)
    [ $# -ge 2 ] || rzr_die "usage: rzr-watchtower.sh show <name>"
    rzr_wtpreset_exists "$2" || rzr_die "no such watchtower preset '$2'"
    rzr_wtpreset_validate "$2" || rzr_die "watchtower preset '$2' has invalid JSON or known field types"
    rzr_wtpreset_json "$2" | jq . ;;
  path)
    [ $# -ge 2 ] || rzr_die "usage: rzr-watchtower.sh path <name>"
    rzr_wtpreset_exists "$2" || rzr_die "no such watchtower preset '$2'"
    rzr_wtpreset_path "$2" ;;
  registered)
    printf '%-24s %-18s %-20s %-8s %-8s %s\n' DRIVER NAME PRESET@VERSION HARNESS BACKEND CREATED
    rzr_watchtower_target_json |
      while IFS= read -r json; do
        printf '%s' "$json" | jq -r '[.driver_id // "-", .watchtower_name // "-", (if .preset.name then (.preset.name + "@" + ((.preset.version // "0")|tostring)) else "-" end), .harness // "-", .backend // "-", .created // "-"] | @tsv' |
          while IFS=$'\t' read -r driver name preset harness backend created; do printf '%-24s %-18s %-20s %-8s %-8s %s\n' "$driver" "$name" "$preset" "$harness" "$backend" "$created"; done
      done ;;
  -h|--help) echo "usage: ./bin/rozoro watchtower list|show <name>|path <name>|registered" ;;
  *) rzr_die "unknown command '$cmd' (list | show <name> | path <name> | registered)" ;;
esac
