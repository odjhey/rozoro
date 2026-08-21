#!/usr/bin/env bash
# fl-send.sh - send input to a task's agent.
#
# Usage:
#   fl-send.sh <id> <text>            submit <text> as a prompt to the agent
#   fl-send.sh <id> <text> --wait     ...and block until the agent settles
#   fl-send.sh <id> --key <name>      send a raw key (enter|escape|ctrl+c|...)
#   fl-send.sh <id> --text <text>     type literal text WITHOUT submitting
#
# The default path is `herdr agent prompt`, which types the text and submits it
# in one call and is rejected up front if the agent is blocked. Raw keys and
# literal (unsubmitted) text drop to the pane primitives for interrupts and
# manual composition.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

[ $# -ge 1 ] || fl_die "usage: fl-send.sh <id> <text> | <id> --key <name> | <id> --text <text>"
ID="$1"; shift
fl_task_exists "$ID" || fl_die "no such task '$ID'"
PANE="$(fl_pane_of "$ID")"

MODE="prompt" ; PAYLOAD="" ; WAIT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --key)  MODE="key";  PAYLOAD="$2"; shift 2 ;;
    --text) MODE="text"; PAYLOAD="$2"; shift 2 ;;
    --wait) WAIT=1; shift ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    -*) fl_die "unknown flag: $1" ;;
    *)  PAYLOAD="$1"; shift ;;
  esac
done
[ -n "$PAYLOAD" ] || fl_die "nothing to send"

case "$MODE" in
  prompt)
    args=(agent prompt "$PANE" "$PAYLOAD")
    [ "$WAIT" -eq 1 ] && args+=(--wait)
    if fl_herdr "${args[@]}" >/dev/null 2>&1; then
      echo "fl: sent to '$ID'"
    else
      fl_die "herdr rejected the prompt to '$ID' (agent blocked, or pane gone)"
    fi
    ;;
  key)
    fl_herdr pane send-keys "$PANE" "$PAYLOAD" >/dev/null 2>&1 \
      && echo "fl: key '$PAYLOAD' -> '$ID'" || fl_die "send-keys failed"
    ;;
  text)
    fl_herdr pane send-text "$PANE" "$PAYLOAD" >/dev/null 2>&1 \
      && echo "fl: typed literal text -> '$ID' (not submitted)" || fl_die "send-text failed"
    ;;
esac
