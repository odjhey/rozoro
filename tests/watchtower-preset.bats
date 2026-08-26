#!/usr/bin/env bats
load test_helper/common

make_preset() { mkdir -p "$ROZORO_HOME/watchtower-presets"; printf '%s\n' "$2" > "$ROZORO_HOME/watchtower-presets/$1.json"; }

@test "watchtower preset list show path and registered expose versioned identity" {
  make_preset luna '{"schema":1,"version":3,"harness":"pi","model":"luna","effort":"high","permission_mode":"","notes":"trial","future":true}'
  run rozoro watchtower list; assert_success
  assert_output_contains luna; assert_output_contains high; assert_output_contains 3
  run rozoro watchtower show luna; assert_success; assert_output_contains '"future": true'
  run rozoro watchtower path luna; assert_success; [ "$output" = "$ROZORO_HOME/watchtower-presets/luna.json" ]
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-p1"
  printf '%s\n' '{"schema":1,"registration_id":"registered-id","driver_id":"herdr-p1","watchtower_name":"north","preset":{"name":"luna","version":"3"},"harness":"pi","backend":"herdr","created":"now"}' > "$ROZORO_HOME/watchtowers/herdr-p1/target.json"
  chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/herdr-p1"; chmod 600 "$ROZORO_HOME/watchtowers/herdr-p1/target.json"
  run rozoro watchtower registered; assert_success; assert_output_contains north; assert_output_contains 'luna@3'
}

@test "watchtower preset validation rejects malformed known fields and tolerates unknown keys" {
  make_preset good '{"harness":"claude","effort":"max","new_key":{"x":1}}'
  run rozoro watchtower show good; assert_success
  make_preset effort '{"harness":"pi","effort":"huge"}'
  run rozoro watchtower show effort; assert_failure
  make_preset harness '{"harness":"codex"}'
  run rozoro watchtower show harness; assert_failure
  make_preset array '[]'
  run rozoro watchtower show array; assert_failure
}
