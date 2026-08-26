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
sentinel="$tmp/outside-sentinel"; printf 'unchanged\n' > "$sentinel"
export HERDR_PANE_ID=fifo-pane
printf 'idle\n' > "$FAKE_HERDR_ROOT/status.fifo-pane"; printf 'pi\n' > "$FAKE_HERDR_ROOT/kind.fifo-pane"; printf 'true\n' > "$FAKE_HERDR_ROOT/ready.fifo-pane"
fifo_driver="$ROZORO_HOME/watchtowers/herdr-fifo-pane"; mkdir -p "$fifo_driver"; chmod 700 "$fifo_driver"
mkfifo "$fifo_driver/.registration.lock"; chmod 600 "$fifo_driver/.registration.lock"
rzr-register.sh --harness pi --quiet >"$tmp/fifo.out" 2>&1 & fifo_pid=$!
count=0
while kill -0 "$fifo_pid" 2>/dev/null && [ "$count" -lt 50 ]; do sleep 0.1; count=$((count + 1)); done
if kill -0 "$fifo_pid" 2>/dev/null; then kill "$fifo_pid" 2>/dev/null || true; wait "$fifo_pid" 2>/dev/null || true; echo 'registration lock FIFO hung' >&2; exit 1; fi
if wait "$fifo_pid"; then echo 'registration lock FIFO unexpectedly succeeded' >&2; exit 1; fi
[ ! -e "$fifo_driver/target.json" ] && [ ! -e "$fifo_driver/registrations.jsonl" ]
[ "$(cat "$sentinel")" = unchanged ]
printf 'registration concurrency probe: %s/%s writer pairs and lock-FIFO fail-closed passed\n' "$iterations" "$iterations"
