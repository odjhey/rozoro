#!/usr/bin/env bash
# Launch or exactly resume a daemon-authoritative Claude watchtower.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

RESUME="" CWD="$PWD" PASS=() PRESET="" WT_NAME="" MODEL="" EFFORT="" VERSION="" PRESET_SHA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --resume) RESUME="${2:-}"; shift 2 ;;
    --cwd) CWD="${2:-}"; shift 2 ;;
    --preset) PRESET="${2:-}"; [ -n "$PRESET" ] || rzr_die "--preset requires a name"; shift 2 ;;
    --wt-name) WT_NAME="${2:-}"; [ -n "$WT_NAME" ] || rzr_die "--wt-name requires a name"; shift 2 ;;
    --) shift; PASS+=("$@"); break ;;
    -h|--help) echo "usage: ./bin/rozoro claude-watchtower [--preset name] [--wt-name name] [--resume session-id] [--cwd dir] [-- claude-args...]"; exit 0 ;;
    *) PASS+=("$1"); shift ;;
  esac
done
[ -z "$WT_NAME" ] || rzr_validate_wt_metadata "$WT_NAME" "watchtower name"
if [ -n "$PRESET" ]; then
  RESOLVED="$(rzr_wtpreset_resolve "$PRESET")" || rzr_die "watchtower preset '$PRESET' has invalid or unsafe content"
  [ "$(printf '%s' "$RESOLVED" | jq -r '.document.harness')" = claude ] || rzr_die "watchtower preset '$PRESET' is not for harness claude"
  [ -n "$WT_NAME" ] || WT_NAME="$PRESET"
  MODEL="$(printf '%s' "$RESOLVED" | jq -r '.document.model // empty')"
  EFFORT="$(printf '%s' "$RESOLVED" | jq -r '.document.effort // empty')"
  VERSION="$(printf '%s' "$RESOLVED" | jq -r '.document.version // 0')"
  PRESET_SHA="$(printf '%s' "$RESOLVED" | jq -r '.sha256')"
fi
rzr_claude_event_capability || exit 1
"$RZR_BIN/rzr-monitor.sh" start >/dev/null || rzr_die "resident monitor failed readiness"
CLAUDE_BIN="$(command -v claude)"
PANE="${HERDR_PANE_ID:-}"
[ -n "$PANE" ] || rzr_die "Claude watchtower launch requires its owning HERDR_PANE_ID"
[ "$(rzr_agent_status "$PANE")" != gone ] || rzr_die "Herdr pane '$PANE' does not exist"
CWD="$(cd "$CWD" && pwd)" || rzr_die "bad cwd"
NATIVE_SESSION="${RESUME:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
case "$NATIVE_SESSION" in ''|*[!A-Za-z0-9._-]*) rzr_die "invalid Claude session id" ;; esac
INCARNATION="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
ADAPTER_SESSION="$NATIVE_SESSION.$INCARNATION"
DRIVER="claude-$NATIVE_SESSION"
if [ -n "$WT_NAME" ]; then
  export ROZORO_WT_DRIVER="$DRIVER" ROZORO_WT_NAME="$WT_NAME" ROZORO_WT_PRESET="$PRESET"
  export ROZORO_WT_PRESET_VERSION="$VERSION" ROZORO_WT_PRESET_SHA256="$PRESET_SHA"
  export ROZORO_WT_MODEL="$MODEL" ROZORO_WT_EFFORT="$EFFORT"
fi
DIR="$(rzr_driver_dir_prepare "$DRIVER")"
# Refuse mixed ownership before starting either path.
if [ -e "$DIR/pending.json" ] || [ -e "$DIR/ack" ]; then
  g="$(rzr_ledger_int "$DIR" generation)"; a="$(rzr_ledger_int "$DIR" ack)"
  [ "$g" -eq "$a" ] || rzr_die "legacy wake ledger has pending work for $DRIVER"
fi
SETTINGS="$DIR/claude-event-settings.json"
rzr_claude_watchtower_settings "$SETTINGS" "$DRIVER" "$ADAPTER_SESSION" "$NATIVE_SESSION" "$PANE"
READY="$DIR/poller-ready.$INCARNATION"; rm -f "$READY"

# Registration is validated only after Herdr observes the launched Claude. The
# child retains the same session/driver/pane tuple and dies when the exec'd
# Claude owner exits; reconnects create fresh daemon epochs for redelivery.
(
  rzr_wait_agent_ready "$PANE" 40 || exit 1
  line="$(rzr_pane_harness_ready "$PANE")"; [ "$line" = "claude true" ] || exit 1
  "$RZR_BIN/rzr-register.sh" --harness claude --backend herdr --driver-id "$DRIVER" --quiet
  python3 "$RZR_BIN/rzr-claude-watchtower-poll.py" --home "$RZR_HOME" \
    --driver "$DRIVER" --session "$ADAPTER_SESSION" --pane "$PANE" --parent "$$" --ready-file "$READY" & poller=$!
  ready=0
  for _ in $(seq 1 40); do [ -s "$READY" ] && ready=1 && break; kill -0 "$poller" 2>/dev/null || break; sleep .05; done
  [ "$ready" -eq 1 ] || { kill "$poller" 2>/dev/null || true; wait "$poller" 2>/dev/null || true; exit 1; }
  python3 "$RZR_BIN/rzr-event-bus-client.py" authority-activate --driver "$DRIVER" >/dev/null \
    || { kill "$poller" 2>/dev/null || true; wait "$poller" 2>/dev/null || true; exit 1; }
  [ -f "$DIR/.event-bus-authority" ] || { kill "$poller" 2>/dev/null || true; exit 1; }
  wait "$poller"
) &

args=(--settings "$SETTINGS")
if [ -n "$RESUME" ]; then args+=(--resume "$NATIVE_SESSION"); else args+=(--session-id "$NATIVE_SESSION"); fi
[ -z "$MODEL" ] || args+=(--model "$MODEL")
[ -z "$EFFORT" ] || args+=(--effort "$EFFORT")
if [ "${#PASS[@]}" -gt 0 ]; then exec "$CLAUDE_BIN" "${args[@]}" "${PASS[@]}"; fi
exec "$CLAUDE_BIN" "${args[@]}"
