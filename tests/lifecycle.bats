#!/usr/bin/env bats
load test_helper/common

@test "spawn records metadata and keeps the task prompt out of Claude system prompt" {
  run rzr-spawn.sh task --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'pane=p1'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=claude'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\ttab\tcreate'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tstart\ttask\t--kind\tclaude\t--pane\tp1'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\tdo exactly this'
  ! grep -F 'do exactly this' "$ROZORO_HOME/tasks/task/sysprompt.md"
}

@test "spawn retries transient pane busy" {
  export FAKE_HERDR_BUSY_ONCE_MATCH=' agent start '
  run rzr-spawn.sh task --cwd "$TEST_ROOT"
  assert_success
  [ -e "$FAKE_HERDR_ROOT/busy-once" ]
}

@test "spawn records terminal agent start failure" {
  export FAKE_HERDR_FAIL_MATCH=' agent start '
  export FAKE_HERDR_FAIL_TEXT='terminal start error'
  run rzr-spawn.sh task --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'terminal start error'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'agent_start=failed'
}

@test "send fails closed for unknown and dead targets" {
  run rzr-send.sh missing hello
  assert_failure
  assert_output_contains "no such task 'missing'"
  write_meta task 'pane=p1'
  export FAKE_HERDR_FAIL_MATCH=' agent prompt '
  run rzr-send.sh task hello
  assert_failure
  assert_output_contains 'agent blocked, or pane gone'
}

@test "data and control planes use distinct Herdr operations" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 idle
  run rzr-send.sh task 'interrupt'
  assert_success
  run rzr-control.sh task interrupt
  assert_success
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\tinterrupt'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tsend-keys\tp1\tesc'
}

@test "control refuses a dead pane" {
  write_meta task 'pane=p1' 'tab=t1'
  run rzr-control.sh task cancel
  assert_failure
  assert_output_contains 'dead target'
  ! grep -F $'send-keys\tp1' "$FAKE_HERDR_LOG"
}

@test "teardown removes state but preserves durable task folder" {
  write_meta task 'pane=p1' 'tab=t1' "cwd=$TEST_ROOT"
  mkdir -p "$ROZORO_HOME/tasks/task"; printf 'history\n' > "$ROZORO_HOME/tasks/task/handoff.md"
  run rzr-teardown.sh task --force
  assert_success
  [ ! -e "$ROZORO_HOME/state/task.meta" ]
  [ "$(cat "$ROZORO_HOME/tasks/task/handoff.md")" = history ]
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\ttab\tclose\tt1'
}

@test "legacy Claude session link can be resumed" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf '{"session_id":"uuid-1","harness":"claude","cwd":"%s"}\n' "$TEST_ROOT" > "$ROZORO_HOME/tasks/task/session.json"
  run rzr-resume.sh task --prompt 'continue'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'session=uuid-1'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tstart\ttask\t--kind\tclaude\t--pane\tp1\t--\t--resume\tuuid-1'
}

@test "resume refuses a currently tracked task" {
  write_meta task 'pane=p1'
  run rzr-resume.sh task
  assert_failure
  assert_output_contains "still tracked"
}
