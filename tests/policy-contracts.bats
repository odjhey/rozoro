#!/usr/bin/env bats

@test "delivery policy contracts agree" {
  run python3 "$BATS_TEST_DIRNAME/python/test_policy_contracts.py"
  [ "$status" -eq 0 ]
}
