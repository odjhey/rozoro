#!/usr/bin/env bats
load test_helper/common

@test "dispatcher monitor status diagnoses down in JSON" {
  run "$REPO_ROOT/bin/rozoro" monitor status --json
  assert_failure
  python3 -c 'import json,sys; v=json.loads(sys.argv[1]); assert v["running"] is False and v["spool_backlog"] == 0' "$output"
}

@test "dispatcher monitor detached lifecycle becomes healthy and stops proven owner" {
  run "$REPO_ROOT/bin/rozoro" monitor start
  assert_success
  run "$REPO_ROOT/bin/rozoro" monitor status --json
  assert_success
  python3 -c 'import json,sys; v=json.loads(sys.argv[1]); assert v["running"] and v["schema_version"] >= 1' "$output"
  run "$REPO_ROOT/bin/rozoro" monitor stop
  assert_success
  run "$REPO_ROOT/bin/rozoro" monitor status --json
  assert_failure
}
