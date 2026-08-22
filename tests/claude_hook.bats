#!/usr/bin/env bats

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"

setup() {
  export TEST_ROOT="$BATS_TEST_TMPDIR/root"
  export CLAUDE_PROJECT_DIR="$TEST_ROOT/project"
  export HERDR_PANE_ID=pane-1
  export HOOK_LOG="$TEST_ROOT/hook.log"
  export ATTEMPT_FILE="$TEST_ROOT/attempts"
  mkdir -p "$CLAUDE_PROJECT_DIR/bin" "$TEST_ROOT/fakes"

  cat > "$CLAUDE_PROJECT_DIR/bin/rozoro" <<'SH'
#!/usr/bin/env bash
set -u
attempt=0
[ ! -f "$ATTEMPT_FILE" ] || attempt="$(cat "$ATTEMPT_FILE")"
attempt=$((attempt + 1))
printf '%s' "$attempt" > "$ATTEMPT_FILE"
printf '%s\n' "$*" >> "$HOOK_LOG"
[ "$attempt" -ge "${SUCCEED_ON:-1}" ]
SH
  chmod +x "$CLAUDE_PROJECT_DIR/bin/rozoro"

  cat > "$TEST_ROOT/fakes/sleep" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  chmod +x "$TEST_ROOT/fakes/sleep"
  export PATH="$TEST_ROOT/fakes:$PATH"
}

@test "Claude registration hook is inert without the watchtower role" {
  unset ROZORO_ROLE
  run "$REPO_ROOT/hooks/claude-register-watchtower.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$HOOK_LOG" ]
}

@test "Claude registration hook requires a Herdr pane" {
  export ROZORO_ROLE=watchtower
  unset HERDR_PANE_ID
  run "$REPO_ROOT/hooks/claude-register-watchtower.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$HOOK_LOG" ]
}

@test "Claude registration hook retries quietly until registration succeeds" {
  export ROZORO_ROLE=watchtower SUCCEED_ON=3
  run "$REPO_ROOT/hooks/claude-register-watchtower.sh"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ "$(cat "$ATTEMPT_FILE")" -eq 3 ]
  [ "$(grep -Fxc 'register --harness claude --quiet' "$HOOK_LOG")" -eq 3 ]
}

@test "Claude registration hook remains successful after retry exhaustion" {
  export ROZORO_ROLE=watchtower SUCCEED_ON=99
  run "$REPO_ROOT/hooks/claude-register-watchtower.sh"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ "$(cat "$ATTEMPT_FILE")" -eq 20 ]
  [ "$(grep -Fxc 'register --harness claude --quiet' "$HOOK_LOG")" -eq 20 ]
}
