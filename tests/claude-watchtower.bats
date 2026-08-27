#!/usr/bin/env bats
load test_helper/common

@test "Claude watchtower launch activates authority and exact resume uses a fresh incarnation" {
  export PYTHONDONTWRITEBYTECODE=1
  if [ -x /opt/homebrew/bin/python3 ]; then mkdir "$TEST_ROOT/pybin"; ln -s /opt/homebrew/bin/python3 "$TEST_ROOT/pybin/python3"; export PATH="$TEST_ROOT/pybin:$PATH"; fi
  export HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION=2.1.241 FAKE_CLAUDE_LOG="$TEST_ROOT/claude.log" FAKE_CLAUDE_SLEEP=10
  export ROZORO_WT_POLICY_SHA256="$(printf 'a%.0s' $(seq 1 64))" ROZORO_WT_POLICY_CORE_SHA256="$(printf 'b%.0s' $(seq 1 64))"
  export ROZORO_WT_POLICY_MISSION_NAME=stale ROZORO_WT_POLICY_MISSION_SOURCE=operator ROZORO_WT_POLICY_MISSION_SHA256="$(printf 'c%.0s' $(seq 1 64))"
  fake_pane p1 idle claude true
  chmod 700 "$ROZORO_HOME" "$ROZORO_HOME/state" "$ROZORO_HOME/tasks"
  "$REPO_ROOT/bin/rozoro" monitor start >/dev/null || { cat "$ROZORO_HOME/monitor.log" >&2; false; }
  "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT" -- --permission-mode auto >"$TEST_ROOT/launcher.log" 2>&1 & owner=$!; register_pid "$owner"
  for _ in $(seq 1 80); do session="$(grep -- '--session-id' "$FAKE_CLAUDE_LOG" 2>/dev/null | tail -1 | sed 's/.*--session-id //; s/ .*//')"; [ -n "${session:-}" ] && break; sleep .05; done
  [ -n "${session:-}" ] || { cat "$TEST_ROOT/launcher.log" >&2; cat "$FAKE_CLAUDE_LOG" >&2; false; }
  dir="$ROZORO_HOME/watchtowers/claude-$session"
  # Claude starts before registration and authority activation. Under a loaded
  # parallel runner, observing its argv is not evidence that authority is ready.
  for _ in $(seq 1 240); do [ -f "$dir/.event-bus-authority" ] && break; sleep .05; done
  [ -f "$dir/.event-bus-authority" ] || { cat "$TEST_ROOT/launcher.log" >&2; find "$dir" -maxdepth 2 -print >&2; cat "$ROZORO_HOME/monitor.log" >&2; false; }
  ready="$(find "$dir" -name 'poller-ready.*' -type f | head -1)"; [ -s "$ready" ]; poller="$(cat "$ready")"; kill -0 "$poller"
  [ "$(jq '[.policy_sha256,.policy_core_sha256,.policy_mission_name,.policy_mission_source,.policy_mission_sha256] | map(select(. != null)) | length' "$dir/target.json")" -eq 0 ]
  [ "$(jq '[.policy_sha256,.policy_core_sha256,.policy_mission_name,.policy_mission_source,.policy_mission_sha256] | map(select(. != null)) | length' "$dir/registrations.jsonl")" -eq 0 ]
  settings="$dir/claude-event-settings.json"; command="$(jq -r '.hooks.SessionStart[0].hooks[0].command' "$settings")"
  printf '{"hook_event_name":"SessionStart","session_id":"%s"}\n' "$session" | sh -c "$command"
  old_adapter="$(python3 - "$ROZORO_HOME/monitor.db" <<'PY2'
import sqlite3,sys
print(sqlite3.connect(sys.argv[1]).execute("select session_id from sessions where role='watchtower' order by latest_durable_seq desc limit 1").fetchone()[0])
PY2
)"
  end_command="$(jq -r '.hooks.SessionEnd[0].hooks[0].command' "$settings")"
  printf '{"hook_event_name":"SessionEnd","session_id":"%s"}\n' "$session" | sh -c "$end_command"
  kill "$owner"; wait "$owner" 2>/dev/null || true
  for _ in $(seq 1 30); do kill -0 "$poller" 2>/dev/null || break; sleep .05; done
  ! kill -0 "$poller" 2>/dev/null

  : > "$FAKE_CLAUDE_LOG"
  "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --resume "$session" --cwd "$TEST_ROOT" >/dev/null 2>&1 & resumed=$!; register_pid "$resumed"
  for _ in $(seq 1 80); do grep -F -- "--resume $session" "$FAKE_CLAUDE_LOG" >/dev/null 2>&1 && [ -f "$dir/.event-bus-authority" ] && break; sleep .05; done
  command="$(jq -r '.hooks.SessionStart[0].hooks[0].command' "$settings")"
  printf '{"hook_event_name":"SessionStart","session_id":"%s"}\n' "$session" | sh -c "$command"
  python3 - "$ROZORO_HOME/monitor.db" "$old_adapter" <<'PY2'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]); rows=c.execute("select session_id,availability from sessions where role='watchtower' order by latest_durable_seq").fetchall()
assert any(s==sys.argv[2] and a=='gone' for s,a in rows), rows
assert any(s!=sys.argv[2] and a!='gone' for s,a in rows), rows
assert c.execute("select count(*) from watchtower_registrations where driver_id=?",('claude-'+sys.argv[2].split('.')[0],)).fetchone()[0] == 1
PY2
  kill "$resumed"; wait "$resumed" 2>/dev/null || true
  "$REPO_ROOT/bin/rozoro" monitor stop >/dev/null
}

@test "installed unsupported Claude version fails before settings or launch" {
  export HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION=2.2.0 FAKE_CLAUDE_LOG="$TEST_ROOT/claude.log"
  run "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains "certified only for >=2.1.240 <2.2.0"
  [ ! -d "$ROZORO_HOME/watchtowers" ]
}

@test "older or malformed Claude versions fail before settings or launch" {
  for version in 2.1.239 2.1.240rc 2.2.0-rc 3.0.0; do
    export HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION="$version" FAKE_CLAUDE_LOG="$TEST_ROOT/claude.log"
    run "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT"
    assert_failure
    assert_output_contains "certified only for >=2.1.240 <2.2.0"
    [ ! -d "$ROZORO_HOME/watchtowers" ]
  done
}

@test "watchtower settings failure leaves no random temporary" {
  mkdir -p "$TEST_ROOT/private"; chmod 700 "$TEST_ROOT/private"
  long="$(printf '%0300d' 0)"
  run bash -c '. "$1/bin/rzr-lib.sh"; rzr_claude_watchtower_settings "$2/$3" d adapter native p' _ "$REPO_ROOT" "$TEST_ROOT/private" "$long"
  assert_failure
  run find "$TEST_ROOT/private" -name '.claude-watchtower-*.tmp' -print
  assert_success
  [ -z "$output" ]
}
