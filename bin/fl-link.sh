#!/usr/bin/env bash
# fl-link.sh - link a task to its Claude session for last-resort resume.
#
# Usage:
#   fl-link.sh <id> <cwd>             write tasks/<id>/session.json
#
# Finds the crew's transcript by grepping the cwd's Claude projects dir for the
# unique `rozoro-task: <id>` marker fl-render put in the brief (concurrency-safe:
# no reliance on "newest file", which breaks when crews share a cwd). Idempotent
# — a no-op once a valid link exists — so the watch step can call it freely.
# Run a few seconds after fl-spawn (the crew must have received the brief).
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

[ $# -ge 2 ] || fl_die "usage: fl-link.sh <id> <cwd>"
ID="$1"; CWD="$(cd "$2" && pwd)" || fl_die "bad cwd '$2'"
FOLDER="$(fl_task_dir "$ID")"
mkdir -p "$FOLDER"
OUT="$FOLDER/session.json"

# idempotent: a valid link already captured -> nothing to do.
if [ -s "$OUT" ] && python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("session_id") else 1)' "$OUT" 2>/dev/null; then
  echo "fl-link: $ID already linked ($(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$OUT"))"
  exit 0
fi

# Claude stores sessions under ~/.claude/projects/<cwd with / and . -> ->.
SLUG="$(printf '%s' "$CWD" | sed 's/[/.]/-/g')"
PROJ="$HOME/.claude/projects/$SLUG"
[ -d "$PROJ" ] || fl_die "no Claude projects dir $PROJ"

match="$(grep -l "rozoro-task: $ID\b" "$PROJ"/*.jsonl 2>/dev/null | head -1 || true)"
[ -n "$match" ] || { echo "fl-link: no session yet for '$ID' in $PROJ (retry in a few s)" >&2; exit 2; }

uuid="$(basename "$match" .jsonl)"
FL_OUT="$OUT" FL_ID="$ID" FL_CWD="$CWD" FL_UUID="$uuid" FL_PATH="$match" python3 - <<'PY'
import json, os
json.dump({"id": os.environ["FL_ID"], "harness": "claude", "cwd": os.environ["FL_CWD"],
           "session_id": os.environ["FL_UUID"], "session_path": os.environ["FL_PATH"],
           "resume": "claude --resume " + os.environ["FL_UUID"]},
          open(os.environ["FL_OUT"], "w"), indent=2)
PY
echo "fl-link: $ID -> $uuid  (resume: claude --resume $uuid)"
