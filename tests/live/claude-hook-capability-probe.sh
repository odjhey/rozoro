#!/usr/bin/env bash
# Cost-incurring, opt-in reproduction for tests/fixtures/claude-hooks-2.1.240.json.
# All settings and output stay in a new temporary directory. Standard Claude
# setting sources are disabled, so this never reads or changes user/project hooks.
set -euo pipefail

command -v claude >/dev/null
work="$(mktemp -d "${TMPDIR:-/tmp}/rozoro-claude-hook-probe.XXXXXX")"
printf 'Raw probe evidence (contains sensitive paths/prose): %s\n' "$work"

cat >"$work/hook.py" <<'PY'
#!/usr/bin/env python3
import json, os, sys, time
payload = json.load(sys.stdin)
with open(os.environ["PROBE_LOG"], "a", encoding="utf-8") as out:
    out.write(json.dumps({"captured_at_ns": time.time_ns(), "payload": payload}) + "\n")
PY
cat >"$work/timeout.py" <<'PY'
#!/usr/bin/env python3
import json, sys, time
json.load(sys.stdin)
time.sleep(3)
PY
cat >"$work/continue.py" <<'PY'
#!/usr/bin/env python3
import json, os, sys, time
payload = json.load(sys.stdin)
with open(os.environ["PROBE_LOG"], "a", encoding="utf-8") as out:
    out.write(json.dumps({"captured_at_ns": time.time_ns(), "payload": payload}) + "\n")
if not payload.get("stop_hook_active"):
    print("Reply only STOP_CONTINUATION_CONFIRMED.", file=sys.stderr)
    raise SystemExit(2)
PY
chmod 700 "$work"/*.py

python3 - "$work" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
capture = str(root / "hook.py")
timeout = str(root / "timeout.py")
continuation = str(root / "continue.py")
def group(command, seconds=10):
    return [{"hooks": [{"type": "command", "command": command, "timeout": seconds}]}]
events = ("SessionStart", "UserPromptSubmit", "SubagentStart", "SubagentStop", "Stop", "SessionEnd")
(root / "lifecycle.settings.json").write_text(json.dumps({"hooks": {e: group(capture) for e in events}}))
(root / "timeout.settings.json").write_text(json.dumps({"hooks": {
    "SessionStart": group(capture), "UserPromptSubmit": group(timeout, 1),
    "Stop": group(capture), "SessionEnd": group(capture)}}))
(root / "continuation.settings.json").write_text(json.dumps({"hooks": {
    "SessionStart": group(capture), "UserPromptSubmit": group(capture),
    "Stop": group(continuation), "SessionEnd": group(capture)}}))
PY

run_claude() {
  local settings="$1" prompt="$2" stem="$3"
  PROBE_LOG="$work/$stem.hooks.ndjson" claude -p --verbose \
    --model haiku --permission-mode bypassPermissions \
    --setting-sources '' --settings "$settings" \
    --debug hooks --debug-file "$work/$stem.debug.log" \
    --include-hook-events --output-format stream-json \
    "$prompt" >"$work/$stem.stream.ndjson" 2>"$work/$stem.stderr.log"
}

run_claude "$work/lifecycle.settings.json" \
  'Use Agent once with run_in_background=true. Ask it to use Bash to sleep 8 seconds, then reply BG_DONE. Immediately reply MAIN_LAUNCHED without waiting or calling TaskOutput.' \
  background
run_claude "$work/timeout.settings.json" 'Reply only TIMEOUT_OK.' timeout
run_claude "$work/continuation.settings.json" 'Reply only INITIAL_STOP.' continuation

# Print a compact verification without copying raw sensitive evidence elsewhere.
python3 - "$work" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
def records(name):
    return [json.loads(line) for line in (root / name).read_text().splitlines()]
hooks = [r["payload"] for r in records("background.hooks.ndjson")]
stops = [p for p in hooks if p["hook_event_name"] == "Stop"]
print("claude_version:", __import__("subprocess").check_output(["claude", "--version"], text=True).strip())
print("hooks:", sorted({p["hook_event_name"] for p in hooks}))
print("stop_background_types:", [[t["type"] for t in p["background_tasks"]] for p in stops])
for stem in ("timeout", "continuation"):
    stream = records(stem + ".stream.ndjson")
    responses = [(r.get("hook_event"), r.get("exit_code"), r.get("outcome"))
                 for r in stream if r.get("subtype") == "hook_response"]
    results = [(r.get("num_turns"), r.get("is_error")) for r in stream if r.get("type") == "result"]
    print(stem + "_responses:", responses)
    print(stem + "_results:", results)
PY

printf 'Delete raw evidence after inspection: rm -rf %q\n' "$work"
