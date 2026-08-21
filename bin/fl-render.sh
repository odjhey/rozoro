#!/usr/bin/env bash
# fl-render.sh - render a task's persistent brief from the handoff template.
#
# Usage:
#   fl-render.sh <id> <body-file>     write tasks/<id>/brief.md, print its path
#
# Wraps the task body in templates/brief.md, adding the handoff protocol and a
# unique `rozoro-task: <id>` marker. The brief thus persists at a predictable
# path (survives teardown) and carries the marker fl-link greps to find the
# session. Feed the printed path to `fl-spawn.sh <id> --brief <path>`.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

[ $# -ge 2 ] || fl_die "usage: fl-render.sh <id> <body-file>"
ID="$1"; BODY_FILE="$2"
TEMPLATE="$FL_TEMPLATES/brief.md"
[ -f "$TEMPLATE" ]  || fl_die "no template at $TEMPLATE"
[ -f "$BODY_FILE" ] || fl_die "no body file at $BODY_FILE"

FOLDER="$(fl_task_dir "$ID")"
mkdir -p "$FOLDER"
touch "$FOLDER/handoff.md"          # exists from the start so a watcher can tail it

FL_TMPL="$TEMPLATE" FL_ID="$ID" FL_FOLDER="$FOLDER" \
FL_BODY_FILE="$BODY_FILE" FL_OUT="$FOLDER/brief.md" python3 - <<'PY'
import os
tmpl = open(os.environ["FL_TMPL"]).read()
body = open(os.environ["FL_BODY_FILE"]).read()
open(os.environ["FL_OUT"], "w").write(
    tmpl.replace("{{ID}}", os.environ["FL_ID"])
        .replace("{{FOLDER}}", os.environ["FL_FOLDER"])
        .replace("{{BODY}}", body))
PY

echo "$FOLDER/brief.md"
