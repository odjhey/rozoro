#!/usr/bin/env bats
# Watchtower registration: pin ONE validated wake target, never guess from env.
load test_helper/common

@test "herdr backend registers a pane that reports the declared harness" {
  export HERDR_PANE_ID=driver-pane
  fake_pane driver-pane idle claude true
  run rzr-register.sh --harness claude
  assert_success
  driver="$output"
  target="$ROZORO_HOME/watchtowers/$driver/target.json"
  [ -f "$target" ]
  [ "$(jq -r '.backend' "$target")" = herdr ]
  [ "$(jq -r '.harness' "$target")" = claude ]
  [ "$(jq -r '.identity' "$target")" = driver-pane ]
  [ "$(file_perm "$target")" = 600 ]
}

@test "auto selection ignores a stale CODEX_THREAD_ID and picks the validated harness" {
  # A Claude watchtower launched from a Codex environment inherits CODEX_THREAD_ID.
  # It must NOT wake that stale thread; it must register the real Claude pane.
  export CODEX_THREAD_ID=stale-thread HERDR_PANE_ID=driver-pane
  export FAKE_CODEX_HAS_QUEUE=1
  fake_pane driver-pane idle claude true
  run rzr-register.sh --harness claude
  assert_success
  target="$ROZORO_HOME/watchtowers/$output/target.json"
  [ "$(jq -r '.backend' "$target")" = herdr ]
  [ "$(jq -r '.identity' "$target")" = driver-pane ]
  # No codex-thread ledger/target was created.
  [ ! -e "$ROZORO_HOME/watchtowers/codex-stale-thread" ]
}

@test "registration refuses a pane whose harness does not match the declaration" {
  export HERDR_PANE_ID=driver-pane
  fake_pane driver-pane idle pi true
  run rzr-register.sh --harness claude
  assert_failure
  assert_output_contains 'does not match'
}

@test "registration refuses a pane that is not interactive_ready" {
  export HERDR_PANE_ID=driver-pane
  fake_pane driver-pane working claude false
  run rzr-register.sh --harness claude
  assert_failure
  assert_output_contains 'not interactive_ready'
}

@test "codex backend registers a resident thread with queue capability" {
  export CODEX_THREAD_ID=thread-123 FAKE_CODEX_HAS_QUEUE=1
  run rzr-register.sh --harness codex --backend codex
  assert_success
  target="$ROZORO_HOME/watchtowers/$output/target.json"
  [ "$(jq -r '.backend' "$target")" = codex ]
  [ "$(jq -r '.identity' "$target")" = thread-123 ]
}

@test "auto selects codex when the declared harness is codex and queue is available" {
  export CODEX_THREAD_ID=thread-123 FAKE_CODEX_HAS_QUEUE=1
  run rzr-register.sh --harness codex
  assert_success
  [ "$(jq -r '.backend' "$ROZORO_HOME/watchtowers/$output/target.json")" = codex ]
}

@test "registration fails when no valid backend is available" {
  run rzr-register.sh --harness claude
  assert_failure
  assert_output_contains 'HERDR_PANE_ID'
}
