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
