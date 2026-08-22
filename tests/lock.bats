#!/usr/bin/env bats
load test_helper/common

@test "live lock holder is refused" {
  mkdir -p "$ROZORO_HOME/state/.lock"
  printf '%s\n' "$$" > "$ROZORO_HOME/state/.lock/pid"
  run rzr-lock.sh acquire </dev/null
  assert_failure
  assert_output_contains "held by pid $$"
}

@test "stale holder is reclaimed" {
  mkdir -p "$ROZORO_HOME/state/.lock"
  printf '99999999\n' > "$ROZORO_HOME/state/.lock/pid"
  run rzr-lock.sh acquire </dev/null
  assert_success
  [ ! -d "$ROZORO_HOME/state/.lock" ]
}

@test "normal lock release removes owned directory" {
  run rzr-lock.sh acquire </dev/null
  assert_success
  [ ! -d "$ROZORO_HOME/state/.lock" ]
}

@test "protected command failure still releases lock" {
  run bash -c '. "$1/bin/rzr-lib.sh"; fail() { return 23; }; rzr_with_lock 0 fail' _ "$REPO_ROOT"
  [ "$status" -eq 23 ]
  [ ! -d "$ROZORO_HOME/state/.lock" ]
}
