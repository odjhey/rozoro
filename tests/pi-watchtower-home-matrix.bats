#!/usr/bin/env bats
# Pi home contract: real launcher -> fake Pi -> real registrar -> fake Herdr.
load test_helper/common

make_pi_registrar() {
  export HERDR_PANE_ID=home-matrix-pane PI_OBSERVED="$TEST_ROOT/pi-observed"
  fake_pane "$HERDR_PANE_ID" idle pi true
  mkdir -p "$TEST_ROOT/bin"
  cat > "$TEST_ROOT/bin/pi" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf 'home=%s\ncwd=%s\n' "$ROZORO_HOME" "$PWD" > "$PI_OBSERVED"
printf 'arg=%s\n' "$@" >> "$PI_OBSERVED"
"$REPO_ROOT/bin/rzr-register.sh" --harness pi --quiet
SH
  chmod +x "$TEST_ROOT/bin/pi"
  export PATH="$TEST_ROOT/bin:$PATH" REPO_ROOT
}

assert_projection_only_in() {
  selected=$1
  target="$selected/watchtowers/herdr-home-matrix-pane/target.json"
  history="${target%/target.json}/registrations.jsonl"
  [ -f "$target" ] && [ -f "$history" ]
  [ "$(jq -r .identity "$target")" = home-matrix-pane ]
  [ "$(jq -r .harness "$target")" = pi ]
  [ "$(wc -l < "$history" | tr -d ' ')" = 1 ]
  [ "$(jq -r .identity "$history")" = home-matrix-pane ]
  return 0
}

run_home_row() {
  label=$1 public=$2 legacy=$3 expected=$4
  mkdir -p "$expected" "$TEST_ROOT/work-$label"
  chmod 700 "$expected"
  rm -f "$PI_OBSERVED"
  run env ROZORO_HOME="$public" RZR_HOME="$legacy" XDG_STATE_HOME="$TEST_ROOT/xdg-$label" \
    HERDR_PANE_ID="$HERDR_PANE_ID" PI_OBSERVED="$PI_OBSERVED" FAKE_HERDR_ROOT="$FAKE_HERDR_ROOT" \
    FAKE_HERDR_LOG="$FAKE_HERDR_LOG" PATH="$PATH" REPO_ROOT="$REPO_ROOT" HOME="$HOME" \
    "$REPO_ROOT/bin/rzr-pi-watchtower.sh" --resume "session-$label" --cwd "$TEST_ROOT/work-$label" -- --model "model-$label"
  assert_success
  grep -Fx "home=$expected" "$PI_OBSERVED"
  grep -Fx "cwd=$TEST_ROOT/work-$label" "$PI_OBSERVED"
  grep -A1 -Fx 'arg=--session' "$PI_OBSERVED" | grep -Fx "arg=session-$label"
  grep -A1 -Fx 'arg=--model' "$PI_OBSERVED" | grep -Fx "arg=model-$label"
  assert_projection_only_in "$expected"
  [ "$public" = "$expected" ] || [ ! -e "$public/watchtowers" ]
  [ "$legacy" = "$expected" ] || [ ! -e "$legacy/watchtowers" ]
}

@test "P L B E D R T X select, hold, and project one absolute Pi home" {
  make_pi_registrar
  run_home_row P "$TEST_ROOT/home-P" "$TEST_ROOT/legacy-P" "$TEST_ROOT/home-P"
  run_home_row L '' "$TEST_ROOT/home-L" "$TEST_ROOT/home-L"
  run_home_row B "$TEST_ROOT/home-B" "$TEST_ROOT/legacy-B" "$TEST_ROOT/home-B"
  run_home_row E '' "$TEST_ROOT/home-E" "$TEST_ROOT/home-E"

  mkdir -p "$HOME/.rozoro"; chmod 700 "$HOME/.rozoro"
  run_home_row D '' '' "$HOME/.rozoro"

  mkdir -p "$TEST_ROOT/anchor" "$TEST_ROOT/work-R"; chmod 700 "$TEST_ROOT/anchor"
  mkdir -p "$TEST_ROOT/anchor/relative-home"
  rm -f "$PI_OBSERVED"
  run bash -c 'cd "$1" && env ROZORO_HOME=relative-home RZR_HOME="$2" XDG_STATE_HOME="$3" HERDR_PANE_ID="$4" PI_OBSERVED="$5" FAKE_HERDR_ROOT="$6" FAKE_HERDR_LOG="$7" PATH="$8" REPO_ROOT="$9" HOME="${10}" "${9}/bin/rzr-pi-watchtower.sh" --resume session-R --cwd "${11}" -- --model model-R' _ \
    "$TEST_ROOT/anchor" "$TEST_ROOT/legacy-R" "$TEST_ROOT/xdg-R" "$HERDR_PANE_ID" "$PI_OBSERVED" "$FAKE_HERDR_ROOT" "$FAKE_HERDR_LOG" "$PATH" "$REPO_ROOT" "$HOME" "$TEST_ROOT/work-R"
  assert_success
  expected_R="$TEST_ROOT/anchor/relative-home"
  grep -Fx "home=$expected_R" "$PI_OBSERVED"; grep -Fx "cwd=$TEST_ROOT/work-R" "$PI_OBSERVED"
  assert_projection_only_in "$expected_R"

  run_home_row T '~/' '' "$HOME"
  export HOME="$TEST_ROOT/xdg-default-home"
  mkdir -p "$HOME/.rozoro"; chmod 700 "$HOME/.rozoro"
  run_home_row X '' '' "$HOME/.rozoro"
}

@test "unresolved tilde user fails before Pi and creates no state" {
  make_pi_registrar
  unresolved='~rozoro-home-matrix-user-that-cannot-exist/subdir'
  rm -f "$PI_OBSERVED"
  run env ROZORO_HOME="$unresolved" RZR_HOME="$TEST_ROOT/legacy" HERDR_PANE_ID="$HERDR_PANE_ID" \
    PI_OBSERVED="$PI_OBSERVED" FAKE_HERDR_ROOT="$FAKE_HERDR_ROOT" PATH="$PATH" HOME="$HOME" \
    "$REPO_ROOT/bin/rzr-pi-watchtower.sh" --cwd "$TEST_ROOT"
  assert_failure
  [ ! -e "$PI_OBSERVED" ]
  [ -z "$(find "$TEST_ROOT" -type d -name watchtowers -print -quit)" ]
}
