#!/usr/bin/env bats
load test_helper/common

@test "preset names cannot traverse and preset symlinks are rejected" {
  mkdir -p "$ROZORO_HOME/watchtower-presets"
  printf '%s\n' '{"harness":"pi","model":"outside","effort":"low"}' > "$ROZORO_HOME/outside.json"
  for command in "show ../outside" "path ../outside"; do
    run bash -c '"$1/bin/rozoro" watchtower $2 $3' _ "$REPO_ROOT" ${command}
    assert_failure
  done
  ln -s "$ROZORO_HOME/outside.json" "$ROZORO_HOME/watchtower-presets/link.json"
  run rozoro watchtower show link; assert_failure
  run rozoro watchtower list; assert_failure
}

@test "identity candidates are ambiguous while explicit driver still wins" {
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-pane" "$ROZORO_HOME/watchtowers/codex-thread"
  printf '%s\n' '{"driver_id":"herdr-pane","identity":"pane","watchtower_name":"herdr"}' > "$ROZORO_HOME/watchtowers/herdr-pane/target.json"
  printf '%s\n' '{"driver_id":"codex-thread","identity":"thread","watchtower_name":"codex"}' > "$ROZORO_HOME/watchtowers/codex-thread/target.json"
  chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/herdr-pane" "$ROZORO_HOME/watchtowers/codex-thread"; chmod 600 "$ROZORO_HOME/watchtowers"/*/target.json
  run env HERDR_PANE_ID=pane CODEX_THREAD_ID=thread bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
  run env HERDR_PANE_ID=pane CODEX_THREAD_ID=thread ROZORO_WT_DRIVER=codex-thread bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ "$(printf '%s' "$output" | jq -r .driver_id)" = codex-thread ]
}

@test "dispatcher lookup supports spaces and rejects multiline metadata" {
  home="$TEST_ROOT/rozoro home"; mkdir -p "$home/state" "$home/watchtowers/herdr-pane"
  printf '%s\n' '{"driver_id":"herdr-pane","identity":"pane","watchtower_name":"north","preset":{"name":"luna","version":"3","sha256":"abc"}}' > "$home/watchtowers/herdr-pane/target.json"
  chmod 700 "$home" "$home/watchtowers" "$home/watchtowers/herdr-pane"; chmod 600 "$home/watchtowers/herdr-pane/target.json"
  run env ROZORO_HOME="$home" RZR_HOME="$home" HERDR_PANE_ID=pane bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ "$(printf '%s' "$output" | jq -r .watchtower_name)" = north ]
  python3 - "$home/watchtowers/herdr-pane/target.json" <<'PY'
import json,sys
json.dump({"driver_id":"herdr-pane","identity":"pane","watchtower_name":"north\ndispatcher_preset=forged"},open(sys.argv[1],"w"))
PY
  run env ROZORO_HOME="$home" RZR_HOME="$home" HERDR_PANE_ID=pane bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
}

@test "registration refuses log and driver directory symlinks" {
  export HERDR_PANE_ID=pane
  fake_pane pane idle pi true
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-pane"
  printf 'untouched\n' > "$TEST_ROOT/sentinel"
  ln -s "$TEST_ROOT/sentinel" "$ROZORO_HOME/watchtowers/herdr-pane/registrations.jsonl"
  run rzr-register.sh --harness pi --quiet
  assert_failure; [ "$(cat "$TEST_ROOT/sentinel")" = untouched ]

  rm -rf "$ROZORO_HOME/watchtowers/herdr-pane"; mkdir "$TEST_ROOT/outside"; chmod 755 "$TEST_ROOT/outside"
  ln -s "$TEST_ROOT/outside" "$ROZORO_HOME/watchtowers/herdr-pane"
  run rzr-register.sh --harness pi --quiet
  assert_failure
  [ -z "$(find "$TEST_ROOT/outside" -mindepth 1 -print -quit)" ]
  [ "$(file_perm "$TEST_ROOT/outside")" = 755 ]
}

@test "registration writer anchors traversal against watchtowers rename swap" {
  export HERDR_PANE_ID=pane
  fake_pane pane idle pi true
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-pane" "$TEST_ROOT/outside/herdr-pane" "$TEST_ROOT/wrap"
  real_python="$(command -v python3)"
  cat > "$TEST_ROOT/wrap/python3" <<'SH'
#!/bin/sh
if [ -n "${RZR_REG_HOME:-}" ] && [ ! -e "$MARK" ]; then
  : > "$MARK"; mv "$HOME_DIR/watchtowers" "$HOME_DIR/watchtowers-checked"; ln -s "$OUTSIDE" "$HOME_DIR/watchtowers"
fi
exec "$REAL_PYTHON" "$@"
SH
  chmod +x "$TEST_ROOT/wrap/python3"
  run env PATH="$TEST_ROOT/wrap:$PATH" REAL_PYTHON="$real_python" MARK="$TEST_ROOT/swapped" \
    HOME_DIR="$ROZORO_HOME" OUTSIDE="$TEST_ROOT/outside" HERDR_PANE_ID=pane ROZORO_HOME="$ROZORO_HOME" \
    rzr-register.sh --harness pi --driver-id herdr-pane --quiet
  assert_failure
  [ -z "$(find "$TEST_ROOT/outside" -mindepth 1 -type f -print -quit)" ]
}

@test "registered and dispatcher skip symlinked or mismatched target storage" {
  home="$TEST_ROOT/read-home"; outside="$TEST_ROOT/read-outside"
  mkdir -p "$home/state" "$home/watchtowers" "$outside/herdr-pane"; chmod 700 "$home" "$home/watchtowers" "$outside" "$outside/herdr-pane"
  printf '%s\n' '{"driver_id":"herdr-pane","identity":"pane","watchtower_name":"external","harness":"pi","backend":"herdr","created":"outside"}' > "$outside/herdr-pane/target.json"; chmod 600 "$outside/herdr-pane/target.json"
  ln -s "$outside/herdr-pane" "$home/watchtowers/herdr-pane"
  run env ROZORO_HOME="$home" RZR_HOME="$home" rozoro watchtower registered
  assert_success; [[ "$output" != *external* ]]
  run env ROZORO_HOME="$home" RZR_HOME="$home" HERDR_PANE_ID=pane bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]

  rm "$home/watchtowers/herdr-pane"; mkdir "$home/watchtowers/herdr-pane"; chmod 700 "$home/watchtowers/herdr-pane"
  ln -s "$outside/herdr-pane/target.json" "$home/watchtowers/herdr-pane/target.json"
  run env ROZORO_HOME="$home" RZR_HOME="$home" rozoro watchtower registered
  assert_success; [[ "$output" != *external* ]]
  rm "$home/watchtowers/herdr-pane/target.json"
  printf '%s\n' '{"driver_id":"different","identity":"pane","watchtower_name":"mismatch"}' > "$home/watchtowers/herdr-pane/target.json"; chmod 600 "$home/watchtowers/herdr-pane/target.json"
  run env ROZORO_HOME="$home" RZR_HOME="$home" HERDR_PANE_ID=pane bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
}

@test "mixed malformed target shapes are skipped while valid optional shapes list" {
  home="$TEST_ROOT/shapes"; mkdir -p "$home/state" "$home/watchtowers"; chmod 700 "$home" "$home/watchtowers"
  make_target() { mkdir "$home/watchtowers/$1"; chmod 700 "$home/watchtowers/$1"; printf '%s\n' "$2" > "$home/watchtowers/$1/target.json"; chmod 600 "$home/watchtowers/$1/target.json"; }
  make_target array '[]'
  make_target null 'null'
  make_target string '"bad"'
  make_target malformed '{'
  make_target preset-string '{"driver_id":"preset-string","preset":"bad"}'
  make_target preset-null '{"driver_id":"preset-null","preset":null}'
  make_target preset-array '{"driver_id":"preset-array","preset":[]}'
  make_target empty-object '{}'
  make_target legacy '{"driver_id":"legacy","identity":"legacy-pane","harness":"pi","backend":"herdr","created":"then","unknown":{"future":true}}'
  make_target valid '{"driver_id":"valid","identity":"valid-pane","watchtower_name":"north","preset":{"name":"luna","version":3,"sha256":"abc","future":{"x":1}},"harness":"pi","backend":"herdr","created":"now","future":true}'
  run env ROZORO_HOME="$home" RZR_HOME="$home" rozoro watchtower registered
  assert_success
  [[ "$output" == *legacy* ]]; [[ "$output" == *north* ]]; [[ "$output" == *'luna@3'* ]]
  [[ "$output" != *preset-string* ]]; [[ "$output" != *preset-null* ]]; [[ "$output" != *preset-array* ]]
  [ "$(printf '%s\n' "$output" | grep -cE '^(legacy|valid)[[:space:]]')" -eq 2 ]
  run env ROZORO_HOME="$home" RZR_HOME="$home" HERDR_PANE_ID=valid-pane bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ "$(printf '%s' "$output" | jq -r .driver_id)" = valid ]
  run env ROZORO_HOME="$home" RZR_HOME="$home" ROZORO_WT_DRIVER=array bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
}

@test "strict JSON known fields and metadata bounds skip targets but preserve valid continuity" {
  home="$TEST_ROOT/strict-targets"; mkdir -p "$home/state" "$home/watchtowers"; chmod 700 "$home" "$home/watchtowers"
  make_target() { mkdir "$home/watchtowers/$1"; chmod 700 "$home/watchtowers/$1"; printf '%s\n' "$2" > "$home/watchtowers/$1/target.json"; chmod 600 "$home/watchtowers/$1/target.json"; }
  make_target nan '{"driver_id":"nan","identity":"bad-pane","preset":{"version":NaN}}'
  make_target infinity '{"driver_id":"infinity","identity":"bad-pane","preset":{"version":Infinity}}'
  make_target overflow '{"driver_id":"overflow","identity":"overflow-pane","preset":{"name":"luna","version":1e999}}'
  make_target unsafe-integer '{"driver_id":"unsafe-integer","identity":"unsafe-pane","preset":{"version":9007199254740993}}'
  make_target oversized-float '{"driver_id":"oversized-float","identity":"oversized-pane","preset":{"version":1e20}}'
  make_target schema-string '{"driver_id":"schema-string","schema":"1"}'
  make_target schema-bool '{"driver_id":"schema-bool","schema":true}'
  make_target schema-negative '{"driver_id":"schema-negative","schema":-1}'
  make_target schema-large '{"driver_id":"schema-large","schema":999999999999999999999999}'
  make_target owner-bool '{"driver_id":"owner-bool","owner_pid":true}'
  make_target owner-text '{"driver_id":"owner-text","owner_pid":"pid"}'
  make_target owner-negative '{"driver_id":"owner-negative","owner_pid":"-1"}'
  make_target owner-large '{"driver_id":"owner-large","owner_pid":"999999999999999999999999999999"}'
  long121="$(printf '%0121d' 0)"; long10k="$(printf '%010000d' 0)"; exact120="$(printf '%0120d' 0)"
  make_target long121 "{\"driver_id\":\"long121\",\"watchtower_name\":\"$long121\"}"
  make_target long10k "{\"driver_id\":\"long10k\",\"watchtower_name\":\"$long10k\"}"
  make_target valid "{\"schema\":1,\"driver_id\":\"valid\",\"owner_pid\":\"42\",\"identity\":\"scan-pane\",\"watchtower_name\":\"$exact120\",\"preset\":{\"name\":\"luna\",\"version\":3,\"sha256\":\"abc\"},\"unknown\":\"$long10k\"}"
  run env ROZORO_HOME="$home" RZR_HOME="$home" rozoro watchtower registered
  assert_success
  [ "$(printf '%s\n' "$output" | grep -c '^valid[[:space:]]')" -eq 1 ]
  [[ "$output" != *long121* ]]; [[ "$output" != *long10k* ]]; [[ "$output" != *overflow* ]]; [[ "$output" != *unsafe-integer* ]]; [[ "$output" != *oversized-float* ]]; [[ "$output" == *'luna@3'* ]]
  run env ROZORO_HOME="$home" RZR_HOME="$home" ROZORO_WT_DRIVER=nan bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
  run env ROZORO_HOME="$home" RZR_HOME="$home" ROZORO_WT_DRIVER=overflow bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
  run env ROZORO_HOME="$home" RZR_HOME="$home" HERDR_PANE_ID=scan-pane bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ "$(printf '%s' "$output" | jq -r .driver_id)" = valid ]
}

@test "preset show and launch reject non-standard JSON and oversized known metadata" {
  mkdir -p "$ROZORO_HOME/watchtower-presets"
  printf '%s\n' '{"harness":"pi","model":"x","effort":"low","version":NaN}' > "$ROZORO_HOME/watchtower-presets/nan.json"
  printf '%s\n' '{"harness":"pi","model":"x","effort":"low","version":Infinity}' > "$ROZORO_HOME/watchtower-presets/infinity.json"
  long121="$(printf '%0121d' 0)"; printf '%s\n' "{\"harness\":\"pi\",\"model\":\"$long121\",\"effort\":\"low\"}" > "$ROZORO_HOME/watchtower-presets/long.json"
  exact120="$(printf '%0120d' 0)"; printf '%s\n' "{\"harness\":\"pi\",\"model\":\"$exact120\",\"effort\":\"low\",\"unknown\":{\"large\":\"$long121\"}}" > "$ROZORO_HOME/watchtower-presets/valid.json"
  for preset in nan infinity long; do
    run rozoro watchtower show "$preset"; assert_failure
  done
  run rozoro watchtower show valid; assert_success
  export HERDR_PANE_ID=pane
  run rzr-pi-watchtower.sh --preset nan; assert_failure
  run rzr-pi-watchtower.sh --preset infinity; assert_failure
  run rzr-pi-watchtower.sh --preset long; assert_failure
}

@test "watchtower names reject line metadata delimiters" {
  mkdir -p "$ROZORO_HOME/watchtower-presets"
  printf '%s\n' '{"harness":"pi","model":"luna","effort":"high"}' > "$ROZORO_HOME/watchtower-presets/luna.json"
  export HERDR_PANE_ID=pane
  for name in $'north\nforged=x' $'north\tbad' 'north=bad'; do
    run rzr-pi-watchtower.sh --preset luna --wt-name "$name"
    assert_failure
  done
}

@test "overflow versions and hardlinked preset and target files are rejected" {
  mkdir -p "$ROZORO_HOME/watchtower-presets" "$ROZORO_HOME/watchtowers/herdr-pane"
  printf '%s\n' '{"harness":"pi","model":"x","effort":"low","version":1e999}' > "$ROZORO_HOME/watchtower-presets/overflow.json"
  printf '%s\n' '{"harness":"pi","model":"x","effort":"low","version":9007199254740993}' > "$ROZORO_HOME/watchtower-presets/unsafe-integer.json"
  run rozoro watchtower show overflow; assert_failure
  run rozoro watchtower show unsafe-integer; assert_failure
  printf '%s\n' '{"harness":"pi","model":"x","effort":"low"}' > "$TEST_ROOT/hardlink.json"
  ln "$TEST_ROOT/hardlink.json" "$ROZORO_HOME/watchtower-presets/hardlink.json"
  run rozoro watchtower show hardlink; assert_failure

  printf '%s\n' '{"driver_id":"herdr-pane","identity":"pane","backend":"herdr"}' > "$TEST_ROOT/target.json"
  ln "$TEST_ROOT/target.json" "$ROZORO_HOME/watchtowers/herdr-pane/target.json"
  chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/herdr-pane"; chmod 600 "$TEST_ROOT/target.json"
  run env HERDR_PANE_ID=pane bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
}

@test "duplicate valid targets sharing the canonical identity are ambiguous" {
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-pane" "$ROZORO_HOME/watchtowers/claude-session"
  printf '%s\n' '{"driver_id":"herdr-pane","identity":"pane","backend":"herdr"}' > "$ROZORO_HOME/watchtowers/herdr-pane/target.json"
  printf '%s\n' '{"driver_id":"claude-session","identity":"pane","backend":"herdr"}' > "$ROZORO_HOME/watchtowers/claude-session/target.json"
  chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers"/*; chmod 600 "$ROZORO_HOME/watchtowers"/*/target.json
  run env HERDR_PANE_ID=pane bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
}

@test "registered wake rejects duplicate identity across custom drivers" {
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-pane" "$ROZORO_HOME/watchtowers/backup"
  printf '%s\n' '{"driver_id":"herdr-pane","identity":"pane","backend":"herdr"}' > "$ROZORO_HOME/watchtowers/herdr-pane/target.json"
  printf '%s\n' '{"driver_id":"backup","identity":"pane","backend":"herdr"}' > "$ROZORO_HOME/watchtowers/backup/target.json"
  chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers"/*; chmod 600 "$ROZORO_HOME/watchtowers"/*/target.json
  run env ROZORO_LEGACY_DIAGNOSTIC=1 HERDR_PANE_ID=pane rzr-watch.sh --once --wake
  assert_failure
  assert_output_contains 'ambiguous'
}

@test "registration refuses a hardlinked registrations log" {
  export HERDR_PANE_ID=pane; fake_pane pane idle pi true
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-pane"
  printf 'untouched\n' > "$TEST_ROOT/sentinel"
  ln "$TEST_ROOT/sentinel" "$ROZORO_HOME/watchtowers/herdr-pane/registrations.jsonl"
  run rzr-register.sh --harness pi --quiet
  assert_failure; [ "$(cat "$TEST_ROOT/sentinel")" = untouched ]
}

@test "Claude settings capability write rejects a swapped watchtowers path" {
  mkdir -p "$ROZORO_HOME/watchtowers/claude-session" "$TEST_ROOT/outside/claude-session"
  chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/claude-session" "$TEST_ROOT/outside" "$TEST_ROOT/outside/claude-session"
  mv "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers-original"
  ln -s "$TEST_ROOT/outside" "$ROZORO_HOME/watchtowers"
  run bash -c '. "$1/bin/rzr-lib.sh"; rzr_claude_watchtower_settings "$RZR_HOME/watchtowers/claude-session/claude-event-settings.json" claude-session adapter native pane' _ "$REPO_ROOT"
  assert_failure
  [ -z "$(find "$TEST_ROOT/outside" -type f -print -quit)" ]
}

@test "task-local Claude capability proof rejects a predictable hardlink" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  ln "$SENTINEL" "$ROZORO_HOME/tasks/task/claude-event-settings.json.capability.json.tmp"
  run bash -c '. "$1/bin/rzr-lib.sh"; rzr_claude_event_settings task session' _ "$REPO_ROOT"
  assert_failure
  [ "$(cat "$SENTINEL")" = untouched ]
}
