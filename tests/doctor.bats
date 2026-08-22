#!/usr/bin/env bats
load test_helper/common

@test "doctor succeeds checkout-locally without Rozoro bin on PATH" {
  mkdir -p "$ROZORO_HOME/crew"
  printf '%s\n' '{"harness":"codex","model":"gpt-5.6-sol","effort":"low"}' > "$ROZORO_HOME/crew/default.json"

  run env PATH="$REPO_ROOT/tests/fakes:/usr/bin:/bin:/usr/sbin:/sbin" "$REPO_ROOT/bin/rozoro" doctor
  assert_success
  assert_output_contains 'all good'
  assert_output_contains './bin/rozoro start t1 --body <file> --cwd <repo>'
  [[ "$output" != *'bin/ on PATH'* ]]
}

@test "doctor still reports missing external dependencies" {
  mkdir -p "$TEST_ROOT/doctor-path"
  for command_name in bash dirname jq python3; do
    ln -s "$(command -v "$command_name")" "$TEST_ROOT/doctor-path/$command_name"
  done

  run env PATH="$TEST_ROOT/doctor-path" "$REPO_ROOT/bin/rozoro" doctor
  assert_failure
  assert_output_contains 'herdr not found on PATH'
  assert_output_contains './bin/rozoro doctor'
}
