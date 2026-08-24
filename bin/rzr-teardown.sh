#!/usr/bin/env bash
# rzr-teardown.sh - close a task's tab and remove its record.
# Usage: rzr-teardown.sh <id> [--keep-tab] [--force]
#   --keep-tab  remove the state record but leave the herdr tab open
#   --force     deprecated compatibility no-op
#
# Minimal and intentionally NOT clever: it closes the recorded tab and deletes
# only live Rozoro state. Repository/worktree cleanup and delivery policy belong
# to higher-level tools; teardown never inspects or mutates the recorded cwd.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-teardown.sh <id> [--keep-tab] [--force]"
ID="$1"; shift
KEEP=0; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --keep-tab) KEEP=1; shift ;;
    --force)    FORCE=1; shift ;;
    *) rzr_die "usage: rzr-teardown.sh <id> [--keep-tab] [--force]" ;;
  esac
done
rzr_task_exists "$ID" || rzr_die "no such task '$ID'"
[ "$FORCE" -eq 0 ] || echo "rzr: warning: --force is deprecated and unnecessary; teardown never inspects repository state" >&2

TAB=$(rzr_meta_get "$ID" tab || true)
ADAPTER_PID=$(rzr_meta_get "$ID" event_adapter_pid || true)
if [[ "$ADAPTER_PID" =~ ^[0-9]+$ ]] && [ -r "/proc/$ADAPTER_PID/cmdline" ] && \
   tr '\0' ' ' <"/proc/$ADAPTER_PID/cmdline" | grep -Fq "rzr-codex-event-adapter.py --task $ID "; then
  kill "$ADAPTER_PID" 2>/dev/null || true
fi
if [ "$KEEP" -eq 0 ] && [ -n "$TAB" ]; then
  rzr_herdr tab close "$TAB" >/dev/null 2>&1 \
    && echo "rzr: closed tab $TAB" \
    || echo "rzr: warning: could not close tab $TAB (already gone?)" >&2
fi
rm -f "$(rzr_meta_path "$ID")" "$(rzr_status_path "$ID")" \
  "$RZR_STATE/$ID.runtime.json" "$RZR_STATE/$ID.runtime.json.lock" "$RZR_STATE/$ID.runtime.json".*
echo "rzr: removed task '$ID'"
