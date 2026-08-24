#!/usr/bin/env bats
load test_helper/common

setup_pi() {
  export HERDR_PANE_ID=manual:p1 PI_LOG="$TEST_ROOT/pi.log"
  cat > "$TEST_ROOT/pi" <<'SH'
#!/bin/sh
printf 'role=%s\n' "${ROZORO_WATCHTOWER:-}" > "$PI_LOG"
printf '%s\n' "$@" >> "$PI_LOG"
SH
  chmod +x "$TEST_ROOT/pi"
  export PATH="$TEST_ROOT:$PATH"
}

@test "supported Pi watchtower launch carries immutable role and explicit resources" {
  setup_pi
  run rzr-pi-watchtower.sh --cwd "$TEST_ROOT" -- --model test/model
  assert_success
  grep -Fx 'role=1' "$PI_LOG"
  grep -Fx -- '--extension' "$PI_LOG"
  grep -Fx "$REPO_ROOT/.pi/extensions/rozoro-watchtower.ts" "$PI_LOG"
  grep -Fx -- '--append-system-prompt' "$PI_LOG"
  grep -Fx "$REPO_ROOT/templates/watchtower.md" "$PI_LOG"
  grep -Fx -- '--approve' "$PI_LOG"
}

@test "supported exact resume reapplies role extension and prompt" {
  setup_pi
  run rzr-pi-watchtower.sh --resume session-123 --cwd "$TEST_ROOT"
  assert_success
  grep -Fx 'role=1' "$PI_LOG"
  grep -A1 -Fx -- '--session' "$PI_LOG" | grep -Fx session-123
  grep -Fx "$REPO_ROOT/.pi/extensions/rozoro-watchtower.ts" "$PI_LOG"
  grep -Fx "$REPO_ROOT/templates/watchtower.md" "$PI_LOG"
}

@test "watchtower launcher refuses outside an owning Herdr pane" {
  setup_pi; unset HERDR_PANE_ID
  run rzr-pi-watchtower.sh
  assert_failure
  assert_output_contains HERDR_PANE_ID
  [ ! -e "$PI_LOG" ]
}
