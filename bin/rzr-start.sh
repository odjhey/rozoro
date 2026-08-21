#!/usr/bin/env bash
# rzr-start.sh - render + spawn + link a task in one unskippable command.
#
# Usage:
#   rzr-start.sh <id> --body <file> [--cwd <dir>] [rzr-spawn flags...]
#
# The blessed way to begin a task, so linking can never be forgotten:
#   1. rzr-render.sh  -> persist tasks/<id>/brief.md (with handoff protocol + marker)
#   2. rzr-spawn.sh   -> spawn the crew with that brief
#   3. rzr-link.sh    -> capture the session (bounded retry for the crew to boot)
# Any flag other than --body is passed straight through to rzr-spawn.sh.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-start.sh <id> --body <file> [--cwd dir] [rzr-spawn flags]"
ID="$1"; shift
BODY=""; CWD="$PWD"; PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --body) BODY="$2"; shift 2 ;;
    --cwd)  CWD="$2"; PASS+=(--cwd "$2"); shift 2 ;;
    *)      PASS+=("$1"); shift ;;
  esac
done
[ -n "$BODY" ] || rzr_die "--body <file> required"
CWD="$(cd "$CWD" && pwd)" || rzr_die "bad --cwd"

BRIEF="$("$RZR_BIN/rzr-render.sh" "$ID" "$BODY")"
echo "rzr-start: brief -> $BRIEF"
"$RZR_BIN/rzr-spawn.sh" "$ID" --brief "$BRIEF" "${PASS[@]}"

# The session .jsonl appears a beat after the prompt is delivered; retry briefly.
for _ in $(seq 1 20); do
  if "$RZR_BIN/rzr-link.sh" "$ID" "$CWD" 2>/dev/null; then exit 0; fi
  sleep 0.5
done
echo "rzr-start: '$ID' spawned but session not linked yet — the watch step links it" \
     "on first sense, or run: rzr-link.sh $ID $CWD" >&2
exit 0
