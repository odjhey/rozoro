#!/usr/bin/env bats
load test_helper/common

@test "event subscriber sends exact request and projects multiple panes" {
  start_event_server events 'p1,w1,working,claude' 'p2,w1,done,codex'
  run python3 "$REPO_ROOT/bin/herdr-eventwait.py" "$FAKE_HERDR_SOCKET" 1 p1 p2
  assert_failure
  [ "$status" -eq 4 ]
  assert_output_contains $'@subscribed\np1\tw1\tworking\tclaude\np2\tw1\tdone\tcodex'
  run python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d == {"id":"rozoro-eventwait","method":"events.subscribe","params":{"subscriptions":[{"type":"pane.agent_status_changed","pane_id":"p1"},{"type":"pane.agent_status_changed","pane_id":"p2"}]}}' "$FAKE_HERDR_ROOT/request.json"
  assert_success
}

@test "bounded timeout after acknowledgement exits cleanly" {
  start_event_server timeout
  run python3 "$REPO_ROOT/bin/herdr-eventwait.py" "$FAKE_HERDR_SOCKET" 0.1 p1
  assert_success
  [ "$output" = '@subscribed' ]
}

@test "malformed acknowledgement is rejected" {
  start_event_server malformed
  run python3 "$REPO_ROOT/bin/herdr-eventwait.py" "$FAKE_HERDR_SOCKET" 1 p1
  [ "$status" -eq 3 ]
}

@test "server close before acknowledgement is a transport failure" {
  start_event_server close
  run python3 "$REPO_ROOT/bin/herdr-eventwait.py" "$FAKE_HERDR_SOCKET" 1 p1
  [ "$status" -eq 2 ]
}

@test "server close after acknowledgement is a stream failure" {
  start_event_server events
  run python3 "$REPO_ROOT/bin/herdr-eventwait.py" "$FAKE_HERDR_SOCKET" 1 p1
  [ "$status" -eq 4 ]
  [ "$output" = '@subscribed' ]
}

@test "missing socket fails without consulting a real server" {
  run python3 "$REPO_ROOT/bin/herdr-eventwait.py" "$TEST_ROOT/missing.sock" 1 p1
  [ "$status" -eq 2 ]
}

@test "closed stdout is handled as success" {
  start_event_server events 'p1,w1,working,agent'
  run bash -c 'set -o pipefail; python3 "$1" "$2" 1 p1 | head -n 1' _ "$REPO_ROOT/bin/herdr-eventwait.py" "$FAKE_HERDR_SOCKET"
  assert_success
  [ "$output" = '@subscribed' ]
}
