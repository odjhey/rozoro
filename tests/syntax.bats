#!/usr/bin/env bats
load test_helper/common

@test "all shell entry points parse" {
  for file in "$REPO_ROOT"/bin/* "$REPO_ROOT"/hooks/*.sh "$REPO_ROOT"/tests/run.sh "$REPO_ROOT"/tests/fakes/herdr "$REPO_ROOT"/tests/test_helper/common.bash; do
    [ -f "$file" ] || continue
    case "$file" in *.py) continue ;; esac
    run bash -n "$file"
    [ "$status" -eq 0 ] || { echo "$file: $output" >&2; return 1; }
  done
}

@test "Pi watchtower event-bus adapter is covered by Node tests" {
  run node --experimental-strip-types --test \
    "$REPO_ROOT/tests/pi-event-bus-adapter.test.ts" \
    "$REPO_ROOT/tests/pi-cutover-additional.test.ts"
  assert_success
}

@test "Python helpers compile into the isolated bytecode root" {
  run python3 -m py_compile "$REPO_ROOT/bin/herdr-eventwait.py" "$REPO_ROOT/tests/test_helper/event_server.py"
  assert_success
  run find "$PYTHONPYCACHEPREFIX" -type f -name 'herdr-eventwait.*.pyc' -print
  assert_success
  [ -n "$output" ]
  run find "$PYTHONPYCACHEPREFIX" -type f -name 'event_server.*.pyc' -print
  assert_success
  [ -n "$output" ]
}
