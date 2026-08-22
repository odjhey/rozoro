#!/usr/bin/env bats
load test_helper/common

@test "status reports no handoff" {
  write_handoff task ""
  run rzr-status.sh task --json
  assert_success
  assert_output_contains '"verdict": "(no-handoff-yet)"'
}

@test "one done block is projected" {
  write_handoff task '## turn 1 — complete' 'verdict: done' 'reason:' 'pending: none' 'inputs-needed: none' 'artifacts: abc123'
  run rzr-status.sh task --json
  assert_success
  assert_output_contains '"verdict": "done"'
  assert_output_contains '"blocks": 1'
  assert_output_contains '"artifacts": "abc123"'
}

@test "open input remains surfaced after later done" {
  write_handoff task '## turn 1 — question' 'verdict: needs-action' 'inputs-needed: choose A or B' '## turn 2 — waiting' 'verdict: done' 'inputs-needed: none'
  run rzr-status.sh task --json
  assert_success
  assert_output_contains '"verdict": "done"'
  assert_output_contains '"unresolved": 1'
  assert_output_contains 'choose A or B'
}

@test "acknowledgement cursor resolves FIFO blocks through boundary" {
  write_handoff task '## turn 1' 'verdict: failed' 'inputs-needed: none' '## turn 2' 'verdict: blocked' 'inputs-needed: help' '## turn 3' 'verdict: needs-action' 'inputs-needed: answer'
  run rzr-ack.sh task --through 2
  assert_success
  [ "$(cat "$ROZORO_HOME/tasks/task/.acked-blocks")" = 2 ]
  run rzr-status.sh task --json --peek
  assert_output_contains '"unresolved": 1'
  assert_output_contains '"turn": 3'
}

@test "malformed and missing fields use explicit fallbacks" {
  write_handoff task '## turn 1' 'this is not a field' '## turn 2' 'reason: incomplete'
  run rzr-status.sh task --json
  assert_success
  assert_output_contains '"verdict": "(none)"'
  assert_output_contains '"reason": "incomplete"'
}

@test "Markdown headings inside content currently count as handoff blocks" {
  write_handoff task '## turn 1' 'verdict: done' 'did: notes follow' '## embedded heading' 'not-a-field'
  run rzr-status.sh task --json
  assert_success
  assert_output_contains '"blocks": 2'
  assert_output_contains '"heading": "embedded heading"'
}

@test "characterization: status read mutates reader-relative seen cursor" {
  write_handoff task '## turn 1' 'verdict: done' 'inputs-needed: none'
  run rzr-status.sh task --json
  assert_output_contains '"new_block": true'
  run rzr-status.sh task --json
  assert_output_contains '"new_block": false'
  [ "$(cat "$ROZORO_HOME/tasks/task/.seen-blocks")" = 1 ]
}

@test "peek is pure with respect to the seen cursor" {
  write_handoff task '## turn 1' 'verdict: done'
  run rzr-status.sh task --json --peek
  assert_success
  [ ! -e "$ROZORO_HOME/tasks/task/.seen-blocks" ]
}

@test "concurrent readers leave a complete numeric cursor" {
  write_handoff task '## turn 1' 'verdict: done' '## turn 2' 'verdict: done'
  for _ in 1 2 3 4 5 6 7 8; do rzr-status.sh task --json >/dev/null & register_pid "$!"; done
  wait
  TEST_PIDS=""
  [ "$(cat "$ROZORO_HOME/tasks/task/.seen-blocks")" = 2 ]
}
