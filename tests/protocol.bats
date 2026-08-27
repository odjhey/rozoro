#!/usr/bin/env bats
load test_helper/common

@test "protocol v1 Python contract tests pass" {
  # Python filesystem tests exercise ordinary process defaults explicitly.
  umask 022
  run python3 -m unittest discover -s "$REPO_ROOT/tests/python" -p 'test_*.py' -v
  assert_success
}
