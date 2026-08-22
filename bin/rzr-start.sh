#!/usr/bin/env bash
# rzr-start.sh - render + spawn + link a task in one unskippable command.
#
# Usage:
#   rzr-start.sh <display-name> --body <file> --cwd <dir> [rzr-spawn flags...]
#
# The blessed way to begin a task, so linking can never be forgotten:
#   1. rzr-render.sh  -> persist tasks/<id>/brief.md (with handoff protocol + marker)
#   2. rzr-spawn.sh   -> spawn the crew with that brief
#   3. rzr-link.sh    -> capture the session (bounded retry for the crew to boot)
# Any flag other than --body is passed straight through to rzr-spawn.sh.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-start.sh <display-name> --body <file> --cwd dir [rzr-spawn flags]"
DISPLAY="$1"; shift
BODY=""; CWD=""; PASS=(); NO_AGENT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --body) [ $# -ge 2 ] || rzr_die "--body <file> required"; BODY="$2"; shift 2 ;;
    --cwd)  [ $# -ge 2 ] || rzr_die "--cwd <dir> required"; CWD="$2"; PASS+=(--cwd "$2"); shift 2 ;;
    --no-agent) NO_AGENT=1; PASS+=("$1"); shift ;;
    *)      PASS+=("$1"); shift ;;
  esac
done
[ -n "$BODY" ] || rzr_die "--body <file> required"
[ -n "$CWD" ] || rzr_die "--cwd <dir> required for a fresh task"
CWD="$(cd "$CWD" && pwd)" || rzr_die "bad --cwd"
rzr_validate_task_component "$DISPLAY" "display name"

# Allocate before render: every start owns a new durable folder even when its
# display name is already live, was used before, or is started concurrently.
ID="$(rzr_task_reserve "$DISPLAY" "$CWD")"
echo "rzr-start: task key -> $ID"

BRIEF="$("$RZR_BIN/rzr-render.sh" "$ID" "$BODY")"
echo "rzr-start: brief -> $BRIEF"
"$RZR_BIN/rzr-spawn.sh" "$ID" --label "$DISPLAY" --brief "$BRIEF" "${PASS[@]}"

[ "$NO_AGENT" -eq 1 ] && exit 0

# The session .jsonl appears a beat after the prompt is delivered; retry briefly.
for _ in $(seq 1 20); do
  if "$RZR_BIN/rzr-link.sh" "$ID" "$CWD" 2>/dev/null; then exit 0; fi
  sleep 0.5
done
echo "rzr-start: '$ID' spawned but session not linked yet — the watch step links it" \
     "on first sense, or run: ./bin/rozoro link $ID $CWD" >&2
exit 0
