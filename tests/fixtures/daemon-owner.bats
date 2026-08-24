#!/usr/bin/env bats
load ../test_helper/common
REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

@test "interrupted Bats owner reaps its detached daemon" {
  export PATH="$(dirname "$INTERRUPT_PYTHON"):$PATH"
  chmod 700 "$ROZORO_HOME"
  "$REPO_ROOT/bin/rozoro" monitor start
  register_daemon_from_lock "$ROZORO_HOME"
  printf '%s\n' "$ROZORO_HOME" > "$INTERRUPT_HOME_FILE"
  while :; do sleep 1; done
}
