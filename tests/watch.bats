#!/usr/bin/env bats
load test_helper/common

@test "watch reconciles initial level and persists it" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 working
  start_event_server events
  run rzr-watch.sh task
  assert_success
  assert_output_contains $'task\tworking\t(initial)'
  [ "$(cat "$ROZORO_HOME/state/task.status")" = working ]
}

@test "watch attributes pane events and persists subsequent edge" {
  write_meta alpha 'pane=p1' 'tab=t1'
  write_meta beta 'pane=p2' 'tab=t2'
  fake_status p1 idle; fake_status p2 working
  start_event_server events 'p2,w1,done,codex'
  run rzr-watch.sh --once alpha beta
  assert_success
  assert_output_contains $'beta\tdone'
  [ "$(cat "$ROZORO_HOME/state/beta.status")" = done ]
  [ "$(cat "$ROZORO_HOME/state/alpha.status")" = idle ]
}

@test "duplicate edge is suppressed" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 idle
  start_event_server events 'p1,w1,idle,claude' 'p1,w1,done,claude'
  run rzr-watch.sh --once task
  assert_success
  [ "$(printf '%s\n' "$output" | grep -c $'task\tdone')" -eq 1 ]
  [ "$(cat "$ROZORO_HOME/state/task.status")" = done ]
}

@test "two overlapping once watchers wake on the same edge" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 idle
  start_event_server multi 'p1,w1,done,claude'
  rzr-watch.sh --once task > "$TEST_ROOT/one.out" 2>&1 & p1=$!; register_pid "$p1"
  rzr-watch.sh --once task > "$TEST_ROOT/two.out" 2>&1 & p2=$!; register_pid "$p2"
  wait "$p1"; wait "$p2"; TEST_PIDS=""
  grep -F $'task\tdone' "$TEST_ROOT/one.out"
  grep -F $'task\tdone' "$TEST_ROOT/two.out"
  [ "$(cat "$ROZORO_HOME/state/task.status")" = done ]
}

@test "Codex wake ignores reconciliation and working edges, then nudges a settled edge" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 idle
  export CODEX_THREAD_ID=thread-123
  start_event_server events 'p1,w1,working,codex' 'p1,w1,blocked,codex'
  run rzr-watch.sh --wake-codex task
  assert_success
  [ "$(wc -l < "$FAKE_CODEX_LOG")" -eq 2 ]
  [ "$(sed -n '1p' "$FAKE_CODEX_LOG")" = 'queue --help' ]
  [ "$(sed -n '2p' "$FAKE_CODEX_LOG")" = 'queue --thread thread-123 --message Rozoro watch edge: reconcile crew status.' ]
}

@test "Codex wake requires a resident thread and queue capability" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 idle
  run rzr-watch.sh --wake-codex task
  assert_failure
  assert_output_contains 'requires CODEX_THREAD_ID'

  export CODEX_THREAD_ID=thread-123
  mkdir -p "$TEST_ROOT/no-codex"
  ln -s "$REPO_ROOT/tests/fakes/herdr" "$TEST_ROOT/no-codex/herdr"
  run env PATH="$TEST_ROOT/no-codex:/usr/bin:/bin" "$REPO_ROOT/bin/rzr-watch.sh" --wake-codex task
  assert_failure
  assert_output_contains "requires 'codex' on PATH"

  export FAKE_CODEX_HAS_QUEUE=0
  run rzr-watch.sh --wake-codex task
  assert_failure
  assert_output_contains "does not provide the queue capability"
}

@test "Codex wake reports queue delivery failure" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 working
  export CODEX_THREAD_ID=thread-123 FAKE_CODEX_QUEUE_FAIL=1
  start_event_server events 'p1,w1,done,codex'
  run rzr-watch.sh --once --wake-codex task
  assert_failure
  assert_output_contains "could not queue wake nudge to Codex thread 'thread-123'"
}
