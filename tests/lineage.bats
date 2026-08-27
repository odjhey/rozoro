#!/usr/bin/env bats
# Tests for rzr-lineage: stitching one agent's communication back together from
# the four durable stores it is scattered across.
load test_helper/common

lineage() { run python3 "$REPO_ROOT/bin/rzr-lineage.py" "$@"; }

# Build a fixture agent: task folder, harness transcript, handoff, attention
# item, and monitor events, all consistent with each other.
fixture() {  # <key> <inbound-count> <block-count> <stop-count>
  local key="$1" inbound="$2" blocks="$3" stops="$4"
  local dir="$ROZORO_HOME/tasks/$key"
  local transcript="$ROZORO_HOME/transcripts/$key.jsonl"
  mkdir -p "$dir" "$ROZORO_HOME/transcripts" "$ROZORO_HOME/watchtowers/attention/items"

  printf '{"schema":1,"task_key":"%s","display_name":"%s"}' "$key" "${key%%--*}" > "$dir/identity.json"
  python3 - "$dir/session.json" "$transcript" <<'PY'
import json, sys
json.dump({"id": "t", "harness": "pi", "cwd": "/w", "session_path": sys.argv[2],
           "resume": "pi --session t",
           "profile": {"harness": "pi", "model": "test-model", "effort": "high"}},
          open(sys.argv[1], "w"))
PY

  : > "$transcript"
  local i
  for ((i = 1; i <= inbound; i++)); do
    python3 - "$transcript" "$i" <<'PY'
import json, sys
rec = {"type": "message", "id": f"m{sys.argv[2]}", "timestamp": f"2026-01-01T00:0{sys.argv[2]}:00.000Z",
       "message": {"role": "user", "content": [{"type": "text", "text": f"prompt number {sys.argv[2]}"}]}}
open(sys.argv[1], "a").write(json.dumps(rec) + "\n")
PY
  done

  : > "$dir/handoff.md"
  for ((i = 1; i <= blocks; i++)); do
    cat >> "$dir/handoff.md" <<EOF
## turn $i — did work $i
verdict:       done
reason:        none
did:           performed step $i
pending:       none
inputs-needed: none
artifacts:     none

EOF
  done

  cat > "$ROZORO_HOME/watchtowers/attention/items/20260101T000500-$key-aaaa.md" <<EOF
---
schema: rozoro.watchtower-attention-ledger/v1
id: 20260101T000500-$key-aaaa
task: $key
reason: quiescent
priority: urgent
status: handled
---
# Routed the fixture agent

## Snapshot

Fixture snapshot.

## Handling log

- 2026-01-01T00:05:00Z new->open: created via reconcile
- 2026-01-01T00:06:00Z open->handled: dispatched the follow-on crew
EOF

  python3 - "$ROZORO_HOME/monitor.db" "$key" "$stops" <<'PY'
import sqlite3, sys, json
db = sqlite3.connect(sys.argv[1])
db.execute("CREATE TABLE IF NOT EXISTS events (durable_seq INTEGER PRIMARY KEY AUTOINCREMENT,"
           " event_id TEXT NOT NULL UNIQUE, session_id TEXT NOT NULL, task_id TEXT, driver_id TEXT,"
           " event_type TEXT NOT NULL, payload_json TEXT NOT NULL, received_at TEXT NOT NULL)")
for i in range(1, int(sys.argv[3]) + 1):
    for kind in ("turn.start", "turn.stop"):
        db.execute("INSERT INTO events (event_id, session_id, task_id, event_type, payload_json, received_at)"
                   " VALUES (?,?,?,?,?,?)",
                   (f"{sys.argv[2]}-{i}-{kind}", "s", sys.argv[2], kind,
                    json.dumps({"turn_id": f"turn-{i}"}), f"2026-01-01T00:0{i}:3{0 if kind=='turn.start' else 5}.000Z"))
db.commit()
PY
}

@test "lineage interleaves prompts, reports, turns and watchtower decisions in time order" {
  fixture agent-a--01AAAA 2 2 2
  lineage agent-a--01AAAA
  assert_success
  assert_output_contains "DISPATCH"
  assert_output_contains "prompt number 2"
  assert_output_contains "report #1 [done]"
  assert_output_contains "watchtower open->handled"
  assert_output_contains "dispatched the follow-on crew"

  # The dispatch prompt must precede the first report, which must precede the
  # decision the watchtower took after reading it.
  run bash -c "python3 \"$REPO_ROOT/bin/rzr-lineage.py\" agent-a--01AAAA \
    | grep -n 'DISPATCH\|report #1\|open->handled' | cut -d: -f1 | tr '\n' ' '"
  assert_success
  first=$(echo "$output" | awk '{print $1}')
  second=$(echo "$output" | awk '{print $2}')
  third=$(echo "$output" | awk '{print $3}')
  [ "$first" -lt "$second" ]
  [ "$second" -lt "$third" ]
}

@test "handoff blocks are anchored to turn boundaries and marked inferred" {
  fixture agent-b--01BBBB 1 1 1
  lineage agent-b--01BBBB
  assert_success
  # '~' immediately before the outbound marker flags a derived timestamp.
  assert_output_contains "~→ report #1"
}

@test "a prompt that produced no report is reported as drift" {
  fixture agent-c--01CCCC 3 1 1
  lineage agent-c--01CCCC
  assert_success
  assert_output_contains "! drift"
}

@test "aligned counts do not raise drift" {
  fixture agent-d--01DDDD 2 2 2
  lineage agent-d--01DDDD
  assert_success
  run bash -c "python3 \"$REPO_ROOT/bin/rzr-lineage.py\" agent-d--01DDDD | grep -c 'drift' || true"
  [ "$output" = 0 ]
}

@test "an unrecoverable transcript is called out rather than silently empty" {
  fixture agent-e--01EEEE 1 1 1
  rm "$ROZORO_HOME/transcripts/agent-e--01EEEE.jsonl"
  lineage agent-e--01EEEE
  assert_success
  assert_output_contains "transcript missing"
}

@test "invalid handoff blocks surface the protocol error inline" {
  fixture agent-f--01FFFF 1 1 1
  printf '## turn 2 — malformed\nverdict:       done\nreason:        none\npending:       none\ninputs-needed: none\nartifacts:     none\n' \
    >> "$ROZORO_HOME/tasks/agent-f--01FFFF/handoff.md"
  lineage agent-f--01FFFF
  assert_success
  assert_output_contains "INVALID: missing field: did"
}

@test "reports are marked acked only up to the durable ack watermark" {
  fixture agent-g--01GGGG 2 2 2
  printf '1\n' > "$ROZORO_HOME/tasks/agent-g--01GGGG/.acked-blocks-v2"
  lineage agent-g--01GGGG
  assert_success
  assert_output_contains "report #1 [done] (acked)"
  assert_output_contains "report #2 [done] (unacked)"
}

@test "a task is addressable by unique prefix and ambiguity is refused" {
  fixture agent-h--01HHHH 1 1 1
  fixture agent-hh--01HHHJ 1 1 1
  lineage agent-hh
  assert_success
  lineage agent-h
  [ "$status" -ne 0 ]
  assert_output_contains "matches 2 tasks"
}

@test "the index counts every agent and flags the drifting ones" {
  fixture agent-i--01IIII 1 1 1
  fixture agent-j--01JJJJ 4 1 1
  lineage
  assert_success
  assert_output_contains "agent-i--01IIII"
  assert_output_contains "agent-j--01JJJJ"

  lineage --drift
  assert_success
  assert_output_contains "agent-j--01JJJJ"
  run bash -c "python3 \"$REPO_ROOT/bin/rzr-lineage.py\" --drift | grep -c 'agent-i--01IIII' || true"
  [ "$output" = 0 ]
}

@test "json output carries the same events as the rendered timeline" {
  fixture agent-k--01KKKK 2 2 2
  run bash -c "python3 \"$REPO_ROOT/bin/rzr-lineage.py\" agent-k--01KKKK --json"
  assert_success
  run bash -c "python3 \"$REPO_ROOT/bin/rzr-lineage.py\" agent-k--01KKKK --json | python3 -c '
import json, sys
d = json.load(sys.stdin)
kinds = [e[\"kind\"] for e in d[\"events\"]]
assert d[\"counts\"] == {\"inbound\": 2, \"blocks\": 2, \"turns\": 2, \"attention\": 1, \"compactions\": 0}, d[\"counts\"]
assert d[\"drift\"] is False
assert kinds.count(\"out\") == 2 and kinds.count(\"attn\") == 2 and \"dispatch\" in kinds
print(\"ok\")'"
  assert_success
  assert_output_contains ok
}

@test "lineage reads the stores without mutating them" {
  fixture agent-l--01LLLL 2 2 2
  before="$(directory_snapshot "$ROZORO_HOME/tasks")"
  lineage agent-l--01LLLL
  assert_success
  [ "$(directory_snapshot "$ROZORO_HOME/tasks")" = "$before" ]
}
