REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"

setup() {
  unset CODEX_THREAD_ID HERDR_PANE_ID FAKE_CODEX_HAS_QUEUE FAKE_CODEX_QUEUE_FAIL FAKE_HERDR_FAIL_MATCH
  export TEST_ROOT="$BATS_TEST_TMPDIR/fixture"
  export HOME="$TEST_ROOT/home"
  export ROZORO_HOME="$TEST_ROOT/rozoro"
  export RZR_HOME="$ROZORO_HOME"
  export FAKE_HERDR_ROOT="$TEST_ROOT/herdr"
  export FAKE_HERDR_LOG="$FAKE_HERDR_ROOT/argv.log"
  export FAKE_HERDR_SOCKET="$TEST_ROOT/herdr.sock"
  export FAKE_CODEX_LOG="$TEST_ROOT/codex.log"
  export PYTHONPYCACHEPREFIX="$TEST_ROOT/pycache"
  export PYTHONPATH="$REPO_ROOT/tests/test_helper:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
  export PATH="$REPO_ROOT/tests/fakes:$REPO_ROOT/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  mkdir -p "$HOME" "$ROZORO_HOME/state" "$ROZORO_HOME/tasks" "$FAKE_HERDR_ROOT" "$PYTHONPYCACHEPREFIX"
  chmod 700 "$ROZORO_HOME"
  : > "$FAKE_CODEX_LOG"
  SENTINEL="$BATS_TEST_TMPDIR/outside-sentinel"
  printf 'untouched\n' > "$SENTINEL"
  export SENTINEL
  TEST_PIDS=""
  registry_root="${ROZORO_TEST_PROCESS_REGISTRY_ROOT:-$TEST_ROOT}"
  mkdir -p "$registry_root"
  export ROZORO_TEST_PROCESS_REGISTRY="$registry_root/owned-processes-$BATS_TEST_NUMBER-$$.jsonl"
  : > "$ROZORO_TEST_PROCESS_REGISTRY"
  chmod 600 "$ROZORO_TEST_PROCESS_REGISTRY"
}

teardown() {
  PYTHONPATH="$REPO_ROOT" python3 -c 'from tests.test_helper.process_cleanup import cleanup; cleanup()' || true
  for pid in $TEST_PIDS; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  [ "$(cat "$SENTINEL")" = untouched ]
  case "$TEST_ROOT" in "$BATS_TEST_TMPDIR"/*) rm -rf "$TEST_ROOT" ;; *) return 1 ;; esac
}

register_pid() { TEST_PIDS="$TEST_PIDS $1"; }

register_daemon_from_spawn() {
  ROZORO_PROCESS_CLEANUP_NO_ATEXIT=1 PYTHONPATH="$REPO_ROOT" python3 - "$ROZORO_TEST_PROCESS_REGISTRY" <<'PY'
import sys
from pathlib import Path
from tests.test_helper.process_cleanup import register_spawn_file
register_spawn_file(Path(sys.argv[1]))
PY
}

# Octal permission bits of a file, portable across GNU and macOS. Try GNU
# `stat -c` first: on BSD/macOS `-c` is rejected (clean non-zero) so we fall back
# to `stat -f`. The reverse order is unsafe — GNU treats `-f` as --file-system and
# would print filesystem info with a zero exit, masking the real permission bits.
file_perm() { stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"; }

# Stable byte/shape snapshot of a directory, including VCS metadata. Timestamps
# are intentionally excluded: teardown must not change names, modes, links, or
# file bytes, while merely reading a directory may update access times.
directory_snapshot() {
  python3 - "$1" <<'PY'
import hashlib, os, stat, sys
root = os.fsencode(sys.argv[1])
for parent, dirs, files in os.walk(root):
    dirs.sort(); files.sort()
    for name in dirs + files:
        path = os.path.join(parent, name)
        rel = os.path.relpath(path, root)
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            payload = b"link:" + os.readlink(path)
        elif stat.S_ISREG(mode):
            with open(path, "rb") as handle: payload = handle.read()
        else:
            payload = b""
        print(os.fsdecode(rel), oct(stat.S_IMODE(mode)), hashlib.sha256(payload).hexdigest())
PY
}

assert_success() {
  [ "$status" -eq 0 ] || { printf 'expected success, got %s:\n%s\n' "$status" "$output" >&2; return 1; }
}

assert_failure() {
  [ "$status" -ne 0 ] || { printf 'expected failure:\n%s\n' "$output" >&2; return 1; }
}

assert_output_contains() {
  case "$output" in *"$1"*) ;; *) printf 'output did not contain <%s>:\n%s\n' "$1" "$output" >&2; return 1 ;; esac
}

assert_file_contains() {
  grep -F -- "$2" "$1" >/dev/null || { printf '%s did not contain <%s>\n' "$1" "$2" >&2; return 1; }
}

write_meta() {
  id="$1"; shift
  mkdir -p "$ROZORO_HOME/state"
  printf '%s\n' "$@" > "$ROZORO_HOME/state/$id.meta"
}

write_handoff() {
  id="$1"; shift
  mkdir -p "$ROZORO_HOME/tasks/$id"
  printf '%s\n' "$@" > "$ROZORO_HOME/tasks/$id/handoff.md"
}

fake_response() {
  key="$1"; shift
  printf '%s\n' "$@" > "$FAKE_HERDR_ROOT/$key.out"
}

fake_status() {
  pane="$1" status_value="$2"
  printf '%s\n' "$status_value" > "$FAKE_HERDR_ROOT/status.$pane"
}

# Configure a pane's full agent-get shape for registration/gating tests:
#   fake_pane <pane> <status> [kind] [interactive_ready:true|false] [agent_session]
fake_pane() {
  pane="$1"; printf '%s\n' "$2" > "$FAKE_HERDR_ROOT/status.$pane"
  [ $# -ge 3 ] && printf '%s\n' "$3" > "$FAKE_HERDR_ROOT/kind.$pane"
  printf '%s\n' "${4:-true}" > "$FAKE_HERDR_ROOT/ready.$pane"
  [ $# -lt 5 ] || printf '%s\n' "$5" > "$FAKE_HERDR_ROOT/session.$pane"
}

start_event_server() {
  mode="$1"; shift
  python3 "$REPO_ROOT/tests/test_helper/event_server.py" "$FAKE_HERDR_SOCKET" "$FAKE_HERDR_ROOT/request.json" "$mode" "$@" 3>&- &
  register_pid "$!"
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    [ -S "$FAKE_HERDR_SOCKET" ] && return 0
    sleep 0.05
  done
  return 1
}
