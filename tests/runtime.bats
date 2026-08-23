#!/usr/bin/env bats
load test_helper/common

export ROZORO_LEGACY_DIAGNOSTIC=1

reduce() { python3 "$REPO_ROOT/bin/rzr-runtime.py" "$1" --id task --path "$ROZORO_HOME/state/task.runtime.json" --handoff "$ROZORO_HOME/tasks/task/handoff.md" --parser "$REPO_ROOT/bin/rzr-handoff.py" --foreground "$2"; }

@test "initial settled reconciliation is unobserved and a missing report is turn-aware" {
  write_handoff task ""
  run reduce reconcile idle; assert_success; [ "$(printf '%s' "$output"|jq -r .turn.report_status)" = unobserved ]
  reduce event working >/dev/null
  reduce event done >/dev/null
  [ "$(jq -r .turn.report_status "$ROZORO_HOME/state/task.runtime.json")" = missing-handoff ]
  [ "$(jq -r .action.reason "$ROZORO_HOME/state/task.runtime.json")" = missing-handoff ]
}

@test "one fresh canonical report is attributed to the observed turn" {
  write_handoff task ""
  reduce reconcile working >/dev/null
  write_handoff task '## turn 1 — done' 'verdict: done' 'reason:' 'did: work' 'pending: none' 'inputs-needed: none' 'artifacts: none'
  reduce event done >/dev/null
  [ "$(jq -r .turn.report_status "$ROZORO_HOME/state/task.runtime.json")" = reported ]
  [ "$(jq -r .action.reason "$ROZORO_HOME/state/task.runtime.json")" = turn-settled ]
}

@test "old Herdr waiting report is actionable not certified" {
  write_handoff task ""
  reduce reconcile working >/dev/null
  write_handoff task '## turn 1 — waiting' 'verdict: waiting' 'reason: job active' 'did: launched' 'pending: consume result' 'inputs-needed: none' 'artifacts: none'
  reduce event done >/dev/null
  [ "$(jq -r .action.reason "$ROZORO_HOME/state/task.runtime.json")" = inconsistent-wait ]
  run rzr-status.sh task --json; assert_success; assert_output_contains '"supported":null'; assert_output_contains '"action_reason":"inconsistent-wait"'
}

@test "stale marking retains facts and changes freshness only" {
  write_handoff task ""; reduce reconcile working >/dev/null
  python3 "$REPO_ROOT/bin/rzr-runtime.py" mark-stale --id task --path "$ROZORO_HOME/state/task.runtime.json" --handoff "$ROZORO_HOME/tasks/task/handoff.md" --parser "$REPO_ROOT/bin/rzr-handoff.py" >/dev/null
  [ "$(jq -r .source.freshness "$ROZORO_HOME/state/task.runtime.json")" = stale ]
  [ "$(jq -r .foreground_status "$ROZORO_HOME/state/task.runtime.json")" = working ]
}

@test "older and duplicate Herdr revisions cannot regress projection" {
  write_handoff task ""
  python3 "$REPO_ROOT/bin/rzr-runtime.py" reconcile --id task --path "$ROZORO_HOME/state/task.runtime.json" --handoff "$ROZORO_HOME/tasks/task/handoff.md" --parser "$REPO_ROOT/bin/rzr-handoff.py" --foreground done --seq 20 >/dev/null
  python3 "$REPO_ROOT/bin/rzr-runtime.py" event --id task --path "$ROZORO_HOME/state/task.runtime.json" --handoff "$ROZORO_HOME/tasks/task/handoff.md" --parser "$REPO_ROOT/bin/rzr-handoff.py" --foreground working --seq 19 >/dev/null
  [ "$(jq -r .foreground_status "$ROZORO_HOME/state/task.runtime.json")" = done ]
  [ "$(jq -r .source.event_seq "$ROZORO_HOME/state/task.runtime.json")" = 20 ]
  [ "$(jq -r .source.sequence_kind "$ROZORO_HOME/state/task.runtime.json")" = herdr ]
}

@test "settlement performs exactly one bounded delayed handoff reconciliation" {
  write_handoff task ""; RZR_HANDOFF_DELAY_MS=0 reduce reconcile working >/dev/null
  (sleep 0.05; write_handoff task '## turn 1 — done' 'verdict: done' 'reason:' 'did: work' 'pending: none' 'inputs-needed: none' 'artifacts: none') & register_pid "$!"
  run env RZR_HANDOFF_DELAY_MS=200 python3 "$REPO_ROOT/bin/rzr-runtime.py" event --id task --path "$ROZORO_HOME/state/task.runtime.json" --handoff "$ROZORO_HOME/tasks/task/handoff.md" --parser "$REPO_ROOT/bin/rzr-handoff.py" --foreground done
  assert_success; wait; TEST_PIDS=""
  [ "$(printf '%s' "$output" | jq -r .turn.report_status)" = reported ]
}

@test "pane gone is actionable only after a live observation" {
  write_handoff task ""
  python3 "$REPO_ROOT/bin/rzr-runtime.py" reconcile --id task --path "$ROZORO_HOME/state/task.runtime.json" --handoff "$ROZORO_HOME/tasks/task/handoff.md" --parser "$REPO_ROOT/bin/rzr-handoff.py" --foreground idle --seq 1 >/dev/null
  run python3 "$REPO_ROOT/bin/rzr-runtime.py" event --id task --path "$ROZORO_HOME/state/task.runtime.json" --handoff "$ROZORO_HOME/tasks/task/handoff.md" --parser "$REPO_ROOT/bin/rzr-handoff.py" --foreground gone --seq 2
  assert_success; [ "$(printf '%s' "$output" | jq -r .action.reason)" = pane-gone ]
  rm -f "$ROZORO_HOME/state/task.runtime.json"
  run python3 "$REPO_ROOT/bin/rzr-runtime.py" reconcile --id task --path "$ROZORO_HOME/state/task.runtime.json" --handoff "$ROZORO_HOME/tasks/task/handoff.md" --parser "$REPO_ROOT/bin/rzr-handoff.py" --foreground gone --seq 1
  assert_success; [ "$(printf '%s' "$output" | jq -r .action.required)" = false ]
}
