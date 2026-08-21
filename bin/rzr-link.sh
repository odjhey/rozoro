#!/usr/bin/env bash
# rzr-link.sh - link a task to its Claude session for last-resort resume.
#
# Usage:
#   rzr-link.sh <id> <cwd>             write tasks/<id>/session.json
#
# Finds the crew's transcript by grepping the cwd's Claude projects dir for the
# unique `rozoro-task: <id>` marker rzr-render put in the brief (concurrency-safe:
# no reliance on "newest file", which breaks when crews share a cwd). Idempotent
# — a no-op once a valid link exists — so the watch step can call it freely.
# Run a few seconds after rzr-spawn (the crew must have received the brief).
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 2 ] || rzr_die "usage: rzr-link.sh <id> <cwd>"
ID="$1"; CWD="$(cd "$2" && pwd)" || rzr_die "bad cwd '$2'"
FOLDER="$(rzr_task_dir "$ID")"
mkdir -p "$FOLDER"
OUT="$FOLDER/session.json"

# idempotent: a valid link already captured -> nothing to do.
if [ -s "$OUT" ] && python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("session_id") else 1)' "$OUT" 2>/dev/null; then
  echo "rzr-link: $ID already linked ($(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$OUT"))"
  exit 0
fi

# Claude stores sessions under ~/.claude/projects/<cwd with / and . -> ->.
SLUG="$(printf '%s' "$CWD" | sed 's/[/.]/-/g')"
PROJ="$HOME/.claude/projects/$SLUG"
[ -d "$PROJ" ] || rzr_die "no Claude projects dir $PROJ"

match="$(grep -l "rozoro-task: $ID\b" "$PROJ"/*.jsonl 2>/dev/null | head -1 || true)"
[ -n "$match" ] || { echo "rzr-link: no session yet for '$ID' in $PROJ (retry in a few s)" >&2; exit 2; }

uuid="$(basename "$match" .jsonl)"
RZR_OUT="$OUT" RZR_ID="$ID" RZR_CWD="$CWD" RZR_UUID="$uuid" RZR_PATH="$match" python3 - <<'PY'
import json, os
json.dump({"id": os.environ["RZR_ID"], "harness": "claude", "cwd": os.environ["RZR_CWD"],
           "session_id": os.environ["RZR_UUID"], "session_path": os.environ["RZR_PATH"],
           "resume": "claude --resume " + os.environ["RZR_UUID"]},
          open(os.environ["RZR_OUT"], "w"), indent=2)
PY
echo "rzr-link: $ID -> $uuid  (resume: claude --resume $uuid)"
