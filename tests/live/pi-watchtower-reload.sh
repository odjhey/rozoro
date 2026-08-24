#!/usr/bin/env bash
# Opt-in, no-model-call manual Pi 0.84.2 + Herdr lifecycle regression.
set -euo pipefail
[ "${RZR_LIVE_PI_RELOAD:-0}" = 1 ] || { echo 'SKIP: set RZR_LIVE_PI_RELOAD=1' >&2; exit 77; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
command -v pi >/dev/null && command -v herdr >/dev/null && command -v jq >/dev/null || { echo 'pi, herdr, and jq are required' >&2; exit 1; }
[ "$(pi --version)" = 0.84.2 ] || { echo 'this regression is pinned to Pi 0.84.2' >&2; exit 1; }
TMP="$(mktemp -d)"; HOME_DIR="$TMP/home"; SESSIONS="$TMP/sessions"; mkdir -p "$HOME_DIR" "$SESSIONS"; chmod 700 "$HOME_DIR"
TAB=""; PANE=""; NORMAL_EXIT=0
cleanup() {
  [ -z "$TAB" ] || herdr tab close "$TAB" >/dev/null 2>&1 || true
  ROZORO_HOME="$HOME_DIR" "$ROOT/bin/rozoro" monitor stop >/dev/null 2>&1 || true
  if [ "$NORMAL_EXIT" -eq 1 ] && pgrep -f "rozorod.py.*$HOME_DIR" >/dev/null 2>&1; then echo "leaked isolated rozorod" >&2; exit 1; fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM
created="$(herdr tab create --cwd "$ROOT" --label "pi-manual-$RANDOM" --no-focus \
  --env "ROZORO_HOME=$HOME_DIR" --env "PI_CODING_AGENT_SESSION_DIR=$SESSIONS")"
TAB="$(jq -r .result.tab.tab_id <<<"$created")"; PANE="$(jq -r .result.root_pane.pane_id <<<"$created")"; DRIVER="herdr-${PANE//:/_}"
sleep 1
send_shell() { herdr pane send-text "$PANE" "$1" >/dev/null; herdr pane send-keys "$PANE" enter >/dev/null; }
agent_json() { herdr agent get "$PANE" 2>/dev/null; }
wait_identity() {
  for _ in $(seq 1 150); do
    value="$(agent_json | jq -r '.result.agent.agent_session.value // empty' 2>/dev/null || true)"
    [ -n "$value" ] && { printf '%s\n' "$value"; return 0; }
    sleep .1
  done
  return 1
}
wait_epoch_gt() {
  local prior="$1" epoch
  for _ in $(seq 1 150); do
    epoch="$(python3 - "$HOME_DIR/monitor.db" "$DRIVER" <<'PY' 2>/dev/null || true
import sqlite3,sys
r=sqlite3.connect(sys.argv[1]).execute('select registration_epoch from watchtower_registrations where driver_id=?',(sys.argv[2],)).fetchone()
print(r[0] if r else '')
PY
)"
    [ -n "$epoch" ] && [ "$epoch" -gt "$prior" ] && { printf '%s\n' "$epoch"; return 0; }
    sleep .1
  done
  return 1
}
wait_authority() { for _ in $(seq 1 150); do [ -f "$HOME_DIR/watchtowers/$DRIVER/.event-bus-authority" ] && return 0; sleep .1; done; return 1; }

# Seed a stale-looking valid marker: startup must still prove a fresh daemon epoch.
mkdir -p "$HOME_DIR/watchtowers/$DRIVER"; chmod 700 "$HOME_DIR/watchtowers" "$HOME_DIR/watchtowers/$DRIVER"
printf 'event-bus-v1\n' > "$HOME_DIR/watchtowers/$DRIVER/.event-bus-authority"; chmod 600 "$HOME_DIR/watchtowers/$DRIVER/.event-bus-authority"

# Manual shell launch: deliberately do not use `herdr agent start`.
send_shell "./bin/rozoro pi-watchtower"
SESSION_FILE="$(wait_identity)"
agent_json | jq -e '.result.agent.agent == "pi" and .result.agent.pane_id == "'"$PANE"'" and (.result.agent | has("interactive_ready") | not)' >/dev/null
wait_authority
EPOCH1="$(wait_epoch_gt 0)" || { herdr pane read "$PANE" --source recent --lines 50 >&2 || true; exit 1; }
[ "$(find "$HOME_DIR/watchtowers" -name target.json | wc -l | tr -d ' ')" -eq 1 ]

# Wrong process/session identity must be refused without replacing the owner.
: > "$SESSION_FILE.stale"; chmod 600 "$SESSION_FILE.stale"
if HERDR_PANE_ID="$PANE" ROZORO_HOME="$HOME_DIR" "$ROOT/bin/rozoro" register --harness pi --backend herdr --agent-session "$SESSION_FILE.stale" >/dev/null 2>&1; then
  echo "stale Pi agent_session was accepted" >&2; exit 1
fi

# Reload must create a strictly fresh daemon registration epoch, not pass on a stale marker.
herdr agent prompt "$PANE" /reload >/dev/null
EPOCH2="$(wait_epoch_gt "$EPOCH1")"; [ "$EPOCH2" -gt "$EPOCH1" ]; wait_authority

# Exact resume through the supported launcher restores role/resources and advances epoch.
herdr pane send-keys "$PANE" esc ctrl+u ctrl+d >/dev/null; sleep 3
send_shell "./bin/rozoro pi-watchtower --resume '$SESSION_FILE'"
RESUMED_FILE="$(wait_identity)"; [ "$RESUMED_FILE" = "$SESSION_FILE" ]
EPOCH3="$(wait_epoch_gt "$EPOCH2")" || { herdr pane read "$PANE" --source recent --lines 50 >&2 || true; exit 1; }
[ "$EPOCH3" -gt "$EPOCH2" ]; wait_authority
python3 - "$HOME_DIR/monitor.db" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
assert c.execute('select count(*) from watchtower_registrations').fetchone()[0] == 1
assert c.execute("select count(distinct driver_id) from sessions where role='watchtower'").fetchone()[0] == 1
PY
[ "$(find "$HOME_DIR/watchtowers" -name target.json | wc -l | tr -d ' ')" -eq 1 ]

# Shutdown must cancel work and remove the sole live client registration.
herdr pane send-keys "$PANE" esc ctrl+u ctrl+d >/dev/null; sleep 3
ROZORO_HOME="$HOME_DIR" "$ROOT/bin/rozoro" monitor stop >/dev/null
! pgrep -f "rozorod.py.*$HOME_DIR" >/dev/null 2>&1
NORMAL_EXIT=1
echo "PASS: manual startup/exact-resume/reload used exact agent_session, fresh epochs, one owner, and clean shutdown ($DRIVER)"
