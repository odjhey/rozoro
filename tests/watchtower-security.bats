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
  run env HERDR_PANE_ID=pane CODEX_THREAD_ID=thread bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ -z "$output" ]
  run env HERDR_PANE_ID=pane CODEX_THREAD_ID=thread ROZORO_WT_DRIVER=codex-thread bash -c '. "$1/bin/rzr-lib.sh"; rzr_dispatcher_lookup' _ "$REPO_ROOT"
  assert_success; [ "$(printf '%s' "$output" | jq -r .driver_id)" = codex-thread ]
}

@test "dispatcher lookup supports spaces and rejects multiline metadata" {
  home="$TEST_ROOT/rozoro home"; mkdir -p "$home/state" "$home/watchtowers/herdr-pane"
  printf '%s\n' '{"driver_id":"herdr-pane","identity":"pane","watchtower_name":"north","preset":{"name":"luna","version":"3","sha256":"abc"}}' > "$home/watchtowers/herdr-pane/target.json"
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

@test "watchtower names reject line metadata delimiters" {
  mkdir -p "$ROZORO_HOME/watchtower-presets"
  printf '%s\n' '{"harness":"pi","model":"luna","effort":"high"}' > "$ROZORO_HOME/watchtower-presets/luna.json"
  export HERDR_PANE_ID=pane
  for name in $'north\nforged=x' $'north\tbad' 'north=bad'; do
    run rzr-pi-watchtower.sh --preset luna --wt-name "$name"
    assert_failure
  done
}
