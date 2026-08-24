#!/usr/bin/env bash
# rzr-reconcile.sh - process a watchtower's pending wake ledger and acknowledge it.
#
# Usage:
#   rzr-reconcile.sh [--driver <id>] [--json]
#
# The driver runs this when a wake nudge arrives. It snapshots the pending
# generation, reports each affected task's handoff verdict (via rzr-status
# --json), flags any task that vanished, and then advances `ack` to EXACTLY the
# generation it snapshotted — never a later one, so an edge that lands mid-reconcile
# stays pending and re-nudges. Acking a wake is separate from resolving a crew's
# OPEN items: this never advances rzr-ack, so a needs-action/blocked verdict keeps
# surfacing until the driver explicitly handles it.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

DRIVER="" JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --driver) DRIVER="${2:-}"; shift 2 ;;
    --json) JSON=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) rzr_die "unknown flag: $1" ;;
  esac
done

DIR="$(rzr_resolve_driver_dir "$DRIVER")"

if [ "${ROZORO_LEGACY_DIAGNOSTIC:-0}" != 1 ]; then
  args=(reconcile --driver "$(basename "$DIR")")
  [ "$JSON" -eq 1 ] && args+=(--json)
  exec python3 "$RZR_BIN/rzr-event-bus-client.py" "${args[@]}"
fi

GEN="$(rzr_ledger_int "$DIR" generation)"

# Gather the affected tasks recorded in the ledger, newest snapshot wins. For each
# still-known task, take a real status snapshot; a task with no folder vanished.
STATUSES="$(RZR_RC_PENDING="$DIR/pending.json" python3 - <<'PY'
import json, os
try:    d = json.load(open(os.environ["RZR_RC_PENDING"]))
except Exception: d = {}
for tid in sorted((d.get("tasks") or {}).keys()):
    print(tid)
PY
)"

REPORTS="[]" VANISHED="[]"
if [ -n "$STATUSES" ]; then
  reports=""; vanished=""
  while IFS= read -r tid; do
    [ -n "$tid" ] || continue
    if [ -f "$(rzr_task_dir "$tid")/handoff.md" ]; then
      line="$("$RZR_BIN/rzr-status.sh" "$tid" --json 2>/dev/null || true)"
      [ -n "$line" ] && reports="$reports$line
"
    elif rzr_task_exists "$tid"; then
      : # known but no handoff yet; leave to the driver's status loop
    else
      vanished="$vanished$tid
"
    fi
  done <<EOF
$STATUSES
EOF
  REPORTS="$(printf '%s' "$reports" | jq -s '.' 2>/dev/null || echo '[]')"
  VANISHED="$(printf '%s' "$vanished" | jq -R 'select(length>0)' 2>/dev/null | jq -s '.' 2>/dev/null || echo '[]')"
fi

# Acknowledge exactly the snapshotted generation (not any later edge).
rzr_ledger_ack "$DIR" "$GEN"

if [ "$JSON" -eq 1 ]; then
  jq -n --arg driver "$(basename "$DIR")" --argjson gen "$GEN" \
        --argjson reports "$REPORTS" --argjson vanished "$VANISHED" \
        '{driver: $driver, acknowledged_generation: $gen, reports: $reports, vanished: $vanished}'
  exit 0
fi

echo "reconciled driver $(basename "$DIR") through generation $GEN"
printf '%s' "$REPORTS" | jq -r '.[] | "  \(.id): runtime=\(.runtime_status) task=\(.task_status) turn=\(.turn_report_status) action=\(.action_reason // "none")"' 2>/dev/null || true
printf '%s' "$VANISHED" | jq -r '.[] | "  \(.) : vanished (no task folder)"' 2>/dev/null || true
