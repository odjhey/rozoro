#!/usr/bin/env bash
# rzr-watch.sh - event-driven fleet monitor.
#
# Usage:
#   rzr-watch.sh [--once] [--wake-codex] [id ...]
#     (no ids) watch every known task; otherwise just the listed ids
#     --once   exit after the first real edge (or first queued settled edge when
#              combined with --wake-codex)
#     --wake-codex  queue a fixed reconciliation nudge to $CODEX_THREAD_ID on
#                   settled edges (idle, done, or blocked)
#
# Zero polling, genuinely: it consumes herdr's native pane.agent_status_changed
# PUSH stream over the control socket (via bin/herdr-eventwait.py). Every stream
# message IS a real edge, so there is no re-arm loop and nothing to spin. (The
# older design re-armed `agent wait --until`, which is LEVEL-triggered and
# returned instantly while a pane sat in a transient `unknown` state - a busy
# wait. The push stream removes that failure mode by construction.) Each edge is
# deduped against this watcher's OWN last-seen status (per-process, so overlapping
# watchers on the same id don't suppress each other's --once break) and only real
# changes are printed and mirrored to state/<id>.status for the driver to read.
#
# Wake line format (TAB-separated):
#   <iso-time>  <id>  <status>     status in: idle working done blocked unknown gone
#
# Requires: python3 (stdlib only) for the socket subscriber.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

ONCE=0 WAKE_CODEX=0 ; declare -a WANT=()
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1; shift ;;
    --wake-codex) WAKE_CODEX=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    -*) rzr_die "unknown flag: $1" ;;
    *)  WANT+=("$1"); shift ;;
  esac
done

# This is intentionally a fixed adapter, not a configurable command or message:
# event/task/handoff data must never become instructions queued into Codex.
if [ "$WAKE_CODEX" -eq 1 ]; then
  [ -n "${CODEX_THREAD_ID:-}" ] || rzr_die "--wake-codex requires CODEX_THREAD_ID from the resident Codex thread"
  command -v codex >/dev/null 2>&1 || rzr_die "--wake-codex requires 'codex' on PATH"
  codex queue --help >/dev/null 2>&1 || rzr_die "installed 'codex' does not provide the queue capability"
fi
# (no ids given) watch every known task. Read loop instead of `mapfile` so this
# runs on stock macOS bash 3.2, which has no mapfile/readarray.
if [ "${#WANT[@]}" -eq 0 ]; then
  while IFS= read -r _id; do WANT+=("$_id"); done < <(rzr_task_ids)
fi
[ "${#WANT[@]}" -gt 0 ] || rzr_die "no tasks to watch"

command -v python3 >/dev/null 2>&1 || rzr_die "python3 not found on PATH (needed for the event stream)"
SOCK=$(rzr_socket_path)
[ -n "$SOCK" ] && [ -S "$SOCK" ] || rzr_die "could not resolve herdr control socket (is the server running?)"

# Parallel indexed arrays (bash-3.2 safe; no associative arrays): the watched
# panes to subscribe to, the id each pane maps back to when an edge arrives, and
# this process's own last-seen status per pane (SEEN). SEEN is the dedup key for
# printing and for the --once break: it is PER-PROCESS, so a sibling watcher
# advancing the shared on-disk status can never suppress this process's break
# (see the event loop below).
declare -a IDS=() PANES=() SEEN=()
idx_for_pane() {  # <pane> -> index into IDS/PANES/SEEN, or fail
  local i=0
  while [ "$i" -lt "${#PANES[@]}" ]; do
    [ "${PANES[$i]}" = "$1" ] && { printf '%s' "$i"; return 0; }
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
  rzr_task_exists "$id" || { echo "rzr: skip unknown task '$id'" >&2; continue; }
  p=$(rzr_pane_of "$id"); s=$(rzr_agent_status "$p")
  rzr_status_set "$id" "$s"
  printf '%s\t%s\t%s\t(initial)\n' "$(date -u +%H:%M:%S)" "$id" "$s"
  case "$s" in
    gone|shell) echo "rzr: '$id' has no agent to watch ($s); skipping" >&2; continue ;;
  esac
  IDS+=("$id"); PANES+=("$p"); SEEN+=("$s")
done
[ "${#PANES[@]}" -gt 0 ] || rzr_die "no live tasks to watch"

# Subscribe to the push stream for all live panes. The reader writes one line
# per edge to a fifo; we hold only the READ end so its exit surfaces as EOF.
PIPE="$RZR_STATE/.watch.$$.pipe"
mkfifo "$PIPE" || rzr_die "could not create event pipe"
SUBPID=""
cleanup() {
  [ -n "$SUBPID" ] && kill "$SUBPID" 2>/dev/null || true
  exec 3<&- 2>/dev/null || true
  rm -f "$PIPE"
}
trap cleanup EXIT INT TERM

python3 "$(rzr_eventwait_py)" "$SOCK" 0 "${PANES[@]}" > "$PIPE" 2>/dev/null &
SUBPID=$!
exec 3< "$PIPE"

IFS= read -r ack <&3 || rzr_die "event subscriber closed before acknowledging (socket $SOCK)"
[ "$ack" = "@subscribed" ] || rzr_die "unexpected event subscriber output: $ack"

# Event loop: block on the next pushed edge, print+persist only REAL changes.
# A `<pane> <ws> <status> <agent>` line whose status equals THIS PROCESS's last
# seen status for that pane (SEEN) is a no-op; print nothing, churn nothing. The
# dedup key is deliberately per-process, NOT the shared on-disk status: with
# overlapping watchers on the same id, the first to process an edge would flip
# the disk file and (under --once) exit, and every sibling reading that already-
# advanced disk value would see st==prev, `continue`, and block forever waiting
# for a next edge that never comes. Keying on SEEN lets each watcher recognize
# and break on the same real edge independently. We still mirror every real edge
# to state/<id>.status (an idempotent, last-writer-wins token) so the driver can
# reconcile crew state. When the subscriber exits (socket closed / all panes
# gone) the read returns EOF and we stop.
while IFS=$'\t' read -r pane ws st agent <&3; do
  i=$(idx_for_pane "$pane") || continue
  [ "$st" = "${SEEN[$i]}" ] && continue
  id="${IDS[$i]}"
  printf '%s\t%s\t%s\n' "$(date -u +%H:%M:%S)" "$id" "$st"
  SEEN[$i]="$st"
  rzr_status_set "$id" "$st"
  QUEUED_WAKE=0
  if [ "$WAKE_CODEX" -eq 1 ]; then
    case "$st" in
      idle|done|blocked)
        codex queue --thread "$CODEX_THREAD_ID" --message "Rozoro watch edge: reconcile crew status." \
          || rzr_die "could not queue wake nudge to Codex thread '$CODEX_THREAD_ID'"
        QUEUED_WAKE=1
        ;;
    esac
  fi
  if [ "$ONCE" -eq 1 ] && { [ "$WAKE_CODEX" -eq 0 ] || [ "$QUEUED_WAKE" -eq 1 ]; }; then
    break
  fi
done
exit 0
