#!/usr/bin/env bats
# Generic registered wake: ledger-backed delivery, driver-status gating, reconcile.
load test_helper/common

# Register a herdr-backed Claude driver on pane "driver-pane" and echo its id.
register_claude_driver() {
  export HERDR_PANE_ID=driver-pane
  fake_pane driver-pane "${1:-idle}" claude true
  rzr-register.sh --harness claude --quiet
  driver="herdr-driver-pane"
}

@test "generic --wake refuses an unregistered environment" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 idle
  export HERDR_PANE_ID=driver-pane
  start_event_server events 'p1,w1,done,claude'
  run rzr-watch.sh --once --wake task
  assert_failure
  assert_output_contains 'no registered watchtower'
}

@test "generic --wake delivers through the registered Herdr pane on a settled edge" {
  register_claude_driver idle
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 working
  start_event_server events 'p1,w1,done,claude'
  run rzr-watch.sh --once --wake task
  assert_success
  assert_output_contains $'task\tdone'
  grep -F $'CALL\tagent\tprompt\tdriver-pane\tRozoro notification pending; run ./bin/rozoro reconcile.' "$FAKE_HERDR_LOG"
  ledger="$ROZORO_HOME/watchtowers/$driver/pending.json"
  [ "$(jq -r '.generation' "$ledger")" -eq 1 ]
  [ "$(jq -r '.delivered' "$ledger")" -eq 1 ]
  [ "$(jq -r '.delivery_state' "$ledger")" = delivered ]
}

@test "event-bus opted-in crew is excluded from legacy wake authority" {
  register_claude_driver idle
  write_meta task 'pane=p1' 'tab=t1' 'event_bus=true'
  fake_status p1 working
  start_event_server events 'p1,w1,done,claude'
  run rzr-watch.sh --once --wake task
  assert_success
  ! grep -F $'CALL\tagent\tprompt\tdriver-pane' "$FAKE_HERDR_LOG"
  ledger="$ROZORO_HOME/watchtowers/$driver/pending.json"
  [ ! -e "$ledger" ]
}

@test "a settle that did not follow working never wakes the driver" {
  # A freshly-spawned crew boots shell -> unknown -> idle before it starts; that
  # first idle is not a finished turn and must not nudge the driver.
  register_claude_driver idle
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 unknown
  start_event_server events 'p1,w1,idle,claude'
  run rzr-watch.sh --once --wake task
  assert_success
  assert_output_contains $'task\tidle'
  ! grep -F $'agent\tprompt\tdriver-pane' "$FAKE_HERDR_LOG"
  [ ! -f "$ROZORO_HOME/watchtowers/$driver/pending.json" ]
}

@test "Herdr wake defers while the driver is working and never prompts into its turn" {
  register_claude_driver working
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 working
  start_event_server events 'p1,w1,done,claude'
  run rzr-watch.sh --once --wake task
  assert_success
  # The crew edge was recorded, but no prompt was injected into the busy driver.
  ! grep -F $'agent\tprompt\tdriver-pane' "$FAKE_HERDR_LOG"
  ledger="$ROZORO_HOME/watchtowers/$driver/pending.json"
  [ "$(jq -r '.generation' "$ledger")" -eq 1 ]
  [ "$(jq -r '.delivered' "$ledger")" -eq 0 ]
  [ "$(jq -r '.delivery_state' "$ledger")" = deferred ]
}

@test "Herdr wake retries when the busy driver becomes idle without another crew edge" {
  register_claude_driver working
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 working
  start_event_server events 'p1,w1,done,claude' 'driver-pane,w1,idle,claude'
  run rzr-watch.sh --once --wake task
  assert_success
  grep -F $'CALL\tagent\tprompt\tdriver-pane\tRozoro notification pending; run ./bin/rozoro reconcile.' "$FAKE_HERDR_LOG"
  ledger="$ROZORO_HOME/watchtowers/$driver/pending.json"
  [ "$(jq -r '.generation' "$ledger")" -eq 1 ]
  [ "$(jq -r '.delivered' "$ledger")" -eq 1 ]
}

@test "a restarted watcher delivers an older pending generation" {
  register_claude_driver idle
  ledger="$ROZORO_HOME/watchtowers/$driver"
  bash -c ". '$REPO_ROOT/bin/rzr-lib.sh'; rzr_ledger_bump '$ledger' task done"
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 working
  start_event_server hold
  run rzr-watch.sh --once --wake task
  assert_success
  grep -F $'CALL\tagent\tprompt\tdriver-pane\tRozoro notification pending; run ./bin/rozoro reconcile.' "$FAKE_HERDR_LOG"
  [ "$(jq -r '.generation' "$ledger/pending.json")" -eq 1 ]
  [ "$(jq -r '.delivered' "$ledger/pending.json")" -eq 1 ]
}

@test "Herdr wake retains a pending edge when the driver is blocked" {
  register_claude_driver blocked
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 idle
  start_event_server events 'p1,w1,blocked,claude'
  run rzr-watch.sh --once --wake task
  assert_success
  ! grep -F $'agent\tprompt\tdriver-pane' "$FAKE_HERDR_LOG"
  [ "$(jq -r '.delivery_state' "$ROZORO_HOME/watchtowers/$driver/pending.json")" = blocked-target ]
}

@test "reconcile acknowledges exactly the snapshotted generation and reports verdicts" {
  register_claude_driver idle
  write_meta task 'pane=p1' 'tab=t1'
  write_handoff task '## turn 1' 'verdict: needs-action' 'inputs-needed: which branch?'
  fake_status p1 working
  start_event_server events 'p1,w1,done,claude'
  run rzr-watch.sh --once --wake task
  assert_success

  run rzr-reconcile.sh --json
  assert_success
  assert_output_contains '"acknowledged_generation": 1'
  assert_output_contains '"verdict": "needs-action"'
  [ "$(cat "$ROZORO_HOME/watchtowers/$driver/ack")" -eq 1 ]
  # A reconciled wake must NOT resolve the crew's open item (that needs rozoro ack).
  run rzr-status.sh task
  assert_output_contains 'unresolved open item'
}

@test "an edge that arrives after the ack re-nudges the driver" {
  register_claude_driver idle
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 working
  start_event_server events 'p1,w1,done,claude'
  run rzr-watch.sh --once --wake task
  assert_success
  driver="herdr-driver-pane"
  [ "$(jq -r '.delivered' "$ROZORO_HOME/watchtowers/$driver/pending.json")" -eq 1 ]

  # Driver reconciles generation 1.
  run rzr-reconcile.sh --driver "$driver"
  assert_success
  [ "$(cat "$ROZORO_HOME/watchtowers/$driver/ack")" -eq 1 ]

  # A fresh settled edge (generation 2 > ack 1, delivered 1 <= ack 1) delivers again.
  fake_status p1 working
  start_event_server events 'p1,w1,idle,claude'
  run rzr-watch.sh --once --wake task
  assert_success
  [ "$(jq -r '.generation' "$ROZORO_HOME/watchtowers/$driver/pending.json")" -eq 2 ]
  [ "$(jq -r '.delivered' "$ROZORO_HOME/watchtowers/$driver/pending.json")" -eq 2 ]
}
