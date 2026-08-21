#!/usr/bin/env bash
# rzr-send.sh - send input to a task's agent.
#
# Usage:
#   rzr-send.sh <id> <text>            submit <text> as a prompt to the agent
#   rzr-send.sh <id> <text> --wait     ...and block until the agent settles
#   rzr-send.sh <id> --key <name>      send a raw key (enter|escape|ctrl+c|...)
#   rzr-send.sh <id> --text <text>     type literal text WITHOUT submitting
#
# The default path is `herdr agent prompt`, which types the text and submits it
# in one call and is rejected up front if the agent is blocked. Raw keys and
# literal (unsubmitted) text drop to the pane primitives for interrupts and
# manual composition.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-send.sh <id> <text> | <id> --key <name> | <id> --text <text>"
ID="$1"; shift
rzr_task_exists "$ID" || rzr_die "no such task '$ID'"
PANE="$(rzr_pane_of "$ID")"

MODE="prompt" ; PAYLOAD="" ; WAIT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --key)  MODE="key";  PAYLOAD="$2"; shift 2 ;;
    --text) MODE="text"; PAYLOAD="$2"; shift 2 ;;
    --wait) WAIT=1; shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    -*) rzr_die "unknown flag: $1" ;;
    *)  PAYLOAD="$1"; shift ;;
  esac
done
[ -n "$PAYLOAD" ] || rzr_die "nothing to send"

case "$MODE" in
  prompt)
    args=(agent prompt "$PANE" "$PAYLOAD")
    [ "$WAIT" -eq 1 ] && args+=(--wait)
    if rzr_herdr "${args[@]}" >/dev/null 2>&1; then
      echo "rzr: sent to '$ID'"
    else
      rzr_die "herdr rejected the prompt to '$ID' (agent blocked, or pane gone)"
    fi
    ;;
  key)
    rzr_herdr pane send-keys "$PANE" "$PAYLOAD" >/dev/null 2>&1 \
      && echo "rzr: key '$PAYLOAD' -> '$ID'" || rzr_die "send-keys failed"
    ;;
  text)
    rzr_herdr pane send-text "$PANE" "$PAYLOAD" >/dev/null 2>&1 \
      && echo "rzr: typed literal text -> '$ID' (not submitted)" || rzr_die "send-text failed"
    ;;
esac
