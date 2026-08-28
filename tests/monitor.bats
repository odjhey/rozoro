#!/usr/bin/env bats
load test_helper/common

@test "dispatcher monitor status diagnoses down in JSON" {
  run "$REPO_ROOT/bin/rozoro" monitor status --json
  assert_failure
  python3 -c 'import json,sys; v=json.loads(sys.argv[1]); assert v["running"] is False and v["spool_backlog"] == 0' "$output"
}

@test "explicit monitor reset rolls back v5 database state but preserves authoritative task folders" {
  mkdir -p "$ROZORO_HOME/tasks/task-1"
  printf 'authoritative\n' > "$ROZORO_HOME/tasks/task-1/handoff.md"
  chmod 700 "$ROZORO_HOME"
  run "$REPO_ROOT/bin/rozoro" monitor start; assert_success
  run "$REPO_ROOT/bin/rozoro" monitor reset --force; assert_failure
  [ -e "$ROZORO_HOME/monitor.db" ]
  run "$REPO_ROOT/bin/rozoro" monitor stop; assert_success
  [ -e "$ROZORO_HOME/monitor.db" ]
  run "$REPO_ROOT/bin/rozoro" monitor reset; assert_failure
  [ -e "$ROZORO_HOME/monitor.db" ]
  external="$BATS_TEST_TMPDIR/external"; printf sentinel > "$external"
  ln -s "$external" "$ROZORO_HOME/monitor.db-shm"
  run "$REPO_ROOT/bin/rozoro" monitor reset --force; assert_failure
  [ -e "$ROZORO_HOME/monitor.db" ]; [ "$(cat "$external")" = sentinel ]
  rm "$ROZORO_HOME/monitor.db-shm"
  mkdir -p "$ROZORO_HOME/producer-seq" "$ROZORO_HOME/spool"
  chmod 700 "$ROZORO_HOME/producer-seq" "$ROZORO_HOME/spool"
  printf '3' > "$ROZORO_HOME/producer-seq/session.seq"
  printf '{"durable":"event"}' > "$ROZORO_HOME/spool/event.json"
  chmod 600 "$ROZORO_HOME/producer-seq/session.seq" "$ROZORO_HOME/spool/event.json"
  run "$REPO_ROOT/bin/rozoro" monitor reset --force; assert_success
  [ ! -e "$ROZORO_HOME/monitor.db" ]
  [ ! -e "$ROZORO_HOME/monitor.db-wal" ]
  [ ! -e "$ROZORO_HOME/producer-seq" ]
  [ ! -e "$ROZORO_HOME/spool" ]
  [ "$(cat "$ROZORO_HOME/tasks/task-1/handoff.md")" = authoritative ]
  run "$REPO_ROOT/bin/rozoro" monitor start; assert_success
  run "$REPO_ROOT/bin/rozoro" monitor status --json; assert_success
  # A reset database is rebuilt at the current schema, whatever that is now.
  assert_output_contains "\"schema_version\":$(PYTHONPATH="$REPO_ROOT/lib" python3 -c 'from rozoro_monitor.store import SCHEMA_VERSION; print(SCHEMA_VERSION)')"
  run "$REPO_ROOT/bin/rozoro" monitor stop; assert_success
}

@test "dispatcher monitor detached lifecycle becomes healthy and stops proven owner" {
  chmod 700 "$ROZORO_HOME"
  run "$REPO_ROOT/bin/rozoro" monitor start
  assert_success
  run "$REPO_ROOT/bin/rozoro" monitor status --json
  assert_success
  python3 -c 'import json,sys; v=json.loads(sys.argv[1]); assert v["running"] and v["schema_version"] >= 1' "$output"
  run "$REPO_ROOT/bin/rozoro" monitor stop
  assert_success
  run "$REPO_ROOT/bin/rozoro" monitor status --json
  assert_failure
}
