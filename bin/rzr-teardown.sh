#!/usr/bin/env bash
# rzr-teardown.sh - close a task's tab and remove its record.
# Usage: rzr-teardown.sh <id> [--keep-tab]
#   --keep-tab  remove the state record but leave the herdr tab open
#
# Minimal and intentionally NOT clever: it closes the recorded tab and deletes
# state/<id>.meta. It does not verify unlanded work - this is a scratch harness,
# not a release tool. Grow that guard in if you build ship semantics on top.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-teardown.sh <id> [--keep-tab]"
ID="$1"; shift
KEEP=0
[ "${1:-}" = "--keep-tab" ] && KEEP=1
rzr_task_exists "$ID" || rzr_die "no such task '$ID'"

TAB=$(rzr_meta_get "$ID" tab || true)
if [ "$KEEP" -eq 0 ] && [ -n "$TAB" ]; then
  rzr_herdr tab close "$TAB" >/dev/null 2>&1 \
    && echo "rzr: closed tab $TAB" \
    || echo "rzr: warning: could not close tab $TAB (already gone?)" >&2
fi
rm -f "$(rzr_meta_path "$ID")" "$(rzr_status_path "$ID")"
echo "rzr: removed task '$ID'"
