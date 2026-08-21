#!/usr/bin/env bash
# fl-watch.sh - event-driven fleet monitor.
#
# Usage:
#   fl-watch.sh [--once] [id ...]
#     (no ids) watch every known task; otherwise just the listed ids
#     --once   print the first event that arrives, then exit (handy for tests)
#
# Zero polling. For each task it blocks on herdr's native `agent wait`, armed to
# fire the instant the pane's agent state changes to anything OTHER than its
# current state (edge detection - no busy-wait, no immediate-return spin). When a
# waiter fires it prints one wake line and re-arms that task against its new
# state. A task whose pane has gone away prints `gone` and drops out.
#
# Wake line format (TAB-separated):
#   <iso-time>  <id>  <status>     status in: idle working done blocked unknown gone
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

ONCE=0 ; declare -a WANT=()
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) fl_die "unknown flag: $1" ;;
    *)  WANT+=("$1"); shift ;;
  esac
done
[ "${#WANT[@]}" -gt 0 ] || mapfile -t WANT < <(fl_task_ids)
[ "${#WANT[@]}" -gt 0 ] || fl_die "no tasks to watch"

# The --until set that means "any state except <current>".
until_except() {  # <state>
  local s
  for s in idle working done blocked unknown; do
    [ "$s" = "$1" ] || printf ' --until %s' "$s"
  done
}

PIPE="$FL_STATE/.watch.$$.pipe"
mkfifo "$PIPE" || fl_die "could not create event pipe"
exec 3<>"$PIPE"
cleanup() { exec 3>&- 2>/dev/null || true; rm -f "$PIPE"; pkill -P $$ 2>/dev/null || true; }
trap cleanup EXIT INT TERM

declare -A LAST=()   # id -> last observed status
declare -A PANE=()   # id -> pane

# Background waiter: block until the pane leaves <state>, then emit one event.
arm() {  # <id> <pane> <state>
  local id="$1" pane="$2" state="$3" untils
  untils=$(until_except "$state")
  (
    local out rc st
    # shellcheck disable=SC2086
    out=$(fl_herdr agent wait "$pane" $untils 2>/dev/null); rc=$?
    if [ $rc -ne 0 ]; then
      st=gone
    else
      st=$(printf '%s' "$out" | jq -r '.result.agent_status // .result.status // .agent_status // "unknown"' 2>/dev/null | grep . || echo unknown)
    fi
    printf '%s\t%s\t%s\n' "$id" "$pane" "$st" >&3
  ) &
}

# Seed: record each task's current state and arm a waiter for it.
for id in "${WANT[@]}"; do
  fl_task_exists "$id" || { echo "fl: skip unknown task '$id'" >&2; continue; }
  p=$(fl_pane_of "$id"); s=$(fl_agent_status "$p")
  PANE[$id]="$p"; LAST[$id]="$s"
  printf '%s\t%s\t%s\t(initial)\n' "$(date -u +%H:%M:%S)" "$id" "$s"
  case "$s" in
    gone|shell) echo "fl: '$id' has no agent to watch ($s); skipping" >&2; unset 'PANE[$id]'; continue ;;
  esac
  arm "$id" "$p" "$s"
done
[ "${#PANE[@]}" -gt 0 ] || fl_die "no live tasks to watch"

# Event loop: block on the next wake line, print it, re-arm (unless gone).
while [ "${#PANE[@]}" -gt 0 ]; do
  IFS=$'\t' read -r id pane st <&3 || break
  printf '%s\t%s\t%s\n' "$(date -u +%H:%M:%S)" "$id" "$st"
  LAST[$id]="$st"
  if [ "$ONCE" -eq 1 ]; then break; fi
  if [ "$st" = gone ]; then unset 'PANE[$id]'; continue; fi
  arm "$id" "$pane" "$st"
done
