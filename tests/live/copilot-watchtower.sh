#!/usr/bin/env bash
# Opt-in, cost-incurring proof that a settled crew edge wakes a Copilot-hosted watchtower.
set -euo pipefail
[ "${RZR_LIVE_COPILOT:-0}" = 1 ] || { echo 'SKIP: set RZR_LIVE_COPILOT=1 (uses paid Copilot requests)' >&2; exit 77; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
command -v copilot >/dev/null && command -v herdr >/dev/null || { echo 'copilot and herdr are required (run copilot login first)' >&2; exit 1; }
TMP="$(mktemp -d)"; export ROZORO_HOME="$TMP/home"; mkdir -p "$TMP/work"
SUFFIX="$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
DRIVER="live-copilot-watchtower-$SUFFIX" WORKER="live-copilot-worker-$SUFFIX" WATCH_PID=""
cleanup() {
  [ -z "$WATCH_PID" ] || { kill "$WATCH_PID" 2>/dev/null || true; wait "$WATCH_PID" 2>/dev/null || true; }
  "$ROOT/bin/rozoro" teardown "$WORKER" --force >/dev/null 2>&1 || true
  "$ROOT/bin/rozoro" teardown "$DRIVER" --force >/dev/null 2>&1 || true
  rm -rf "$TMP"
}; trap cleanup EXIT INT TERM
wait_settled() {
  local id="$1" pane status
  pane="$(sed -n 's/^pane=//p' "$ROZORO_HOME/state/$id.meta")"
  for _ in $(seq 1 120); do
    status="$(herdr agent get "$pane" 2>/dev/null | jq -r '.result.agent_status // .result.agent.agent_status // .agent_status // "unknown"' 2>/dev/null || true)"
    case "$status" in done|idle) return 0 ;; esac
    sleep 1
  done
  return 1
}

"$ROOT/bin/rozoro" spawn "$DRIVER" --harness copilot --model auto --cwd "$TMP/work" \
  --prompt 'You are a watchtower. For every prompt, follow it and append the required handoff turn.'
wait_settled "$DRIVER"
DRIVER_PANE="$(sed -n 's/^pane=//p' "$ROZORO_HOME/state/$DRIVER.meta")"
DRIVER_ID="$(HERDR_PANE_ID="$DRIVER_PANE" CODEX_THREAD_ID=stale-live-thread "$ROOT/bin/rozoro" register --harness copilot --backend auto)"
[ "$(jq -r .backend "$ROZORO_HOME/watchtowers/$DRIVER_ID/target.json")" = herdr ]

"$ROOT/bin/rozoro" spawn "$WORKER" --harness copilot --model auto --cwd "$TMP/work" \
  --prompt 'Reply WORKER_READY and append the required done handoff.'
wait_settled "$WORKER"
DRIVER_SEQ_BEFORE="$(herdr agent get "$DRIVER_PANE" | jq -r '.result.state_change_seq // .result.agent.state_change_seq // .state_change_seq // 0')"
"$ROOT/bin/rozoro" watch --once --wake --driver "$DRIVER_ID" "$WORKER" >"$TMP/watch.log" 2>&1 & WATCH_PID=$!
sleep 2
"$ROOT/bin/rozoro" send "$WORKER" 'Reply WORKER_SETTLED_EDGE and append the next required done handoff.'
wait "$WATCH_PID"; WATCH_PID=""
PENDING="$ROZORO_HOME/watchtowers/$DRIVER_ID/pending.json"
[ "$(jq -r .delivery_state "$PENDING")" = delivered ]
[ "$(jq -r '.delivered > 0 and .generation >= .delivered' "$PENDING")" = true ]
for _ in $(seq 1 120); do
  DRIVER_SEQ_AFTER="$(herdr agent get "$DRIVER_PANE" 2>/dev/null | jq -r '.result.state_change_seq // .result.agent.state_change_seq // .state_change_seq // 0' 2>/dev/null || echo 0)"
  [ "$DRIVER_SEQ_AFTER" -gt "$DRIVER_SEQ_BEFORE" ] && wait_settled "$DRIVER" && break
  sleep 1
done
[ "${DRIVER_SEQ_AFTER:-0}" -gt "$DRIVER_SEQ_BEFORE" ] || { echo 'Copilot watchtower pane did not process the delivered wake' >&2; cat "$TMP/watch.log" >&2; exit 1; }
echo "PASS: settled worker edge delivered and ran a Herdr wake in Copilot watchtower $DRIVER_ID (driver revision $DRIVER_SEQ_BEFORE -> $DRIVER_SEQ_AFTER)"
