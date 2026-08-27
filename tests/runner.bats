#!/usr/bin/env bats
load test_helper/common
bats_require_minimum_version 1.5.0

make_engine() {
  name="$1"
  mkdir -p "$TEST_ROOT/engines"
  cat > "$TEST_ROOT/engines/$name" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = info ]; then
  exit 0
fi
{
  printf 'call'
  printf '\t%s' "$@"
  printf '\n'
} >> "$ENGINE_LOG"
case " $* " in
  *" --entrypoint node "*)
    case "${H3_TAP_MODE:-pass}" in
      pass) printf '%s\n' 'TAP version 13' 'ok 1 - a' 'ok 2 - b' 'ok 3 - c' 'ok 4 - d' 'ok 5 - e' 'ok 6 - f' '1..6' '# tests 6' '# suites 0' '# pass 6' '# fail 0' '# cancelled 0' '# skipped 0' '# todo 0' '# duration_ms 1' ;;
      skip) printf '%s\n' '1..6' '# tests 6' '# pass 5' '# fail 0' '# cancelled 0' '# skipped 1' '# todo 0' ;;
      removed) : ;;
      count) printf '%s\n' '1..5' '# tests 5' '# pass 5' '# fail 0' '# cancelled 0' '# skipped 0' '# todo 0' ;;
      fail) printf '%s\n' '1..6' '# tests 6' '# pass 5' '# fail 1' '# cancelled 0' '# skipped 0' '# todo 0' ;;
      cancelled) printf '%s\n' '1..6' '# tests 6' '# pass 5' '# fail 0' '# cancelled 1' '# skipped 0' '# todo 0' ;;
      todo) printf '%s\n' '1..6' '# tests 6' '# pass 5' '# fail 0' '# cancelled 0' '# skipped 0' '# todo 1' ;;
      malformed) printf '%s\n' '1..6' '# tests six' '# pass 6' '# fail 0' '# cancelled 0' '# skipped 0' '# todo 0' ;;
      spoof) printf '%s\n' '    1..6' '    # tests 6' '    # pass 6' '    # fail 0' '    # cancelled 0' '    # skipped 0' '    # todo 0' ;;
      status) echo 'original H3 failure output'; exit 42 ;;
    esac
    ;;
esac
SH
  chmod +x "$TEST_ROOT/engines/$name"
}

make_unavailable_engine() {
  name="$1"
  mkdir -p "$TEST_ROOT/engines"
  cat > "$TEST_ROOT/engines/$name" <<'SH'
#!/usr/bin/env bash
exit 125
SH
  chmod +x "$TEST_ROOT/engines/$name"
}

@test "runner prefers Podman and applies its SELinux-safe option" {
  make_engine podman
  make_engine docker
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env PATH="$TEST_ROOT/engines:$PATH" TEST_JOBS=4 bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 3 ]
  assert_file_contains "$ENGINE_LOG" $'call\tbuild'
  assert_file_contains "$ENGINE_LOG" "$REPO_ROOT/tests/Containerfile"
  assert_file_contains "$ENGINE_LOG" $'localhost/rozoro-tests:bats-1.14.0\t'
  assert_file_contains "$ENGINE_LOG" $'call\trun\t--rm\t--network\tnone\t--read-only'
  assert_file_contains "$ENGINE_LOG" $'label=disable\t--entrypoint\tnode\tlocalhost/rozoro-tests:bats-1.14.0\t--test\t--test-reporter=tap\t/workspace/tests/pi-extension-home-matrix.test.ts'
  assert_file_contains "$ENGINE_LOG" "$REPO_ROOT:/workspace:ro"
  assert_file_contains "$ENGINE_LOG" $'label=disable\tlocalhost/rozoro-tests:bats-1.14.0\t--formatter\ttap\t--jobs\t4\t/workspace/tests'
}

@test "runner falls back to Docker without Podman-only options" {
  make_engine docker
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env PATH="$TEST_ROOT/engines:$PATH" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 3 ]
  assert_file_contains "$ENGINE_LOG" $'call\tbuild'
  assert_file_contains "$ENGINE_LOG" $'call\trun'
  assert_file_contains "$ENGINE_LOG" $'--entrypoint\tnode\tlocalhost/rozoro-tests:bats-1.14.0\t--test\t--test-reporter=tap\t/workspace/tests/pi-extension-home-matrix.test.ts'
  case "$(cat "$ENGINE_LOG")" in
    *label=disable*) return 1 ;;
  esac
}

@test "runner skips unavailable Podman and uses Docker" {
  make_unavailable_engine podman
  make_engine docker
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env PATH="$TEST_ROOT/engines:$PATH" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 3 ]
  assert_file_contains "$ENGINE_LOG" $'call\tbuild'
  assert_file_contains "$ENGINE_LOG" $'call\trun'
  assert_file_contains "$ENGINE_LOG" $'--entrypoint\tnode\tlocalhost/rozoro-tests:bats-1.14.0\t--test\t--test-reporter=tap\t/workspace/tests/pi-extension-home-matrix.test.ts'
  case "$(cat "$ENGINE_LOG")" in
    *label=disable*) return 1 ;;
  esac
}

@test "CONTAINER_ENGINE selects an explicit executable" {
  make_engine custom-engine
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env CONTAINER_ENGINE="$TEST_ROOT/engines/custom-engine" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 3 ]
}

@test "runner rejects skipped, absent, drifted, non-passing, and malformed H3 summaries" {
  make_engine custom-engine
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  for mode in skip removed count fail cancelled todo malformed spoof; do
    : > "$ENGINE_LOG"
    run env CONTAINER_ENGINE="$TEST_ROOT/engines/custom-engine" H3_TAP_MODE="$mode" bash "$REPO_ROOT/tests/run.sh"
    assert_failure
    assert_output_contains "H3 requires exactly 6 passing, non-skipped top-level tests"
    [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
  done
}

@test "runner preserves H3 output and exit status" {
  make_engine custom-engine
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env CONTAINER_ENGINE="$TEST_ROOT/engines/custom-engine" H3_TAP_MODE=status bash "$REPO_ROOT/tests/run.sh"
  [ "$status" -eq 42 ]
  assert_output_contains "original H3 failure output"
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
