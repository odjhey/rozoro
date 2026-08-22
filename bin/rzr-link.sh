#!/usr/bin/env bash
# rzr-link.sh - link a task to its harness session for last-resort resume.
#
# Usage:
#   rzr-link.sh <id> <cwd>             write tasks/<id>/session.json
#
# Finds the crew's transcript by searching the harness session store for the
# unique `rozoro-task: <id>` marker rzr-render put in the brief (concurrency-safe:
# no reliance on "newest file", which breaks when crews share a cwd). Supports
# Claude, Codex, and Pi. Idempotent — a no-op once a valid link exists — so the watch
# step can call it freely. Run a few seconds after rzr-spawn (the crew must have
# received the brief). Pi uses its native preallocated session UUID, with marker
# discovery retained for sessions created before native linking was added.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 2 ] || rzr_die "usage: rzr-link.sh <id> <cwd>"
ID="$1"; CWD="$(cd "$2" && pwd)" || rzr_die "bad cwd '$2'"
FOLDER="$(rzr_task_dir "$ID")"
mkdir -p "$FOLDER"
OUT="$FOLDER/session.json"
HARNESS="$(rzr_meta_get "$ID" harness || true)"
if [ -z "$HARNESS" ] && [ -s "$OUT" ]; then
  HARNESS="$(jq -r '.harness // empty' "$OUT" 2>/dev/null)"
fi
HARNESS="${HARNESS:-claude}"

# idempotent: a valid link for this harness/cwd already captured -> nothing to do.
if [ -s "$OUT" ] && RZR_EXPECT_HARNESS="$HARNESS" RZR_EXPECT_CWD="$CWD" \
  python3 -c 'import json,os,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("session_id") and d.get("harness") == os.environ["RZR_EXPECT_HARNESS"] and d.get("cwd") == os.environ["RZR_EXPECT_CWD"] else 1)' \
  "$OUT" 2>/dev/null; then
  echo "rzr-link: $ID already linked ($(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$OUT"))"
  exit 0
fi

case "$HARNESS" in
  claude)
    # Claude stores sessions under ~/.claude/projects/<cwd with / and . -> ->.
    SLUG="$(printf '%s' "$CWD" | sed 's/[/.]/-/g')"
    STORE="$HOME/.claude/projects/$SLUG"
    [ -d "$STORE" ] || rzr_die "no Claude projects dir $STORE"
    match="$(grep -l "rozoro-task: $ID\b" "$STORE"/*.jsonl 2>/dev/null | head -1 || true)"
    uuid="${match:+$(basename "$match" .jsonl)}"
    resume="claude --resume $uuid"
    ;;
  codex)
    # Codex stores rollouts in date-partitioned directories. Match the marker,
    # but only inside real user messages, then confirm the session metadata cwd
    # in case an id was reused elsewhere.
    codex_data="${CODEX_HOME:-$HOME/.codex}"
    STORE="$codex_data/sessions"
    [ -d "$STORE" ] || rzr_die "no Codex sessions dir $STORE"
    found="$(RZR_STORE="$STORE" RZR_MARKER="rozoro-task: $ID" RZR_CWD="$CWD" python3 - <<'PY'
import glob, json, os

for path in sorted(glob.glob(os.path.join(os.environ["RZR_STORE"], "**", "*.jsonl"), recursive=True), reverse=True):
    try:
        with open(path) as stream:
            meta = json.loads(next(stream))
            payload = meta.get("payload", {})
            if meta.get("type") != "session_meta" or payload.get("cwd") != os.environ["RZR_CWD"]:
                continue
            for line in stream:
                item = json.loads(line)
                message = item.get("payload", {})
                if item.get("type") != "response_item" or message.get("type") != "message" or message.get("role") != "user":
                    continue
                if any(
                    os.environ["RZR_MARKER"] in part.get("text", "").splitlines()
                    for part in message.get("content", [])
                    if isinstance(part, dict)
                ):
                    print(path + "\t" + payload.get("id", ""))
                    raise SystemExit
    except (OSError, StopIteration, ValueError):
        continue
PY
)"
    match="${found%%$'\t'*}"
    uuid="${found#*$'\t'}"
    [ "$uuid" != "$found" ] || uuid=""
    resume="codex resume $uuid"
    ;;
  pi)
    # Pi accepts a caller-selected UUID at launch, so normally we only need to
    # locate the file whose header confirms that UUID and cwd. For Pi tasks
    # created by older Rozoro versions, fall back to matching the unique marker
    # in a real user message. Respect both documented Pi storage overrides.
    pi_data="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"
    STORE="${PI_CODING_AGENT_SESSION_DIR:-$pi_data/sessions}"
    [ -d "$STORE" ] || rzr_die "no Pi sessions dir $STORE"
    expected="$(rzr_meta_get "$ID" session || true)"
    found="$(RZR_STORE="$STORE" RZR_MARKER="rozoro-task: $ID" RZR_CWD="$CWD" RZR_EXPECTED="$expected" python3 - <<'PY'
import glob, json, os

for path in sorted(glob.glob(os.path.join(os.environ["RZR_STORE"], "**", "*.jsonl"), recursive=True), reverse=True):
    try:
        with open(path) as stream:
            header = json.loads(next(stream))
            if header.get("type") != "session" or header.get("cwd") != os.environ["RZR_CWD"]:
                continue
            session_id = header.get("id", "")
            expected = os.environ["RZR_EXPECTED"]
            if expected:
                if session_id == expected:
                    print(path + "\t" + session_id)
                    raise SystemExit
                continue
            for line in stream:
                item = json.loads(line)
                message = item.get("message", {})
                if item.get("type") != "message" or message.get("role") != "user":
                    continue
                content = message.get("content", "")
                texts = [content] if isinstance(content, str) else [
                    part.get("text", "") for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                if any(os.environ["RZR_MARKER"] in text.splitlines() for text in texts):
                    print(path + "\t" + session_id)
                    raise SystemExit
    except (OSError, StopIteration, ValueError):
        continue
PY
)"
    match="${found%%$'\t'*}"
    uuid="${found#*$'\t'}"
    [ "$uuid" != "$found" ] || uuid=""
    resume="pi --session $uuid"
    ;;
  *) rzr_die "session linking is not supported for harness '$HARNESS'" ;;
esac

[ -n "$match" ] && [ -n "$uuid" ] || {
  echo "rzr-link: no $HARNESS session yet for '$ID' in $STORE (retry in a few s)" >&2
  exit 2
}

RZR_OUT="$OUT" RZR_ID="$ID" RZR_HARNESS="$HARNESS" RZR_CWD="$CWD" \
RZR_UUID="$uuid" RZR_PATH="$match" RZR_RESUME="$resume" python3 - <<'PY'
import json, os
json.dump({"id": os.environ["RZR_ID"], "harness": os.environ["RZR_HARNESS"], "cwd": os.environ["RZR_CWD"],
           "session_id": os.environ["RZR_UUID"], "session_path": os.environ["RZR_PATH"],
           "resume": os.environ["RZR_RESUME"]},
          open(os.environ["RZR_OUT"], "w"), indent=2)
PY
echo "rzr-link: $ID -> $uuid  (resume: $resume)"
