#!/usr/bin/env bash
# rzr-ack.sh - mark a task's handoff open items resolved up to a point.
#
# Usage:
#   rzr-ack.sh <id> [--through <n>]
#     <id>         a task with a tasks/<id>/handoff.md
#     --through N  resolve through block N (default: the current last block)
#
# The explicit-resolution half of leak-proof status. rzr-status surfaces EVERY
# handoff block whose verdict is needs-action|blocked|failed (or whose
# inputs-needed is set) as an OPEN item, and keeps surfacing it — regardless of
# later `done` blocks or repeated status reads — until you ack it here. Ack
# records a cursor (tasks/<id>/.acked-blocks = block index) that status treats as
# "resolved through this block"; only blocks AFTER the cursor stay open.
#
# Run this once you've actually handled the open items (answered the crew via
# rzr-send, or decided they're moot). It never touches handoff.md — the log stays
# append-only and honest; ack only moves your own read cursor forward.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-ack.sh <id> [--through <n>]"
ID="$1"; shift
THROUGH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --through) THROUGH="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) rzr_die "unknown arg: $1" ;;
  esac
done

FOLDER="$(rzr_task_dir "$ID")"
HF="$FOLDER/handoff.md"
[ -f "$HF" ] || rzr_die "no task folder for '$ID' ($HF missing)"

# Count handoff blocks (headings begin with '## '); bash-3.2 safe.
COUNT=$(grep -c '^## ' "$HF" 2>/dev/null || true); COUNT=${COUNT:-0}

if [ -n "$THROUGH" ]; then
  case "$THROUGH" in
    ''|*[!0-9]*) rzr_die "--through wants a non-negative integer, got '$THROUGH'" ;;
  esac
  [ "$THROUGH" -le "$COUNT" ] || rzr_die "--through $THROUGH exceeds block count ($COUNT)"
  TARGET="$THROUGH"
else
  TARGET="$COUNT"
fi

printf '%s\n' "$TARGET" > "$FOLDER/.acked-blocks"
echo "rzr: acked '$ID' through block $TARGET/$COUNT — status will only surface open items after block $TARGET"
