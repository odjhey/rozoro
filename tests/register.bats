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

@test "registration records optional watchtower preset and appends private tenure records" {
  export HERDR_PANE_ID=driver-pane ROZORO_WT_NAME=north ROZORO_WT_PRESET=luna
  export ROZORO_WT_PRESET_VERSION=3 ROZORO_WT_PRESET_SHA256=abc
  export ROZORO_WT_POLICY_SHA256="$(printf 'a%.0s' $(seq 1 64))" ROZORO_WT_POLICY_CORE_SHA256="$(printf 'b%.0s' $(seq 1 64))"
  export ROZORO_WT_POLICY_MISSION_NAME=delivery ROZORO_WT_POLICY_MISSION_SOURCE=shipped ROZORO_WT_POLICY_MISSION_SHA256="$(printf 'c%.0s' $(seq 1 64))"
  export ROZORO_WT_MODEL=luna ROZORO_WT_EFFORT=high
  fake_pane driver-pane idle pi true
  run rzr-register.sh --harness pi; assert_success
  target="$ROZORO_HOME/watchtowers/$output/target.json"; log="${target%/target.json}/registrations.jsonl"
  [ "$(jq -r '.watchtower_name' "$target")" = north ]
  [ "$(jq -r '.preset | [.name,.version,.sha256,.model,.effort] | join(":")' "$target")" = 'luna:3:abc:luna:high' ]
  [ "$(jq -r '[.policy_core_sha256,.policy_mission_name,.policy_mission_source,.policy_mission_sha256] | join(":")' "$target")" = "$(printf 'b%.0s' $(seq 1 64)):delivery:shipped:$(printf 'c%.0s' $(seq 1 64))" ]
  [ "$(wc -l < "$log" | tr -d ' ')" = 1 ]; [ "$(file_perm "$log")" = 600 ]
  run rzr-register.sh --harness pi; assert_success
  [ "$(wc -l < "$log" | tr -d ' ')" = 2 ]
}

@test "named unpreset Pi registration records policy provenance" {
  export HERDR_PANE_ID=driver-pane ROZORO_WT_NAME=north
  export ROZORO_WT_POLICY_SHA256="$(printf 'a%.0s' $(seq 1 64))" ROZORO_WT_POLICY_CORE_SHA256="$(printf 'b%.0s' $(seq 1 64))"
  export ROZORO_WT_POLICY_MISSION_NAME=delivery ROZORO_WT_POLICY_MISSION_SOURCE=shipped ROZORO_WT_POLICY_MISSION_SHA256="$(printf 'c%.0s' $(seq 1 64))"
  fake_pane driver-pane idle pi true
  run rzr-register.sh --harness pi
  assert_success
  target="$ROZORO_HOME/watchtowers/$output/target.json"
  log="${target%/target.json}/registrations.jsonl"
  [ "$(jq -r '.watchtower_name' "$target")" = north ]
  [ "$(jq -r '.policy_mission_name' "$target")" = delivery ]
  [ "$(jq 'has("preset")' "$target")" = false ]
  [ "$(jq -r '.policy_mission_source' "$log")" = shipped ]
}

@test "policy tuple ingress is Pi-only and fails before writes" {
  export HERDR_PANE_ID=driver-pane
  export ROZORO_WT_POLICY_SHA256="$(printf 'a%.0s' $(seq 1 64))" ROZORO_WT_POLICY_CORE_SHA256="$(printf 'b%.0s' $(seq 1 64))"
  export ROZORO_WT_POLICY_MISSION_NAME=delivery ROZORO_WT_POLICY_MISSION_SOURCE=shipped ROZORO_WT_POLICY_MISSION_SHA256="$(printf 'c%.0s' $(seq 1 64))"
  for harness in claude codex copilot; do
    fake_pane driver-pane idle "$harness" true
    run rzr-register.sh --harness "$harness" --backend herdr
    assert_failure
    [ "$output" = "rzr: Pi policy attribution is valid only for harness pi" ]
    [ ! -e "$ROZORO_HOME/watchtowers" ]
  done
}

@test "every harness and policy-field subset has exact ingress and no-write behavior" {
  fields=(ROZORO_WT_POLICY_SHA256 ROZORO_WT_POLICY_CORE_SHA256 ROZORO_WT_POLICY_MISSION_NAME ROZORO_WT_POLICY_MISSION_SOURCE ROZORO_WT_POLICY_MISSION_SHA256)
  values=("$(printf 'a%.0s' $(seq 1 64))" "$(printf 'b%.0s' $(seq 1 64))" delivery shipped "$(printf 'c%.0s' $(seq 1 64))")
  for harness in pi claude codex copilot; do
    for mask in $(seq 0 31); do
      home="$TEST_ROOT/matrix-$harness-$mask"; rm -rf "$home"
      for field in "${fields[@]}"; do unset "$field"; done
      for index in $(seq 0 4); do
        if (( mask & (1 << index) )); then export "${fields[$index]}=${values[$index]}"; fi
      done
      export ROZORO_HOME="$home" HERDR_PANE_ID="pane-$harness-$mask"
      fake_pane "$HERDR_PANE_ID" idle "$harness" true
      run rzr-register.sh --harness "$harness" --backend herdr
      if { [ "$harness" = pi ] && { [ "$mask" -eq 0 ] || [ "$mask" -eq 31 ]; }; } || { [ "$harness" != pi ] && [ "$mask" -eq 0 ]; }; then
        assert_success
        target="$home/watchtowers/$output/target.json"
        [ -f "$target" ]; [ "$(wc -l < "${target%/target.json}/registrations.jsonl" | tr -d ' ')" = 1 ]
      else
        assert_failure
        [ "$(printf '%s\n' "$output" | wc -l | tr -d ' ')" = 1 ]
        [ ! -e "$home" ]
        find "$TEST_ROOT" -name '*.tmp.*' -print -quit | grep -q . && return 1 || true
      fi
    done
  done
}

@test "registration without watchtower env preserves legacy target shape" {
  export HERDR_PANE_ID=driver-pane
  fake_pane driver-pane idle claude true
  run rzr-register.sh --harness claude; assert_success
  target="$ROZORO_HOME/watchtowers/$output/target.json"
  [ "$(jq 'has("watchtower_name") or has("preset")' "$target")" = false ]
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

@test "early empty harness is bounded-retriable, not a terminal harness mismatch" {
  # During Herdr startup a pane can report an agent record whose harness is still
  # empty while interactive_ready/pane_id are already populated. Field positions
  # must be preserved so this stays the retriable 'does not report a harness'
  # transient the watchtower retries, never the terminal 'does not match'.
  export HERDR_PANE_ID=driver-pane
  fake_pane driver-pane idle "" true
  run rzr-register.sh --harness claude
  assert_failure
  assert_output_contains 'does not report a harness'
  case "$output" in *'does not match'*) printf 'empty harness must not surface as a terminal mismatch:\n%s\n' "$output" >&2; return 1 ;; esac
  [ ! -e "$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json" ]
}

@test "empty Pi harness with a populated agent_session stays retriable" {
  # Leading empty field followed by populated later columns is the exact shape
  # that tab-as-IFS collapse would shift, mis-reading the session path into the
  # harness slot. Position preservation keeps this the retriable transient.
  export HERDR_PANE_ID=driver-pane
  session="$TEST_ROOT/pi-session.jsonl"; : > "$session"; chmod 600 "$session"
  fake_pane driver-pane idle "" false "$session"
  run rzr-register.sh --harness pi --backend herdr --agent-session "$session"
  assert_failure
  assert_output_contains 'does not report a harness'
  case "$output" in *'does not match'*) printf 'empty harness must not surface as a terminal mismatch:\n%s\n' "$output" >&2; return 1 ;; esac
  [ ! -e "$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json" ]
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
