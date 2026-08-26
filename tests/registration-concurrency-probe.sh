#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
iterations="${1:-20}"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/rzr-registration-probe.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
export HOME="$tmp/home" ROZORO_HOME="$tmp/rozoro" RZR_HOME="$tmp/rozoro"
export FAKE_HERDR_ROOT="$tmp/herdr" FAKE_HERDR_LOG="$tmp/herdr/argv.log" HERDR_PANE_ID=probe-pane PYTHONPYCACHEPREFIX="$tmp/pycache"
mkdir -p "$HOME" "$ROZORO_HOME" "$FAKE_HERDR_ROOT"
chmod 700 "$ROZORO_HOME"
printf 'idle\n' > "$FAKE_HERDR_ROOT/status.probe-pane"
printf 'pi\n' > "$FAKE_HERDR_ROOT/kind.probe-pane"
printf 'true\n' > "$FAKE_HERDR_ROOT/ready.probe-pane"
export PATH="$ROOT/tests/fakes:$ROOT/bin:$PATH"
for iteration in $(seq 1 "$iterations"); do
  ROZORO_WT_NAME="north-$iteration" rzr-register.sh --harness pi --quiet & first=$!
  ROZORO_WT_NAME="south-$iteration" rzr-register.sh --harness pi --quiet & second=$!
  wait "$first"; wait "$second"
done
target="$ROZORO_HOME/watchtowers/herdr-probe-pane/target.json"
history="${target%/target.json}/registrations.jsonl"
python3 - "$target" "$history" "$iterations" <<'PY'
import json, sys
with open(sys.argv[1]) as stream: target = json.load(stream)
with open(sys.argv[2]) as stream: rows = [json.loads(line) for line in stream]
iterations = int(sys.argv[3])
assert len(rows) == iterations * 2
ids = [row["registration_id"] for row in rows]
assert len(ids) == len(set(ids))
assert target["registration_id"] in ids
for iteration in range(1, iterations + 1):
    assert {row["watchtower_name"] for row in rows if row["watchtower_name"] in (f"north-{iteration}", f"south-{iteration}")} == {f"north-{iteration}", f"south-{iteration}"}
PY
printf 'registration concurrency probe: %s/%s writer pairs passed\n' "$iterations" "$iterations"
