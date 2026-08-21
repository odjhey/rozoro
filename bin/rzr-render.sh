#!/usr/bin/env bash
# rzr-render.sh - render a task's persistent brief from the handoff template.
#
# Usage:
#   rzr-render.sh <id> <body-file>     write tasks/<id>/brief.md, print its path
#
# Wraps the task body in templates/brief.md, adding the handoff protocol and a
# unique `rozoro-task: <id>` marker. The brief thus persists at a predictable
# path (survives teardown) and carries the marker rzr-link greps to find the
# session. Feed the printed path to `rzr-spawn.sh <id> --brief <path>`.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 2 ] || rzr_die "usage: rzr-render.sh <id> <body-file>"
ID="$1"; BODY_FILE="$2"
TEMPLATE="$RZR_TEMPLATES/brief.md"
[ -f "$TEMPLATE" ]  || rzr_die "no template at $TEMPLATE"
[ -f "$BODY_FILE" ] || rzr_die "no body file at $BODY_FILE"

FOLDER="$(rzr_task_dir "$ID")"
mkdir -p "$FOLDER"
touch "$FOLDER/handoff.md"          # exists from the start so a watcher can tail it

RZR_TMPL="$TEMPLATE" RZR_ID="$ID" RZR_FOLDER="$FOLDER" \
RZR_BODY_FILE="$BODY_FILE" RZR_OUT="$FOLDER/brief.md" python3 - <<'PY'
import os
tmpl = open(os.environ["RZR_TMPL"]).read()
body = open(os.environ["RZR_BODY_FILE"]).read()
open(os.environ["RZR_OUT"], "w").write(
    tmpl.replace("{{ID}}", os.environ["RZR_ID"])
        .replace("{{FOLDER}}", os.environ["RZR_FOLDER"])
        .replace("{{BODY}}", body))
PY

echo "$FOLDER/brief.md"
