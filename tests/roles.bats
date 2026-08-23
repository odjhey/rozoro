#!/usr/bin/env bats
# Per-machine role preferences (coder/planner -> harness/model), host-local
# under $ROZORO_HOME/crew/roles/<role>.json. See rzr-lib.sh rzr_role_* and
# rzr-spawn.sh --role.
load test_helper/common

@test "unconfigured machine: --role coder resolves to Claude Sonnet" {
  run rzr-spawn.sh task --role coder --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'role=coder'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'crew='
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=claude'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'model=sonnet'
  agent_name="$(sed -n 's/^herdr_agent_name=//p' "$ROZORO_HOME/state/task.meta")"
  assert_file_contains "$FAKE_HERDR_LOG" $'CALL\tagent\tstart\t'"$agent_name"$'\t--kind\tclaude\t--pane\tp1\t--\t--model\tsonnet'
}

@test "unconfigured machine: --role planner resolves to Claude Opus" {
  run rzr-spawn.sh task --role planner --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'role=planner'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=claude'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'model=opus'
}

@test "a host-local role file overrides the built-in fallback" {
  mkdir -p "$ROZORO_HOME/crew/roles"
  cat > "$ROZORO_HOME/crew/roles/coder.json" <<'JSON'
{"harness":"codex","model":"gpt-5.6-sol","effort":"low","permission_mode":"yolo","fast":false,"rules":["never push"]}
JSON
  run rzr-spawn.sh task --role coder --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=codex'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'model=gpt-5.6-sol'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'effort=low'
  assert_file_contains "$FAKE_HERDR_LOG" $'\t--yolo\t--model\tgpt-5.6-sol\t--config\tmodel_reasoning_effort=low'
}

@test "a host-local role file leaves the OTHER role on its built-in fallback" {
  mkdir -p "$ROZORO_HOME/crew/roles"
  cat > "$ROZORO_HOME/crew/roles/coder.json" <<'JSON'
{"harness":"codex","model":"gpt-5.6-sol"}
JSON
  run rzr-spawn.sh task --role planner --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=claude'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'model=opus'
}

@test "an explicit flag overrides the role's field" {
  run rzr-spawn.sh task --role coder --model opus --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'role=coder'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=claude'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'model=opus'
}

@test "an unknown role fails before Herdr mutation" {
  run rzr-spawn.sh task --role qa --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_failure
  assert_output_contains "unknown role 'qa'"
  [ ! -e "$ROZORO_HOME/state/task.meta" ]
  [ ! -s "$FAKE_HERDR_LOG" ]
}

@test "--role and --crew are mutually exclusive" {
  run rzr-spawn.sh task --role coder --crew default --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_failure
  assert_output_contains 'mutually exclusive'
  [ ! -e "$ROZORO_HOME/state/task.meta" ]
  [ ! -s "$FAKE_HERDR_LOG" ]
}

@test "a malformed role file fails validation before Herdr mutation" {
  mkdir -p "$ROZORO_HOME/crew/roles"
  printf '%s\n' '{"harness":"codex","fast":"yes"}' > "$ROZORO_HOME/crew/roles/coder.json"
  run rzr-spawn.sh task --role coder --cwd "$TEST_ROOT"
  assert_failure
  assert_output_contains 'invalid JSON or known field types'
  [ ! -s "$FAKE_HERDR_LOG" ]
}

@test "role rules are appended as a Claude system prompt, task prompt stays verbatim" {
  mkdir -p "$ROZORO_HOME/crew/roles"
  cat > "$ROZORO_HOME/crew/roles/coder.json" <<'JSON'
{"harness":"claude","model":"sonnet","rules":["always run tests first"]}
JSON
  run rzr-spawn.sh task --role coder --cwd "$TEST_ROOT" --prompt 'do exactly this'
  assert_success
  assert_file_contains "$ROZORO_HOME/tasks/task/sysprompt.md" 'always run tests first'
  ! grep -F 'do exactly this' "$ROZORO_HOME/tasks/task/sysprompt.md"
}

@test "rzr-crew.sh roles lists built-in and host-local roles" {
  mkdir -p "$ROZORO_HOME/crew/roles"
  cat > "$ROZORO_HOME/crew/roles/coder.json" <<'JSON'
{"harness":"codex","model":"gpt-5.6-sol"}
JSON
  run rzr-crew.sh roles
  assert_success
  assert_output_contains 'coder'
  assert_output_contains 'codex'
  assert_output_contains 'gpt-5.6-sol'
  assert_output_contains 'host-local'
  assert_output_contains 'planner'
  assert_output_contains 'claude'
  assert_output_contains 'opus'
  assert_output_contains 'built-in'
}

@test "rzr-crew.sh role-show prints a role's resolved JSON" {
  run rzr-crew.sh role-show planner
  assert_success
  assert_output_contains '"harness": "claude"'
  assert_output_contains '"model": "opus"'
}

@test "rzr-crew.sh role-path prints the file path even when unconfigured" {
  run rzr-crew.sh role-path coder
  assert_success
  assert_output_contains "$ROZORO_HOME/crew/roles/coder.json"
}

@test "restart replays --role rather than a nonexistent crew preset" {
  mkdir -p "$ROZORO_HOME/tasks/task"
  printf 'continue\n' > "$ROZORO_HOME/tasks/task/brief.md"
  write_meta task 'pane=p0' 'tab=t0' "cwd=$TEST_ROOT" 'crew=' 'role=coder' 'harness=claude' 'model=sonnet' 'effort=' 'fast=false' 'permission_mode=auto'
  fake_status p1 idle
  run rzr-control.sh task restart
  assert_success
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'role=coder'
  assert_file_contains "$ROZORO_HOME/state/task.meta" 'harness=claude'
}
