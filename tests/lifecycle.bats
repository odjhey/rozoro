#!/usr/bin/env bats
load test_helper/common

@test "fresh spawn requires an explicit cwd before mutation" {
  run rzr-spawn.sh task --prompt 'do exactly this'
  assert_failure
  assert_output_contains '--cwd <dir> required for a fresh task'
  [ ! -e "$ROZORO_HOME/state/task.meta" ]
  [ ! -e "$ROZORO_HOME/tasks/task" ]
  [ ! -s "$FAKE_HERDR_LOG" ]
}

@test "fresh start requires an explicit cwd before reserving a task" {
  printf 'ship it\n' > "$TEST_ROOT/body"
  run rzr-start.sh task --body "$TEST_ROOT/body" --no-agent
  assert_failure
  assert_output_contains '--cwd <dir> required for a fresh task'
  [ -z "$(find "$ROZORO_HOME/tasks" -mindepth 1 -print -quit)" ]
  [ -z "$(find "$ROZORO_HOME/state" -mindepth 1 -print -quit)" ]
  [ ! -s "$FAKE_HERDR_LOG" ]
}

@test "spawn records metadata and keeps the task prompt out of Claude system prompt" {
  run rzr-spawn.sh task --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'pane=p1'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=claude'
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/task.meta")"
  [[ "$agent_name" =~ ^[a-z0-9_-]{1,32}$ ]]
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\ttab\tcreate\t--cwd\t'"$TEST_ROOT"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tstart\t'"$agent_name"$'\t--kind\tclaude\t--pane\tp1'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\tdo exactly this'
  ! grep -F 'do exactly this' "$ROZORO_HOME/tasks/task/sysprompt.md"
  ! grep -F 'dispatcher_' "$ROZORO_HOME/state/task.meta"
}

@test "spawn link and idempotent relink preserve named unpreset and preset policy provenance" {
  mkdir -p "$ROZORO_HOME/watchtowers/herdr-driver-pane"
  target="$ROZORO_HOME/watchtowers/herdr-driver-pane/target.json"
  chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/herdr-driver-pane"
  store="$HOME/.pi/agent/sessions/fixture"; mkdir -p "$store"

  printf '%s\n' '{"schema":1,"registration_id":"unpreset-id","driver_id":"herdr-driver-pane","identity":"driver-pane","watchtower_name":"north","policy_sha256":"policy-unpreset"}' > "$target"; chmod 600 "$target"
  run env HERDR_PANE_ID=driver-pane ROZORO_WT_DRIVER=herdr-driver-pane "$REPO_ROOT/bin/rzr-spawn.sh" unpreset --cwd "$TEST_ROOT" --harness pi --no-agent
  assert_success
  meta="$ROZORO_HOME/state/unpreset.meta"; uuid="$(sed -n 's/^session=//p' "$meta")"
  assert_file_contains "$meta" 'dispatcher_policy_sha=policy-unpreset'; assert_file_contains "$meta" 'dispatcher_preset='
  printf '{"type":"session","version":3,"id":"%s","cwd":"%s"}\n' "$uuid" "$TEST_ROOT" > "$store/unpreset.jsonl"
  run rzr-link.sh unpreset "$TEST_ROOT"; assert_success
  descriptor="$ROZORO_HOME/tasks/unpreset/session.json"
  [ "$(jq -r '.dispatcher.policy_sha256' "$descriptor")" = policy-unpreset ]; [ "$(jq -r '.dispatcher.preset' "$descriptor")" = '' ]
  run rzr-link.sh unpreset "$TEST_ROOT"; assert_success
  [ "$(jq -r '.dispatcher.policy_sha256' "$descriptor")" = policy-unpreset ]; [ "$(jq -r '.dispatcher.preset' "$descriptor")" = '' ]

  printf '%s\n' '{"schema":1,"registration_id":"preset-id","driver_id":"herdr-driver-pane","identity":"driver-pane","watchtower_name":"north","policy_sha256":"policy-preset","preset":{"name":"luna","version":"3","sha256":"abc","policy_sha256":"policy-preset"}}' > "$target"
  run env HERDR_PANE_ID=driver-pane ROZORO_WT_DRIVER=herdr-driver-pane "$REPO_ROOT/bin/rzr-spawn.sh" preset --cwd "$TEST_ROOT" --harness pi --no-agent
  assert_success
  meta="$ROZORO_HOME/state/preset.meta"; uuid="$(sed -n 's/^session=//p' "$meta")"
  assert_file_contains "$meta" 'dispatcher_preset=luna'; assert_file_contains "$meta" 'dispatcher_policy_sha=policy-preset'
  printf '{"type":"session","version":3,"id":"%s","cwd":"%s"}\n' "$uuid" "$TEST_ROOT" > "$store/preset.jsonl"
  run rzr-link.sh preset "$TEST_ROOT"; assert_success
  descriptor="$ROZORO_HOME/tasks/preset/session.json"
  [ "$(jq -r '[.dispatcher.preset,.dispatcher.policy_sha256] | join(":")' "$descriptor")" = luna:policy-preset ]
  run rzr-link.sh preset "$TEST_ROOT"; assert_success
  [ "$(jq -r '[.dispatcher.preset,.dispatcher.policy_sha256] | join(":")' "$descriptor")" = luna:policy-preset ]
}

@test "ambiguous dispatcher identity never blocks spawn or stamps attribution" {
  for driver in one two; do
    mkdir -p "$ROZORO_HOME/watchtowers/$driver"; chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/$driver"
    printf '{"schema":1,"registration_id":"%s-id","driver_id":"%s","identity":"shared-pane"}\n' "$driver" "$driver" > "$ROZORO_HOME/watchtowers/$driver/target.json"
    chmod 600 "$ROZORO_HOME/watchtowers/$driver/target.json"
  done
  run env HERDR_PANE_ID=shared-pane "$REPO_ROOT/bin/rzr-spawn.sh" ambiguous --cwd "$TEST_ROOT" --no-agent
  assert_success
  ! grep -F 'dispatcher_' "$ROZORO_HOME/state/ambiguous.meta"
}

@test "Claude event-bus production generates isolated hooks and exact launch identity" {
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rzr-spawn.sh" task --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  session="$(sed -n 's/^session=//p' "$ROZORO_HOME/state/task.meta")"
  [ -n "$session" ]
  [ "$(sed -n 's/^event_bus=//p' "$ROZORO_HOME/state/task.meta")" = true ]
  settings="$ROZORO_HOME/tasks/task/claude-event-settings.json"
  [ "$(file_perm "$settings")" = 600 ]
  [ "$(jq '.hooks | keys | length' "$settings")" -eq 6 ]
  command="$(jq -r '.hooks.Stop[0].hooks[0].command' "$settings")"
  [[ "$command" == *"ROZORO_TASK_ID=task"* ]]
  [[ "$command" == *"ROZORO_SESSION_ID=$session"* ]]
  assert_file_contains "$FAKE_HERDR_LOG" $'--session-id\t'"$session"
  assert_file_contains "$FAKE_HERDR_LOG" $'--settings\t'"$settings"
}

@test "Claude generated settings refuse final and predictable-temp symlinks" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  ln -s "$SENTINEL" "$ROZORO_HOME/tasks/task/claude-event-settings.json"
  ln -s "$SENTINEL" "$ROZORO_HOME/tasks/task/claude-event-settings.json.tmp"
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rzr-spawn.sh" task --cwd "$TEST_ROOT"
  assert_failure
  [ -L "$ROZORO_HOME/tasks/task/claude-event-settings.json" ]
  [ "$(cat "$SENTINEL")" = untouched ]
}


@test "Pi spawn maps profile fields, keeps the task verbatim, and preallocates a session" {
  mkdir -p "$ROZORO_HOME/crew"
  cat > "$ROZORO_HOME/crew/pi-worker.json" <<'JSON'
{"harness":"pi","model":"anthropic/claude-sonnet-4-6","effort":"high","permission_mode":"auto","rules":["never push"]}
JSON
  run rzr-spawn.sh task --crew pi-worker --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=pi'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'model=anthropic/claude-sonnet-4-6'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'effort=high'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'session='
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/task.meta")"
  [[ "$agent_name" =~ ^[a-z0-9_-]{1,32}$ ]]
  assert_file_contains "$ROZORO_HOME/tasks/task/sysprompt.md" 'never push'
  ! grep -F 'do exactly this' "$ROZORO_HOME/tasks/task/sysprompt.md"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tstart\t'"$agent_name"$'\t--kind\tpi\t--pane\tp1\t--\t--extension\t'
  assert_file_contains "$FAKE_HERDR_LOG" $'rozoro-watchtower.ts\t--model\tanthropic/claude-sonnet-4-6\t--thinking\thigh\t--approve\t--append-system-prompt'
  assert_file_contains "$FAKE_HERDR_LOG" $'\t--session-id\t'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\tdo exactly this'
}

@test "Codex preset maps high effort and fast tier independently" {
  mkdir -p "$ROZORO_HOME/crew"
  printf '%s\n' '{"harness":"codex","model":"gpt-5.6-sol","effort":"high","fast":true,"permission_mode":"auto","rules":[]}' > "$ROZORO_HOME/crew/fast.json"
  run rzr-spawn.sh task --crew fast --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'model=gpt-5.6-sol'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'effort=high'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'fast=true'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'permission_mode=yolo'
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/task.meta")"
  expected=$'CALL\tagent\tstart\t'"$agent_name"$'\t--kind\tcodex\t--pane\tp1\t--\t--yolo\t--model\tgpt-5.6-sol\t--config\tmodel_reasoning_effort=high\t--config\tservice_tier=priority'
  [ "$(grep -Fc "$expected" "$FAKE_HERDR_LOG")" -eq 1 ]
  assert_file_contains "$FAKE_HERDR_LOG" $'--config\thooks.Stop='
  assert_file_contains "$FAKE_HERDR_LOG" $'\t--dangerously-bypass-hook-trust'
}

@test "explicit no-fast overrides a fast preset without emitting a tier" {
  mkdir -p "$ROZORO_HOME/crew"
  printf '%s\n' '{"harness":"codex","model":"gpt-5.6-sol","effort":"high","fast":true}' > "$ROZORO_HOME/crew/fast.json"
  run rzr-spawn.sh task --crew fast --no-fast --cwd "$TEST_ROOT"
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'fast=false'
  ! grep -F 'service_tier=' "$FAKE_HERDR_LOG"
}

@test "invalid and unsupported fast presets fail before Herdr mutation" {
  mkdir -p "$ROZORO_HOME/crew"
  printf '%s\n' '{"harness":"codex","model":"gpt-5.6-sol","effort":"high","fast":"yes"}' > "$ROZORO_HOME/crew/bad-type.json"
  run rzr-spawn.sh task --crew bad-type --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'invalid JSON or known field types'
  [ ! -s "$FAKE_HERDR_LOG" ]

  printf '%s\n' '{"harness":"codex","fast":' > "$ROZORO_HOME/crew/malformed.json"
  run rzr-spawn.sh task --crew malformed --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'invalid JSON or known field types'
  [ ! -s "$FAKE_HERDR_LOG" ]

  printf '%s\n' '{"harness":"pi","model":"openai-codex/gpt-5.6-sol","effort":"high","fast":true}' > "$ROZORO_HOME/crew/pi-fast.json"
  run rzr-spawn.sh task --crew pi-fast --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'only for the codex harness'
  [ ! -s "$FAKE_HERDR_LOG" ]

  printf '%s\n' '{"harness":"codex","model":"gpt-5.6-terra","effort":"high","fast":true}' > "$ROZORO_HOME/crew/wrong-model.json"
  run rzr-spawn.sh task --crew wrong-model --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'only for codex model gpt-5.6-sol'
  [ ! -s "$FAKE_HERDR_LOG" ]
}

@test "spawn retries transient pane busy" {
  export FAKE_HERDR_BUSY_ONCE_MATCH=' agent start '
  run rzr-spawn.sh task --cwd "$TEST_ROOT"
  assert_success
  [ -e "$FAKE_HERDR_ROOT/busy-once" ]
}

@test "spawn accepts a launched agent that becomes ready after agent_not_ready" {
  fake_pane p1 idle codex true
  export FAKE_HERDR_FAIL_MATCH=' agent start '
  export FAKE_HERDR_FAIL_TEXT='{"error":{"code":"agent_not_ready","message":"blocked during startup"}}'
  run rzr-spawn.sh task --harness codex --cwd "$TEST_ROOT"
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'agent_start=ok'
  [ "$(grep -c $'CALL\tagent\tstart\t' "$FAKE_HERDR_LOG")" -eq 1 ]
}

@test "spawn records terminal agent start failure" {
  export FAKE_HERDR_FAIL_MATCH=' agent start '
  export FAKE_HERDR_FAIL_TEXT='terminal start error'
  run rzr-spawn.sh task --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'terminal start error'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'agent_start=failed'
}

@test "fake Herdr counter tolerates long agent-start argv while validating the name" {
  long_arg="$(printf '%0300d' 0)"
  run herdr agent start valid-agent --kind claude --pane p1 -- "$long_arg"
  assert_success

  run herdr agent start 'INVALID-AGENT' --kind claude --pane p1
  assert_failure
  assert_output_contains 'invalid_agent_name'
}

@test "send fails closed for unknown and dead targets" {
  run rzr-send.sh missing hello
  assert_failure
  assert_output_contains "no such task 'missing'"
  write_meta task 'pane=p1'
  export FAKE_HERDR_FAIL_MATCH=' agent prompt '
  run rzr-send.sh task hello
  assert_failure
  assert_output_contains 'agent blocked, or pane gone'
}

@test "data and control planes use distinct Herdr operations" {
  write_meta task 'pane=p1' 'tab=t1'
  fake_status p1 idle
  run rzr-send.sh task 'interrupt'
  assert_success
  run rzr-control.sh task interrupt
  assert_success
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\tinterrupt'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tsend-keys\tp1\tesc'
}

@test "send defaults a pi-harness task to followup mode, deferring a working pane" {
  write_meta task 'pane=p1' 'harness=pi'
  fake_status p1 working
  run rzr-send.sh task hello
  assert_success
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\twait\tp1\t--timeout\t120000\t--until\tidle\t--until\tblocked\t--until\tdone'
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\thello'
}

@test "send followup mode delivers immediately when the pane is already idle" {
  write_meta task 'pane=p1' 'harness=pi'
  fake_status p1 idle
  run rzr-send.sh task hello
  assert_success
  ! grep -F $'agent\twait\tp1' "$FAKE_HERDR_LOG"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\thello'
}

@test "send followup mode fails closed when the pane never leaves working" {
  write_meta task 'pane=p1' 'harness=pi'
  fake_status p1 working
  export FAKE_HERDR_FAIL_MATCH=' agent wait '
  run rzr-send.sh task hello
  assert_failure
  assert_output_contains 'still working'
  ! grep -F $'agent\tprompt\tp1' "$FAKE_HERDR_LOG"
}

@test "send --mode steer bypasses followup even on a pi-harness task" {
  write_meta task 'pane=p1' 'harness=pi'
  fake_status p1 working
  run rzr-send.sh task hello --mode steer
  assert_success
  ! grep -F $'agent\twait\tp1' "$FAKE_HERDR_LOG"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\thello'
}

@test "send defaults a non-pi-harness task to steer mode, unchanged" {
  write_meta task 'pane=p1' 'harness=claude'
  fake_status p1 working
  run rzr-send.sh task hello
  assert_success
  ! grep -F $'agent\twait\tp1' "$FAKE_HERDR_LOG"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tprompt\tp1\thello'
}

@test "send rejects an unknown --mode" {
  write_meta task 'pane=p1' 'harness=pi'
  fake_status p1 idle
  run rzr-send.sh task hello --mode bogus
  assert_failure
  assert_output_contains "unknown --mode 'bogus'"
}

@test "control refuses a dead pane" {
  write_meta task 'pane=p1' 'tab=t1'
  run rzr-control.sh task cancel
  assert_failure
  assert_output_contains 'dead target'
  ! grep -F $'send-keys\tp1' "$FAKE_HERDR_LOG"
}

@test "teardown removes state but preserves durable task folder" {
  write_meta task 'pane=p1' 'tab=t1' "cwd=$TEST_ROOT"
  mkdir -p "$ROZORO_HOME/tasks/task"; printf 'history\n' > "$ROZORO_HOME/tasks/task/handoff.md"
  run rzr-teardown.sh task --force
  assert_success
  [ ! -e "$ROZORO_HOME/state/task.meta" ]
  [ "$(cat "$ROZORO_HOME/tasks/task/handoff.md")" = history ]
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\ttab\tclose\tt1'
}

teardown_preserves_cwd() {
  id="$1" cwd="$2"
  write_meta "$id" 'pane=p1' 'tab=t1' "cwd=$cwd"
  mkdir -p "$ROZORO_HOME/tasks/$id"
  printf 'resume-custody\n' > "$ROZORO_HOME/tasks/$id/session.json"
  before="$(directory_snapshot "$cwd")"
  run rzr-teardown.sh "$id"
  assert_success
  [ "$(directory_snapshot "$cwd")" = "$before" ]
  [ "$(cat "$ROZORO_HOME/tasks/$id/session.json")" = resume-custody ]
}

@test "teardown is VCS-agnostic and leaves every cwd byte untouched" {
  non_vcs="$TEST_ROOT/non-vcs"
  mkdir -p "$non_vcs/subdir"
  printf 'ordinary bytes\n' > "$non_vcs/subdir/file"
  teardown_preserves_cwd non-vcs "$non_vcs"

  no_upstream="$TEST_ROOT/no-upstream"
  mkdir -p "$no_upstream/.git/refs/heads" "$no_upstream/.git/objects"
  printf 'ref: refs/heads/main\n' > "$no_upstream/.git/HEAD"
  printf '[core]\n\trepositoryformatversion = 0\n' > "$no_upstream/.git/config"
  printf '1111111111111111111111111111111111111111\n' > "$no_upstream/.git/refs/heads/main"
  printf 'tracked\n' > "$no_upstream/tracked"
  teardown_preserves_cwd no-upstream "$no_upstream"

  dirty="$TEST_ROOT/dirty"
  cp -R "$no_upstream" "$dirty"
  printf 'index bytes\n' > "$dirty/.git/index"
  printf 'modified\n' >> "$dirty/tracked"
  printf 'untracked\n' > "$dirty/untracked"
  teardown_preserves_cwd dirty "$dirty"

  detached="$TEST_ROOT/detached"
  cp -R "$no_upstream" "$detached"
  printf '1111111111111111111111111111111111111111\n' > "$detached/.git/HEAD"
  teardown_preserves_cwd detached "$detached"

  ahead="$TEST_ROOT/ahead"
  cp -R "$no_upstream" "$ahead"
  mkdir -p "$ahead/.git/refs/remotes/origin"
  printf '2222222222222222222222222222222222222222\n' > "$ahead/.git/refs/heads/main"
  printf '1111111111111111111111111111111111111111\n' > "$ahead/.git/refs/remotes/origin/main"
  printf '[branch "main"]\n\tremote = origin\n\tmerge = refs/heads/main\n' >> "$ahead/.git/config"
  printf 'unpushed\n' >> "$ahead/tracked"
  teardown_preserves_cwd ahead "$ahead"

  jj="$TEST_ROOT/jj"
  mkdir -p "$jj/.jj/repo/store" "$jj/src"
  printf 'jj metadata\n' > "$jj/.jj/repo/store/state"
  printf 'dirty jj work\n' > "$jj/src/file"
  teardown_preserves_cwd jj "$jj"
}

@test "deprecated teardown force remains a harmless compatibility no-op" {
  cwd="$TEST_ROOT/force-compat"
  mkdir -p "$cwd"
  printf 'preserved\n' > "$cwd/file"
  write_meta task 'pane=p1' 'tab=t1' "cwd=$cwd"
  before="$(directory_snapshot "$cwd")"
  run rzr-teardown.sh task --force
  assert_success
  assert_output_contains '--force is deprecated and unnecessary'
  [ "$(directory_snapshot "$cwd")" = "$before" ]
}

@test "teardown keep-tab and unknown-task protections are unchanged" {
  write_meta task 'pane=p1' 'tab=t1'
  run rzr-teardown.sh task --keep-tab
  assert_success
  ! grep -F $'CALL\ttab\tclose\tt1' "$FAKE_HERDR_LOG"

  run rzr-teardown.sh unknown
  assert_failure
  assert_output_contains "no such task 'unknown'"
}

@test "Pi session link uses the preallocated native UUID" {
  uuid='11111111-2222-4333-8444-555555555555'
  write_meta task 'harness=pi' "session=$uuid" 'dispatcher_driver=herdr-p1' 'dispatcher_wt_name=north' \
    'dispatcher_policy_sha=policy-unpreset'
  store="$HOME/.pi/agent/sessions/--fixture--"
  mkdir -p "$store"
  printf '{"type":"session","version":3,"id":"%s","cwd":"%s"}\n' "$uuid" "$TEST_ROOT" > "$store/pi.jsonl"
  run rzr-link.sh task "$TEST_ROOT"
  assert_success
  assert_output_contains "$uuid"
  assert_file_contains "$ROZORO_HOME/tasks/task/session.json" '"harness": "pi"'
  assert_file_contains "$ROZORO_HOME/tasks/task/session.json" "\"session_id\": \"$uuid\""
  assert_file_contains "$ROZORO_HOME/tasks/task/session.json" "\"session_path\": \"$store/pi.jsonl\""
  assert_file_contains "$ROZORO_HOME/tasks/task/session.json" '"fast": false'
  [ "$(jq -r '[.dispatcher.driver_id,.dispatcher.watchtower_name,.dispatcher.policy_sha256] | join(":")' "$ROZORO_HOME/tasks/task/session.json")" = 'herdr-p1:north:policy-unpreset' ]
}

@test "session link persists and enriches the effective launch profile" {
  uuid='11111111-2222-4333-8444-555555555555'
  write_meta task 'harness=pi' 'model=anthropic/claude-sonnet-4-6' 'effort=high' 'permission_mode=auto' 'fast=false' "session=$uuid" \
    'dispatcher_driver=herdr-p1' 'dispatcher_wt_name=north' 'dispatcher_preset=luna' \
    'dispatcher_preset_version=3' 'dispatcher_preset_sha=abc' 'dispatcher_policy_sha=policy-preset'
  store="$HOME/.pi/agent/sessions/--fixture--"
  mkdir -p "$store" "$ROZORO_HOME/tasks/task"
  printf '{"type":"session","version":3,"id":"%s","cwd":"%s"}\n' "$uuid" "$TEST_ROOT" > "$store/pi.jsonl"
  printf '{"session_id":"%s","harness":"pi","cwd":"%s"}\n' "$uuid" "$TEST_ROOT" > "$ROZORO_HOME/tasks/task/session.json"
  run rzr-link.sh task "$TEST_ROOT"
  assert_success
  [ "$(jq -r '.profile.model' "$ROZORO_HOME/tasks/task/session.json")" = 'anthropic/claude-sonnet-4-6' ]
  [ "$(jq -r '.profile.effort' "$ROZORO_HOME/tasks/task/session.json")" = high ]
  [ "$(jq -r '.profile.fast' "$ROZORO_HOME/tasks/task/session.json")" = false ]
  [ "$(jq -r '[.dispatcher.driver_id,.dispatcher.watchtower_name,.dispatcher.preset,.dispatcher.preset_version,.dispatcher.preset_sha256,.dispatcher.policy_sha256] | join(":")' "$ROZORO_HOME/tasks/task/session.json")" = 'herdr-p1:north:luna:3:abc:policy-preset' ]
}

@test "Codex session link stores a fast resolved profile" {
  write_meta task 'harness=codex' 'model=gpt-5.6-sol' 'effort=high' 'permission_mode=yolo' 'fast=true'
  store="$HOME/.codex/sessions/2026/08/22"
  mkdir -p "$store"
  cat > "$store/codex.jsonl" <<JSON
{"type":"session_meta","payload":{"id":"uuid-codex","cwd":"$TEST_ROOT"}}
{"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"rozoro-task: task\nbody"}]}}
JSON
  run rzr-link.sh task "$TEST_ROOT"
  assert_success
  descriptor="$ROZORO_HOME/tasks/task/session.json"
  [ "$(jq -r '.profile.harness' "$descriptor")" = codex ]
  [ "$(jq -r '.profile.model' "$descriptor")" = gpt-5.6-sol ]
  [ "$(jq -r '.profile.effort' "$descriptor")" = high ]
  [ "$(jq -r '.profile.fast' "$descriptor")" = true ]
}

@test "Pi session link falls back to an isolated real user marker" {
  write_meta task 'harness=pi'
  export PI_CODING_AGENT_SESSION_DIR="$TEST_ROOT/pi-sessions"
  mkdir -p "$PI_CODING_AGENT_SESSION_DIR/project"
  cat > "$PI_CODING_AGENT_SESSION_DIR/project/pi.jsonl" <<JSON
{"type":"session","version":3,"id":"legacy-pi","cwd":"$TEST_ROOT"}
{"type":"message","id":"12345678","parentId":null,"message":{"role":"user","content":[{"type":"text","text":"rozoro-task: task\\nbody"}]}}
JSON
  run rzr-link.sh task "$TEST_ROOT"
  assert_success
  assert_file_contains "$ROZORO_HOME/tasks/task/session.json" '"session_id": "legacy-pi"'
}

@test "legacy Claude session link can be resumed" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf '{"session_id":"uuid-1","harness":"claude","cwd":"%s"}\n' "$TEST_ROOT" > "$ROZORO_HOME/tasks/task/session.json"
  run rzr-resume.sh task --prompt 'continue'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'session=uuid-1'
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/task.meta")"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tstart\t'"$agent_name"$'\t--kind\tclaude\t--pane\tp1\t--\t--resume\tuuid-1'
}

@test "Claude event-bus resume preserves exact session identity in generated hooks" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf '{"session_id":"uuid-1","harness":"claude","cwd":"%s"}\n' "$TEST_ROOT" > "$ROZORO_HOME/tasks/task/session.json"
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rzr-resume.sh" task
  assert_success
  settings="$ROZORO_HOME/tasks/task/claude-event-settings.json"
  [[ "$(jq -r '.hooks.SessionStart[0].hooks[0].command' "$settings")" == *"ROZORO_SESSION_ID=uuid-1"* ]]
  assert_file_contains "$FAKE_HERDR_LOG" $'--resume\tuuid-1\t--permission-mode\tauto\t--settings\t'"$settings"
}

@test "Codex resume reapplies durable model effort and fast tier" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  cat > "$ROZORO_HOME/tasks/task/session.json" <<JSON
{"session_id":"uuid-codex","harness":"codex","cwd":"$TEST_ROOT","profile":{"harness":"codex","model":"gpt-5.6-sol","effort":"high","permission_mode":"yolo","fast":true}}
JSON
  run rzr-resume.sh task --prompt 'continue'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'effort=high'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'fast=true'
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/task.meta")"
  expected=$'CALL\tagent\tstart\t'"$agent_name"$'\t--kind\tcodex\t--pane\tp1\t--\tresume\tuuid-codex\t--yolo\t--model\tgpt-5.6-sol\t--config\tmodel_reasoning_effort=high\t--config\tservice_tier=priority'
  [ "$(grep -Fc "$expected" "$FAKE_HERDR_LOG")" -eq 1 ]
  assert_file_contains "$FAKE_HERDR_LOG" $'--config\thooks.Stop='
  assert_file_contains "$FAKE_HERDR_LOG" $'\t--dangerously-bypass-hook-trust'
}

@test "resume accepts a launched agent that becomes ready after agent_not_ready" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf '{"session_id":"uuid-codex","harness":"codex","cwd":"%s"}\n' "$TEST_ROOT" > "$ROZORO_HOME/tasks/task/session.json"
  fake_pane p1 idle codex true
  export FAKE_HERDR_FAIL_MATCH=' agent start '
  export FAKE_HERDR_FAIL_TEXT='{"error":{"code":"agent_not_ready","message":"blocked during startup"}}'
  run rzr-resume.sh task
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'agent_start=ok'
  [ "$(grep -c $'CALL\tagent\tstart\t' "$FAKE_HERDR_LOG")" -eq 1 ]
}

@test "Codex resume overrides can disable fast and change effort" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  cat > "$ROZORO_HOME/tasks/task/session.json" <<JSON
{"session_id":"uuid-codex","harness":"codex","cwd":"$TEST_ROOT","profile":{"harness":"codex","model":"gpt-5.6-sol","effort":"high","permission_mode":"yolo","fast":true}}
JSON
  run rzr-resume.sh task --effort low --no-fast
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'effort=low'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'fast=false'
  assert_file_contains "$FAKE_HERDR_LOG" $'\t--config\tmodel_reasoning_effort=low'
  ! grep -F 'service_tier=' "$FAKE_HERDR_LOG"
}

@test "relink persists resume overrides for the next plain resume" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  cat > "$ROZORO_HOME/tasks/task/session.json" <<JSON
{"session_id":"uuid-codex","harness":"codex","cwd":"$TEST_ROOT","profile":{"harness":"codex","model":"gpt-5.6-sol","effort":"high","permission_mode":"yolo","fast":true}}
JSON
  run rzr-resume.sh task --effort low --no-fast
  assert_success

  run rzr-link.sh task "$TEST_ROOT"
  assert_success
  descriptor="$ROZORO_HOME/tasks/task/session.json"
  [ "$(jq -r '.profile.effort' "$descriptor")" = low ]
  [ "$(jq -r '.profile.fast' "$descriptor")" = false ]

  run rzr-teardown.sh task --force
  assert_success
  : > "$FAKE_HERDR_LOG"
  run rzr-resume.sh task
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'effort=low'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'fast=false'
  assert_file_contains "$FAKE_HERDR_LOG" $'\t--config\tmodel_reasoning_effort=low'
  ! grep -F 'service_tier=' "$FAKE_HERDR_LOG"
}

@test "legacy Codex descriptor resumes without injecting model effort or tier" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf '{"session_id":"uuid-codex","harness":"codex","cwd":"%s"}\n' "$TEST_ROOT" > "$ROZORO_HOME/tasks/task/session.json"
  run rzr-resume.sh task
  assert_success
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/task.meta")"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tstart\t'"$agent_name"$'\t--kind\tcodex\t--pane\tp1\t--\tresume\tuuid-codex\t--yolo'
  ! grep -F 'model_reasoning_effort=' "$FAKE_HERDR_LOG"
  ! grep -F 'service_tier=' "$FAKE_HERDR_LOG"
}

@test "ULID durable task key launches and resumes with one Herdr-safe identity" {
  id='fix-syntax-isolation--01M0KK771Z1PV4428XKJ3MJPC7'
  mkdir -p "$ROZORO_HOME/tasks/$id"
  printf '{"session_id":"uuid-2","harness":"claude","cwd":"%s"}\n' "$TEST_ROOT" > "$ROZORO_HOME/tasks/$id/session.json"

  run rzr-spawn.sh "$id" --cwd "$TEST_ROOT"
  assert_success
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/$id.meta")"
  [[ "$agent_name" =~ ^[a-z0-9_-]{1,32}$ ]]
  [ "$agent_name" != "$id" ]

  run rzr-teardown.sh "$id" --force
  assert_success
  run rzr-resume.sh "$id"
  assert_success
  [ "$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/$id.meta")" = "$agent_name" ]
  [ "$(grep -F $'CALL\tagent\tstart\t'"$agent_name" "$FAKE_HERDR_LOG" | wc -l)" -eq 2 ]
}

@test "Pi session can be resumed with trust, model override, and persisted system prompt" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf 'handoff rules\n' > "$ROZORO_HOME/tasks/task/sysprompt.md"
  printf '{"session_id":"uuid-pi","harness":"pi","cwd":"%s"}\n' "$TEST_ROOT" > "$ROZORO_HOME/tasks/task/session.json"
  run rzr-resume.sh task --model anthropic/claude-sonnet-4-6 --prompt 'continue'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'session=uuid-pi'
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/task.meta")"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tstart\t'"$agent_name"$'\t--kind\tpi\t--pane\tp1\t--\t--extension\t'
  assert_file_contains "$FAKE_HERDR_LOG" $'rozoro-watchtower.ts\t--session\tuuid-pi\t--approve\t--model\tanthropic/claude-sonnet-4-6\t--append-system-prompt'
  assert_file_contains "$ROZORO_HOME/tasks/task/sysprompt.md" 'rozoro-task: task'
  assert_file_contains "$FAKE_HERDR_LOG" "$ROZORO_HOME/tasks/task/sysprompt.md"
}

@test "resume refuses a currently tracked task" {
  write_meta task 'pane=p1'
  run rzr-resume.sh task
  assert_failure
  assert_output_contains "still tracked"
}

@test "spawn and resume help stop before executable source" {
  run rzr-spawn.sh --help
  assert_success
  assert_output_contains '--fast'
  [[ "$output" != *'set -euo pipefail'* ]]
  [[ "$output" != *'BASH_SOURCE'* ]]
  [[ "$output" != *'ID=""'* ]]
  [[ "$output" != *'while [ $# -gt 0 ]'* ]]

  run rzr-resume.sh --help
  assert_success
  assert_output_contains '--no-fast'
  [[ "$output" != *'set -euo pipefail'* ]]
  [[ "$output" != *'BASH_SOURCE'* ]]
  [[ "$output" != *'ID=""'* ]]
  [[ "$output" != *'while [ $# -gt 0 ]'* ]]
}

@test "restart preserves Codex fast profile" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf 'continue\n' > "$ROZORO_HOME/tasks/task/brief.md"
  write_meta task 'pane=p0' 'tab=t0' "cwd=$TEST_ROOT" 'crew=default' 'harness=codex' 'model=gpt-5.6-sol' 'effort=high' 'fast=true' 'permission_mode=yolo'
  fake_status p1 idle
  run rzr-control.sh task restart
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'fast=true'
  assert_file_contains "$FAKE_HERDR_LOG" $'\t--config\tmodel_reasoning_effort=high\t--config\tservice_tier=priority'
}

@test "restart after resume does not treat the lifecycle marker as a crew preset" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf 'continue\n' > "$ROZORO_HOME/tasks/task/brief.md"
  cat > "$ROZORO_HOME/tasks/task/session.json" <<JSON
{"session_id":"uuid-codex","harness":"codex","cwd":"$TEST_ROOT","profile":{"harness":"codex","model":"gpt-5.6-sol","effort":"high","permission_mode":"yolo","fast":true}}
JSON
  fake_pane p1 idle codex true
  run rzr-resume.sh task
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'crew=resumed'

  store="$HOME/.codex/sessions/2026/08/22"
  mkdir -p "$store"
  cat > "$store/restarted.jsonl" <<JSON
{"type":"session_meta","payload":{"id":"uuid-restarted","cwd":"$TEST_ROOT"}}
{"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"rozoro-task: task\nbody"}]}}
JSON

  run rzr-control.sh task restart
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'fast=true'
  assert_file_contains "$FAKE_HERDR_LOG" $'\t--config\tmodel_reasoning_effort=high\t--config\tservice_tier=priority'
  [ "$(jq -r '.session_id' "$ROZORO_HOME/tasks/task/session.json")" = uuid-restarted ]
}

@test "start gives repeated display names distinct durable task keys" {
  printf 'ship it\n' > "$TEST_ROOT/body"
  run rzr-start.sh same-name --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent
  assert_success
  key1="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  run rzr-start.sh same-name --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent
  assert_success
  key2="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  [ "$key1" != "$key2" ]
  [ -f "$ROZORO_HOME/tasks/$key1/brief.md" ]
  [ -f "$ROZORO_HOME/tasks/$key2/brief.md" ]
  assert_file_contains "$ROZORO_HOME/state/$key1.meta" 'display_name=same-name'
  agent_name1="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/$key1.meta")"
  agent_name2="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/$key2.meta")"
  [[ "$agent_name1" =~ ^[a-z0-9_-]{1,32}$ ]]
  [ "$agent_name1" != "$agent_name2" ]
  assert_file_contains "$ROZORO_HOME/tasks/$key1/identity.json" '"herdr_agent_name"'
}

@test "start passes fast through to spawn" {
  printf 'ship it\n' > "$TEST_ROOT/body"
  run rzr-start.sh fast-start --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --harness codex --model gpt-5.6-sol --effort high --fast --no-agent
  assert_success
  key="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  assert_file_contains "$ROZORO_HOME/state/$key.meta" 'fast=true'
}

@test "reuse after teardown preserves the old durable record" {
  printf 'first\n' > "$TEST_ROOT/first"
  printf 'second\n' > "$TEST_ROOT/second"
  run rzr-start.sh reusable --body "$TEST_ROOT/first" --cwd "$TEST_ROOT" --no-agent
  assert_success
  old="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  run rzr-teardown.sh "$old" --force
  assert_success
  run rzr-start.sh reusable --body "$TEST_ROOT/second" --cwd "$TEST_ROOT" --no-agent
  assert_success
  new="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  [ "$old" != "$new" ]
  assert_file_contains "$ROZORO_HOME/tasks/$old/brief.md" 'first'
  assert_file_contains "$ROZORO_HOME/tasks/$new/brief.md" 'second'
}

@test "concurrent same-name starts reserve different folders" {
  printf 'parallel\n' > "$TEST_ROOT/body"
  rzr-start.sh concurrent --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent > "$TEST_ROOT/a.out" 2>&1 & p1=$!
  rzr-start.sh concurrent --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent > "$TEST_ROOT/b.out" 2>&1 & p2=$!
  wait "$p1"; wait "$p2"
  key1="$(sed -n 's/^rzr-start: task key -> //p' "$TEST_ROOT/a.out")"
  key2="$(sed -n 's/^rzr-start: task key -> //p' "$TEST_ROOT/b.out")"
  [ -n "$key1" ] && [ -n "$key2" ] && [ "$key1" != "$key2" ]
  [ -d "$ROZORO_HOME/tasks/$key1" ] && [ -d "$ROZORO_HOME/tasks/$key2" ]
}

@test "same display name across repositories has distinct identities" {
  mkdir -p "$TEST_ROOT/repo-a" "$TEST_ROOT/repo-b"
  printf 'cross repo\n' > "$TEST_ROOT/body"
  run rzr-start.sh shared --body "$TEST_ROOT/body" --cwd "$TEST_ROOT/repo-a" --no-agent
  assert_success
  key1="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  run rzr-start.sh shared --body "$TEST_ROOT/body" --cwd "$TEST_ROOT/repo-b" --no-agent
  assert_success
  key2="$(printf '%s\n' "$output" | sed -n 's/^rzr-start: task key -> //p')"
  [ "$key1" != "$key2" ]
  assert_file_contains "$ROZORO_HOME/tasks/$key1/identity.json" "$TEST_ROOT/repo-a"
  assert_file_contains "$ROZORO_HOME/tasks/$key2/identity.json" "$TEST_ROOT/repo-b"
}

@test "unsafe display names cannot escape the task root" {
  printf 'unsafe\n' > "$TEST_ROOT/body"
  run rzr-start.sh ../escape --body "$TEST_ROOT/body" --cwd "$TEST_ROOT" --no-agent
  assert_failure
  assert_output_contains 'display name'
  [ ! -e "$ROZORO_HOME/escape" ]
}

@test "Copilot fallback is autonomous, preallocates identity, links without private storage, and resumes exactly" {
  run rzr-spawn.sh task --harness copilot --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'model=auto'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'permission_mode=yolo'
  uuid="$(sed -n 's/^session=//p' "$ROZORO_HOME/state/task.meta")"
  [ -n "$uuid" ]
  assert_file_contains "$FAKE_HERDR_LOG" $'--no-auto-update\t--autopilot\t--yolo\t--no-ask-user\t--model\tauto\t--session-id\t'"$uuid"
  assert_file_contains "$FAKE_HERDR_LOG" $'--- task ---\ndo exactly this'
  run rzr-link.sh task "$TEST_ROOT"
  assert_success
  [ "$(jq -r .session_id "$ROZORO_HOME/tasks/task/session.json")" = "$uuid" ]
  [ "$(jq 'has("session_path")' "$ROZORO_HOME/tasks/task/session.json")" = false ]
  rm "$ROZORO_HOME/state/task.meta"
  : > "$FAKE_HERDR_LOG"
  run rzr-resume.sh task --prompt continue
  assert_success
  assert_file_contains "$FAKE_HERDR_LOG" $'--no-auto-update\t--resume='"$uuid"$'\t--autopilot\t--yolo\t--no-ask-user\t--model\tauto'
  assert_file_contains "$FAKE_HERDR_LOG" '--- my follow-up ---'
}

@test "Copilot capability drift and fast fail before Herdr mutation" {
  export FAKE_COPILOT_OMIT=--session-id
  run rzr-spawn.sh task --harness copilot --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'missing required capability --session-id'
  [ ! -s "$FAKE_HERDR_LOG" ]
  unset FAKE_COPILOT_OMIT
  run rzr-spawn.sh task2 --harness copilot --fast --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'fast mode is currently supported only for the codex harness'
  [ ! -s "$FAKE_HERDR_LOG" ]
}
