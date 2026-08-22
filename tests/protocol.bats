#!/usr/bin/env bats
load test_helper/common

@test "protocol v1 Python contract tests pass" {
  run python3 -m unittest discover -s "$REPO_ROOT/tests/python" -p 'test_*.py' -v
  assert_success
}
