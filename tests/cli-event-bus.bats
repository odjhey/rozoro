#!/usr/bin/env bats
load test_helper/common

start_monitor() { chmod 700 "$ROZORO_HOME"; run "$REPO_ROOT/bin/rozoro" monitor start; assert_success; }
seed_task() {
  write_handoff task-1 '## turn 1 — done' 'verdict:       done' 'reason:        ' 'did:           tested' 'pending:       none' 'inputs-needed: none' 'artifacts:     none'
  chmod 700 "$ROZORO_HOME"
  PYTHONPATH="$REPO_ROOT/lib" python3 - <<'PY'
import os
from rozoro_monitor.store import EventStore
s=EventStore(os.path.join(os.environ['ROZORO_HOME'],'monitor.db'))
base={'v':1,'session_id':'crew-1','harness':'pi','role':'crew','task_id':'task-1'}
s.accept_event({**base,'type':'session.register','event_id':'evt-register','producer_seq':1})
accepted=s.accept_event({**base,'type':'turn.stop','event_id':'evt-stop','producer_seq':2,'background_active':False})
s.register_driver('driver-1','adapter-1','pi')
s.close()
PY
  mkdir -p "$ROZORO_HOME/watchtowers/driver-1"
  printf '%s\n' '{"driver_id":"driver-1","harness":"pi"}' > "$ROZORO_HOME/watchtowers/driver-1/target.json"
}

@test "opt-in status preserves v2 fields and adds daemon availability source" {
  seed_task; start_monitor
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_success
  [ "$(jq -r .schema_version <<<"$output")" = 2 ]
  [ "$(jq -r .availability_source <<<"$output")" = event-bus ]
  [ "$(jq -r .availability <<<"$output")" = quiescent ]
  [ "$(jq -r .acked_through <<<"$output")" = 0 ]
}

@test "opt-in reconcile renders snapshot then ACKs exactly its generation without handoff ACK" {
  seed_task; start_monitor
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" reconcile --driver driver-1 --json
  assert_success
  gen="$(jq -r .acknowledged_generation <<<"$output")"; [ "$gen" -gt 0 ]
  [ "$(jq -r '.reports[0].availability_source' <<<"$output")" = event-bus-snapshot ]
  [ ! -e "$ROZORO_HOME/tasks/task-1/.acked-blocks-v2" ]
  run env ROZORO_EVENT_BUS=1 python3 "$REPO_ROOT/bin/rzr-event-bus-client.py" snapshot --driver driver-1 --harness pi
  assert_success; [ "$(jq -r .through <<<"$output")" = "$gen" ]; [ "$(jq '.reports|length' <<<"$output")" = 0 ]
}

@test "legacy pending ledger refuses opt-in and explicit fallback remains available" {
  seed_task
  printf '%s\n' '{"generation":2,"delivered":1,"tasks":{}}' > "$ROZORO_HOME/watchtowers/driver-1/pending.json"
  printf '1\n' > "$ROZORO_HOME/watchtowers/driver-1/ack"
  start_monitor
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_failure; assert_output_contains 'Reconcile legacy state first'
  run env ROZORO_EVENT_BUS=1 ROZORO_EVENT_BUS_FALLBACK=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_success; [ "$(jq -r .availability_source <<<"$output")" = legacy-v2 ]
}

@test "daemon-down opt-in diagnoses failure and does not silently fallback" {
  seed_task
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_failure; assert_output_contains 'event-bus daemon unavailable'
  run env ROZORO_EVENT_BUS=1 ROZORO_EVENT_BUS_FALLBACK=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_success
}
