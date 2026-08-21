#!/usr/bin/env bash
# fl-teardown.sh - close a task's tab and remove its record.
# Usage: fl-teardown.sh <id> [--keep-tab]
#   --keep-tab  remove the state record but leave the herdr tab open
#
# Minimal and intentionally NOT clever: it closes the recorded tab and deletes
# state/<id>.meta. It does not verify unlanded work - this is a scratch harness,
# not firstmate. Grow that guard in if you build ship semantics on top.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

[ $# -ge 1 ] || fl_die "usage: fl-teardown.sh <id> [--keep-tab]"
ID="$1"; shift
KEEP=0
[ "${1:-}" = "--keep-tab" ] && KEEP=1
fl_task_exists "$ID" || fl_die "no such task '$ID'"

TAB=$(fl_meta_get "$ID" tab || true)
if [ "$KEEP" -eq 0 ] && [ -n "$TAB" ]; then
  fl_herdr tab close "$TAB" >/dev/null 2>&1 \
    && echo "fl: closed tab $TAB" \
    || echo "fl: warning: could not close tab $TAB (already gone?)" >&2
fi
rm -f "$(fl_meta_path "$ID")"
echo "fl: removed task '$ID'"
