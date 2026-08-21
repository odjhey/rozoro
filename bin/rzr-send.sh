#!/usr/bin/env bash
# rzr-send.sh - send a DATA-plane message: text the agent reads and reasons about.
#
# Usage:
#   rzr-send.sh <id> <text>            submit <text> as a prompt to the agent
#   rzr-send.sh <id> <text> --wait     ...and block until the agent settles
#
# This is the DATA plane, and ONLY the data plane: free text that becomes part
# of the agent's own context, via `herdr agent prompt` (types + submits
# atomically; rejected up front if the agent is blocked). It never executes a
# lifecycle action - for CONTROL-plane verbs (interrupt, cancel, a raw key
# press, stop, restart), use rzr-control.sh, a closed verb list that is
# EXECUTED, never handed to the agent as something to read. Keeping the two
# apart is the whole point: a lifecycle command must never arrive as chat the
# agent might interpret instead of the harness carrying out.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-send.sh <id> <text> [--wait]"
ID="$1"; shift
rzr_task_exists "$ID" || rzr_die "no such task '$ID'"
PANE="$(rzr_pane_of "$ID")"

PAYLOAD="" ; WAIT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --wait) WAIT=1; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    -*) rzr_die "unknown flag: $1 (rzr-send.sh is data-plane only - interrupt/cancel/key/stop/restart live in rzr-control.sh)" ;;
    *)  PAYLOAD="$1"; shift ;;
  esac
done
[ -n "$PAYLOAD" ] || rzr_die "nothing to send"

args=(agent prompt "$PANE" "$PAYLOAD")
[ "$WAIT" -eq 1 ] && args+=(--wait)
if rzr_herdr "${args[@]}" >/dev/null 2>&1; then
  echo "rzr: sent to '$ID'"
else
  rzr_die "herdr rejected the prompt to '$ID' (agent blocked, or pane gone)"
fi
