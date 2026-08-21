#!/usr/bin/env bash
# fl-start.sh - render + spawn + link a task in one unskippable command.
#
# Usage:
#   fl-start.sh <id> --body <file> [--cwd <dir>] [fl-spawn flags...]
#
# The blessed way to begin a task, so linking can never be forgotten:
#   1. fl-render.sh  -> persist tasks/<id>/brief.md (with handoff protocol + marker)
#   2. fl-spawn.sh   -> spawn the crew with that brief
#   3. fl-link.sh    -> capture the session (bounded retry for the crew to boot)
# Any flag other than --body is passed straight through to fl-spawn.sh.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

[ $# -ge 1 ] || fl_die "usage: fl-start.sh <id> --body <file> [--cwd dir] [fl-spawn flags]"
ID="$1"; shift
BODY=""; CWD="$PWD"; PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --body) BODY="$2"; shift 2 ;;
    --cwd)  CWD="$2"; PASS+=(--cwd "$2"); shift 2 ;;
    *)      PASS+=("$1"); shift ;;
  esac
done
[ -n "$BODY" ] || fl_die "--body <file> required"
CWD="$(cd "$CWD" && pwd)" || fl_die "bad --cwd"

BRIEF="$("$FL_BIN/fl-render.sh" "$ID" "$BODY")"
echo "fl-start: brief -> $BRIEF"
"$FL_BIN/fl-spawn.sh" "$ID" --brief "$BRIEF" "${PASS[@]}"

# The session .jsonl appears a beat after the prompt is delivered; retry briefly.
for _ in $(seq 1 20); do
  if "$FL_BIN/fl-link.sh" "$ID" "$CWD" 2>/dev/null; then exit 0; fi
  sleep 0.5
done
echo "fl-start: '$ID' spawned but session not linked yet — the watch step links it" \
     "on first sense, or run: fl-link.sh $ID $CWD" >&2
exit 0
