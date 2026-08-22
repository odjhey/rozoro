#!/usr/bin/env bats
load test_helper/common

@test "all shell entry points parse" {
  for file in "$REPO_ROOT"/bin/* "$REPO_ROOT"/tests/run.sh "$REPO_ROOT"/tests/fakes/herdr "$REPO_ROOT"/tests/test_helper/common.bash; do
    [ -f "$file" ] || continue
    case "$file" in *.py) continue ;; esac
    run bash -n "$file"
    [ "$status" -eq 0 ] || { echo "$file: $output" >&2; return 1; }
  done
}

@test "Python helpers compile into the isolated bytecode root" {
  run python3 -m py_compile "$REPO_ROOT/bin/herdr-eventwait.py" "$REPO_ROOT/tests/test_helper/event_server.py"
  assert_success
  [ -d "$PYTHONPYCACHEPREFIX" ]
  [ ! -d "$REPO_ROOT/bin/__pycache__" ]
  [ ! -d "$REPO_ROOT/tests/test_helper/__pycache__" ]
}
