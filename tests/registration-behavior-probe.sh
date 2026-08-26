#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/rzr-registration-behavior.XXXXXX")"
pids=""
cleanup() { for pid in $pids; do kill "$pid" 2>/dev/null || true; done; "$ROOT/bin/rzr-monitor.sh" stop >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT
tmp="$(cd "$tmp" && pwd)"
export HOME="$tmp/home" ROZORO_HOME="$tmp/rozoro" RZR_HOME="$tmp/rozoro"
export FAKE_HERDR_ROOT="$tmp/herdr" FAKE_HERDR_LOG="$tmp/herdr/argv.log" PYTHONPYCACHEPREFIX="$tmp/pycache"
export PATH="$ROOT/tests/fakes:$ROOT/bin:$PATH"
unset PI_CODING_AGENT_DIR PI_CODING_AGENT_SESSION_DIR
mkdir -p "$HOME" "$ROZORO_HOME/state" "$ROZORO_HOME/tasks" "$FAKE_HERDR_ROOT"; chmod 700 "$ROZORO_HOME"
: > "$FAKE_HERDR_LOG"
make_target() { mkdir -p "$ROZORO_HOME/watchtowers/$1"; chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/$1"; printf '%s\n' "$2" > "$ROZORO_HOME/watchtowers/$1/target.json"; chmod 600 "$ROZORO_HOME/watchtowers/$1/target.json"; }
link_case() {
  id="$1" policy="$2" preset="$3" target="$ROZORO_HOME/watchtowers/driver/target.json"
  if [ -n "$preset" ]; then
    json="{\"schema\":1,\"registration_id\":\"$id-id\",\"driver_id\":\"driver\",\"identity\":\"dispatch-pane\",\"watchtower_name\":\"north\",\"policy_sha256\":\"$policy\",\"preset\":{\"name\":\"$preset\",\"version\":\"3\",\"sha256\":\"preset-sha\",\"policy_sha256\":\"$policy\"}}"
  else
    json="{\"schema\":1,\"registration_id\":\"$id-id\",\"driver_id\":\"driver\",\"identity\":\"dispatch-pane\",\"watchtower_name\":\"north\",\"policy_sha256\":\"$policy\"}"
  fi
  printf '%s\n' "$json" > "$target"; chmod 600 "$target"
  HERDR_PANE_ID=dispatch-pane ROZORO_WT_DRIVER=driver rzr-spawn.sh "$id" --cwd "$tmp" --harness pi --no-agent >/dev/null
  meta="$ROZORO_HOME/state/$id.meta"; test "$(sed -n 's/^dispatcher_policy_sha=//p' "$meta")" = "$policy"
  uuid="$(sed -n 's/^session=//p' "$meta")"; store="$HOME/.pi/agent/sessions/probe"; mkdir -p "$store"
  printf '{"type":"session","version":3,"id":"%s","cwd":"%s"}\n' "$uuid" "$tmp" > "$store/$id.jsonl"
  rzr-link.sh "$id" "$tmp" >/dev/null; rzr-link.sh "$id" "$tmp" >/dev/null
  descriptor="$ROZORO_HOME/tasks/$id/session.json"; test "$(jq -r .dispatcher.policy_sha256 "$descriptor")" = "$policy"; test "$(jq -r .dispatcher.preset "$descriptor")" = "$preset"
}
mkdir -p "$ROZORO_HOME/watchtowers/driver"; chmod 700 "$ROZORO_HOME/watchtowers" "$ROZORO_HOME/watchtowers/driver"
link_case unpreset unpreset-policy ""
link_case preset preset-policy luna
make_target one '{"schema":1,"registration_id":"one-id","driver_id":"one","identity":"ambiguous-pane"}'
make_target two '{"schema":1,"registration_id":"two-id","driver_id":"two","identity":"ambiguous-pane"}'
HERDR_PANE_ID=ambiguous-pane rzr-spawn.sh ambiguous --cwd "$tmp" --no-agent >/dev/null
if grep -q '^dispatcher_' "$ROZORO_HOME/state/ambiguous.meta"; then exit 1; fi

export HERDR_PANE_ID=register-pane
printf 'idle\n' > "$FAKE_HERDR_ROOT/status.register-pane"; printf 'pi\n' > "$FAKE_HERDR_ROOT/kind.register-pane"; printf 'true\n' > "$FAKE_HERDR_ROOT/ready.register-pane"
rzr-register.sh --harness pi --quiet
driver="$ROZORO_HOME/watchtowers/herdr-register-pane"; target="$driver/target.json"; history="$driver/registrations.jsonl"
jq '.registration_id="crash-gap-id"' "$target" > "$target.tmp"; mv "$target.tmp" "$target"; chmod 600 "$target"
rzr-register.sh --harness pi --quiet; rzr-register.sh --harness pi --quiet
test "$(jq -r 'select(.registration_id == "crash-gap-id" and .recovered == true) | .registration_id' "$history" | wc -l | tr -d ' ')" = 1
test "$(jq -r .registration_id "$target")" = "$(tail -n 1 "$history" | jq -r .registration_id)"
printf 'unrelated\n' > "$driver/.target.predictable.tmp"; cp "$target" "$tmp/target.before"; cp "$history" "$tmp/history.before"
mkdir "$tmp/intercept"; cat > "$tmp/intercept/sitecustomize.py" <<'PY'
import os
original = os.replace
def fail(src, dst, *args, **kwargs):
    if dst == "target.json" and isinstance(src, str) and src.startswith(".target."):
        raise OSError("probe commit failure")
    return original(src, dst, *args, **kwargs)
os.replace = fail
PY
if PYTHONPATH="$tmp/intercept" rzr-register.sh --harness pi --quiet; then exit 1; fi
cmp "$target" "$tmp/target.before"; cmp "$history" "$tmp/history.before"; test "$(cat "$driver/.target.predictable.tmp")" = unrelated
test -z "$(find "$driver" -name '.target.*.tmp' ! -name '.target.predictable.tmp' -print -quit)"

rm -f "$driver/.registration.lock"; mkfifo "$driver/.registration.lock"; chmod 600 "$driver/.registration.lock"
rzr-register.sh --harness pi --quiet >"$tmp/fifo.out" 2>&1 & pid=$!; pids="$pids $pid"
for _ in $(seq 1 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
if kill -0 "$pid" 2>/dev/null; then echo 'FIFO probe hung' >&2; exit 1; fi
if wait "$pid"; then echo 'FIFO probe unexpectedly succeeded' >&2; exit 1; fi
printf 'registration behavior probe: PASS\n'
