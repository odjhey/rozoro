#!/usr/bin/env bats
load test_helper/common

@test "Claude watchtower launch and exact resume carry stable identity and private settings" {
  export HERDR_PANE_ID=p1 FAKE_CLAUDE_LOG="$TEST_ROOT/claude.log"
  fake_pane p1 idle claude true
  run "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT" -- --permission-mode auto
  assert_success
  session="$(grep -- '--session-id' "$FAKE_CLAUDE_LOG" | tail -1 | sed 's/.*--session-id //; s/ .*//')"
  [ -n "$session" ]
  settings="$ROZORO_HOME/watchtowers/claude-$session/claude-event-settings.json"
  [ -s "$settings" ]; [ "$(file_perm "$settings")" = 600 ]
  jq -e --arg s "$session" --arg p p1 '
    [.hooks[][] | .hooks[] | .command] | all(contains("ROZORO_ROLE=watchtower") and contains("ROZORO_SESSION_ID="+$s) and contains("ROZORO_HERDR_PANE_ID="+$p) and contains("--claude-binary") and (contains("ROZORO_CLAUDE_BINARY")|not) and (contains("ROZORO_CLAUDE_CAPABILITY")|not))' "$settings"
  : > "$FAKE_CLAUDE_LOG"
  run "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --resume "$session" --cwd "$TEST_ROOT"
  assert_success
  assert_file_contains "$FAKE_CLAUDE_LOG" "--resume $session"
  [ -d "$ROZORO_HOME/watchtowers/claude-$session" ]
}

@test "installed unsupported Claude version fails before settings or launch" {
  export HERDR_PANE_ID=p1 FAKE_CLAUDE_VERSION=2.1.241 FAKE_CLAUDE_LOG="$TEST_ROOT/claude.log"
  fake_pane p1 idle claude true
  run "$REPO_ROOT/bin/rzr-claude-watchtower.sh" --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains "certified only for 2.1.240"
  [ ! -d "$ROZORO_HOME/watchtowers" ]
}

@test "watchtower settings failure leaves no random temporary" {
  mkdir -p "$TEST_ROOT/private"; chmod 700 "$TEST_ROOT/private"
  long="$(printf '%0300d' 0)"
  run bash -c '. "$1/bin/rzr-lib.sh"; rzr_claude_watchtower_settings "$2/$3" d s p' _ "$REPO_ROOT" "$TEST_ROOT/private" "$long"
  assert_failure
  run find "$TEST_ROOT/private" -name '.claude-watchtower-*.tmp' -print
  assert_success
  [ -z "$output" ]
}
