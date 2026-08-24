#!/usr/bin/env bats
load test_helper/common

export ROZORO_LEGACY_DIAGNOSTIC=1

block() { printf '%s\n' "## turn $1 — report" "verdict: $2" "reason: ${3:-}" "did: work" "pending: none" "inputs-needed: none" "artifacts: none"; }

@test "status v2 is pure and stable with no handoff" {
  write_handoff task ""
  before=$(find "$ROZORO_HOME" -type f -exec shasum {} \; | sort)
  run rzr-status.sh task --json; assert_success; first="$output"
  run rzr-status.sh task --json; assert_success; [ "$output" = "$first" ]
  after=$(find "$ROZORO_HOME" -type f -exec shasum {} \; | sort); [ "$before" = "$after" ]
  assert_output_contains '"task_status":"no-handoff"'; [ ! -e "$ROZORO_HOME/tasks/task/.seen-blocks" ]
}

@test "canonical parser ignores content H2 and reports protocol errors" {
  write_handoff task "$(block 1 done)" '## embedded heading' 'prose'
  run rzr-status.sh task --json; assert_success
  assert_output_contains '"blocks":1'; assert_output_contains 'noncanonical H2'
}

@test "open input survives later done until FIFO acknowledgement" {
  write_handoff task '## turn 1 — question' 'verdict: needs-action' 'reason: choose' 'did: asked' 'pending: choice' 'inputs-needed: choose A or B' 'artifacts: none' "$(block 2 done)"
  run rzr-status.sh task --json; assert_success; assert_output_contains '"unresolved":1'; assert_output_contains 'choose A or B'
  run rzr-ack.sh task --through 1; assert_success
  [ "$(cat "$ROZORO_HOME/tasks/task/.acked-blocks-v2")" = 1 ]
  run rzr-status.sh task --json; assert_success; assert_output_contains '"unresolved":0'
}

@test "legacy H2 acknowledgement maps to canonical boundary" {
  write_handoff task "$(block 1 done)" '## notes' 'x' '## turn 2 — blocked' 'verdict: blocked' 'reason: help' 'did: work' 'pending: help' 'inputs-needed: help' 'artifacts: none'
  printf '2\n' > "$ROZORO_HOME/tasks/task/.acked-blocks"
  run rzr-status.sh task --json; assert_success
  assert_output_contains '"acked_source":"legacy-mapped"'; assert_output_contains '"acked_through":1'; assert_output_contains '"unresolved":1'
}

@test "invalid waiting is protocol error and old Herdr cannot certify waiting" {
  write_handoff task '## turn 1 — waiting' 'verdict: waiting' 'reason:' 'did: launched' 'pending: none' 'inputs-needed: question' 'artifacts: none'
  run rzr-status.sh task --json; assert_success; assert_output_contains '"task_status":"protocol-error"'; assert_output_contains 'waiting requires'
  write_handoff task '## turn 1 — waiting' 'verdict: waiting' 'reason: job runs' 'did: launched' 'pending: consume job result' 'inputs-needed: none' 'artifacts: none'
  run rzr-status.sh task --json; assert_success; assert_output_contains '"action_reason":"inconsistent-wait"'; assert_output_contains '"supported":null'
}

@test "status task_status is case-insensitive on the verdict field" {
  write_handoff task "$(block 1 Done)"
  run rzr-status.sh task --json; assert_success
  assert_output_contains '"task_status":"reported-done"'; assert_output_contains '"handoff_verdict":"Done"'

  write_handoff task '## turn 1 — report' 'verdict: FAILED' 'reason: broke' 'did: work' 'pending: none' 'inputs-needed: none' 'artifacts: none'
  run rzr-ack.sh task --through 1; assert_success
  run rzr-status.sh task --json; assert_success
  assert_output_contains '"task_status":"reported-failed"'
}

@test "duplicate and skipped turns are deterministic protocol errors" {
  write_handoff task "$(block 1 done)" "$(block 3 done)"
  run rzr-status.sh task --json; assert_success; assert_output_contains 'turn sequence expected 2, got 3'
}

@test "parallel independent readers are equivalent and filesystem-pure" {
  write_handoff task '## turn 1 — done' 'verdict: done' 'reason:' 'did: work' 'pending: none' 'inputs-needed: none' 'artifacts: none'
  before=$(find "$ROZORO_HOME" -type f -exec shasum {} \; | sort)
  for n in 1 2 3 4 5 6 7 8; do rzr-status.sh task --json > "$BATS_TEST_TMPDIR/status.$n" & register_pid "$!"; done
  wait; TEST_PIDS=""; first=$(cat "$BATS_TEST_TMPDIR/status.1")
  for n in 2 3 4 5 6 7 8; do [ "$(cat "$BATS_TEST_TMPDIR/status.$n")" = "$first" ]; done
  after=$(find "$ROZORO_HOME" -type f -exec shasum {} \; | sort); [ "$before" = "$after" ]
  [ ! -e "$ROZORO_HOME/tasks/task/.seen-blocks" ]
}
