#!/usr/bin/env bats
load test_helper/common

run_pi_watchtower() {
  local session="$1" sys="$TEST_ROOT/watchtower.md"
  printf 'You are a rozoro **watchtower**.\n' > "$sys"
  PATH="$REPO_ROOT/tests/fakes:${RUNTIME_BIN:+$RUNTIME_BIN:}$REPO_ROOT/bin:/usr/bin:/bin:/usr/sbin:/sbin" ROZORO_WATCHTOWER=1 ROZORO_PI_PROCESS_SETTLE_MS=1200 ROZORO_PI_REGISTRATION_RETRY_MS=20 ROZORO_PI_REGISTRATION_TIMEOUT_MS="${ROZORO_PI_REGISTRATION_TIMEOUT_MS:-1000}" \
    "${NODE_BIN:-node}" --experimental-strip-types "$REPO_ROOT/tests/pi-extension-process.ts" "$sys" "$session"
}

@test "Pi watchtower startup waits outside session_start for Herdr readiness and owns one target" {
  export HERDR_PANE_ID='wR:p1'
  fake_pane "$HERDR_PANE_ID" idle pi false
  run_pi_watchtower pi-startup & child=$!
  sleep .12
  printf 'true\n' > "$FAKE_HERDR_ROOT/ready.$HERDR_PANE_ID"
  wait "$child"
  [ -d "$ROZORO_HOME/watchtowers" ] || { cat "$ROZORO_HOME/monitor.log" >&2 2>/dev/null || true; false; }

  driver='herdr-wR_p1'
  [ "$(find "$ROZORO_HOME/watchtowers" -name target.json | wc -l | tr -d ' ')" -eq 1 ]
  [ "$(jq -r .driver_id "$ROZORO_HOME/watchtowers/$driver/target.json")" = "$driver" ]
  run python3 - "$ROZORO_HOME/monitor.db" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
assert c.execute("select count(*) from watchtower_registrations").fetchone()[0] == 1
assert c.execute("select count(*) from sessions where role='watchtower'").fetchone()[0] == 1
PY
  assert_success
}

@test "Pi exact resume and reload-style replacement stay idempotent" {
  export HERDR_PANE_ID='wR:p1'
  fake_pane "$HERDR_PANE_ID" idle pi true
  run run_pi_watchtower pi-exact-session; assert_success
  run run_pi_watchtower pi-exact-session; assert_success

  [ "$(find "$ROZORO_HOME/watchtowers" -name target.json | wc -l | tr -d ' ')" -eq 1 ]
  run python3 - "$ROZORO_HOME/monitor.db" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
assert c.execute("select count(*) from watchtower_registrations").fetchone()[0] == 1
assert c.execute("select count(*) from sessions where role='watchtower' and session_id='pi-exact-session'").fetchone()[0] == 1
PY
  assert_success
}

@test "Pi watchtower readiness timeout and identity refusal fail closed" {
  export HERDR_PANE_ID='wR:p1' ROZORO_PI_REGISTRATION_TIMEOUT_MS=80
  fake_pane "$HERDR_PANE_ID" idle pi false
  run run_pi_watchtower pi-timeout; assert_success
  [ ! -e "$ROZORO_HOME/watchtowers/herdr-wR_p1/target.json" ]
  [ ! -e "$ROZORO_HOME/watchtowers/herdr-wR_p1/.event-bus-authority" ]

  fake_pane "$HERDR_PANE_ID" idle claude true
  run run_pi_watchtower pi-refused; assert_success
  [ ! -e "$ROZORO_HOME/watchtowers/herdr-wR_p1/target.json" ]
  [ ! -e "$ROZORO_HOME/watchtowers/herdr-wR_p1/.event-bus-authority" ]
}
