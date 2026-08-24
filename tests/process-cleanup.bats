#!/usr/bin/env bats
TOOL_PATH="$PATH"
load test_helper/common

wait_for_file() { for _ in $(seq 1 200); do [ -s "$1" ] && return; sleep .02; done; return 1; }
assert_no_process() { run kill -0 "$1"; [ "$status" -ne 0 ]; }
_scan_processes() { ps -eo command= | grep -F 'rozorod.py --home' | grep -F -- "$1"; }
_scan_artifacts() { find "$1" -type s -o -name monitor.lock -o -name 'monitor.db*' | grep .; }
assert_isolated_clean() {
  root="$1"
  run _scan_processes "$root"
  [ "$status" -ne 0 ] || { printf 'leaked rozorod.py process under %s:\n%s\n' "$root" "$output" >&2; return 1; }
  run _scan_artifacts "$root"
  [ "$status" -ne 0 ] || { printf 'leftover daemon artifacts under %s:\n%s\n' "$root" "$output" >&2; return 1; }
}

@test "SIGINT and SIGTERM reap exact Python direct and detached daemon owners" {
  for spec in 'direct INT' 'detached TERM'; do
    set -- $spec; root="/tmp/rzr-int-py-$BATS_TEST_NUMBER-$$-$1"; mkdir -p "$root"; out="$root/home-path"
    PATH="$TOOL_PATH" TMPDIR="$root" python3 "$REPO_ROOT/tests/fixtures/daemon_owner.py" "$1" "$out" & runner=$!
    wait_for_file "$out"; home="$(cat "$out")"; daemon_pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "$home/monitor.lock")"
    kill -"$2" "$runner"; wait "$runner" 2>/dev/null || true
    for _ in $(seq 1 100); do kill -0 "$daemon_pid" 2>/dev/null || break; sleep .02; done
    assert_no_process "$daemon_pid"
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
  assert_no_process "$daemon_pid"
  assert_isolated_clean "$root"
}

@test "interrupted Bats test tears down detached daemon without relying on socket" {
  root="/tmp/rzr-int-bats-$$"; mkdir -p "$root"; out="$root/home-path"
  PATH="$TOOL_PATH" TMPDIR="$root" ROZORO_TEST_PROCESS_REGISTRY_ROOT="$root" INTERRUPT_REGISTRY_ROOT="$root" INTERRUPT_HOME_FILE="$out" INTERRUPT_PYTHON="$(PATH="$TOOL_PATH" command -v python3)" \
    python3 "$REPO_ROOT/tests/test_helper/interrupt_runner.py" bats "$REPO_ROOT/tests/fixtures/daemon-owner.bats" & runner=$!
  wait_for_file "$out"; home="$(cat "$out")"; daemon_pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "$home/monitor.lock")"
  rm -f "$home/monitor.sock"
  kill -TERM "$runner"; wait "$runner" 2>/dev/null || true
  for _ in $(seq 1 100); do kill -0 "$daemon_pid" 2>/dev/null || break; sleep .02; done
  assert_no_process "$daemon_pid"
  assert_isolated_clean "$root"
}

@test "manual live cleanup reaps exact spawn owner after socket and lock loss" {
  root="/tmp/rzr-live-stop-$$"; home="$root/home"; registry="$root/owned-processes.jsonl"; mkdir -p "$home"; chmod 700 "$home"
  PATH="$TOOL_PATH" PYTHONPATH="$REPO_ROOT/tests/test_helper:$REPO_ROOT" ROZORO_HOME="$home" ROZORO_TEST_PROCESS_REGISTRY="$registry" \
    python3 "$REPO_ROOT/bin/rzr-monitor.py" start
  daemon_pid="$(python3 -c 'import json,sys; print(json.loads(open(sys.argv[1]).readline())["pid"])' "$registry")"
  rm -f "$home/monitor.sock" "$home/monitor.lock"
  run env PATH="$TOOL_PATH" PYTHONPATH="$REPO_ROOT/tests/test_helper:$REPO_ROOT" ROZORO_HOME="$home" ROZORO_TEST_PROCESS_REGISTRY="$registry" ROZORO_TEST_CLEANUP_ON_STOP=1 \
    python3 "$REPO_ROOT/bin/rzr-monitor.py" stop
  assert_failure
  for _ in $(seq 1 100); do kill -0 "$daemon_pid" 2>/dev/null || break; sleep .02; done
  assert_no_process "$daemon_pid"; assert_isolated_clean "$root"
}

@test "SIGKILLed interrupt runner is reaped by a surviving external guardian" {
  root="/tmp/rzr-kill-bats-$$"; mkdir -p "$root"; out="$root/home-path"; child_file="$root/child-pid"
  PATH="$TOOL_PATH" TMPDIR="$root" ROZORO_TEST_PROCESS_REGISTRY_ROOT="$root" INTERRUPT_REGISTRY_ROOT="$root" INTERRUPT_CHILD_PID_FILE="$child_file" INTERRUPT_HOME_FILE="$out" INTERRUPT_PYTHON="$(PATH="$TOOL_PATH" command -v python3)" \
    python3 "$REPO_ROOT/tests/test_helper/interrupt_runner.py" bats "$REPO_ROOT/tests/fixtures/daemon-owner.bats" & guardian=$!
  wait_for_file "$out"; wait_for_file "$child_file"; home="$(cat "$out")"; daemon_pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "$home/monitor.lock")"
  registry="$(find "$root" -name 'owned-processes-*.jsonl' | head -1)"; wait_for_file "$registry"
  kill -KILL "$guardian"; wait "$guardian" 2>/dev/null || true
  for _ in $(seq 1 100); do kill -0 "$daemon_pid" 2>/dev/null || break; sleep .02; done
  assert_no_process "$daemon_pid"
  assert_isolated_clean "$root"
}
