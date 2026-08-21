#!/usr/bin/env bash
# rzr-list.sh - show known tasks and their live agent state.
# Usage: rzr-list.sh
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

ids=$(rzr_task_ids || true)
[ -n "$ids" ] || { echo "rzr: no tasks"; exit 0; }

printf '%-14s %-10s %-9s %-10s %s\n' ID STATE PANE TAB CWD
while IFS= read -r id; do
  [ -n "$id" ] || continue
  pane=$(rzr_meta_get "$id" pane || echo "?")
  tab=$(rzr_meta_get "$id" tab || echo "?")
  cwd=$(rzr_meta_get "$id" cwd || echo "?")
  state=$(rzr_agent_status "$pane")
  printf '%-14s %-10s %-9s %-10s %s\n' "$id" "$state" "$pane" "$tab" "$cwd"
done <<< "$ids"
