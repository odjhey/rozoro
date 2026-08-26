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

@test "unsafe target-ahead metadata never appends recovery or publishes" {
  export HERDR_PANE_ID=driver-pane; fake_pane driver-pane idle pi true
  cases='schema_true schema_float schema_missing schema_string json_nan json_infinity json_negative_infinity version_null version_bool version_object version_array version_nan version_infinity version_oversized version_unsafe_integer top_null top_bool top_object top_long top_control preset_null nested_null nested_bool nested_object nested_long owner_null owner_text owner_bool owner_zero owner_large'
  for fixture in $cases; do
    rm -rf "$ROZORO_HOME/watchtowers"; run rzr-register.sh --harness pi --quiet; assert_success
    target="$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json"; log="${target%/target.json}/registrations.jsonl"
    FIXTURE="$fixture" TARGET="$target" python3 - <<'PY'
import json, os
path=os.environ["TARGET"]; fixture=os.environ["FIXTURE"]
with open(path) as stream: data=json.load(stream)
data["registration_id"]="target-ahead-"+fixture
data["preset"]={"name":"luna","version":3,"sha256":"abc","model":"luna","effort":"high"}
if fixture == "schema_true": data["schema"]=True
elif fixture == "schema_float": data["schema"]=1.0
elif fixture == "schema_missing": data.pop("schema")
elif fixture == "schema_string": data["schema"]="1"
elif fixture == "json_nan": data["created"]=float("nan")
elif fixture == "json_infinity": data["created"]=float("inf")
elif fixture == "json_negative_infinity": data["created"]=-float("inf")
elif fixture == "version_null": data["preset"]["version"]=None
elif fixture == "version_bool": data["preset"]["version"]=True
elif fixture == "version_object": data["preset"]["version"]={}
elif fixture == "version_array": data["preset"]["version"]=[]
elif fixture == "version_nan": data["preset"]["version"]=float("nan")
elif fixture == "version_infinity": data["preset"]["version"]=float("inf")
elif fixture == "version_oversized": data["preset"]["version"]=1e20
elif fixture == "version_unsafe_integer": data["preset"]["version"]=9007199254740993
elif fixture == "top_null": data["watchtower_name"]=None
elif fixture == "top_bool": data["identity"]=True
elif fixture == "top_object": data["policy_sha256"]={}
elif fixture == "top_long": data["created"]="x"*121
elif fixture == "top_control": data["harness"]="pi\nforged"
elif fixture == "preset_null": data["preset"]=None
elif fixture == "nested_null": data["preset"]["name"]=None
elif fixture == "nested_bool": data["preset"]["model"]=False
elif fixture == "nested_object": data["preset"]["sha256"]={}
elif fixture == "nested_long": data["preset"]["effort"]="x"*121
elif fixture == "owner_null": data["owner_pid"]=None
elif fixture == "owner_text": data["owner_pid"]="pid"
elif fixture == "owner_bool": data["owner_pid"]=True
elif fixture == "owner_zero": data["owner_pid"]="0"
elif fixture == "owner_large": data["owner_pid"]="999999999999999999999999999"
with open(path,"w") as stream: json.dump(data,stream,allow_nan=True)
PY
    chmod 600 "$target"; cp "$target" "$TEST_ROOT/before-target"; cp "$log" "$TEST_ROOT/before-log"
    run rzr-register.sh --harness pi --quiet; assert_failure
    cmp "$target" "$TEST_ROOT/before-target"; cmp "$log" "$TEST_ROOT/before-log"
    [ -z "$(find "${target%/target.json}" -name '.target.*.tmp' -print -quit)" ]; [ "$(cat "$SENTINEL")" = untouched ]
  done
}

@test "valid target-ahead boundaries recover once as standard JSON" {
  export HERDR_PANE_ID=driver-pane; fake_pane driver-pane idle pi true
  for version in string integer float; do
    rm -rf "$ROZORO_HOME/watchtowers"; run rzr-register.sh --harness pi --quiet; assert_success
    target="$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json"; log="${target%/target.json}/registrations.jsonl"; valid120="$(printf '%0120d' 0)"
    VERSION="$version" VALID120="$valid120" TARGET="$target" python3 - <<'PY'
import json,os
path=os.environ["TARGET"]
with open(path) as stream: data=json.load(stream)
data.update({"registration_id":"valid-ahead-"+os.environ["VERSION"],"watchtower_name":os.environ["VALID120"],"unknown":{"future":True}})
versions={"string":os.environ["VALID120"],"integer":3,"float":3.5}
data["preset"]={"name":"luna","version":versions[os.environ["VERSION"]],"sha256":"abc","policy_sha256":"policy","model":"luna","effort":"high","future":True}
with open(path,"w") as stream: json.dump(data,stream,allow_nan=False)
PY
    chmod 600 "$target"; recovered="valid-ahead-$version"
    run rzr-register.sh --harness pi --quiet; assert_success
    run rzr-register.sh --harness pi --quiet; assert_success
    [ "$(jq -r --arg id "$recovered" 'select(.registration_id == $id and .recovered == true) | .registration_id' "$log" | wc -l | tr -d ' ')" = 1 ]
    recovered_row="$(jq -c --arg id "$recovered" 'select(.registration_id == $id and .recovered == true)' "$log")"
    [ "$(printf '%s' "$recovered_row" | jq -r 'has("unknown")')" = false ]
    [ "$(printf '%s' "$recovered_row" | jq -r '.preset | keys | sort | join(":")')" = 'effort:model:name:policy_sha256:sha256:version' ]
    [ "$(printf '%s' "$recovered_row" | jq -r '[.preset.name,.preset.sha256,.preset.policy_sha256,.preset.model,.preset.effort] | join(":")')" = 'luna:abc:policy:luna:high' ]
    case "$version" in string) [ "$(printf '%s' "$recovered_row" | jq -r '.preset.version | length')" = 120 ];; integer) [ "$(printf '%s' "$recovered_row" | jq -r .preset.version)" = 3 ];; float) [ "$(printf '%s' "$recovered_row" | jq -r .preset.version)" = 3.5 ];; esac
    python3 - "$target" "$log" <<'PY'
import json,sys
with open(sys.argv[1]) as stream: json.load(stream,parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
with open(sys.argv[2]) as stream:
    for line in stream: json.loads(line,parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
PY
  done
}

@test "target-ahead recovery accepts absent owner and preset and projects empty preset" {
  export HERDR_PANE_ID=driver-pane; fake_pane driver-pane idle pi true
  run rzr-register.sh --harness pi --quiet; assert_success
  target="$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json"; log="${target%/target.json}/registrations.jsonl"
  jq 'del(.owner_pid,.preset) | .registration_id="absent-optionals"' "$target" > "$target.tmp"; mv "$target.tmp" "$target"; chmod 600 "$target"
  run rzr-register.sh --harness pi --quiet; assert_success
  [ "$(jq -r 'select(.registration_id == "absent-optionals" and .recovered == true) | has("preset")' "$log")" = false ]
  jq 'del(.owner_pid) | .preset={} | .registration_id="empty-preset"' "$target" > "$target.tmp"; mv "$target.tmp" "$target"; chmod 600 "$target"
  run rzr-register.sh --harness pi --quiet; assert_success
  [ "$(jq -c 'select(.registration_id == "empty-preset" and .recovered == true) | .preset' "$log")" = '{}' ]
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
