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
