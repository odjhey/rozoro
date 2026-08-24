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

@test "registration refuses a non-Pi pane that is not interactive_ready" {
  export HERDR_PANE_ID=driver-pane
  fake_pane driver-pane working claude false
  run rzr-register.sh --harness claude
  assert_failure
  assert_output_contains 'not interactive_ready'
}

@test "manual Pi registration uses exact Herdr agent_session without interactive_ready" {
  export HERDR_PANE_ID=driver-pane
  session="$TEST_ROOT/pi-session.jsonl"; : > "$session"; chmod 600 "$session"
  fake_pane driver-pane idle pi false "$session"
  run rzr-register.sh --harness pi --backend herdr --agent-session "$session"
  assert_success
  [ "$(jq -r .identity "$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json")" = driver-pane ]
}

@test "manual Pi registration refuses stale agent_session identity" {
  export HERDR_PANE_ID=driver-pane
  : > "$TEST_ROOT/current.jsonl"; chmod 600 "$TEST_ROOT/current.jsonl"
  fake_pane driver-pane idle pi false "$TEST_ROOT/stale.jsonl"
  run rzr-register.sh --harness pi --backend herdr --agent-session "$TEST_ROOT/current.jsonl"
  assert_failure
  assert_output_contains 'does not match this process session file'
  [ ! -e "$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json" ]
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

@test "Copilot registration uses Herdr and rejects Codex backend" {
  export HERDR_PANE_ID=p-driver CODEX_THREAD_ID=stale
  fake_pane p-driver idle copilot true
  run rzr-register.sh --harness copilot --backend auto
  assert_success
  [ "$(jq -r .backend "$ROZORO_HOME/watchtowers/$output/target.json")" = herdr ]
  run rzr-register.sh --harness copilot --backend codex
  assert_failure
  assert_output_contains 'codex backend requires --harness codex'
}
