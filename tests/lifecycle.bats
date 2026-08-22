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

@test "start gives repeated display names distinct durable task keys" {
  printf 'ship it\n' > "$TEST_ROOT/body"
  run rzr-start.sh same-name --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent
  assert_success
  key1="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  run rzr-start.sh same-name --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent
  assert_success
  key2="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  [ "$key1" != "$key2" ]
  [ -f "$ROZORO_HOME/tasks/$key1/brief.md" ]
  [ -f "$ROZORO_HOME/tasks/$key2/brief.md" ]
  assert_file_contains "$ROZORO_HOME/state/$key1.meta" 'display_name=same-name'
}

@test "reuse after teardown preserves the old durable record" {
  printf 'first\n' > "$TEST_ROOT/first"
  printf 'second\n' > "$TEST_ROOT/second"
  run rzr-start.sh reusable --body "$TEST_ROOT/first" --cwd "$TEST_ROOT" --no-agent
  assert_success
  old="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  run rzr-teardown.sh "$old" --force
  assert_success
  run rzr-start.sh reusable --body "$TEST_ROOT/second" --cwd "$TEST_ROOT" --no-agent
  assert_success
  new="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  [ "$old" != "$new" ]
  assert_file_contains "$ROZORO_HOME/tasks/$old/brief.md" 'first'
  assert_file_contains "$ROZORO_HOME/tasks/$new/brief.md" 'second'
}

@test "concurrent same-name starts reserve different folders" {
  printf 'parallel\n' > "$TEST_ROOT/body"
  rzr-start.sh concurrent --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent > "$TEST_ROOT/a.out" 2>&1 & p1=$!
  rzr-start.sh concurrent --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent > "$TEST_ROOT/b.out" 2>&1 & p2=$!
  wait "$p1"; wait "$p2"
  key1="$(sed -n 's/^rzr-start: task key -> //p' "$TEST_ROOT/a.out")"
  key2="$(sed -n 's/^rzr-start: task key -> //p' "$TEST_ROOT/b.out")"
  [ -n "$key1" ] && [ -n "$key2" ] && [ "$key1" != "$key2" ]
  [ -d "$ROZORO_HOME/tasks/$key1" ] && [ -d "$ROZORO_HOME/tasks/$key2" ]
}

@test "same display name across repositories has distinct identities" {
  mkdir -p "$TEST_ROOT/repo-a" "$TEST_ROOT/repo-b"
  printf 'cross repo\n' > "$TEST_ROOT/body"
  run rzr-start.sh shared --body "$TEST_ROOT/body" --cwd "$TEST_ROOT/repo-a" --no-agent
  assert_success
  key1="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  run rzr-start.sh shared --body "$TEST_ROOT/body" --cwd "$TEST_ROOT/repo-b" --no-agent
  assert_success
  key2="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  [ "$key1" != "$key2" ]
  assert_file_contains "$ROZORO_HOME/tasks/$key1/identity.json" "$TEST_ROOT/repo-a"
  assert_file_contains "$ROZORO_HOME/tasks/$key2/identity.json" "$TEST_ROOT/repo-b"
}

@test "unsafe display names cannot escape the task root" {
  printf 'unsafe\n' > "$TEST_ROOT/body"
  run rzr-start.sh ../escape --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent
  assert_failure
  assert_output_contains 'display name'
  [ ! -e "$ROZORO_HOME/escape" ]
}
