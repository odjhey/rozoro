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
  setup_python
  export HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION=2.1.241 FAKE_CLAUDE_SLEEP=30
  fake_pane p1 idle claude true
  mkdir -p "$TEST_ROOT/fake-bin"
  cat > "$TEST_ROOT/fake-bin/claude" <<'SH'
#!/bin/sh
printf 'home=%s policy=%s core=%s mission_name=%s mission_source=%s mission=%s\n' \
  "${ROZORO_HOME-<unset>}" "${ROZORO_WT_POLICY_SHA256-<unset>}" \
  "${ROZORO_WT_POLICY_CORE_SHA256-<unset>}" "${ROZORO_WT_POLICY_MISSION_NAME-<unset>}" \
  "${ROZORO_WT_POLICY_MISSION_SOURCE-<unset>}" "${ROZORO_WT_POLICY_MISSION_SHA256-<unset>}" >> "$CLAUDE_ENV_LOG"
exec "$CLAUDE_FAKE" "$@"
SH
  chmod +x "$TEST_ROOT/fake-bin/claude"
  export CLAUDE_FAKE="$REPO_ROOT/tests/fakes/claude"
  export PATH="$TEST_ROOT/fake-bin:$PATH"
}

setup_python() {
  if [ -x /opt/homebrew/bin/python3 ]; then
    mkdir -p "$TEST_ROOT/pybin"
    ln -s /opt/homebrew/bin/python3 "$TEST_ROOT/pybin/python3"
    PATH="$TEST_ROOT/pybin:$PATH"
  fi
  export PYTHONDONTWRITEBYTECODE=1 PATH
}

stop_case() {
  owner="$1" poller="$2" selected="$3"
  kill "$owner" 2>/dev/null || true
  wait "$owner" 2>/dev/null || true
  for _ in $(seq 1 80); do ! kill -0 "$poller" 2>/dev/null && break; sleep .025; done
  ! kill -0 "$poller" 2>/dev/null
  ROZORO_HOME="$selected" RZR_HOME= "$REPO_ROOT/bin/rzr-monitor.sh" stop >/dev/null 2>&1 || true
  [ ! -e "$ready" ]
}

run_launcher_row() {
  label="$1" expected="$2"; shift 2
  CLAUDE_ENV_LOG="$TEST_ROOT/$label.env" FAKE_CLAUDE_LOG="$TEST_ROOT/$label.argv" \
    env "$@" CLAUDE_ENV_LOG="$TEST_ROOT/$label.env" FAKE_CLAUDE_LOG="$TEST_ROOT/$label.argv" \
    HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION=2.1.241 FAKE_CLAUDE_SLEEP=30 PATH="$PATH" \
    "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT" >"$TEST_ROOT/$label.launch" 2>&1 & owner=$!
  register_pid "$owner"
  session=""
  for _ in $(seq 1 160); do
    session="$(grep -- '--session-id' "$TEST_ROOT/$label.argv" 2>/dev/null | tail -1 | sed 's/.*--session-id //; s/ .*//')"
    [ -n "$session" ] && ready="$(find "$expected/watchtowers/claude-$session" -name 'poller-ready.*' -type f 2>/dev/null | head -1)" && [ -s "${ready:-}" ] && break
    sleep .025
  done
  [ -n "$session" ] && [ -s "$ready" ] || { cat "$TEST_ROOT/$label.launch" >&2; false; }
  poller="$(cat "$ready")"; kill -0 "$poller"
  # The real launcher must give the real poller a held, normalized absolute option.
  poller_command="$(python3 - "$poller" <<'PY'
import os,subprocess,sys
pid=sys.argv[1]
try: print(open('/proc/'+pid+'/cmdline','rb').read().replace(b'\0',b' ').decode())
except OSError: print(subprocess.check_output(['ps','-p',pid,'-o','command='],text=True))
PY
)"
  printf '%s\n' "$poller_command" | grep -F -- "rzr-claude-watchtower-poll.py --home $expected " >/dev/null

  dir="$expected/watchtowers/claude-$session"
  target="$dir/target.json" history="$dir/registrations.jsonl"
  [ -s "$target" ] && [ -s "$history" ]
  for field in policy_sha256 policy_core_sha256 policy_mission_name policy_mission_source policy_mission_sha256; do
    ! jq -e --arg field "$field" 'has($field) or (.preset? | type == "object" and has($field))' "$target" >/dev/null
    ! jq -e --arg field "$field" 'has($field) or (.preset? | type == "object" and has($field))' "$history" >/dev/null
  done
  grep -F "home=$expected policy=<unset> core=<unset> mission_name=<unset> mission_source=<unset> mission=<unset>" "$TEST_ROOT/$label.env" >/dev/null

  settings="$dir/claude-event-settings.json"
  command="$(jq -r '.hooks.SessionStart[0].hooks[0].command' "$settings")"
  case "$command" in *"ROZORO_HOME=$expected"*) ;; *) printf 'hook did not hold <%s>: %s\n' "$expected" "$command" >&2; false ;; esac
  printf '{"hook_event_name":"SessionStart","session_id":"%s"}\n' "$session" | sh -c "$command"
  python3 - "$expected/monitor.db" <<'PY'
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
assert c.execute("select count(*) from sessions where role='watchtower'").fetchone()[0] >= 1
PY
  stop_case "$owner" "$poller" "$expected"
}

@test "Claude launcher holds the complete P L B E D R T X home matrix through poller hooks and registration" {
  export ROZORO_WT_POLICY_SHA256=stale ROZORO_WT_POLICY_CORE_SHA256=stale \
    ROZORO_WT_POLICY_MISSION_NAME=stale ROZORO_WT_POLICY_MISSION_SOURCE=stale \
    ROZORO_WT_POLICY_MISSION_SHA256=stale XDG_CONFIG_HOME="$TEST_ROOT/xdg-decoy"
  mkdir -p "$TEST_ROOT/origin" "$TEST_ROOT/elsewhere"
  run_launcher_row P "$TEST_ROOT/p" ROZORO_HOME="$TEST_ROOT/p" RZR_HOME="$TEST_ROOT/wrong"
  run_launcher_row L "$TEST_ROOT/l" -u ROZORO_HOME RZR_HOME="$TEST_ROOT/l"
  run_launcher_row B "$TEST_ROOT/b-public" ROZORO_HOME="$TEST_ROOT/b-public" RZR_HOME="$TEST_ROOT/b-legacy"
  run_launcher_row E "$TEST_ROOT/e-legacy" ROZORO_HOME= RZR_HOME="$TEST_ROOT/e-legacy"
  run_launcher_row D-unset "$HOME/.rozoro" -u ROZORO_HOME -u RZR_HOME
  run_launcher_row D-empty "$HOME/.rozoro" ROZORO_HOME= RZR_HOME=
  run_launcher_row T-home "$HOME/claude-tilde" ROZORO_HOME='~/claude-tilde' RZR_HOME=
  user="$(python3 - <<'PY'
import os,pwd
try: print(pwd.getpwuid(os.geteuid()).pw_name)
except KeyError: pass
PY
)"
  [ -z "$user" ] || run_launcher_row T-user "$HOME/claude-user" ROZORO_HOME="~$user/claude-user" RZR_HOME=
  run_launcher_row T-embedded "$TEST_ROOT/origin/a~b" ROZORO_HOME="$TEST_ROOT/origin/a~b" RZR_HOME=
  run_launcher_row X "$TEST_ROOT/x-public" ROZORO_HOME="$TEST_ROOT/x-public" RZR_HOME="$TEST_ROOT/x-legacy" XDG_CONFIG_HOME="$TEST_ROOT/xdg-winner-mutant"
  (
    cd "$TEST_ROOT/origin"
    run_launcher_row R "$TEST_ROOT/origin/relative-home" ROZORO_HOME=relative-home RZR_HOME=
  )
}

@test "Claude launcher rejects unresolved tilde without launch or literal relative state" {
  export ROZORO_HOME='~rozoro_no_such_user_135/home' RZR_HOME= CLAUDE_ENV_LOG="$TEST_ROOT/reject.env" FAKE_CLAUDE_LOG="$TEST_ROOT/reject.argv"
  run "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains "unresolved user home path"
  [ ! -e "$TEST_ROOT/~rozoro_no_such_user_135" ]
  [ ! -e "$TEST_ROOT/reject.env" ]
}
