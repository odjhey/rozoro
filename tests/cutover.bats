#!/usr/bin/env bats
load test_helper/common

@test "normal legacy wake management refuses before ledger or prompt mutation" {
  write_meta task 'pane=p1' 'tab=t1'; fake_status p1 working done
  export HERDR_PANE_ID=driver-pane; fake_pane driver-pane done claude true
  run rzr-register.sh --harness claude --backend herdr; assert_success
  run rzr-watch.sh --once --wake task
  assert_failure; assert_output_contains 'ROZORO_LEGACY_DIAGNOSTIC=1'
  [ ! -e "$ROZORO_HOME/watchtowers/herdr-driver-pane/pending.json" ]
  ! grep -q 'agent prompt' "$FAKE_HERDR_LOG"
}

@test "managed Pi argv explicitly loads checkout event-bus extension" {
  body="$TEST_ROOT/body"; printf 'task\n' > "$body"
  run rzr-start.sh pi-managed --body "$body" --cwd "$TEST_ROOT" --harness pi
  assert_success
  grep -F -- '--extension' "$FAKE_HERDR_LOG"
  grep -F -- 'rozoro-watchtower.ts' "$FAKE_HERDR_LOG"
  rzr-monitor.sh stop >/dev/null
}

@test "production Pi spawn and resume extension publish exact task lifecycle" {
  run rzr-spawn.sh task --cwd "$TEST_ROOT" --harness pi
  assert_success
  session="$(sed -n 's/^session=//p' "$ROZORO_HOME/state/task.meta")"
  sys="$ROZORO_HOME/tasks/task/sysprompt.md"
  grep -Fxq 'rozoro-task: task' "$sys"
  run node --experimental-strip-types "$REPO_ROOT/tests/pi-extension-process.ts" "$sys" "$session"
  assert_success
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf '{"session_id":"%s","harness":"pi","cwd":"%s"}\n' "$session" "$TEST_ROOT" > "$ROZORO_HOME/tasks/task/session.json"
  run rzr-teardown.sh task --force; assert_success
  run rzr-resume.sh task; assert_success
  grep -F -- '--extension' "$FAKE_HERDR_LOG" >/dev/null
  grep -Fxq 'rozoro-task: task' "$sys"
  run node --experimental-strip-types "$REPO_ROOT/tests/pi-extension-process.ts" "$sys" "$session"
  assert_success
  run python3 - "$ROZORO_HOME/monitor.db" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
rows=c.execute("select event_type,session_id,task_id from events where json_extract(payload_json,'$.harness')='pi' order by durable_seq").fetchall()
assert [r[0] for r in rows]==['session.register','turn.start','turn.stop']*2, rows
assert all(r[1] and r[2]=='task' for r in rows)
assert len({r[1] for r in rows})==1
PY
  assert_success
}

@test "Pi lifecycle is retained while asynchronous monitor initialization is pending" {
  run rzr-spawn.sh delayed-pi --cwd "$TEST_ROOT" --harness pi
  assert_success
  session="$(sed -n 's/^session=//p' "$ROZORO_HOME/state/delayed-pi.meta")"
  sys="$ROZORO_HOME/tasks/delayed-pi/sysprompt.md"
  ROZORO_PI_PROCESS_EXEC_DELAY_MS=300 ROZORO_PI_PROCESS_SETTLE_MS=0 \
    ROZORO_PI_PROCESS_FINAL_SETTLE_MS=900 \
    run node --experimental-strip-types "$REPO_ROOT/tests/pi-extension-process.ts" "$sys" "$session"
  assert_success
  run python3 - "$ROZORO_HOME/monitor.db" "$session" <<'PY'
import sqlite3,sys
rows=sqlite3.connect(sys.argv[1]).execute(
    "select event_type from events where session_id=? order by durable_seq", (sys.argv[2],)
).fetchall()
assert rows == [('session.register',), ('turn.start',), ('turn.stop',)], rows
PY
  assert_success
}

@test "dirty refusal then clean rollback tombstones before marker removal" {
  run rzr-monitor.sh start; assert_success
  run python3 "$REPO_ROOT/tests/rollback-process.py" "$REPO_ROOT" "$ROZORO_HOME"
  assert_success
  run rzr-monitor.sh stop; assert_success
}

@test "monitor down health is explicit and per-driver diagnostics are empty" {
  run rzr-monitor.sh status --json; assert_failure
  assert_output_contains '"health_state":"down"'
  assert_output_contains '"drivers":[]'
  assert_output_contains '"herdr_connected":false'
}
