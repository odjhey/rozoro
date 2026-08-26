#!/usr/bin/env bash
# rzr-watch.sh - event-driven fleet monitor.
#
# Diagnostics/legacy compatibility only. Wake/management options are disabled
# unless ROZORO_LEGACY_DIAGNOSTIC=1 is explicitly set.
# Usage:
#   ROZORO_LEGACY_DIAGNOSTIC=1 rzr-watch.sh [--once] [--wake|--wake-codex|--wake-herdr] [--driver <id>] [id ...]
#     (no ids) watch every known task; otherwise just the listed ids
#     --once   exit after the first real edge (or first DELIVERED settled nudge
#              when combined with a wake option)
#     --wake        deliver a fixed reconciliation nudge on settled edges (idle,
#                   done, blocked) through the REGISTERED watchtower target (see
#                   rzr-register). Refuses to guess a backend from the environment.
#     --wake-codex  explicit compatibility backend: force the Codex queue
#     --wake-herdr  explicit compatibility backend: force the resident Herdr pane
#     --driver <id> select a registered driver explicitly (for --wake)
#
# All wake modes route through a durable per-driver ledger (see rzr-lib): the
# actionable generation is persisted BEFORE the backend call, bursts coalesce to
# one outstanding nudge, and the Herdr backend defers delivery while the driver is
# working or blocked instead of prompting into its turn.
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

ONCE=0 JSON=0 WAKE_REQUEST="" DRIVER="" ; declare -a WANT=()
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1; shift ;;
    --json) JSON=1; shift ;;
    --wake) WAKE_REQUEST=registered; shift ;;
    --wake-codex) WAKE_REQUEST=codex; shift ;;
    --wake-herdr) WAKE_REQUEST=herdr; shift ;;
    --driver) DRIVER="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    -*) rzr_die "unknown flag: $1" ;;
    *)  WANT+=("$1"); shift ;;
  esac
done

if [ -n "$WAKE_REQUEST" ] && [ "${ROZORO_LEGACY_DIAGNOSTIC:-0}" != 1 ]; then
  rzr_die "legacy wake management is disabled; use ROZORO_LEGACY_DIAGNOSTIC=1 only for explicit diagnostics/old-release compatibility"
fi

# Resolve the wake backend + immutable identity + durable ledger dir up front so a
# misconfigured watchtower fails before it subscribes. The nudge is a FIXED,
# content-free message: event/task/handoff data must never become instructions
# injected into the resident driver.
WAKE_BACKEND="" WAKE_IDENTITY="" DRIVER_DIR=""
case "$WAKE_REQUEST" in
  "") ;;
  registered)  # backend chosen by the validated registration, never by env priority
    WAKE_TARGET="$(rzr_resolve_driver_target "$DRIVER")"
    WAKE_DRIVER_IDENTITY="$(printf '%s' "$WAKE_TARGET" | jq -r '.__rzr_driver_identity // empty | if type == "array" then join(":") else empty end' 2>/dev/null)"
    [ -n "$WAKE_DRIVER_IDENTITY" ] || rzr_die "registered target is missing driver identity"
    export RZR_DRIVER_EXPECTED_IDENTITY="$WAKE_DRIVER_IDENTITY"
    WAKE_DRIVER="$(printf '%s' "$WAKE_TARGET" | jq -r '.driver_id // empty')"
    DRIVER_DIR="$(rzr_driver_dir_prepare "$WAKE_DRIVER")"
    RZR_DRIVER_EXPECTED_IDENTITY="$(rzr_driver_dir_identity "$DRIVER_DIR")"; export RZR_DRIVER_EXPECTED_IDENTITY
    rzr_driver_dir_open "$DRIVER_DIR" || rzr_die "watchtower directory changed"
    WAKE_BACKEND="$(rzr_target_field "$DRIVER_DIR" backend "$WAKE_TARGET")"
    WAKE_IDENTITY="$(rzr_target_field "$DRIVER_DIR" identity "$WAKE_TARGET")"
    [ -n "$WAKE_DRIVER" ] && [ -n "$WAKE_BACKEND" ] && [ -n "$WAKE_IDENTITY" ] || rzr_die "registered target is missing driver/backend/identity" ;;
  codex)
    [ -n "${CODEX_THREAD_ID:-}" ] || rzr_die "--wake-codex requires CODEX_THREAD_ID from the resident Codex thread"
    command -v codex >/dev/null 2>&1 || rzr_die "--wake-codex requires 'codex' on PATH"
    codex queue --help >/dev/null 2>&1 || rzr_die "installed 'codex' does not provide the queue capability"
    WAKE_BACKEND=codex; WAKE_IDENTITY="$CODEX_THREAD_ID"
    DRIVER_DIR="$(rzr_driver_dir "$(rzr_driver_id_for codex "$WAKE_IDENTITY")")" ;;
  herdr)
    [ -n "${HERDR_PANE_ID:-}" ] || rzr_die "--wake-herdr requires HERDR_PANE_ID from the resident Herdr pane"
    command -v herdr >/dev/null 2>&1 || rzr_die "--wake-herdr requires 'herdr' on PATH"
    WAKE_BACKEND=herdr; WAKE_IDENTITY="$HERDR_PANE_ID"
    DRIVER_DIR="$(rzr_driver_dir "$(rzr_driver_id_for herdr "$WAKE_IDENTITY")")" ;;
esac

# Deliver the fixed nudge through the resolved backend, recording the outcome in
# the ledger. Return codes: 0 delivered; 1 soft-retained (driver busy/blocked — a
# normal, expected wait that must NOT crash the watcher); 2 hard backend error
# (surfaced by the caller). In every non-zero case the generation is already
# persisted, so nothing is lost and the next edge retries.
deliver_wake() {  # [known-herdr-status]
  local attempted_generation
  attempted_generation=$(rzr_ledger_int "$DRIVER_DIR" generation)
  case "$WAKE_BACKEND" in
    codex)  # Codex owns serialization: queue immediately, busy or not.
      if codex queue --thread "$WAKE_IDENTITY" --message "$RZR_WAKE_MESSAGE"; then
        rzr_ledger_record "$DRIVER_DIR" delivered "" "$attempted_generation"; return 0
      else rzr_ledger_record "$DRIVER_DIR" error "codex queue failed"; return 2; fi ;;
    herdr)  # Never prompt into a working/blocked driver's turn; retain instead.
      local ds="${1:-}"; [ -n "$ds" ] || ds=$(rzr_agent_status "$WAKE_IDENTITY")
      case "$ds" in
        idle|done)
          if rzr_herdr agent prompt "$WAKE_IDENTITY" "$RZR_WAKE_MESSAGE" >/dev/null; then
            rzr_ledger_record "$DRIVER_DIR" delivered "" "$attempted_generation"; return 0
          else rzr_ledger_record "$DRIVER_DIR" error "herdr prompt to '$WAKE_IDENTITY' failed"; return 2; fi ;;
        working) rzr_ledger_record "$DRIVER_DIR" deferred "driver working"; return 1 ;;
        blocked) rzr_ledger_record "$DRIVER_DIR" blocked-target "driver blocked"; return 1 ;;
        *) rzr_ledger_record "$DRIVER_DIR" error "driver pane '$WAKE_IDENTITY' is $ds"; return 2 ;;
      esac ;;
    *) return 2 ;;
  esac
}
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
declare -a IDS=() PANES=() SEEN=() EVENT_BUS_FLAGS=()
idx_for_pane() {  # <pane> -> index into IDS/PANES/SEEN, or fail
  local i=0
  while [ "$i" -lt "${#PANES[@]}" ]; do
    [ "${PANES[$i]}" = "$1" ] && { printf '%s' "$i"; return 0; }
    i=$((i + 1))
  done
  return 1
}

# Collect identities without querying agent state. Subscription must be active
# before the synchronized level snapshot so every concurrent edge is either in
# that snapshot or queued on the stream.
for id in "${WANT[@]}"; do
  rzr_task_exists "$id" || { echo "rzr: skip unknown task '$id'" >&2; continue; }
  IDS+=("$id"); PANES+=("$(rzr_pane_of "$id")"); SEEN+=("")
  if [ "$(rzr_meta_get "$id" event_bus 2>/dev/null || true)" = true ]; then EVENT_BUS_FLAGS+=(true)
  else EVENT_BUS_FLAGS+=(false); fi
done
[ "${#PANES[@]}" -gt 0 ] || rzr_die "no known tasks to watch"

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

# A Herdr-backed wake also watches the driver's pane. That edge is what releases
# a notification retained while the driver was working/blocked; waiting only for
# another crew edge could otherwise strand the pending generation forever.
declare -a SUBSCRIBE_PANES=("${PANES[@]}")
if [ "$WAKE_BACKEND" = herdr ]; then
  found_driver=0
  for p in "${SUBSCRIBE_PANES[@]}"; do [ "$p" = "$WAKE_IDENTITY" ] && found_driver=1; done
  [ "$found_driver" -eq 1 ] || SUBSCRIBE_PANES+=("$WAKE_IDENTITY")
fi
python3 "$(rzr_eventwait_py)" "$SOCK" 0 "${SUBSCRIBE_PANES[@]}" > "$PIPE" 2>/dev/null &
SUBPID=$!
exec 3< "$PIPE"

IFS= read -r ack <&3 || rzr_die "event subscriber closed before acknowledging (socket $SOCK)"
[ "$ack" = "@subscribed" ] || rzr_die "unexpected event subscriber output: $ack"

# Synchronized post-subscription level reconciliation. Herdr 0.8.2 exposes the
# ordered foreground state_change_seq; queued events at or below this revision
# are harmlessly rejected by the locked reducer. Panes already gone or shell at
# this point never get a live agent to watch (a gone pane can never emit a
# pane.agent_status_changed event), so drop them here rather than block forever
# in the event loop below; a pane that is live now and disappears later is a
# real edge and stays tracked so its eventual "gone" is reported normally.
i=0
declare -a LIVE_IDS=() LIVE_PANES=() LIVE_SEEN=() LIVE_EVENT_BUS_FLAGS=()
while [ "$i" -lt "${#PANES[@]}" ]; do
  id="${IDS[$i]}"; p="${PANES[$i]}"; snapshot=$(rzr_agent_snapshot "$p")
  IFS=$'\t' read -r s seq <<EOF
$snapshot
EOF
  rzr_status_set "$id" "$s"
  seq_args=(); [ -n "${seq:-}" ] && seq_args=(--seq "$seq")
  projection=$(python3 "$RZR_BIN/rzr-runtime.py" reconcile --id "$id" --path "$RZR_STATE/$id.runtime.json" --handoff "$(rzr_task_dir "$id")/handoff.md" --parser "$RZR_BIN/rzr-handoff.py" --foreground "$s" ${seq_args[@]+"${seq_args[@]}"})
  if [ "$JSON" -eq 1 ]; then printf '%s\n' "$projection"; else printf '%s\t%s\t%s\t(initial)\n' "$(date -u +%H:%M:%S)" "$id" "$s"; fi
  case "$s" in
    gone|shell) echo "rzr: '$id' has no agent to watch ($s); skipping" >&2 ;;
    *) LIVE_IDS+=("$id"); LIVE_PANES+=("$p"); LIVE_SEEN+=("$s"); LIVE_EVENT_BUS_FLAGS+=("${EVENT_BUS_FLAGS[$i]}") ;;
  esac
  i=$((i + 1))
done
IDS=(${LIVE_IDS[@]+"${LIVE_IDS[@]}"})
PANES=(${LIVE_PANES[@]+"${LIVE_PANES[@]}"})
SEEN=(${LIVE_SEEN[@]+"${LIVE_SEEN[@]}"})
EVENT_BUS_FLAGS=(${LIVE_EVENT_BUS_FLAGS[@]+"${LIVE_EVENT_BUS_FLAGS[@]}"})
[ "${#PANES[@]}" -gt 0 ] || rzr_die "no live tasks to watch"

# Recover an undelivered generation from a previous watcher process. Subscribe
# first, then level-check, so a simultaneous driver transition is either seen by
# this check or queued on the stream. Duplicate delivery remains acceptable under
# the ledger's at-least-once contract.
if [ -n "$WAKE_BACKEND" ] && rzr_ledger_should_deliver "$DRIVER_DIR"; then
  deliver_wake && rc=0 || rc=$?
  if [ "$rc" -eq 0 ] && [ "$ONCE" -eq 1 ]; then exit 0
  elif [ "$rc" -eq 2 ]; then rzr_die "wake delivery failed for driver $(basename "$DRIVER_DIR") (edge retained pending)"
  fi
fi

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
while IFS=$'\t' read -r pane _ st _ seq <&3; do
  # Driver status edges retry a retained Herdr wake even when no further crew
  # changes occur. Use the pushed status directly to avoid a stale follow-up
  # query racing the event we just received.
  if [ "$WAKE_BACKEND" = herdr ] && [ "$pane" = "$WAKE_IDENTITY" ] && \
     rzr_ledger_should_deliver "$DRIVER_DIR"; then
    deliver_wake "$st" && rc=0 || rc=$?
    if [ "$rc" -eq 0 ] && [ "$ONCE" -eq 1 ]; then break
    elif [ "$rc" -eq 2 ]; then rzr_die "wake delivery failed for driver $(basename "$DRIVER_DIR") (edge retained pending)"
    fi
  fi
  i=$(idx_for_pane "$pane") || continue
  prev="${SEEN[$i]}"
  [ "$st" = "$prev" ] && continue
  id="${IDS[$i]}"
  seq_args=(); [ -n "${seq:-}" ] && seq_args=(--seq "$seq")
  projection=$(python3 "$RZR_BIN/rzr-runtime.py" event --id "$id" --path "$RZR_STATE/$id.runtime.json" --handoff "$(rzr_task_dir "$id")/handoff.md" --parser "$RZR_BIN/rzr-handoff.py" --foreground "$st" ${seq_args[@]+"${seq_args[@]}"})
  # A queued event older than the synchronized snapshot is not a real edge.
  if [ -n "${seq:-}" ] && [ "$(printf '%s' "$projection" | jq -r '.source.event_seq // ""')" != "$seq" ]; then continue; fi
  SEEN[i]="$st"; rzr_status_set "$id" "$st"
  if [ "$JSON" -eq 1 ]; then printf '%s\n' "$projection"; else printf '%s\t%s\t%s\n' "$(date -u +%H:%M:%S)" "$id" "$st"; fi
  DELIVERED_WAKE=0
  # A wake means "the crew FINISHED a turn", so only a settle that FOLLOWS
  # `working` is actionable. A just-spawned crew boots through `unknown`/`idle`
  # before it ever starts (observed: shell -> unknown -> idle -> working -> done),
  # and treating that first `idle` as a completed turn is what made the driver
  # nudge a crew that had not started. `blocked` still wakes regardless of the
  # prior state: a stuck crew always needs attention.
  wake_this=$(printf '%s' "$projection" | jq -r 'if .action.required then 1 else 0 end')
  # An explicitly opted-in Claude crew is shadow-produced by rozorod. The old
  # watcher may still display it, but must never create a second wake generation.
  [ "${EVENT_BUS_FLAGS[$i]}" = true ] && wake_this=0
  if [ -n "$WAKE_BACKEND" ] && [ "$wake_this" -eq 1 ]; then
    # Persist the generation BEFORE any delivery attempt, then let the ledger
    # coalesce a burst to one outstanding nudge and defer while the driver is
    # busy. A retained edge stays pending and retries on the next edge.
    edge_id=$(printf '%s' "$projection" | jq -r '.action.edge_id // ""')
    rzr_ledger_bump "$DRIVER_DIR" "$id" "$st" "$edge_id"
    if rzr_ledger_should_deliver "$DRIVER_DIR"; then
      deliver_wake && rc=0 || rc=$?
      if [ "$rc" -eq 0 ]; then DELIVERED_WAKE=1
      elif [ "$rc" -eq 2 ]; then rzr_die "wake delivery failed for driver $(basename "$DRIVER_DIR") (edge retained pending)"
      fi
    fi
  fi
  if [ "$ONCE" -eq 1 ] && { [ -z "$WAKE_BACKEND" ] || [ "$DELIVERED_WAKE" -eq 1 ]; }; then
    break
  fi
done
if [ "$ONCE" -eq 0 ]; then
  for id in "${IDS[@]}"; do python3 "$RZR_BIN/rzr-runtime.py" mark-stale --id "$id" --path "$RZR_STATE/$id.runtime.json" --handoff "$(rzr_task_dir "$id")/handoff.md" --parser "$RZR_BIN/rzr-handoff.py" >/dev/null; done
fi
exit 0
