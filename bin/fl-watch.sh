#!/usr/bin/env bash
# fl-watch.sh - event-driven fleet monitor.
#
# Usage:
#   fl-watch.sh [--once] [id ...]
#     (no ids) watch every known task; otherwise just the listed ids
#     --once   print the first event that arrives, then exit (handy for tests)
#
# Zero polling, genuinely: it consumes herdr's native pane.agent_status_changed
# PUSH stream over the control socket (via bin/herdr-eventwait.py). Every stream
# message IS a real edge, so there is no re-arm loop and nothing to spin. (The
# older design re-armed `agent wait --until`, which is LEVEL-triggered and
# returned instantly while a pane sat in a transient `unknown` state - a busy
# wait. The push stream removes that failure mode by construction.) Each edge is
# deduped against the last status on disk and only real changes are printed and
# persisted to state/<id>.status, so the driver can reconcile crew state.
#
# Wake line format (TAB-separated):
#   <iso-time>  <id>  <status>     status in: idle working done blocked unknown gone
#
# Requires: python3 (stdlib only) for the socket subscriber.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

ONCE=0 ; declare -a WANT=()
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    -*) fl_die "unknown flag: $1" ;;
    *)  WANT+=("$1"); shift ;;
  esac
done
# (no ids given) watch every known task. Read loop instead of `mapfile` so this
# runs on stock macOS bash 3.2, which has no mapfile/readarray.
if [ "${#WANT[@]}" -eq 0 ]; then
  while IFS= read -r _id; do WANT+=("$_id"); done < <(fl_task_ids)
fi
[ "${#WANT[@]}" -gt 0 ] || fl_die "no tasks to watch"

command -v python3 >/dev/null 2>&1 || fl_die "python3 not found on PATH (needed for the event stream)"
SOCK=$(fl_socket_path)
[ -n "$SOCK" ] && [ -S "$SOCK" ] || fl_die "could not resolve herdr control socket (is the server running?)"

# Parallel indexed arrays (bash-3.2 safe; no associative arrays): the watched
# panes to subscribe to, and the id each pane maps back to when an edge arrives.
declare -a IDS=() PANES=()
id_for_pane() {  # <pane> -> id, or fail
  local i=0
  while [ "$i" -lt "${#PANES[@]}" ]; do
    [ "${PANES[$i]}" = "$1" ] && { printf '%s' "${IDS[$i]}"; return 0; }
    i=$((i + 1))
  done
  return 1
}

# Seed / level-reconcile: record each task's current state up front (so the disk
# status is authoritative from t0 and the driver can read it immediately), and
# collect the live panes to subscribe to. Reading status here, just before we
# subscribe, leaves a sub-second window where an edge could land before the
# subscription is live; the next edge corrects the disk status, and agent-state
# changes are seconds apart, so in practice nothing is missed.
for id in "${WANT[@]}"; do
  fl_task_exists "$id" || { echo "fl: skip unknown task '$id'" >&2; continue; }
  p=$(fl_pane_of "$id"); s=$(fl_agent_status "$p")
  fl_status_set "$id" "$s"
  printf '%s\t%s\t%s\t(initial)\n' "$(date -u +%H:%M:%S)" "$id" "$s"
  case "$s" in
    gone|shell) echo "fl: '$id' has no agent to watch ($s); skipping" >&2; continue ;;
  esac
  IDS+=("$id"); PANES+=("$p")
done
[ "${#PANES[@]}" -gt 0 ] || fl_die "no live tasks to watch"

# Subscribe to the push stream for all live panes. The reader writes one line
# per edge to a fifo; we hold only the READ end so its exit surfaces as EOF.
PIPE="$FL_STATE/.watch.$$.pipe"
mkfifo "$PIPE" || fl_die "could not create event pipe"
SUBPID=""
cleanup() {
  [ -n "$SUBPID" ] && kill "$SUBPID" 2>/dev/null || true
  exec 3<&- 2>/dev/null || true
  rm -f "$PIPE"
}
trap cleanup EXIT INT TERM

python3 "$(fl_eventwait_py)" "$SOCK" 0 "${PANES[@]}" > "$PIPE" 2>/dev/null &
SUBPID=$!
exec 3< "$PIPE"

IFS= read -r ack <&3 || fl_die "event subscriber closed before acknowledging (socket $SOCK)"
[ "$ack" = "@subscribed" ] || fl_die "unexpected event subscriber output: $ack"

# Event loop: block on the next pushed edge, print+persist only REAL changes.
# A `<pane> <ws> <status> <agent>` line whose status equals the last one on disk
# is a no-op (dedup key = disk status); print nothing, churn nothing. When the
# subscriber exits (socket closed / all panes gone) the read returns EOF and we
# stop.
while IFS=$'\t' read -r pane ws st agent <&3; do
  id=$(id_for_pane "$pane") || continue
  prev=$(fl_status_get "$id" 2>/dev/null || true)
  [ "$st" = "$prev" ] && continue
  printf '%s\t%s\t%s\n' "$(date -u +%H:%M:%S)" "$id" "$st"
  fl_status_set "$id" "$st"
  [ "$ONCE" -eq 1 ] && break
done
