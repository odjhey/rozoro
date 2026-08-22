#!/usr/bin/env bats
load test_helper/common
bats_require_minimum_version 1.5.0

make_engine() {
  name="$1"
  mkdir -p "$TEST_ROOT/engines"
  cat > "$TEST_ROOT/engines/$name" <<'SH'
#!/usr/bin/env bash
{
  printf 'call'
  printf '\t%s' "$@"
  printf '\n'
} >> "$ENGINE_LOG"
SH
  chmod +x "$TEST_ROOT/engines/$name"
}

@test "runner prefers Podman and applies its SELinux-safe option" {
  make_engine podman
  make_engine docker
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env PATH="$TEST_ROOT/engines:$PATH" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
  assert_file_contains "$ENGINE_LOG" $'call\tbuild'
  assert_file_contains "$ENGINE_LOG" "$REPO_ROOT/tests/Containerfile"
  assert_file_contains "$ENGINE_LOG" $'localhost/rozoro-tests:bats-1.14.0\t'
  assert_file_contains "$ENGINE_LOG" $'call\trun\t--rm\t--network\tnone\t--read-only'
  assert_file_contains "$ENGINE_LOG" "$REPO_ROOT:/workspace:ro"
  assert_file_contains "$ENGINE_LOG" $'label=disable\tlocalhost/rozoro-tests:bats-1.14.0\t--formatter\ttap\t/workspace/tests'
}

@test "runner falls back to Docker without Podman-only options" {
  make_engine docker
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env PATH="$TEST_ROOT/engines:$PATH" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
  assert_file_contains "$ENGINE_LOG" $'call\tbuild'
  assert_file_contains "$ENGINE_LOG" $'call\trun'
  case "$(cat "$ENGINE_LOG")" in
    *label=disable*) return 1 ;;
  esac
}

@test "CONTAINER_ENGINE selects an explicit executable" {
  make_engine custom-engine
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env CONTAINER_ENGINE="$TEST_ROOT/engines/custom-engine" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
}

@test "missing explicit container engine fails before a build" {
  run -127 env CONTAINER_ENGINE=missing-engine bash "$REPO_ROOT/tests/run.sh"
  [ "$status" -eq 127 ]
  assert_output_contains "CONTAINER_ENGINE 'missing-engine' was not found on PATH"
}

@test "runner explains when neither container engine is installed" {
  mkdir -p "$TEST_ROOT/no-engines"
  ln -s "$(command -v bash)" "$TEST_ROOT/no-engines/bash"
  ln -s "$(command -v cat)" "$TEST_ROOT/no-engines/cat"
  ln -s "$(command -v dirname)" "$TEST_ROOT/no-engines/dirname"

  run -127 env PATH="$TEST_ROOT/no-engines" "$TEST_ROOT/no-engines/bash" "$REPO_ROOT/tests/run.sh"
  [ "$status" -eq 127 ]
  assert_output_contains "the test suite requires Podman or Docker"
}
