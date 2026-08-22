#!/usr/bin/env bash
# Show task metadata plus pure persisted runtime/task/turn axes.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"
ids=$(rzr_task_ids || true); [ -n "$ids" ] || { echo "rzr: no tasks"; exit 0; }
printf '%-14s %-10s %-10s %-18s %-14s %-9s %-10s %s\n' ID RUNTIME BG TASK TURN PANE TAB CWD
while IFS= read -r id; do
 [ -n "$id" ] || continue; pane=$(rzr_meta_get "$id" pane || echo '?'); tab=$(rzr_meta_get "$id" tab || echo '?'); cwd=$(rzr_meta_get "$id" cwd || echo '?')
 if [ -f "$(rzr_task_dir "$id")/handoff.md" ]; then j=$("$RZR_BIN/rzr-status.sh" "$id" --json); runtime=$(printf '%s' "$j"|jq -r .runtime_status); bg=$(printf '%s' "$j"|jq -r .background_activity.state); task=$(printf '%s' "$j"|jq -r .task_status); turn=$(printf '%s' "$j"|jq -r .turn_report_status); else runtime=unknown; bg=unknown; task=no-handoff; turn=unobserved; fi
 printf '%-14s %-10s %-10s %-18s %-14s %-9s %-10s %s\n' "$id" "$runtime" "$bg" "$task" "$turn" "$pane" "$tab" "$cwd"
done <<< "$ids"
