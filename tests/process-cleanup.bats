#!/usr/bin/env bats
TOOL_PATH="$PATH"
load test_helper/common

wait_for_file() { for _ in $(seq 1 200); do [ -s "$1" ] && return; sleep .02; done; return 1; }
assert_isolated_clean() {
  root="$1"
  ! ps -eo command= | grep -F 'rozorod.py --home' | grep -F -- "$root" >/dev/null
  ! find "$root" -type s -o -name monitor.lock -o -name 'monitor.db*' | grep . >/dev/null
}

@test "SIGINT and SIGTERM reap exact Python direct and detached daemon owners" {
  for spec in 'direct INT' 'detached TERM'; do
    set -- $spec; root="/tmp/rzr-int-py-$BATS_TEST_NUMBER-$$-$1"; mkdir -p "$root"; out="$root/home-path"
    PATH="$TOOL_PATH" TMPDIR="$root" python3 "$REPO_ROOT/tests/fixtures/daemon_owner.py" "$1" "$out" & runner=$!
    wait_for_file "$out"; home="$(cat "$out")"; daemon_pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "$home/monitor.lock")"
    kill -"$2" "$runner"; wait "$runner" 2>/dev/null || true
    for _ in $(seq 1 100); do kill -0 "$daemon_pid" 2>/dev/null || break; sleep .02; done
    ! kill -0 "$daemon_pid" 2>/dev/null
    assert_isolated_clean "$root"
  done
}

@test "assertion failure invokes Python atexit cleanup" {
  root="/tmp/rzr-int-assert-$$"; mkdir -p "$root"; out="$root/home-path"
  run env PATH="$TOOL_PATH" TMPDIR="$root" python3 "$REPO_ROOT/tests/fixtures/daemon_owner.py" assertion "$out"
  assert_failure
  assert_isolated_clean "$root"
}

@test "SIGTERM reaps Node-owned daemon and isolated artifacts" {
  root="/tmp/rzr-int-node-$$"; home="$root/home"; out="$root/home-path"; mkdir -p "$root"
  PATH="$TOOL_PATH" node --experimental-strip-types "$REPO_ROOT/tests/fixtures/daemon-owner.ts" "$home" "$out" & runner=$!
  wait_for_file "$out"; daemon_pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "$home/monitor.lock")"
  kill -TERM "$runner"; wait "$runner" 2>/dev/null || true
  ! kill -0 "$daemon_pid" 2>/dev/null
  assert_isolated_clean "$root"
}

@test "interrupted Bats test tears down detached daemon without relying on socket" {
  root="/tmp/rzr-int-bats-$$"; mkdir -p "$root"; out="$root/home-path"
  PATH="$TOOL_PATH" TMPDIR="$root" INTERRUPT_HOME_FILE="$out" INTERRUPT_PYTHON="$(PATH="$TOOL_PATH" command -v python3)" \
    python3 "$REPO_ROOT/tests/test_helper/interrupt_runner.py" bats "$REPO_ROOT/tests/fixtures/daemon-owner.bats" & runner=$!
  wait_for_file "$out"; home="$(cat "$out")"; daemon_pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "$home/monitor.lock")"
  rm -f "$home/monitor.sock"
  kill -TERM "$runner"; wait "$runner" 2>/dev/null || true
  for _ in $(seq 1 100); do kill -0 "$daemon_pid" 2>/dev/null || break; sleep .02; done
  ! kill -0 "$daemon_pid" 2>/dev/null
  assert_isolated_clean "$root"
}
