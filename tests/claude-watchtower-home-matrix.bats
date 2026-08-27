#!/usr/bin/env bats
load test_helper/common

setup() {
  unset CODEX_THREAD_ID HERDR_PANE_ID FAKE_HERDR_FAIL_MATCH
  export TEST_ROOT="$BATS_TEST_TMPDIR/fixture" HOME="$BATS_TEST_TMPDIR/fixture/home"
  export ROZORO_HOME="$TEST_ROOT/rozoro" RZR_HOME="$TEST_ROOT/rozoro"
  export FAKE_HERDR_ROOT="$TEST_ROOT/herdr" FAKE_HERDR_LOG="$TEST_ROOT/herdr/argv.log"
  export FAKE_HERDR_SOCKET="$TEST_ROOT/herdr.sock" PYTHONPYCACHEPREFIX="$TEST_ROOT/pycache"
  export PATH="$REPO_ROOT/tests/fakes:$REPO_ROOT/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  mkdir -p "$HOME" "$ROZORO_HOME/state" "$ROZORO_HOME/tasks" "$FAKE_HERDR_ROOT" "$PYTHONPYCACHEPREFIX"
  chmod 700 "$ROZORO_HOME"; TEST_PIDS=""
  SENTINEL="$BATS_TEST_TMPDIR/outside-sentinel"; printf 'untouched\n' > "$SENTINEL"; export SENTINEL
  if [ -x /opt/homebrew/bin/python3 ]; then
    mkdir -p "$TEST_ROOT/pybin"; ln -s /opt/homebrew/bin/python3 "$TEST_ROOT/pybin/python3"
    PATH="$TEST_ROOT/pybin:$PATH"
  fi
  export PYTHONDONTWRITEBYTECODE=1 PATH HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION=2.1.241 FAKE_CLAUDE_SLEEP=30
  fake_pane p1 idle claude true
  mkdir -p "$TEST_ROOT/fake-bin"
  cat > "$TEST_ROOT/fake-bin/claude" <<'SH'
#!/bin/sh
if [ "${1:-}" = --version ]; then
  printf 'mode=probe home=%s\n' "${ROZORO_HOME-<unset>}" >> "$CLAUDE_ENV_LOG"
else
  printf 'mode=launch home=%s policy=%s core=%s mission_name=%s mission_source=%s mission=%s\n' \
    "${ROZORO_HOME-<unset>}" "${ROZORO_WT_POLICY_SHA256-<unset>}" \
    "${ROZORO_WT_POLICY_CORE_SHA256-<unset>}" "${ROZORO_WT_POLICY_MISSION_NAME-<unset>}" \
    "${ROZORO_WT_POLICY_MISSION_SOURCE-<unset>}" "${ROZORO_WT_POLICY_MISSION_SHA256-<unset>}" >> "$CLAUDE_ENV_LOG"
  if [ -n "${FAKE_CLAUDE_LAUNCH_FAILURE:-}" ]; then
    if [ "${FAKE_CLAUDE_WAIT_READY:-0}" = 1 ]; then
      for _ in $(seq 1 400); do
        ready="$(find "$ROZORO_HOME/watchtowers" -name 'poller-ready.*' -type f 2>/dev/null | head -1)"
        [ -n "$ready" ] && [ -s "$ready" ] && { sleep 1; break; }
        sleep .025
      done
    else sleep "${FAKE_CLAUDE_FAILURE_DELAY:-1}"
    fi
    exit "$FAKE_CLAUDE_LAUNCH_FAILURE"
  fi
fi
exec "$CLAUDE_FAKE" "$@"
SH
  chmod +x "$TEST_ROOT/fake-bin/claude"
  export CLAUDE_FAKE="$REPO_ROOT/tests/fakes/claude" PATH="$TEST_ROOT/fake-bin:$PATH"
}

process_alive() { kill -0 "$1" 2>/dev/null; }

cleanup_case() {
  rc="$1"; trap - EXIT
  [ -z "${CASE_OWNER:-}" ] || { kill "$CASE_OWNER" 2>/dev/null || true; wait "$CASE_OWNER" 2>/dev/null || true; }
  if [ -n "${CASE_POLLER:-}" ]; then
    for _ in $(seq 1 600); do ! process_alive "$CASE_POLLER" && break; sleep .05; done
    process_alive "$CASE_POLLER" && rc=1
  fi
  monitor_pid=""
  [ -z "${CASE_HOME:-}" ] || [ ! -f "$CASE_HOME/monitor.pid" ] || monitor_pid="$(cat "$CASE_HOME/monitor.pid" 2>/dev/null || true)"
  [ -z "${CASE_HOME:-}" ] || ROZORO_HOME="$CASE_HOME" RZR_HOME= "$REPO_ROOT/bin/rzr-monitor.sh" stop >/dev/null 2>&1 || true
  if [ -n "$monitor_pid" ]; then
    for _ in $(seq 1 600); do ! process_alive "$monitor_pid" && break; sleep .05; done
    process_alive "$monitor_pid" && rc=1
  fi
  [ -z "${CASE_READY:-}" ] || [ ! -e "$CASE_READY" ] || rc=1
  [ -z "${CASE_HOME:-}" ] || [ ! -S "$CASE_HOME/monitor.sock" ] || rc=1
  [ -z "${CASE_GUARD:-}" ] || rm -rf "$CASE_GUARD"
  exit "$rc"
}

poller_command() {
  python3 - "$1" <<'PY'
import os,subprocess,sys
pid=sys.argv[1]
try: print(open('/proc/'+pid+'/cmdline','rb').read().replace(b'\0',b' ').decode())
except OSError: print(subprocess.check_output(['ps','-p',pid,'-o','command='],text=True))
PY
}

run_launcher_row() (
  label="$1" expected="$2"; shift 2
  CASE_OWNER="" CASE_POLLER="" CASE_READY="" CASE_HOME="$expected" CASE_GUARD="${ROW_GUARD:-}"
  trap 'cleanup_case "$?"' EXIT HUP INT TERM
  env "$@" CLAUDE_ENV_LOG="$TEST_ROOT/$label.env" FAKE_CLAUDE_LOG="$TEST_ROOT/$label.argv" \
    HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION=2.1.241 FAKE_CLAUDE_SLEEP=30 PATH="$PATH" \
    "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT" >"$TEST_ROOT/$label.launch" 2>&1 & CASE_OWNER=$!
  session=""
  for _ in $(seq 1 200); do
    session="$(grep -- '--session-id' "$TEST_ROOT/$label.argv" 2>/dev/null | tail -1 | sed 's/.*--session-id //; s/ .*//')"
    [ -n "$session" ] && CASE_READY="$(find "$expected/watchtowers/claude-$session" -name 'poller-ready.*' -type f 2>/dev/null | head -1)" && [ -s "${CASE_READY:-}" ] && break
    process_alive "$CASE_OWNER" || break; sleep .025
  done
  [ -n "$session" ] && [ -s "$CASE_READY" ] || { cat "$TEST_ROOT/$label.launch" >&2; false; }
  CASE_POLLER="$(cat "$CASE_READY")"; process_alive "$CASE_POLLER"
  poller_command "$CASE_POLLER" | grep -F -- "rzr-claude-watchtower-poll.py --home $expected " >/dev/null

  dir="$expected/watchtowers/claude-$session"; target="$dir/target.json"; history="$dir/registrations.jsonl"
  [ -s "$target" ] && [ -s "$history" ]
  for field in policy_sha256 policy_core_sha256 policy_mission_name policy_mission_source policy_mission_sha256; do
    ! jq -e --arg field "$field" 'has($field) or (.preset? | type == "object" and has($field))' "$target" >/dev/null
    ! jq -e --arg field "$field" 'has($field) or (.preset? | type == "object" and has($field))' "$history" >/dev/null
  done
  # Probe writes cannot satisfy this: the actual exec child must retain the selected home and cleared tuple.
  [ "$(grep -c '^mode=launch ' "$TEST_ROOT/$label.env")" -eq 1 ]
  grep -Fx "mode=launch home=$expected policy=<unset> core=<unset> mission_name=<unset> mission_source=<unset> mission=<unset>" "$TEST_ROOT/$label.env" >/dev/null

  settings="$dir/claude-event-settings.json"; command="$(jq -r '.hooks.SessionStart[0].hooks[0].command' "$settings")"
  case "$command" in *"ROZORO_HOME=$expected"*) ;; *) false ;; esac
  printf '{"hook_event_name":"SessionStart","session_id":"%s"}\n' "$session" | sh -c "$command"
  python3 - "$expected/monitor.db" <<'PY'
import sqlite3,sys
assert sqlite3.connect(sys.argv[1]).execute("select count(*) from sessions where role='watchtower'").fetchone()[0] >= 1
PY
)

@test "Claude launcher holds P L B E D R T X through actual child poller hooks and registration with per-row cleanup" {
  # Let the older short-timeout Claude integration row clear its startup window
  # when Bats runs files job-wide; this matrix intentionally starts many daemons.
  sleep 5
  export ROZORO_WT_POLICY_SHA256=stale ROZORO_WT_POLICY_CORE_SHA256=stale \
    ROZORO_WT_POLICY_MISSION_NAME=stale ROZORO_WT_POLICY_MISSION_SOURCE=stale \
    ROZORO_WT_POLICY_MISSION_SHA256=stale XDG_CONFIG_HOME="$TEST_ROOT/xdg-decoy"
  mkdir -p "$TEST_ROOT/origin"; printf 'legacy\n' > "$TEST_ROOT/legacy-decoy"; printf 'xdg\n' > "$TEST_ROOT/xdg-decoy-file"
  run_launcher_row P "$TEST_ROOT/p" ROZORO_HOME="$TEST_ROOT/p" RZR_HOME="$TEST_ROOT/wrong"
  run_launcher_row L "$TEST_ROOT/l" -u ROZORO_HOME RZR_HOME="$TEST_ROOT/l"
  run_launcher_row B "$TEST_ROOT/b-public" ROZORO_HOME="$TEST_ROOT/b-public" RZR_HOME="$TEST_ROOT/b-legacy"
  run_launcher_row E "$TEST_ROOT/e-legacy" ROZORO_HOME= RZR_HOME="$TEST_ROOT/e-legacy"
  run_launcher_row D-unset "$HOME/.rozoro" -u ROZORO_HOME -u RZR_HOME
  run_launcher_row D-empty "$HOME/.rozoro" ROZORO_HOME= RZR_HOME=
  run_launcher_row T-home "$HOME/claude-tilde" ROZORO_HOME='~/claude-tilde' RZR_HOME=

  passwd="$(python3 - <<'PY'
import os,pwd
try:
 p=pwd.getpwuid(os.geteuid()); print(p.pw_name); print(p.pw_dir)
except KeyError: pass
PY
)"
  if [ -n "$passwd" ]; then
    user="$(printf '%s\n' "$passwd" | sed -n 1p)"; user_home="$(printf '%s\n' "$passwd" | sed -n 2p)"
    [ "$(python3 -c 'import os; print(os.path.expanduser("~'"$user"'"))')" = "$user_home" ]
    suffix=".rozoro-h4-${BATS_TEST_NUMBER}-$$"; guard="$user_home/$suffix"
    [ ! -e "$guard" ] && mkdir -m 700 "$guard"
    ROW_GUARD="$guard" run_launcher_row T-user "$guard" ROZORO_HOME="~$user/$suffix" RZR_HOME=
    [ ! -e "$guard" ]
  fi
  run_launcher_row T-embedded "$TEST_ROOT/origin/a~b" ROZORO_HOME="$TEST_ROOT/origin/a~b" RZR_HOME=
  run_launcher_row X "$TEST_ROOT/x-public" ROZORO_HOME="$TEST_ROOT/x-public" RZR_HOME="$TEST_ROOT/x-legacy" XDG_CONFIG_HOME="$TEST_ROOT/xdg-winner-mutant"
  (cd "$TEST_ROOT/origin"; run_launcher_row R "$TEST_ROOT/origin/relative-home" ROZORO_HOME=relative-home RZR_HOME=)
  [ "$(cat "$TEST_ROOT/legacy-decoy")" = legacy ] && [ "$(cat "$TEST_ROOT/xdg-decoy-file")" = xdg ]
  [ ! -e "$TEST_ROOT/wrong" ] && [ ! -e "$TEST_ROOT/b-legacy" ] && [ ! -e "$TEST_ROOT/x-legacy" ] && [ ! -e "$TEST_ROOT/xdg-winner-mutant" ]
}

@test "Claude launcher rejects unresolved tilde without launch or literal state" {
  export ROZORO_HOME='~rozoro_no_such_user_135/home' RZR_HOME= CLAUDE_ENV_LOG="$TEST_ROOT/reject.env" FAKE_CLAUDE_LOG="$TEST_ROOT/reject.argv"
  run "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT"
  assert_failure; assert_output_contains "unresolved user home path"
  [ ! -e "$TEST_ROOT/~rozoro_no_such_user_135" ] && [ ! -e "$TEST_ROOT/reject.env" ]
}

@test "post-readiness Claude launch failure reaps poller and monitor socket" {
 (
  selected="$TEST_ROOT/post-ready-failure"; label=failure
  CASE_OWNER="" CASE_POLLER="" CASE_READY="" CASE_HOME="$selected" CASE_GUARD=""
  trap 'cleanup_case "$?"' EXIT HUP INT TERM
  env ROZORO_HOME="$selected" RZR_HOME= CLAUDE_ENV_LOG="$TEST_ROOT/$label.env" FAKE_CLAUDE_LOG="$TEST_ROOT/$label.argv" \
    FAKE_CLAUDE_LAUNCH_FAILURE=17 FAKE_CLAUDE_WAIT_READY=1 HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION=2.1.241 PATH="$PATH" \
    "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT" >"$TEST_ROOT/$label.launch" 2>&1 & CASE_OWNER=$!
  for _ in $(seq 1 200); do
    CASE_READY="$(find "$selected/watchtowers" -name 'poller-ready.*' -type f 2>/dev/null | head -1)"
    [ -s "${CASE_READY:-}" ] && break; process_alive "$CASE_OWNER" || break; sleep .025
  done
  [ -s "$CASE_READY" ]; CASE_POLLER="$(cat "$CASE_READY")"; process_alive "$CASE_POLLER"
  set +e; wait "$CASE_OWNER"; owner_status=$?; set -e; CASE_OWNER=""
  [ "$owner_status" -eq 17 ]
  [ "$(grep -c '^mode=launch ' "$TEST_ROOT/$label.env")" -eq 1 ]
 )
}
