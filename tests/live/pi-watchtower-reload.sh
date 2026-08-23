#!/usr/bin/env bash
# Opt-in, no-model-call Pi 0.84.2 + Herdr process regression for startup and reload.
set -euo pipefail
[ "${RZR_LIVE_PI_RELOAD:-0}" = 1 ] || { echo 'SKIP: set RZR_LIVE_PI_RELOAD=1' >&2; exit 77; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
command -v pi >/dev/null && command -v herdr >/dev/null && command -v jq >/dev/null || { echo 'pi, herdr, and jq are required' >&2; exit 1; }
[ "$(pi --version)" = 0.84.2 ] || { echo 'this regression is pinned to Pi 0.84.2' >&2; exit 1; }
TMP="$(mktemp -d)"; HOME_DIR="$TMP/home"; SESSIONS="$TMP/sessions"; mkdir -p "$HOME_DIR" "$SESSIONS"; chmod 700 "$HOME_DIR"
UUID="$(python3 -c 'import uuid; print(uuid.uuid4())')"; TAB=""; PANE=""
cleanup() { [ -z "$TAB" ] || herdr tab close "$TAB" >/dev/null 2>&1 || true; "$ROOT/bin/rozoro" monitor stop >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT INT TERM
created="$(herdr tab create --cwd "$ROOT" --label "pi-reload-${UUID%%-*}" --no-focus \
  --env "ROZORO_HOME=$HOME_DIR" --env ROZORO_WATCHTOWER=1 --env "PI_CODING_AGENT_SESSION_DIR=$SESSIONS")"
TAB="$(jq -r .result.tab.tab_id <<<"$created")"; PANE="$(jq -r .result.root_pane.pane_id <<<"$created")"; DRIVER="herdr-${PANE//:/_}"
sleep 1
start_pi() { herdr agent start "pi-reload-${UUID%%-*}" --kind pi --pane "$PANE" --timeout 30000 -- \
  --extension "$ROOT/.pi/extensions/rozoro-watchtower.ts" --session-id "$UUID" --approve \
  --append-system-prompt "$ROOT/templates/watchtower.md" >/dev/null; }
wait_authority() { for _ in $(seq 1 100); do [ -f "$HOME_DIR/watchtowers/$DRIVER/.event-bus-authority" ] && return 0; sleep .1; done; return 1; }
start_pi
wait_authority || { herdr agent read "$PANE" --source recent --lines 40 >&2 || true; find "$HOME_DIR" -maxdepth 3 -print >&2; exit 1; }
[ "$(find "$HOME_DIR/watchtowers" -name target.json | wc -l | tr -d ' ')" -eq 1 ]
epoch_before="$(python3 - "$HOME_DIR/monitor.db" "$DRIVER" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]); print(c.execute('select registration_epoch from watchtower_registrations where driver_id=?',(sys.argv[2],)).fetchone()[0])
PY
)"
herdr agent prompt "$PANE" /reload >/dev/null
sleep 3
wait_authority
epoch_after="$(python3 - "$HOME_DIR/monitor.db" "$DRIVER" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]);
assert c.execute('select count(*) from watchtower_registrations').fetchone()[0] == 1
assert c.execute("select count(*) from sessions where role='watchtower'").fetchone()[0] == 1
print(c.execute('select registration_epoch from watchtower_registrations where driver_id=?',(sys.argv[2],)).fetchone()[0])
PY
)"
[ "$epoch_after" -ge "$epoch_before" ]
echo "PASS: Pi startup and /reload retained one driver/target/authority ($DRIVER)"
