#!/usr/bin/env bash
# rzr-control.sh - lifecycle actions on a task's agent, from a closed verb list.
#
# Usage:
#   rzr-control.sh <id> interrupt      stop the agent's current turn (Escape)
#   rzr-control.sh <id> cancel         hard-stop whatever's running (Ctrl+C)
#   rzr-control.sh <id> key <name>     send one named key press (escape hatch)
#   rzr-control.sh <id> stop           tear the task down for good (= rzr-teardown.sh; irreversible)
#   rzr-control.sh <id> restart        fresh restart: teardown, then re-spawn the
#                                      SAME id from its recorded profile + brief
#                                      (a NEW conversation - not rzr-resume.sh)
#
# This is the CONTROL plane: a closed, EXECUTED verb list, never free text the
# agent might interpret as chat - that's rzr-send.sh, the DATA plane. Keep the
# two apart: a lifecycle command must never arrive as something the agent
# "reads" instead of the harness carrying out.
#
# Every verb fails closed - an unresolved target (no such task, or a pane that's
# already gone) is refused loudly rather than guessed at; a successful send to
# the wrong target is worse than a loud failure. Every verb also verifies its
# own postcondition (herdr agent wait, or a re-checked pane status) rather than
# assuming the herdr call landed.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 2 ] || rzr_die "usage: rzr-control.sh <id> <interrupt|cancel|key <name>|stop|restart>"
ID="$1"; shift
VERB="$1"; shift

rzr_task_exists "$ID" || rzr_die "no such task '$ID' - refusing (fail closed: never guess at a fuzzy id)"

# Verbs that poke a live pane must first confirm it IS live - never send a
# signal to a target that might already be gone.
PANE=""
rzr_require_live_pane() {
  PANE="$(rzr_pane_of "$ID")"
  case "$(rzr_agent_status "$PANE")" in
    gone) rzr_die "task '$ID' pane $PANE is gone - refusing to send '$VERB' to a dead target" ;;
  esac
}

# Poll for a settled pane status after a mutation, instead of trusting the
# herdr call's exit code alone - the verified postcondition.
rzr_wait_status() {  # <pane> <until-states...>
  local pane="$1"; shift
  local args=(agent wait "$pane" --timeout 10000)
  local s; for s in "$@"; do args+=(--until "$s"); done
  rzr_herdr "${args[@]}" >/dev/null 2>&1
}

case "$VERB" in
  interrupt)
    rzr_require_live_pane
    rzr_herdr agent send-keys "$PANE" esc >/dev/null 2>&1 || rzr_die "send-keys esc failed on '$ID'"
    if rzr_wait_status "$PANE" idle blocked "done"; then
      echo "rzr: interrupted '$ID' - agent left 'working' (verified: $(rzr_agent_status "$PANE"))"
    else
      echo "rzr: sent interrupt to '$ID' but could not verify it left 'working' within 10s" >&2
    fi
    ;;
  cancel)
    rzr_require_live_pane
    rzr_herdr agent send-keys "$PANE" ctrl+c >/dev/null 2>&1 || rzr_die "send-keys ctrl+c failed on '$ID'"
    if rzr_wait_status "$PANE" idle blocked "done"; then
      echo "rzr: canceled '$ID' - agent left 'working' (verified: $(rzr_agent_status "$PANE"))"
    else
      echo "rzr: sent cancel to '$ID' but could not verify it left 'working' within 10s" >&2
    fi
    ;;
  key)
    [ $# -ge 1 ] || rzr_die "usage: rzr-control.sh <id> key <name>"
    KEY="$1"
    case "$KEY" in
      *' '*) rzr_die "key name must be a single token, not text (got: '$KEY') - that's rzr-send.sh" ;;
    esac
    rzr_require_live_pane
    rzr_herdr agent send-keys "$PANE" "$KEY" >/dev/null 2>&1 || rzr_die "send-keys '$KEY' failed on '$ID'"
    echo "rzr: sent key '$KEY' -> '$ID' (status now: $(rzr_agent_status "$PANE"))"
    ;;
  stop)
    # Full teardown IS the "stop" lifecycle action - reuse it rather than
    # re-implement (it already fails closed and reports its own postcondition).
    exec "$RZR_BIN/rzr-teardown.sh" "$ID" "$@"
    ;;
  restart)
    # Deliberately does NOT require a live pane - restarting a crashed/gone
    # session is the whole point. Only the recorded profile needs to resolve.
    CWD="$(rzr_meta_get "$ID" cwd || true)"
    [ -n "$CWD" ] || rzr_die "task '$ID' has no recorded cwd - cannot restart"
    CREW="$(rzr_meta_get "$ID" crew || true)"
    HARNESS="$(rzr_meta_get "$ID" harness || true)"
    MODEL="$(rzr_meta_get "$ID" model || true)"
    EFFORT="$(rzr_meta_get "$ID" effort || true)"
    FAST="$(rzr_meta_get "$ID" fast || true)"; FAST="${FAST:-false}"
    PERMMODE="$(rzr_meta_get "$ID" permission_mode || true)"
    BRIEF="$(rzr_task_dir "$ID")/brief.md"

    echo "rzr: restarting '$ID' - tearing down, then re-spawning fresh (a NEW conversation, not a resume)"
    # --force past teardown's unlanded-work guard: restart re-spawns into the SAME
    # cwd, and teardown only drops the tab + record (never the working tree), so any
    # uncommitted work is still on disk for the fresh crew — nothing is lost, and we
    # must not let the guard block an intentional restart of a crashed session.
    "$RZR_BIN/rzr-teardown.sh" "$ID" --force >/dev/null

    spawn_args=("$ID" --cwd "$CWD")
    # `rzr-resume` records the lifecycle origin as crew=resumed, which is not a
    # selectable preset. The resolved harness profile below is sufficient to
    # restart that task as a fresh conversation.
    [ -n "$CREW" ] && [ "$CREW" != resumed ] && spawn_args+=(--crew "$CREW")
    [ -n "$HARNESS" ]   && spawn_args+=(--harness "$HARNESS")
    [ -n "$MODEL" ]     && spawn_args+=(--model "$MODEL")
    [ -n "$EFFORT" ]    && spawn_args+=(--effort "$EFFORT")
    [ "$FAST" = true ]  && spawn_args+=(--fast)
    [ "$FAST" = false ] && spawn_args+=(--no-fast)
    [ -n "$PERMMODE" ]  && spawn_args+=(--permission-mode "$PERMMODE")
    [ -s "$BRIEF" ]     && spawn_args+=(--brief "$BRIEF")
    "$RZR_BIN/rzr-spawn.sh" "${spawn_args[@]}"

    # Restart creates a new conversation. If this task already had a durable
    # resume link, refresh it now so a later resume cannot silently reopen the
    # pre-restart conversation. Session discovery may trail prompt delivery by
    # a beat, just as it does in rzr-start.
    SESS="$(rzr_task_dir "$ID")/session.json"
    if [ -s "$SESS" ]; then
      linked=0
      for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
        if "$RZR_BIN/rzr-link.sh" "$ID" "$CWD" --refresh >/dev/null 2>&1; then linked=1; break; fi
        sleep 0.5
      done
      [ "$linked" -eq 1 ] || echo "rzr: warning: restarted '$ID' but its new session is not linked yet; run: ./bin/rozoro link $ID '$CWD'" >&2
    fi

    NEWPANE="$(rzr_pane_of "$ID")"
    st="unknown"
    for _ in 1 2 3 4 5 6; do
      st="$(rzr_agent_status "$NEWPANE")"
      case "$st" in gone|unknown) sleep 1 ;; *) break ;; esac
    done
    case "$st" in
      gone|unknown) rzr_die "restarted '$ID' but new pane $NEWPANE still reports '$st' - could not verify" ;;
      *) echo "rzr: restarted '$ID' -> new pane $NEWPANE (verified status: $st)" ;;
    esac
    ;;
  -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
  *) rzr_die "unknown control verb '$VERB' (closed list: interrupt cancel key stop restart)" ;;
esac
