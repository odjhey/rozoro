#!/usr/bin/env bats
load test_helper/common

@test "registration repairs a committed target missing from history before the next tenure" {
  export HERDR_PANE_ID=driver-pane ROZORO_WT_NAME=first
  fake_pane driver-pane idle pi true

  run rzr-register.sh --harness pi
  assert_success
  driver="$output"
  target="$ROZORO_HOME/watchtowers/$driver/target.json"
  log="${target%/target.json}/registrations.jsonl"
  [ "$(wc -l < "$log" | tr -d ' ')" = 1 ]

  # Simulate an abrupt process death after target.json committed but before the
  # matching history append. The next registration must repair this exact gap.
  tmp="$target.simulated"
  jq '.registration_id="committed-without-history" | .watchtower_name="gap" | .created="2026-08-26T00:00:00Z"' "$target" > "$tmp"
  mv "$tmp" "$target"
  chmod 600 "$target"

  export ROZORO_WT_NAME=second
  run rzr-register.sh --harness pi
  assert_success
  [ "$(wc -l < "$log" | tr -d ' ')" = 3 ]
  [ "$(sed -n '2p' "$log" | jq -r .registration_id)" = committed-without-history ]
  [ "$(sed -n '2p' "$log" | jq -r .recovered)" = true ]
  [ "$(jq -r .watchtower_name "$target")" = second ]
  [ "$(tail -n 1 "$log" | jq -r .registration_id)" = "$(jq -r .registration_id "$target")" ]

  recovered_count="$(jq -r 'select(.registration_id == "committed-without-history" and .recovered == true) | .registration_id' "$log" | wc -l | tr -d ' ')"
  export ROZORO_WT_NAME=third
  run rzr-register.sh --harness pi
  assert_success
  [ "$(jq -r 'select(.registration_id == "committed-without-history" and .recovered == true) | .registration_id' "$log" | wc -l | tr -d ' ')" = "$recovered_count" ]
  [ "$(tail -n 1 "$log" | jq -r .registration_id)" = "$(jq -r .registration_id "$target")" ]
}

@test "registration tightens pre-existing owner directories before publication" {
  export HERDR_PANE_ID=driver-pane; fake_pane driver-pane idle pi true
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-driver-pane"; chmod 755 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/herdr-driver-pane"
  run rzr-register.sh --harness pi --quiet
  assert_success
  [ "$(file_perm "$ROZORO_HOME/watchtowers")" = 700 ]
  [ "$(file_perm "$ROZORO_HOME/watchtowers/herdr-driver-pane")" = 700 ]
  [ "$(cat "$SENTINEL")" = untouched ]
}

@test "writer fails closed on invalid schema registration IDs and malformed history" {
  export HERDR_PANE_ID=driver-pane; fake_pane driver-pane idle pi true
  long121="$(printf '%0121d' 0)"
  for encoded in '42' '""' '"'$long121'"' '"bad\nid"'; do
    rm -rf "$ROZORO_HOME/watchtowers"
    run rzr-register.sh --harness pi --quiet; assert_success
    target="$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json"; log="${target%/target.json}/registrations.jsonl"
    jq ".registration_id=$encoded" "$target" > "$target.tmp"; mv "$target.tmp" "$target"; chmod 600 "$target"
    cp "$target" "$TEST_ROOT/before-target"; cp "$log" "$TEST_ROOT/before-log"
    run rzr-register.sh --harness pi --quiet; assert_failure
    cmp "$target" "$TEST_ROOT/before-target"; cmp "$log" "$TEST_ROOT/before-log"
  done

  for encoded in '42' '""' '"'$long121'"' '"bad\nid"'; do
    rm -rf "$ROZORO_HOME/watchtowers"; run rzr-register.sh --harness pi --quiet; assert_success
    target="$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json"; log="${target%/target.json}/registrations.jsonl"
    printf '{"registration_id":%s}\n' "$encoded" > "$log"
    cp "$target" "$TEST_ROOT/before-target"; cp "$log" "$TEST_ROOT/before-log"
    run rzr-register.sh --harness pi --quiet; assert_failure
    cmp "$target" "$TEST_ROOT/before-target"; cmp "$log" "$TEST_ROOT/before-log"
  done

  rm -rf "$ROZORO_HOME/watchtowers"; run rzr-register.sh --harness pi --quiet; assert_success
  target="$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json"; log="${target%/target.json}/registrations.jsonl"
  printf '{malformed\n' >> "$log"; cp "$target" "$TEST_ROOT/before-target"; cp "$log" "$TEST_ROOT/before-log"
  run rzr-register.sh --harness pi --quiet; assert_failure
  cmp "$target" "$TEST_ROOT/before-target"; cmp "$log" "$TEST_ROOT/before-log"
}

@test "a valid 120-byte registration ID is recoverable" {
  export HERDR_PANE_ID=driver-pane; fake_pane driver-pane idle pi true
  run rzr-register.sh --harness pi --quiet; assert_success
  target="$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json"; log="${target%/target.json}/registrations.jsonl"
  valid120="$(printf '%0120d' 0)"
  jq --arg id "$valid120" '.registration_id=$id' "$target" > "$target.tmp"; mv "$target.tmp" "$target"; chmod 600 "$target"
  run rzr-register.sh --harness pi --quiet; assert_success
  [ "$(jq -r --arg id "$valid120" 'select(.registration_id == $id and .recovered == true) | .registration_id' "$log" | tail -1)" = "$valid120" ]
}

@test "concurrent Rozoro registrations serialize and retain both history records" {
  export HERDR_PANE_ID=driver-pane
  fake_pane driver-pane idle pi true

  run bash -c '
    set -e
    ROZORO_WT_NAME=north rzr-register.sh --harness pi --quiet & p1=$!
    ROZORO_WT_NAME=south rzr-register.sh --harness pi --quiet & p2=$!
    wait "$p1"
    wait "$p2"
  '
  assert_success

  driver=herdr-driver-pane
  target="$ROZORO_HOME/watchtowers/$driver/target.json"
  log="${target%/target.json}/registrations.jsonl"
  [ "$(wc -l < "$log" | tr -d ' ')" = 2 ]
  [ "$(jq -s 'length' "$log")" = 2 ]
  names="$(jq -rs 'map(.watchtower_name) | sort | join(":")' "$log")"
  [ "$names" = north:south ]
  target_id="$(jq -r .registration_id "$target")"
  [ "$(jq -r --arg id "$target_id" 'select(.registration_id == $id) | .registration_id' "$log" | tail -n 1)" = "$target_id" ]
}
