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

@test "monitor down health is explicit and per-driver diagnostics are empty" {
  run rzr-monitor.sh status --json; assert_failure
  assert_output_contains '"health_state":"down"'
  assert_output_contains '"drivers":[]'
  assert_output_contains '"herdr_connected":false'
}
