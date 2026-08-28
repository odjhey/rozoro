#!/usr/bin/env bash
# rzr-send-status.sh - report the fate of this task's most recent follow-up.
#
# Usage:
#   rzr-send-status.sh <id>           human-readable state
#   rzr-send-status.sh <id> --json    the daemon's reply verbatim
#
# `rozoro send` in followup mode hands a mid-turn crew's text to the resident
# monitor and returns immediately, so this is how a driver learns whether that
# text has since landed. States: pending (waiting for the crew to settle),
# delivering (in flight), delivered, failed (see the reported error), or
# cancelled (a newer follow-up superseded it).
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-send-status.sh <id> [--json]"
ID="$1"; shift
JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --json) JSON=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) rzr_die "unknown arg: $1" ;;
  esac
done
rzr_task_exists "$ID" || rzr_die "no such task '$ID'"

if ! OUT="$(python3 "$RZR_BIN/rzr-event-bus-client.py" send-status --task "$ID")"; then
  rzr_die "could not reach the resident monitor for '$ID' - is rozorod running?"
fi
if [ "$JSON" -eq 1 ]; then
  printf '%s\n' "$OUT"
  exit 0
fi
if [ "$(printf '%s' "$OUT" | jq -r '.found')" != true ]; then
  echo "rzr: no follow-up on record for '$ID'"
  exit 0
fi
STATE="$(printf '%s' "$OUT" | jq -r '.state')"
ERROR="$(printf '%s' "$OUT" | jq -r '.error // ""')"
if [ -n "$ERROR" ]; then
  echo "rzr: follow-up for '$ID': $STATE ($ERROR)"
else
  echo "rzr: follow-up for '$ID': $STATE"
fi
