#!/usr/bin/env bash
# fl-status.sh - read a task's latest handoff verdict (done vs needs-action).
#
# Usage:
#   fl-status.sh <id>                 human line: latest verdict + new-block flag
#   fl-status.sh <id> --json          machine-readable line for the watch loop
#   fl-status.sh <id> --peek          do not advance the seen-marker
#
# Parses tasks/<id>/handoff.md, reports the LAST turn's verdict/inputs-needed and
# whether a NEW block appeared since the previous call — the miss-detector: at an
# idle edge, new_block=false means the crew ended a turn without reporting, so
# nudge it (fl-send) instead of trusting herdr's ambiguous `done`.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

[ $# -ge 1 ] || fl_die "usage: fl-status.sh <id> [--json] [--peek]"
ID="$1"; shift
JSON=0; PEEK=0
for a in "$@"; do case "$a" in --json) JSON=1 ;; --peek) PEEK=1 ;; *) fl_die "unknown flag $a" ;; esac; done

FOLDER="$(fl_task_dir "$ID")"
HF="$FOLDER/handoff.md"
[ -f "$HF" ] || fl_die "no task folder for '$ID' ($HF missing)"

FL_HF="$HF" FL_SEEN="$FOLDER/.seen-blocks" FL_ID="$ID" FL_JSON="$JSON" FL_PEEK="$PEEK" python3 - <<'PY'
import os, re, json
hf = open(os.environ["FL_HF"]).read()
starts = [m.start() for m in re.finditer(r'(?m)^##\s', hf)]
count = len(starts)
last = hf[starts[-1]:] if starts else ""
def field(name):
    m = re.search(r'(?mi)^' + re.escape(name) + r':\s*(.*)$', last)
    return m.group(1).strip() if m else ""
heading = last.splitlines()[0].lstrip('# ').strip() if last else ""
verdict = field("verdict") or ("(none)" if count else "(no-handoff-yet)")
try:    seen = int(open(os.environ["FL_SEEN"]).read().strip())
except Exception: seen = 0
new = count > seen
if os.environ["FL_PEEK"] != "1":
    open(os.environ["FL_SEEN"], "w").write(str(count))
out = {"id": os.environ["FL_ID"], "verdict": verdict, "blocks": count,
       "new_block": new, "heading": heading, "reason": field("reason"),
       "pending": field("pending"), "inputs_needed": field("inputs-needed"),
       "artifacts": field("artifacts")}
if os.environ["FL_JSON"] == "1":
    print(json.dumps(out)); raise SystemExit
flag = "NEW" if new else "same"
print(f'{out["id"]:<16} verdict={out["verdict"]:<13} blocks={count} [{flag}]  {out["heading"]}')
if out["inputs_needed"] and out["inputs_needed"].lower() != "none":
    print(f'  inputs-needed: {out["inputs_needed"]}')
if verdict.startswith("(no-handoff") or (not new and not verdict.startswith("(")):
    print("  ^ ended a turn with no fresh handoff block — nudge the crew to report")
PY
