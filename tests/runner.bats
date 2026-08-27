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
      pass|literal-skip|not-ok|duplicate-header|duplicate-results)
        printf '%s\n' 'TAP version 13'
        [ "${H3_TAP_MODE:-pass}" = duplicate-header ] && printf '%s\n' 'TAP version 13'
        printf '%s\n' \
          'ok 1 - Node: extension socket home matrix P/L/B/E/D/R/T/X plus unresolved user (O=N/A)' \
          'ok 2 - Node: 20x per cell native fresh-process socket-home repetition' \
          'ok 3 - Node: forced timeout and peer-close write race leave no survivors' \
          'ok 4 - Bun: extension socket home matrix P/L/B/E/D/R/T/X plus unresolved user (O=N/A)' \
          'ok 5 - Bun: 20x per cell native fresh-process socket-home repetition' \
          'ok 6 - Bun: forced timeout and peer-close write race leave no survivors' |
          if [ "${H3_TAP_MODE:-pass}" = literal-skip ]; then sed 's/$/ # SKIP/'; elif [ "${H3_TAP_MODE:-pass}" = not-ok ]; then sed '3s/^ok/not ok/'; else cat; fi
        [ "${H3_TAP_MODE:-pass}" = duplicate-results ] && printf '%s\n' 'ok 6 - Bun: forced timeout and peer-close write race leave no survivors'
        printf '%s\n' '1..6' '# tests 6' '# suites 0' '# pass 6' '# fail 0' '# cancelled 0' '# skipped 0' '# todo 0' '# duration_ms 1'
        ;;
      summary-only) printf '%s\n' 'TAP version 13' '1..6' '# tests 6' '# pass 6' '# fail 0' '# cancelled 0' '# skipped 0' '# todo 0' ;;
      child-spoof) printf '%s\n' '    TAP version 13' '    ok 1 - child' '    ok 2 - child' '    ok 3 - child' '    ok 4 - child' '    ok 5 - child' '    ok 6 - child' '    1..6' '    # tests 6' '    # pass 6' '    # fail 0' '    # cancelled 0' '    # skipped 0' '    # todo 0' ;;
      indented) printf '%s\n' 'TAP version 13' '    ok 1 - child' '    ok 2 - child' '    ok 3 - child' '    ok 4 - child' '    ok 5 - child' '    ok 6 - child' '1..6' '# tests 6' '# pass 6' '# fail 0' '# cancelled 0' '# skipped 0' '# todo 0' ;;
      removed) : ;;
      count) printf '%s\n' 'TAP version 13' 'ok 1 - wrong' '1..5' '# tests 5' '# pass 5' '# fail 0' '# cancelled 0' '# skipped 0' '# todo 0' ;;
      fail|cancelled|todo|malformed) printf '%s\n' 'TAP version 13' '1..6' '# tests six' '# pass 5' '# fail 1' '# cancelled 0' '# skipped 0' '# todo 0' ;;
      status) echo 'original H3 failure output'; exit 42 ;;
      signal) kill -TERM "$PPID"; sleep 1 ;;
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

@test "runner rejects spoofed or incomplete TAP and mismatched H3 evidence" {
  make_engine custom-engine
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  for mode in summary-only child-spoof indented duplicate-header duplicate-results literal-skip not-ok removed count fail cancelled todo malformed; do
    : > "$ENGINE_LOG"
    run env CONTAINER_ENGINE="$TEST_ROOT/engines/custom-engine" H3_TAP_MODE="$mode" bash "$REPO_ROOT/tests/run.sh"
    assert_failure
    assert_output_contains "H3 requires exactly 6 passing, non-skipped top-level tests"
    [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
  done
}

@test "runner removes its exact TAP tempfile before full Bats" {
  make_engine custom-engine
  export ENGINE_LOG="$TEST_ROOT/engine.log"
  mkdir -p "$TEST_ROOT/tmp"
  touch "$TEST_ROOT/tmp/sentinel"

  run env CONTAINER_ENGINE="$TEST_ROOT/engines/custom-engine" TMPDIR="$TEST_ROOT/tmp" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(find "$TEST_ROOT/tmp" -mindepth 1 -maxdepth 1 -print | wc -l)" -eq 1 ]
  [ -e "$TEST_ROOT/tmp/sentinel" ]
}

@test "runner removes its TAP tempfile on H3 failure and signal" {
  make_engine custom-engine
  export ENGINE_LOG="$TEST_ROOT/engine.log"
  mkdir -p "$TEST_ROOT/tmp"
  touch "$TEST_ROOT/tmp/sentinel"

  for mode in status signal; do
    run env CONTAINER_ENGINE="$TEST_ROOT/engines/custom-engine" TMPDIR="$TEST_ROOT/tmp" H3_TAP_MODE="$mode" bash "$REPO_ROOT/tests/run.sh"
    assert_failure
    [ "$(find "$TEST_ROOT/tmp" -mindepth 1 -maxdepth 1 -print | wc -l)" -eq 1 ]
    [ -e "$TEST_ROOT/tmp/sentinel" ]
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
