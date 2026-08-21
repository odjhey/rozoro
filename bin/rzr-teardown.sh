#!/usr/bin/env bash
# rzr-teardown.sh - close a task's tab and remove its record.
# Usage: rzr-teardown.sh <id> [--keep-tab] [--force]
#   --keep-tab  remove the state record but leave the herdr tab open
#   --force     tear down even if the crew's cwd has unlanded work
#
# Minimal and intentionally NOT clever: it closes the recorded tab and deletes
# state/<id>.meta. The one thing it refuses by default is discarding a crew's
# unlanded work - uncommitted/untracked changes or unpushed commits in the
# task's recorded cwd (rzr_unlanded_reasons, rzr-lib.sh) - since that's silent
# data loss, not a scratch-harness tradeoff. --force bypasses the check.
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

if [ "$FORCE" -eq 0 ]; then
  CWD=$(rzr_meta_get "$ID" cwd || true)
  if [ -n "$CWD" ]; then
    REASONS=$(rzr_unlanded_reasons "$CWD")
    if [ -n "$REASONS" ]; then
      echo "rzr: refusing to tear down '$ID' - unlanded work in $CWD:" >&2
      echo "$REASONS" | sed 's/^/rzr:   - /' >&2
      echo "rzr: land it, or rerun with --force to discard anyway" >&2
      exit 1
    fi
  fi
fi

TAB=$(rzr_meta_get "$ID" tab || true)
if [ "$KEEP" -eq 0 ] && [ -n "$TAB" ]; then
  rzr_herdr tab close "$TAB" >/dev/null 2>&1 \
    && echo "rzr: closed tab $TAB" \
    || echo "rzr: warning: could not close tab $TAB (already gone?)" >&2
fi
rm -f "$(rzr_meta_path "$ID")" "$(rzr_status_path "$ID")"
echo "rzr: removed task '$ID'"
