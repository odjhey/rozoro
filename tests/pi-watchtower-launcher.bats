#!/usr/bin/env bats
load test_helper/common

setup_pi() {
  export HERDR_PANE_ID=manual:p1 PI_LOG="$TEST_ROOT/pi.log"
  cat > "$TEST_ROOT/pi" <<'SH'
#!/bin/sh
printf 'role=%s\n' "${ROZORO_WATCHTOWER:-}" > "$PI_LOG"
printf 'wt=%s preset=%s version=%s driver=%s preset_sha=%s policy_sha=%s\n' "${ROZORO_WT_NAME:-}" "${ROZORO_WT_PRESET:-}" "${ROZORO_WT_PRESET_VERSION:-}" "${ROZORO_WT_DRIVER:-}" "${ROZORO_WT_PRESET_SHA256:-}" "${ROZORO_WT_POLICY_SHA256:-}" >> "$PI_LOG"
printf '%s\n' "$@" >> "$PI_LOG"
SH
  chmod +x "$TEST_ROOT/pi"
  export PATH="$TEST_ROOT:$PATH"
}

@test "no-preset Pi launch does not require herdr and carries policy" {
  export HERDR_PANE_ID=manual:p1 PI_LOG="$TEST_ROOT/pi.log"
  mkdir "$TEST_ROOT/minbin" "$TEST_ROOT/empty-home"
  cat > "$TEST_ROOT/minbin/pi" <<'SH'
#!/bin/sh
printf '%s\n' "$@" > "$PI_LOG"
SH
  chmod +x "$TEST_ROOT/minbin/pi"
  run env PATH="$TEST_ROOT/minbin:/usr/bin:/bin" HOME="$TEST_ROOT/empty-home" ROZORO_HOME="$TEST_ROOT/empty-home/rozoro" \
    HERDR_PANE_ID="$HERDR_PANE_ID" PI_LOG="$PI_LOG" "$REPO_ROOT/bin/rzr-pi-watchtower.sh" --cwd "$TEST_ROOT"
  assert_success
  grep -Fx -- '--extension' "$PI_LOG"
  grep -Fx "$REPO_ROOT/templates/missions/delivery.md" "$PI_LOG"
}

@test "supported Pi watchtower launch carries immutable role and explicit resources" {
  setup_pi
  run rzr-pi-watchtower.sh --cwd "$TEST_ROOT" -- --model test/model
  assert_success
  grep -Fx 'role=1' "$PI_LOG"
  grep -Fx -- '--extension' "$PI_LOG"
  grep -Fx "$REPO_ROOT/.pi/extensions/rozoro-watchtower.ts" "$PI_LOG"
  grep -Fx -- '--append-system-prompt' "$PI_LOG"
  grep -Fx "$REPO_ROOT/templates/watchtower.md" "$PI_LOG"
  grep -Fx "$REPO_ROOT/templates/missions/delivery.md" "$PI_LOG"
  grep -Fx -- '--approve' "$PI_LOG"
}

@test "supported exact resume reapplies role extension and prompt" {
  setup_pi
  run rzr-pi-watchtower.sh --resume session-123 --cwd "$TEST_ROOT"
  assert_success
  grep -Fx 'role=1' "$PI_LOG"
  grep -A1 -Fx -- '--session' "$PI_LOG" | grep -Fx session-123
  grep -Fx "$REPO_ROOT/.pi/extensions/rozoro-watchtower.ts" "$PI_LOG"
  grep -Fx "$REPO_ROOT/templates/watchtower.md" "$PI_LOG"
  grep -Fx "$REPO_ROOT/templates/missions/delivery.md" "$PI_LOG"
}

@test "Pi no-preset launch clears inherited watchtower attribution" {
  setup_pi
  run env ROZORO_WT_NAME=stale ROZORO_WT_PRESET=old ROZORO_WT_PRESET_VERSION=9 \
    ROZORO_WT_PRESET_SHA256=bad ROZORO_WT_POLICY_SHA256=bad ROZORO_WT_MODEL=old ROZORO_WT_EFFORT=low \
    ROZORO_WT_DRIVER=stale-driver rzr-pi-watchtower.sh --cwd "$TEST_ROOT"
  assert_success
  grep -E '^wt= preset= version= driver=herdr-manual_p1 preset_sha= policy_sha=[0-9a-f]{64}$' "$PI_LOG"
}

@test "named Pi launch stamps shipped policy identity without a preset" {
  setup_pi
  run rzr-pi-watchtower.sh --wt-name north --cwd "$TEST_ROOT"
  assert_success
  grep -E '^wt=north preset= version= driver=herdr-manual_p1 preset_sha= policy_sha=[0-9a-f]{64}$' "$PI_LOG"
}

@test "Pi watchtower preset injects resources and stamps inherited registration env" {
  setup_pi
  mkdir -p "$ROZORO_HOME/watchtower-presets"
  chmod 700 "$ROZORO_HOME/watchtower-presets"
  printf '%s\n' '{"schema":1,"version":3,"harness":"pi","model":"luna","effort":"high"}' > "$ROZORO_HOME/watchtower-presets/luna.json"
  run rzr-pi-watchtower.sh --preset luna --wt-name north --cwd "$TEST_ROOT"
  assert_success
  grep -A1 -Fx -- '--model' "$PI_LOG" | grep -Fx luna
  grep -A1 -Fx -- '--thinking' "$PI_LOG" | grep -Fx high
  grep -E '^wt=north preset=luna version=3 driver=herdr-manual_p1 preset_sha=[0-9a-f]{64} policy_sha=[0-9a-f]{64}$' "$PI_LOG"
}

@test "Pi preset replacement cannot split launch fields from recorded SHA" {
  setup_pi
  mkdir -p "$ROZORO_HOME/watchtower-presets" "$TEST_ROOT/wrap"
  chmod 700 "$ROZORO_HOME/watchtower-presets"
  preset="$ROZORO_HOME/watchtower-presets/luna.json"
  printf '%s\n' '{"harness":"pi","model":"old-model","effort":"low"}' > "$preset"
  printf '%s\n' '{"harness":"pi","model":"new-model","effort":"high"}' > "$TEST_ROOT/new.json"
  expected="$(shasum -a 256 "$TEST_ROOT/new.json" | awk '{print $1}')"; real_python="$(command -v python3)"
  cat > "$TEST_ROOT/wrap/python3" <<'SH'
#!/bin/sh
if [ ! -e "$SWAPPED" ]; then : > "$SWAPPED"; mv "$NEW_PRESET" "$WATCH_PRESET"; fi
exec "$REAL_PYTHON" "$@"
SH
  chmod +x "$TEST_ROOT/wrap/python3"
  run env PATH="$TEST_ROOT/wrap:$PATH" SWAPPED="$TEST_ROOT/swapped" NEW_PRESET="$TEST_ROOT/new.json" \
    WATCH_PRESET="$preset" REAL_PYTHON="$real_python" HERDR_PANE_ID="$HERDR_PANE_ID" PI_LOG="$PI_LOG" \
    ROZORO_HOME="$ROZORO_HOME" rzr-pi-watchtower.sh --preset luna --cwd "$TEST_ROOT"
  assert_success
  grep -A1 -Fx -- '--model' "$PI_LOG" | grep -Fx new-model
  grep -A1 -Fx -- '--thinking' "$PI_LOG" | grep -Fx high
  grep -F "preset_sha=$expected" "$PI_LOG"
}

@test "Pi preset mission selects an operator mission file" {
  setup_pi
  mkdir -p "$ROZORO_HOME/watchtower-presets" "$ROZORO_HOME/watchtower-missions"
  chmod 700 "$ROZORO_HOME/watchtower-presets"
  chmod 700 "$ROZORO_HOME/watchtower-missions"
  printf '%s\n' '{"harness":"pi","mission":"pm"}' > "$ROZORO_HOME/watchtower-presets/pm.json"
  printf '%s\n' 'pm mission policy' > "$ROZORO_HOME/watchtower-missions/pm.md"
  chmod 600 "$ROZORO_HOME/watchtower-missions/pm.md"
  run rzr-pi-watchtower.sh --preset pm --cwd "$TEST_ROOT"
  assert_success
  grep -Fx "$REPO_ROOT/templates/watchtower.md" "$PI_LOG"
  grep -Fx "$ROZORO_HOME/watchtower-missions/pm.md" "$PI_LOG"
  expected="$(cat "$REPO_ROOT/templates/watchtower.md" "$ROZORO_HOME/watchtower-missions/pm.md" | shasum -a 256 | awk '{print $1}')"
  grep -F "policy_sha=$expected" "$PI_LOG"
}

@test "Pi mission defined by both shipped and operator files fails closed" {
  setup_pi
  mkdir -p "$ROZORO_HOME/watchtower-presets" "$ROZORO_HOME/watchtower-missions"
  chmod 700 "$ROZORO_HOME/watchtower-presets"
  chmod 700 "$ROZORO_HOME/watchtower-missions"
  printf '%s\n' '{"harness":"pi","mission":"delivery"}' > "$ROZORO_HOME/watchtower-presets/dup.json"
  printf '%s\n' 'shadowing delivery mission' > "$ROZORO_HOME/watchtower-missions/delivery.md"
  chmod 600 "$ROZORO_HOME/watchtower-missions/delivery.md"
  run rzr-pi-watchtower.sh --preset dup --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains ambiguous
  [ ! -e "$PI_LOG" ]
}

@test "Pi unknown mission fails before launch" {
  setup_pi
  mkdir -p "$ROZORO_HOME/watchtower-presets"
  chmod 700 "$ROZORO_HOME/watchtower-presets"
  printf '%s\n' '{"harness":"pi","mission":"no-such-mission"}' > "$ROZORO_HOME/watchtower-presets/ghost.json"
  run rzr-pi-watchtower.sh --preset ghost --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains "missing or unsafe"
  [ ! -e "$PI_LOG" ]
}

@test "Pi preset mission with unsafe name is rejected" {
  setup_pi
  mkdir -p "$ROZORO_HOME/watchtower-presets"
  chmod 700 "$ROZORO_HOME/watchtower-presets"
  printf '%s\n' '{"harness":"pi","mission":"../evil"}' > "$ROZORO_HOME/watchtower-presets/evil.json"
  run rzr-pi-watchtower.sh --preset evil --cwd "$TEST_ROOT"
  assert_failure
  [ ! -e "$PI_LOG" ]
}

@test "Pi watchtower unknown preset fails before launch" {
  setup_pi
  run rzr-pi-watchtower.sh --preset missing
  assert_failure
  [ ! -e "$PI_LOG" ]
}

@test "unnamed launcher provenance reaches real registration current and history" {
  setup_pi
  fake_pane manual:p1 idle pi true
  export RZR_REGISTER="$REPO_ROOT/bin/rzr-register.sh" DRIVER_LOG="$TEST_ROOT/driver"
  cat > "$TEST_ROOT/pi" <<'SH'
#!/bin/sh
"$RZR_REGISTER" --harness pi > "$DRIVER_LOG"
SH
  chmod +x "$TEST_ROOT/pi"
  run rzr-pi-watchtower.sh --cwd "$TEST_ROOT"
  assert_success
  driver="$(cat "$DRIVER_LOG")"; target="$ROZORO_HOME/watchtowers/$driver/target.json"; history="${target%/target.json}/registrations.jsonl"
  core="$(sha256sum "$REPO_ROOT/templates/watchtower.md" | awk '{print $1}')"
  mission="$(sha256sum "$REPO_ROOT/templates/missions/delivery.md" | awk '{print $1}')"
  composed="$(cat "$REPO_ROOT/templates/watchtower.md" "$REPO_ROOT/templates/missions/delivery.md" | sha256sum | awk '{print $1}')"
  [ "$(jq -r '[.policy_sha256,.policy_core_sha256,.policy_mission_name,.policy_mission_source,.policy_mission_sha256] | join(":")' "$target")" = "$composed:$core:delivery:shipped:$mission" ]
  [ "$(jq -r '[.policy_sha256,.policy_core_sha256,.policy_mission_name,.policy_mission_source,.policy_mission_sha256] | join(":")' "$history")" = "$composed:$core:delivery:shipped:$mission" ]
  [ "$(jq 'has("watchtower_name") or has("preset")' "$target")" = false ]
}

@test "relative effective home is anchored before cwd and exported absolute" {
  setup_pi
  initial="$TEST_ROOT/initial"; destination="$TEST_ROOT/destination"; mkdir -p "$initial/rel/watchtower-presets" "$destination"
  chmod 700 "$initial/rel" "$initial/rel/watchtower-presets"
  printf '%s\n' '{"harness":"pi"}' > "$initial/rel/watchtower-presets/north.json"
  cat > "$TEST_ROOT/pi" <<'SH'
#!/bin/sh
printf 'home=%s cwd=%s\n' "$ROZORO_HOME" "$PWD" > "$PI_LOG"
SH
  chmod +x "$TEST_ROOT/pi"
  run bash -c 'cd "$1" && ROZORO_HOME=rel RZR_HOME=other "$2" --preset north --cwd "$3"' _ "$initial" "$REPO_ROOT/bin/rzr-pi-watchtower.sh" "$destination"
  assert_success
  grep -Fx "home=$initial/rel cwd=$destination" "$PI_LOG"
}

@test "policy lookup does not create absent effective home" {
  setup_pi
  absent="$TEST_ROOT/absent"; rm -rf "$absent"
  run env ROZORO_HOME="$absent" RZR_HOME= HERDR_PANE_ID="$HERDR_PANE_ID" PI_LOG="$PI_LOG" PATH="$PATH" rzr-pi-watchtower.sh --cwd "$TEST_ROOT"
  assert_success
  [ ! -e "$absent" ]
  rm -f "$PI_LOG"
  run env ROZORO_HOME="$absent" RZR_HOME= HERDR_PANE_ID="$HERDR_PANE_ID" PATH="$PATH" rzr-pi-watchtower.sh --preset ghost
  assert_failure
  [ ! -e "$absent" ]
}

@test "preset storage and diagnostics are private fail-closed and controlled" {
  setup_pi
  dir="$ROZORO_HOME/watchtower-presets"; mkdir -p "$dir"; chmod 700 "$dir"
  chmod 700 "$ROZORO_HOME/watchtower-presets"
  printf '%s\n' '{"harness":"pi"}' > "$dir/ok.json"; chmod 600 "$dir/ok.json"
  run rzr-pi-watchtower.sh --preset ok --cwd "$TEST_ROOT"; assert_success
  chmod 755 "$dir"; rm -f "$PI_LOG"
  run rzr-pi-watchtower.sh --preset ok; assert_failure
  [ "$(printf '%s\n' "$output" | grep -c '^rzr:')" -eq 1 ]; ! printf '%s' "$output" | grep -q Traceback
  chmod 700 "$dir"; rm "$dir/ok.json"; mkfifo "$dir/ok.json"
  run rzr-pi-watchtower.sh --preset ok; assert_failure
  [ "$(printf '%s\n' "$output" | grep -c '^rzr:')" -eq 1 ]; ! printf '%s' "$output" | grep -q Traceback
  rm "$dir/ok.json"; printf '{bad\n' > "$dir/ok.json"
  run rzr-pi-watchtower.sh --preset ok; assert_failure
  [ "$(printf '%s\n' "$output" | grep -c '^rzr:')" -eq 1 ]; ! printf '%s' "$output" | grep -q Traceback
}

@test "watchtower launcher refuses outside an owning Herdr pane" {
  setup_pi; unset HERDR_PANE_ID
  run rzr-pi-watchtower.sh
  assert_failure
  assert_output_contains HERDR_PANE_ID
  [ ! -e "$PI_LOG" ]
}
