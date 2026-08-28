#!/usr/bin/env bash
# rzr-send.sh - send a DATA-plane message: text the agent reads and reasons about.
#
# Usage:
#   rzr-send.sh <id> <text>                  submit <text> in this task's default
#                                             dispatch mode (see --mode below)
#   rzr-send.sh <id> <text> --mode followup  deliver only when the agent is idle, done,
#                                             or blocked - never steals a turn in
#                                             progress. Returns immediately: a
#                                             mid-turn agent's follow-up is handed to
#                                             the resident monitor, which delivers it
#                                             on the agent's next settle. Check it
#                                             later with `rozoro send-status <id>`.
#   rzr-send.sh <id> <text> --mode steer     deliver immediately regardless of the
#                                             agent's current state - the original,
#                                             turn-interrupting behavior. Needs no
#                                             resident monitor.
#   rzr-send.sh <id> <text> --timeout <ms>   how long a queued follow-up stays valid
#                                             before the monitor gives up (default
#                                             120000)
#   rzr-send.sh <id> <text> --wait           ...and block until the agent settles
#                                             after delivery (steer mode only)
#
# This is the DATA plane, and ONLY the data plane: free text that becomes part
# of the agent's own context, via `herdr agent prompt` (types + submits
# atomically; rejected up front if the agent is blocked). It never executes a
# lifecycle action - for CONTROL-plane verbs (interrupt, cancel, a raw key
# press, stop, restart), use rzr-control.sh, a closed verb list that is
# EXECUTED, never handed to the agent as something to read. Keeping the two
# apart is the whole point: a lifecycle command must never arrive as chat the
# agent might interpret instead of the harness carrying out.
#
# Dispatch mode defaults per the target's recorded harness (rzr_default_send_mode
# in rzr-lib.sh): `pi` crews default to followup; every other harness still
# defaults to steer (unchanged) until its followup path is validated too.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-send.sh <id> <text> [--mode steer|followup] [--timeout <ms>] [--wait]"
ID="$1"; shift
rzr_task_exists "$ID" || rzr_die "no such task '$ID'"
PANE="$(rzr_pane_of "$ID")"

PAYLOAD="" ; WAIT=0 ; MODE="" ; TIMEOUT_MS=120000
while [ $# -gt 0 ]; do
  case "$1" in
    --wait) WAIT=1; shift ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT_MS="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,35p' "$0"; exit 0 ;;
    -*) rzr_die "unknown flag: $1 (rzr-send.sh is data-plane only - interrupt/cancel/key/stop/restart live in rzr-control.sh)" ;;
    *)  PAYLOAD="$1"; shift ;;
  esac
done
[ -n "$PAYLOAD" ] || rzr_die "nothing to send"
case "$MODE" in
  ""|steer|followup) ;;
  *) rzr_die "unknown --mode '$MODE' (must be 'steer' or 'followup')" ;;
esac
case "$TIMEOUT_MS" in
  ''|*[!0-9]*) rzr_die "--timeout must be a positive integer (milliseconds)" ;;
esac
[ -n "$MODE" ] || MODE="$(rzr_default_send_mode "$(rzr_meta_get "$ID" harness || true)")"

rzr_send_deliver() {
  local args=(agent prompt "$PANE" "$PAYLOAD")
  [ "$WAIT" -eq 1 ] && args+=(--wait)
  if rzr_herdr "${args[@]}" >/dev/null 2>&1; then
    echo "rzr: sent to '$ID' (mode: $MODE)"
  else
    rzr_die "herdr rejected the prompt to '$ID' (agent blocked, or pane gone)"
  fi
}

if [ "$MODE" = steer ]; then
  rzr_send_deliver
  exit 0
fi

# Follow-up delivery is the resident monitor's job, not this process's. It
# already watches every crew pane, so it can deliver the moment the agent
# finishes its turn - and this call returns immediately either way, so a driver
# dispatching a follow-up never blocks its own turn waiting on a busy crew.
if ! OUT="$(python3 "$RZR_BIN/rzr-event-bus-client.py" send-enqueue \
    --task "$ID" --payload "$PAYLOAD" --timeout-ms "$TIMEOUT_MS")"; then
  rzr_die "could not reach the resident monitor to queue a follow-up for '$ID' - is rozorod running? (retry, or pass --mode steer to deliver now)"
fi
STATE="$(printf '%s' "$OUT" | jq -r '.state // "failed"')"
case "$STATE" in
  delivered) echo "rzr: sent to '$ID' (mode: followup)" ;;
  pending)
    echo "rzr: queued follow-up for '$ID' - it is mid-turn; the monitor delivers this once it goes idle (check: ./bin/rozoro send-status $ID)" ;;
  *)
    rzr_die "follow-up to '$ID' was not accepted: $(printf '%s' "$OUT" | jq -r '.error // "unknown error"') (pass --mode steer to deliver now)" ;;
esac
