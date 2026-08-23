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
r=s.register_driver('driver-1','adapter-1','pi'); offer=s.offer_notification('driver-1','adapter-1',r['epoch'])
s.confirm_delivery('driver-1','adapter-1',r['epoch'],offer['generation'])
s.close()
PY
  mkdir -p "$ROZORO_HOME/watchtowers/driver-1"; chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/driver-1"
  printf '%s\n' '{"driver_id":"driver-1","harness":"pi"}' > "$ROZORO_HOME/watchtowers/driver-1/target.json"; chmod 600 "$ROZORO_HOME/watchtowers/driver-1/target.json"
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
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" reconcile --driver driver-1 --json
  assert_success; [ "$(jq -r .acknowledged_generation <<<"$output")" = "$gen" ]; [ "$(jq '.reports|length' <<<"$output")" = 0 ]
}

@test "legacy pending ledger refuses opt-in and explicit fallback remains available" {
  seed_task
  printf '%s\n' '{"generation":2,"delivered":1,"tasks":{}}' > "$ROZORO_HOME/watchtowers/driver-1/pending.json"
  printf '1\n' > "$ROZORO_HOME/watchtowers/driver-1/ack"; chmod 600 "$ROZORO_HOME/watchtowers/driver-1/pending.json" "$ROZORO_HOME/watchtowers/driver-1/ack"
  start_monitor
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_failure; assert_output_contains 'Reconcile legacy state first'
  run env ROZORO_EVENT_BUS=1 ROZORO_EVENT_BUS_FALLBACK=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_success; [ "$(jq -r .availability_source <<<"$output")" = legacy-v2 ]
}

@test "reconcile refuses an unconfirmed offer and never manufactures delivery" {
  seed_task
  PYTHONPATH="$REPO_ROOT/lib" python3 - <<'PY'
import os
from rozoro_monitor.store import EventStore
s=EventStore(os.path.join(os.environ['ROZORO_HOME'],'monitor.db'))
s._connection.execute("UPDATE delivery_offers SET confirmed=0")
s._connection.commit(); s.close()
PY
  start_monitor
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" reconcile --driver driver-1 --json
  assert_failure
  [ "$(python3 - <<'PY'
import os,sqlite3
print(sqlite3.connect(os.path.join(os.environ['ROZORO_HOME'],'monitor.db')).execute('select acked_generation from watchtower_deliveries').fetchone()[0])
PY
)" = 0 ]
}

@test "caller-visible render failure leaves exact delivered generation unacked for duplicate retry" {
  seed_task; start_monitor
  run bash -o pipefail -c 'ROZORO_EVENT_BUS=1 "$1/bin/rozoro" reconcile --driver driver-1 --json | (exit 0)' _ "$REPO_ROOT"
  assert_failure
  [ "$(python3 - <<'PY'
import os,sqlite3
print(sqlite3.connect(os.path.join(os.environ['ROZORO_HOME'],'monitor.db')).execute('select acked_generation from watchtower_deliveries').fetchone()[0])
PY
)" = 0 ]
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" reconcile --driver driver-1 --json
  assert_success; [ "$(jq '.reports|length' <<<"$output")" = 1 ]
}

@test "reconcile N renders frozen fields and does not leak mutable handoff or N plus one" {
  seed_task
  write_handoff task-1 '## turn 99 — changed' 'verdict:       failed' 'reason:        newer' 'did:           changed' 'pending:       later' 'inputs-needed: none' 'artifacts:     newer'
  start_monitor
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" reconcile --driver driver-1 --json
  assert_success
  [ "$(jq -r '.reports[0].heading' <<<"$output")" = 'turn 1 — done' ]
  [ "$(jq -r '.reports[0].verdict' <<<"$output")" = done ]
  [ "$(jq -r '.reports[0].reason' <<<"$output")" = '' ]
}

@test "legacy boundary fails closed on malformed ledger evidence" {
  seed_task; printf '{bad' > "$ROZORO_HOME/watchtowers/driver-1/pending.json"; chmod 600 "$ROZORO_HOME/watchtowers/driver-1/pending.json"; start_monitor
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_failure; assert_output_contains 'malformed legacy pending ledger'
}

@test "bridge rejects unsafe home and fake socket entries" {
  seed_task; chmod 755 "$ROZORO_HOME"
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_failure; assert_output_contains 'unsafe ROZORO_HOME'
  chmod 700 "$ROZORO_HOME"; : > "$ROZORO_HOME/monitor.sock"; chmod 600 "$ROZORO_HOME/monitor.sock"
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_failure; assert_output_contains 'unsafe event-bus socket'
}

@test "CLI reconcile does not replace the live adapter registration epoch" {
  seed_task; start_monitor
  before="$(python3 - <<'PY'
import os,sqlite3
print(sqlite3.connect(os.path.join(os.environ['ROZORO_HOME'],'monitor.db')).execute('select registration_epoch from watchtower_registrations').fetchone()[0])
PY
)"
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" reconcile --driver driver-1 --json; assert_success
  after="$(python3 - <<'PY'
import os,sqlite3
print(sqlite3.connect(os.path.join(os.environ['ROZORO_HOME'],'monitor.db')).execute('select registration_epoch from watchtower_registrations').fetchone()[0])
PY
)"
  [ "$before" = "$after" ]
}

@test "daemon-down opt-in diagnoses failure and does not silently fallback" {
  seed_task
  run env ROZORO_EVENT_BUS=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_failure; assert_output_contains 'event-bus daemon unavailable'
  run env ROZORO_EVENT_BUS=1 ROZORO_EVENT_BUS_FALLBACK=1 "$REPO_ROOT/bin/rozoro" status task-1 --json
  assert_success
}
