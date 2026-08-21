#!/usr/bin/env bash
# rzr-status.sh - read a task's latest handoff verdict + any unresolved open items.
#
# Usage:
#   rzr-status.sh <id>                 human line: latest verdict + new-block flag
#                                      + a leak-proof OPEN list (see below)
#   rzr-status.sh <id> --json          machine-readable line for the watch loop
#   rzr-status.sh <id> --peek          do not advance the seen-marker
#
# Parses tasks/<id>/handoff.md and reports two things:
#   1. The LAST turn's verdict + whether a NEW block appeared since the previous
#      call — the miss-detector: at an idle edge, new_block=false means the crew
#      ended a turn without reporting, so nudge it (rzr-send) rather than trust
#      herdr's ambiguous `done`.
#   2. Leak-proof OPEN items: EVERY block is an open item if its verdict is
#      needs-action|blocked|failed OR its inputs-needed is set — and it stays open
#      until you explicitly `rzr-ack.sh <id>`. Reading only the last block would
#      let a later `done` bury an earlier unanswered needs-action/question; this
#      scan (modeled on firstmate's status drain) makes that impossible. The ack
#      cursor (.acked-blocks) is advanced ONLY by rzr-ack — never by a status read
#      — so the surfacing survives any number of status calls until you resolve it.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

[ $# -ge 1 ] || rzr_die "usage: rzr-status.sh <id> [--json] [--peek]"
ID="$1"; shift
JSON=0; PEEK=0
for a in "$@"; do case "$a" in --json) JSON=1 ;; --peek) PEEK=1 ;; *) rzr_die "unknown flag $a" ;; esac; done

FOLDER="$(rzr_task_dir "$ID")"
HF="$FOLDER/handoff.md"
[ -f "$HF" ] || rzr_die "no task folder for '$ID' ($HF missing)"

RZR_HF="$HF" RZR_SEEN="$FOLDER/.seen-blocks" RZR_ACKED="$FOLDER/.acked-blocks" \
RZR_ID="$ID" RZR_JSON="$JSON" RZR_PEEK="$PEEK" python3 - <<'PY'
import os, re, json
hf = open(os.environ["RZR_HF"]).read()
starts = [m.start() for m in re.finditer(r'(?m)^##\s', hf)]
count = len(starts)
blocks = [hf[starts[i]:(starts[i+1] if i+1 < count else len(hf))] for i in range(count)]

def field(block, name):
    m = re.search(r'(?mi)^' + re.escape(name) + r':\s*(.*)$', block)
    return m.group(1).strip() if m else ""
def heading(block):
    return block.splitlines()[0].lstrip('# ').strip() if block else ""

OPEN_VERDICTS = {"needs-action", "blocked", "failed"}
NONE_VALUES = {"", "none", "n/a", "na", "-"}
def is_open(block):
    if field(block, "verdict").lower() in OPEN_VERDICTS:
        return True
    return field(block, "inputs-needed").lower() not in NONE_VALUES

last = blocks[-1] if blocks else ""
verdict = field(last, "verdict") or ("(none)" if count else "(no-handoff-yet)")

# seen cursor: auto-advanced every non-peek call -> drives the new-block flag.
try:    seen = int(open(os.environ["RZR_SEEN"]).read().strip())
except Exception: seen = 0
new = count > seen
if os.environ["RZR_PEEK"] != "1":
    open(os.environ["RZR_SEEN"], "w").write(str(count))

# ack cursor: advanced ONLY by rzr-ack. An open block at 1-based index > acked is
# unresolved and keeps surfacing here regardless of later blocks or status reads.
try:    acked = int(open(os.environ["RZR_ACKED"]).read().strip())
except Exception: acked = 0
open_items = [{"turn": i + 1, "heading": heading(b), "verdict": field(b, "verdict"),
               "inputs_needed": field(b, "inputs-needed")}
              for i, b in enumerate(blocks) if i + 1 > acked and is_open(b)]

out = {"id": os.environ["RZR_ID"], "verdict": verdict, "blocks": count,
       "new_block": new, "heading": heading(last), "reason": field(last, "reason"),
       "pending": field(last, "pending"), "inputs_needed": field(last, "inputs-needed"),
       "artifacts": field(last, "artifacts"),
       "acked_through": acked, "open_items": open_items, "unresolved": len(open_items)}
if os.environ["RZR_JSON"] == "1":
    print(json.dumps(out)); raise SystemExit

flag = "NEW" if new else "same"
print(f'{out["id"]:<16} verdict={out["verdict"]:<13} blocks={count} [{flag}]  {out["heading"]}')
if open_items:
    print(f'  ⚠ {len(open_items)} unresolved open item(s) — resolve with: rozoro ack {out["id"]}')
    for it in open_items:
        line = f'      turn {it["turn"]} [{it["verdict"] or "?"}] {it["heading"]}'
        if it["inputs_needed"].lower() not in NONE_VALUES:
            line += f'  — needs: {it["inputs_needed"]}'
        print(line)
if verdict.startswith("(no-handoff") or (not new and not verdict.startswith("(")):
    print("  ^ ended a turn with no fresh handoff block — nudge the crew to report")
PY
