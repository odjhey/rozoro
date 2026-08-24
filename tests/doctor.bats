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

@test "doctor rejects Python below the monitor floor with an actionable macOS install" {
  mkdir -p "$TEST_ROOT/doctor-path"
  for command_name in bash dirname herdr jq; do
    ln -s "$(command -v "$command_name")" "$TEST_ROOT/doctor-path/$command_name"
  done
  cat > "$TEST_ROOT/doctor-path/python3" <<'SH'
#!/bin/sh
if [ "$1" = "--version" ]; then echo 'Python 3.8.18'; exit 0; fi
exit 1
SH
  chmod +x "$TEST_ROOT/doctor-path/python3"

  run env PATH="$TEST_ROOT/doctor-path:/usr/bin:/bin:/usr/sbin:/sbin" "$REPO_ROOT/bin/rozoro" doctor
  assert_failure
  assert_output_contains 'python3 >=3.9 required for the resident monitor'
  assert_output_contains 'brew install python'
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
