#!/usr/bin/env bash
# Opt-in, cost-incurring real Copilot/Herdr lifecycle smoke test.
set -euo pipefail
[ "${RZR_LIVE_COPILOT:-0}" = 1 ] || { echo 'SKIP: set RZR_LIVE_COPILOT=1 (uses paid Copilot requests)' >&2; exit 77; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
command -v copilot >/dev/null && command -v herdr >/dev/null || { echo 'copilot and herdr are required (run copilot login first)' >&2; exit 1; }
copilot --version; herdr --version
TMP="$(mktemp -d)"; export ROZORO_HOME="$TMP/home"; mkdir -p "$TMP/work"
ID=""; cleanup() { [ -z "$ID" ] || "$ROOT/bin/rozoro" teardown "$ID" --force >/dev/null 2>&1 || true; rm -rf "$TMP"; }; trap cleanup EXIT INT TERM
printf 'Reply COPILOT_LIVE_ONE and append the required done handoff.\n' > "$TMP/body"
out="$("$ROOT/bin/rozoro" start copilot-live --harness copilot --model "${RZR_LIVE_COPILOT_MODEL:-auto}" --body "$TMP/body" --cwd "$TMP/work")"
ID="$(printf '%s\n' "$out" | sed -n "s/.*task '\([^']*\)'.*/\1/p" | head -1)"; [ -n "$ID" ]
for _ in $(seq 1 120); do "$ROOT/bin/rozoro" status "$ID" | grep -Eq 'done|needs-action' && break; sleep 1; done
meta="$ROZORO_HOME/state/$ID.meta"; uuid="$(sed -n 's/^session=//p' "$meta")"; [ -n "$uuid" ]; grep -q '^permission_mode=yolo$' "$meta"
"$ROOT/bin/rozoro" link "$ID" "$TMP/work"; [ "$(jq -r .session_id "$ROZORO_HOME/tasks/$ID/session.json")" = "$uuid" ]
"$ROOT/bin/rozoro" send "$ID" 'Reply COPILOT_LIVE_TWO and append the next done handoff.'
for _ in $(seq 1 120); do [ "$(grep -c '^## turn ' "$ROZORO_HOME/tasks/$ID/handoff.md" 2>/dev/null || true)" -ge 2 ] && break; sleep 1; done
[ "$(grep -c '^## turn ' "$ROZORO_HOME/tasks/$ID/handoff.md")" -ge 2 ]
"$ROOT/bin/rozoro" teardown "$ID" --force; "$ROOT/bin/rozoro" resume "$ID" --prompt 'State COPILOT_LIVE_TWO to prove retained context, then append a done handoff.'
echo "PASS: Copilot lifecycle UUID $uuid (synthetic content only)"
