#!/usr/bin/env bash
# Acknowledge canonical handoff blocks without rewriting the append-only log.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"
[ $# -ge 1 ] || rzr_die "usage: rzr-ack.sh <id> [--through <n>]"
ID="$1"; shift; THROUGH=""
while [ $# -gt 0 ]; do case "$1" in --through) [ $# -ge 2 ] || rzr_die "--through needs a value"; THROUGH="$2"; shift 2;; -h|--help) sed -n '2,10p' "$0"; exit 0;; *) rzr_die "unknown arg: $1";; esac; done
FOLDER="$(rzr_task_dir "$ID")"; HF="$FOLDER/handoff.md"; [ -f "$HF" ] || rzr_die "no task folder for '$ID'"
result=$(python3 "$RZR_BIN/rzr-handoff.py" "$HF" --acked-v2 "$FOLDER/.acked-blocks-v2" --acked-legacy "$FOLDER/.acked-blocks")
COUNT=$(printf '%s' "$result" | jq -r .blocks)
if [ -n "$THROUGH" ]; then case "$THROUGH" in *[!0-9]*|'') rzr_die "--through wants a non-negative integer";; esac; TARGET="$THROUGH"; else TARGET="$COUNT"; fi
[ "$TARGET" -le "$COUNT" ] || rzr_die "--through $TARGET exceeds canonical block count ($COUNT)"
# Refuse to advance from an unsafe cursor.
printf '%s' "$result" | jq -e '.protocol_errors | map(select(test("acknowledgement cursor"))) | length == 0' >/dev/null || rzr_die "unsafe acknowledgement cursor"
LEGACY=$(printf '%s' "$result" | jq -r --argjson n "$TARGET" 'if $n==0 then 0 else .block_details[$n-1].legacy_index end')
for pair in ".acked-blocks-v2:$TARGET" ".acked-blocks:$LEGACY"; do name=${pair%%:*}; value=${pair#*:}; tmp="$FOLDER/$name.tmp.$$"; printf '%s\n' "$value" > "$tmp"; mv "$tmp" "$FOLDER/$name"; done
echo "rzr: acked '$ID' through canonical block $TARGET/$COUNT"
