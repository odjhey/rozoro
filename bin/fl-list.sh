#!/usr/bin/env bash
# fl-list.sh - show known tasks and their live agent state.
# Usage: fl-list.sh
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

ids=$(fl_task_ids || true)
[ -n "$ids" ] || { echo "fl: no tasks"; exit 0; }

printf '%-14s %-10s %-9s %-10s %s\n' ID STATE PANE TAB CWD
while IFS= read -r id; do
  [ -n "$id" ] || continue
  pane=$(fl_meta_get "$id" pane || echo "?")
  tab=$(fl_meta_get "$id" tab || echo "?")
  cwd=$(fl_meta_get "$id" cwd || echo "?")
  state=$(fl_agent_status "$pane")
  printf '%-14s %-10s %-9s %-10s %s\n' "$id" "$state" "$pane" "$tab" "$cwd"
done <<< "$ids"
