#!/usr/bin/env bash
# rzr-render.sh - render a task's persistent brief from the handoff template.
#
# Usage:
#   rzr-render.sh <id> <body-file>     write tasks/<id>/brief.md, print its path
#
# Wraps the task body in templates/brief.md with a unique `rozoro-task: <id>`
# marker, and separately renders templates/handoff.md -> handoff-protocol.md (the
# handoff protocol, with {{FOLDER}} filled in). The brief carries ONLY the marker
# rzr-link greps for plus the verbatim body; rzr-spawn delivers the handoff
# protocol through the harness's available channel. Both files persist at
# predictable paths (survive teardown). Feed the printed brief path to
# `rzr-spawn.sh <id> --brief <path>`.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 2 ] || rzr_die "usage: rzr-render.sh <id> <body-file>"
ID="$1"; BODY_FILE="$2"
TEMPLATE="$RZR_TEMPLATES/brief.md"
HANDOFF_TMPL="$RZR_TEMPLATES/handoff.md"
[ -f "$TEMPLATE" ]      || rzr_die "no template at $TEMPLATE"
[ -f "$HANDOFF_TMPL" ]  || rzr_die "no handoff template at $HANDOFF_TMPL"
[ -f "$BODY_FILE" ]     || rzr_die "no body file at $BODY_FILE"

FOLDER="$(rzr_task_dir "$ID")"
mkdir -p "$FOLDER"
touch "$FOLDER/handoff.md"          # exists from the start so a watcher can tail it

RZR_TMPL="$TEMPLATE" RZR_HANDOFF_TMPL="$HANDOFF_TMPL" RZR_ID="$ID" \
RZR_FOLDER="$FOLDER" RZR_BODY_FILE="$BODY_FILE" RZR_OUT="$FOLDER/brief.md" \
RZR_HANDOFF_OUT="$(rzr_handoff_protocol_path "$ID")" python3 - <<'PY'
import os
def render(tmpl_path, out_path, **subs):
    t = open(tmpl_path).read()
    for k, v in subs.items():
        t = t.replace("{{%s}}" % k, v)
    open(out_path, "w").write(t)
render(os.environ["RZR_TMPL"], os.environ["RZR_OUT"],
       ID=os.environ["RZR_ID"], FOLDER=os.environ["RZR_FOLDER"],
       BODY=open(os.environ["RZR_BODY_FILE"]).read())
# The handoff protocol, rendered standalone: fresh Claude crews get it as a
# system prompt; other harnesses and resumed crews get it in the prompt.
render(os.environ["RZR_HANDOFF_TMPL"], os.environ["RZR_HANDOFF_OUT"],
       ID=os.environ["RZR_ID"], FOLDER=os.environ["RZR_FOLDER"])
PY

echo "$FOLDER/brief.md"
