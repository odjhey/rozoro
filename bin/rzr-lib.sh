#!/usr/bin/env bash
# rzr-lib.sh - shared helpers for rozoro.
#
# A deliberately tiny orchestrator over the herdr terminal backend. Every task
# is one herdr TAB holding one PANE running one agent. State lives on disk under
# state/, so a restart is a non-event. Sourced by the rzr-* commands; not run
# directly.
#
# Concepts:
#   task key  - immutable globally unique key; names state/<key>.meta and tasks/<key>/
#   display   - caller-chosen concise label (e.g. "fixlogin")
#   pane      - herdr pane id "wX:pN"; the terminal the agent runs in (authority)
#   tab       - herdr tab id "wX:tN"; the clickable container for the pane
#
# Requires: herdr (0.8.x), jq.

set -euo pipefail

RZR_LIB_SRC="${BASH_SOURCE[0]}"
RZR_BIN="$(cd "$(dirname "$RZR_LIB_SRC")" && pwd)"
# Home for all on-disk state. Defaults to ~/.rozoro so the driver's state lives
# outside any one checkout and survives a restart. Precedence: ROZORO_HOME (the
# public knob) > RZR_HOME > default.
RZR_HOME="${ROZORO_HOME:-${RZR_HOME:-$HOME/.rozoro}}"
RZR_STATE="$RZR_HOME/state"
# Per-task folders: the durable record of a task's INPUT (brief.md), append-only
# OUTPUT (handoff.md), and resume link (session.json). Data, so it lives under
# RZR_HOME with state/ — survives teardown, never enters the code repo.
RZR_TASKS="$RZR_HOME/tasks"
# Shipped seeds (the handoff brief template). Code, so it resolves relative to
# this checkout, not RZR_HOME. Override with RZR_TEMPLATES.
RZR_REPO="$(cd "$RZR_BIN/.." && pwd)"
RZR_TEMPLATES="${RZR_TEMPLATES:-$RZR_REPO/templates}"
[ ! -L "$RZR_STATE" ] || { echo "rzr: state directory must not be a symlink" >&2; exit 1; }
mkdir -p "$RZR_STATE"
[ -O "$RZR_STATE" ] || { echo "rzr: state directory must be owned by the current user" >&2; exit 1; }
chmod 700 "$RZR_STATE"

# Task keys and legacy ids are deliberately conservative filesystem components.
# Existing unsuffixed folders remain valid; unsafe historical names must be
# addressed by moving them to a safe component first.
rzr_validate_task_component() {  # <value> [description]
  local value="$1" what="${2:-task key}"
  case "$value" in
    ''|.|..|*[!A-Za-z0-9._-]*) rzr_die "$what '$value' is unsafe; use letters, digits, '.', '_' or '-'" ;;
  esac
  [ "${#value}" -le 120 ] || rzr_die "$what is too long (maximum 120 characters)"
}

# Path to a task's durable folder (does not create it).
rzr_task_dir() { rzr_validate_task_component "$1"; printf '%s/%s' "$RZR_TASKS" "$1"; }

# Herdr agent names are a transport identity, not a task identity: they are
# limited to 32 lowercase ASCII letters/digits/dashes/underscores. Derive a
# stable, namespaced 112-bit digest from the immutable task key so every valid
# legacy id and every new ULID-suffixed key can use the same safe path.
rzr_herdr_agent_name() {  # <task-key>
  RZR_AGENT_TASK_KEY="$1" python3 - <<'PY'
import hashlib, os
digest = hashlib.sha256(os.environ["RZR_AGENT_TASK_KEY"].encode()).hexdigest()[:28]
print("rzr-" + digest)
PY
}

# Prefer the durable identity recorded at reservation time. Older task folders
# have no such field, so derive the same safe identity without migrating them.
rzr_task_agent_name() {  # <task-key>
  local id="$1" identity recorded=""
  identity="$(rzr_task_dir "$id")/identity.json"
  [ -s "$identity" ] && recorded="$(jq -r '.herdr_agent_name // empty' "$identity" 2>/dev/null || true)"
  case "$recorded" in
    ''|*[!a-z0-9_-]*) recorded="" ;;
  esac
  [ "${#recorded}" -le 32 ] || recorded=""
  if [ -n "$recorded" ]; then printf '%s\n' "$recorded"
  else rzr_herdr_agent_name "$id"
  fi
}

# Reserve a fresh durable identity with an atomic mkdir. The time-sortable ULID
# suffix supplies 80 bits of randomness; mkdir remains the collision arbiter.
rzr_task_reserve() {  # <display-name> <cwd> -> task key
  local display="$1" cwd="$2" suffix key folder agent_name attempt=0 tmp
  rzr_validate_task_component "$display" "display name"
  [ "${#display}" -le 80 ] || rzr_die "display name is too long (maximum 80 characters)"
  mkdir -p "$RZR_TASKS"
  while [ "$attempt" -lt 20 ]; do
    suffix=$(python3 - <<'PY'
import os, time
alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
out = []
for _ in range(26):
    out.append(alphabet[value & 31]); value >>= 5
print("".join(reversed(out)))
PY
)
    key="$display--$suffix"
    folder="$RZR_TASKS/$key"
    if mkdir "$folder" 2>/dev/null; then
      agent_name="$(rzr_herdr_agent_name "$key")"
      tmp="$folder/identity.json.tmp.$$"
      RZR_IDENTITY_OUT="$tmp" RZR_TASK_KEY="$key" RZR_DISPLAY_NAME="$display" RZR_CWD="$cwd" RZR_HERDR_AGENT_NAME="$agent_name" python3 - <<'PY'
import json, os
json.dump({"schema": 1, "task_key": os.environ["RZR_TASK_KEY"],
           "display_name": os.environ["RZR_DISPLAY_NAME"], "cwd": os.environ["RZR_CWD"],
           "herdr_agent_name": os.environ["RZR_HERDR_AGENT_NAME"]},
          open(os.environ["RZR_IDENTITY_OUT"], "w"), indent=2)
PY
      mv "$tmp" "$folder/identity.json"
      printf '%s' "$key"
      return 0
    fi
    attempt=$((attempt + 1))
  done
  rzr_die "could not reserve a unique task key for '$display'"
}

# The rendered handoff protocol for a task (rzr-render writes it). Delivered to
# fresh claude crews as a system prompt and re-injected into resume prompts; it
# survives teardown, so resume can always find it.
rzr_handoff_protocol_path() { printf '%s/handoff-protocol.md' "$(rzr_task_dir "$1")"; }

# Ensure handoff-protocol.md exists for a task, rendering it from the template if
# rzr-render never ran (e.g. a direct `rzr-spawn --prompt ...`). Idempotent.
rzr_render_handoff_protocol() {  # <id>
  local id="$1" out tmpl folder
  out="$(rzr_handoff_protocol_path "$id")"
  [ -s "$out" ] && return 0
  tmpl="$RZR_TEMPLATES/handoff.md"
  [ -f "$tmpl" ] || rzr_die "no handoff template at $tmpl"
  folder="$(rzr_task_dir "$id")"
  mkdir -p "$folder"
  sed -e "s#{{ID}}#$id#g" -e "s#{{FOLDER}}#$folder#g" "$tmpl" > "$out"
}

rzr_die() { echo "rzr: $*" >&2; exit 1; }

command -v herdr >/dev/null 2>&1 || rzr_die "herdr not found on PATH"
command -v jq    >/dev/null 2>&1 || rzr_die "jq not found on PATH"

# --- herdr invocation ------------------------------------------------------
# Talks to the running herdr server over its control socket. A single local
# server needs no --session; set RZR_SESSION to target a named one.
rzr_herdr() {  # <herdr args...>
  if [ -n "${RZR_SESSION:-}" ]; then
    herdr --session "$RZR_SESSION" "$@"
  else
    herdr "$@"
  fi
}

# The workspace new tabs are created in. Defaults to the orchestrator's own
# herdr workspace so every task tab is a sibling you can click to (the flat
# "tabs" layout). Override with RZR_WORKSPACE.
rzr_workspace() { printf '%s' "${RZR_WORKSPACE:-${HERDR_WORKSPACE_ID:-}}"; }

# Path to the herdr control socket (for the native pane.agent_status_changed
# push stream that rzr-watch consumes). Resolves the named session's socket, or
# the single local server's when RZR_SESSION is unset.
rzr_socket_path() {
  if [ -n "${RZR_SESSION:-}" ]; then
    herdr session list --json 2>/dev/null \
      | jq -r --arg n "$RZR_SESSION" '.sessions[]? | select(.name==$n) | .socket_path // empty' 2>/dev/null | head -1
  else
    herdr session list --json 2>/dev/null \
      | jq -r '.sessions[0].socket_path // empty' 2>/dev/null | head -1
  fi
}

# The raw-socket event subscriber (wire transport for rzr-watch). Ships alongside
# the bin/ scripts; requires python3 (stdlib only).
rzr_eventwait_py() { printf '%s/herdr-eventwait.py' "$RZR_BIN"; }

# --- crewmember presets (spawn profiles) -----------------------------------
# A preset bundles HOW a crew agent is booted - harness, model, effort, fast
# service tier, and any
# standing crew RULES - never WHAT its task is (the task prompt is always passed
# verbatim). Presets are one JSON file per name under $RZR_HOME/crew/<name>.json.
# `rules` are crew-behavioral (e.g. "open a draft PR, never push"), deliberately
# distinct from REPO rules, which the agent auto-loads from its --cwd.
RZR_CREW="$RZR_HOME/crew"

rzr_crew_path() { printf '%s/%s.json' "$RZR_CREW" "$1"; }
rzr_crew_exists() { [ -f "$(rzr_crew_path "$1")" ]; }

# The personal default file is authoritative when present. If it is absent,
# resolve `default` to an in-memory fallback without creating or changing any
# file under $RZR_HOME. Claude is the no-flag fallback; explicit Codex and
# Copilot selections get coherent harness-specific profiles.
rzr_crew_builtin_default() {
  case "${1:-claude}" in
    claude) cat <<'JSON'
{
  "harness": "claude",
  "model": "sonnet",
  "permission_mode": "auto",
  "effort": "",
  "fast": false,
  "rules": []
}
JSON
      ;;
    codex) cat <<'JSON'
{
  "harness": "codex",
  "model": "gpt-5.6-sol",
  "permission_mode": "yolo",
  "effort": "low",
  "fast": false,
  "rules": []
}
JSON
      ;;
    copilot) cat <<'JSON'
{
  "harness": "copilot",
  "model": "auto",
  "permission_mode": "yolo",
  "effort": "",
  "fast": false,
  "rules": []
}
JSON
      ;;
    *) jq -n --arg harness "$1" '{harness: $harness, model: "", permission_mode: "auto", effort: "", fast: false, rules: []}' ;;
  esac
}

rzr_crew_builtin_field() {  # <harness> <field>
  rzr_crew_builtin_default "$1" | jq -r --arg k "$2" '.[$k] // empty'
}

rzr_crew_resolves() { rzr_crew_exists "$1" || [ "$1" = default ]; }

rzr_crew_json() {  # <preset> -> configured JSON or built-in default JSON
  local f; f=$(rzr_crew_path "$1")
  if [ -f "$f" ]; then cat "$f"
  elif [ "$1" = default ]; then rzr_crew_builtin_default claude
  else return 1
  fi
}

# Validate known preset fields without rejecting unknown keys. Unknown keys may
# belong to a newer rozoro and ignoring them preserves forward compatibility;
# malformed known fields must never degrade silently into empty defaults.
rzr_crew_validate() {  # <preset>
  local name="$1" json
  json="$(rzr_crew_json "$name")" || return 1
  printf '%s' "$json" | jq -e '
    . as $p |
    type == "object" and
    (["harness", "model", "permission_mode", "effort"] |
      all(. as $k | ($p | has($k) | not) or ($p[$k] | type == "string"))) and
    (($p | has("fast") | not) or ($p.fast | type == "boolean")) and
    (($p | has("rules") | not) or
      (($p.rules | type == "array") and ($p.rules | all(type == "string")))) and
    (($p.effort // "") | IN("", "low", "medium", "high", "xhigh", "max"))
  ' >/dev/null 2>&1
}

rzr_crew_field() {  # <preset> <field> -> value, or empty
  rzr_crew_json "$1" | jq -r --arg k "$2" '.[$k] // empty' 2>/dev/null
}

rzr_crew_bool_field() {  # <preset> <field> -> true|false, or empty when absent
  rzr_crew_json "$1" | jq -r --arg k "$2" 'if has($k) then .[$k] else empty end' 2>/dev/null
}

rzr_crew_rules() {  # <preset> -> rules joined by newlines (empty if none)
  rzr_crew_json "$1" | jq -r '(.rules // []) | join("\n")' 2>/dev/null
}

# --- watchtower presets ----------------------------------------------------
# Named, versioned launch metadata for resident drivers. Unlike crew presets,
# there is intentionally no virtual default: no preset preserves legacy launch
# behavior exactly.
RZR_WT_PRESETS="$RZR_HOME/watchtower-presets"

rzr_validate_wtpreset_name() { rzr_validate_task_component "$1" "watchtower preset name"; }
rzr_validate_wt_metadata() {  # <value> <description>
  local value="$1" what="$2"
  case "$value" in *$'\n'*|*$'\r'*|*$'\t'*|*=*) rzr_die "$what contains unsafe control or metadata characters" ;; esac
  [ "${#value}" -le 120 ] || rzr_die "$what is too long (maximum 120 characters)"
}
rzr_wtpreset_path() { rzr_validate_wtpreset_name "$1"; printf '%s/%s.json' "$RZR_WT_PRESETS" "$1"; }

# Open and read a preset exactly once through no-follow descriptors. The result
# contains both the parsed document and the SHA of those exact same bytes.
rzr_wtpreset_resolve() {  # <name> -> {document,sha256}
  local name="$1"; rzr_validate_wtpreset_name "$name"
  RZR_WTP_DIR="$RZR_WT_PRESETS" RZR_WTP_FILE="$name.json" python3 - <<'PY'
import hashlib, json, math, os, stat
root = os.open(os.environ["RZR_WTP_DIR"], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
try:
    fd = os.open(os.environ["RZR_WTP_FILE"], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), dir_fd=root)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise SystemExit("preset is not a singly-linked owned regular file")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk: break
            chunks.append(chunk)
    finally: os.close(fd)
finally: os.close(root)
raw = b"".join(chunks)
def reject_constant(value): raise ValueError("non-standard JSON constant: "+value)
try: doc = json.loads(raw, parse_constant=reject_constant)
except (UnicodeError, ValueError): raise SystemExit("invalid preset JSON")
if not isinstance(doc, dict): raise SystemExit("preset must be an object")
def finite_json(value):
    if isinstance(value, float): return math.isfinite(value)
    if isinstance(value, dict): return all(finite_json(item) for item in value.values())
    if isinstance(value, list): return all(finite_json(item) for item in value)
    return True
if not finite_json(doc): raise SystemExit("preset contains a non-finite number")
for key in ("harness", "model", "effort", "permission_mode", "notes"):
    if key in doc and not isinstance(doc[key], str): raise SystemExit("invalid preset field type")
for key in ("harness", "model", "effort", "permission_mode", "notes"):
    if len(doc.get(key, "")) > 120: raise SystemExit("preset field is too long")
    if any(char in doc.get(key, "") for char in "\r\n\t="): raise SystemExit("preset field contains unsafe metadata characters")
for key in ("schema", "version"):
    if key in doc and (not isinstance(doc[key], (int, float)) or isinstance(doc[key], bool)):
        raise SystemExit("invalid preset field type")
if "version" in doc and len(str(doc["version"])) > 120: raise SystemExit("preset version is too long")
if doc.get("harness", "") not in ("claude", "pi"): raise SystemExit("invalid preset harness")
if doc.get("effort", "") not in ("", "low", "medium", "high", "xhigh", "max"):
    raise SystemExit("invalid preset effort")
print(json.dumps({"document": doc, "sha256": hashlib.sha256(raw).hexdigest()}, separators=(",", ":"), allow_nan=False))
PY
}
rzr_wtpreset_exists() { rzr_wtpreset_resolve "$1" >/dev/null 2>&1; }
rzr_wtpreset_json() { rzr_wtpreset_resolve "$1" | jq -c '.document'; }
rzr_wtpreset_field() { rzr_wtpreset_resolve "$1" | jq -r --arg k "$2" '.document[$k] // empty' 2>/dev/null; }
rzr_wtpreset_validate() { rzr_wtpreset_resolve "$1" >/dev/null 2>&1; }

rzr_file_identity() { python3 - "$1" <<'PY'
import hashlib, os, stat, sys
fd=os.open(sys.argv[1], os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
try:
    info=os.fstat(fd)
    if not stat.S_ISREG(info.st_mode): raise SystemExit("not a regular file")
    digest=hashlib.sha256()
    while True:
        chunk=os.read(fd,65536)
        if not chunk: break
        digest.update(chunk)
    print(f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{digest.hexdigest()}")
finally: os.close(fd)
PY
}
rzr_sha256_file() { rzr_file_identity "$1" | awk -F: '{print $5}'; }

# Enumerate only records reached through owned, private, no-follow directory
# descriptors. An optional driver id selects one record. Malformed/unsafe state
# is skipped so read-only attribution remains best-effort.
rzr_watchtower_target_json() {  # [driver-id]
  local selected="${1:-}"
  [ -z "$selected" ] || rzr_validate_task_component "$selected" "driver id"
  RZR_TARGET_HOME="$RZR_HOME" RZR_TARGET_DRIVER="$selected" python3 - <<'PY' 2>/dev/null
import json, os, stat
nofollow=getattr(os,"O_NOFOLLOW",0); directory=getattr(os,"O_DIRECTORY",0)
def private_dir(info): return stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and not stat.S_IMODE(info.st_mode)&0o077
def safe(value): return isinstance(value,str) and len(value)<=120 and not any(c in value for c in "\r\n\t=")
def reject_constant(value): raise ValueError("non-standard JSON constant: "+value)
try: root=os.open(os.environ["RZR_TARGET_HOME"],os.O_RDONLY|directory|nofollow)
except OSError: raise SystemExit
try:
    try:
        info=os.stat("watchtowers",dir_fd=root,follow_symlinks=False)
        if not private_dir(info): raise SystemExit
        towers=os.open("watchtowers",os.O_RDONLY|directory|nofollow,dir_fd=root)
    except OSError: raise SystemExit
    try:
        selected=os.environ["RZR_TARGET_DRIVER"]
        names=[selected] if selected else sorted(os.listdir(towers))
        for name in names:
            if not name or name in (".","..") or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in name): continue
            try:
                info=os.stat(name,dir_fd=towers,follow_symlinks=False)
                if not private_dir(info): continue
                driver=os.open(name,os.O_RDONLY|directory|nofollow,dir_fd=towers)
                try:
                    fd=os.open("target.json",os.O_RDONLY|nofollow|getattr(os,"O_NONBLOCK",0),dir_fd=driver)
                    info=os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)&0o077:
                        os.close(fd); continue
                    with os.fdopen(fd) as stream: data=json.load(stream,parse_constant=reject_constant)
                finally: os.close(driver)
                if not isinstance(data,dict) or data.get("driver_id") != name or not safe(data.get("driver_id")): continue
                if "schema" in data and (not isinstance(data["schema"],int) or isinstance(data["schema"],bool) or data["schema"]!=1): continue
                if "owner_pid" in data and (not isinstance(data["owner_pid"],str) or not data["owner_pid"].isdigit() or not 1<=int(data["owner_pid"])<=2**63-1): continue
                if any(key in data and not isinstance(data[key],str) for key in ("identity","watchtower_name","harness","backend","created")): continue
                if any(isinstance(data.get(key),str) and not safe(data[key]) for key in ("identity","watchtower_name","harness","backend","created")): continue
                if "preset" in data:
                    preset=data["preset"]
                    if not isinstance(preset,dict): continue
                    if any(key in preset and not isinstance(preset[key],str) for key in ("name","sha256","policy_sha256","model","effort")): continue
                    if "version" in preset and (not isinstance(preset["version"],(str,int,float)) or isinstance(preset["version"],bool) or len(str(preset["version"]))>120): continue
                    if any(isinstance(preset.get(key),str) and not safe(preset[key]) for key in ("name","version","sha256","policy_sha256","model","effort")): continue
                print(json.dumps(data,separators=(",",":")))
            except (OSError,ValueError,TypeError,AttributeError): continue
    finally: os.close(towers)
finally: os.close(root)
PY
}
rzr_dispatcher_target_json() { rzr_watchtower_target_json "$1" | head -n 1; }
rzr_dispatcher_candidate_matches() {  # <json> <backend> <identity>
  local json="$1" backend="$2" identity="$3" actual_backend
  [ -n "$json" ] || return 1
  [ "$(printf '%s' "$json" | jq -r '.identity // empty')" = "$identity" ] || return 1
  actual_backend="$(printf '%s' "$json" | jq -r '.backend // empty')"
  [ -z "$actual_backend" ] || [ "$actual_backend" = "$backend" ]
}
rzr_dispatcher_add_candidate() {  # <driver-id> <backend> <identity>
  local candidate="$1" backend="$2" identity="$3" existing
  if [ "${#dispatcher_candidates[@]}" -gt 0 ]; then
    for existing in "${dispatcher_candidates[@]}"; do
      [ "$existing" = "$candidate" ] && return 0
    done
  fi
  dispatcher_candidates+=("$candidate")
  dispatcher_backends+=("$backend")
  dispatcher_identities+=("$identity")
}

# Best-effort dispatcher discovery. Explicit driver wins; identity-derived and
# scan candidates are deduplicated and accepted only when unambiguous.
rzr_dispatcher_lookup() {
  local candidate json
  local -a dispatcher_candidates=() dispatcher_backends=() dispatcher_identities=()
  if [ -n "${ROZORO_WT_DRIVER:-}" ]; then
    json="$(rzr_dispatcher_target_json "$ROZORO_WT_DRIVER" || true)"
    if [ -n "$json" ]; then printf '%s\n' "$json"; return 0; fi
  fi
  if [ -n "${HERDR_PANE_ID:-}" ]; then
    candidate="$(rzr_driver_id_for herdr "$HERDR_PANE_ID")"
    json="$(rzr_dispatcher_target_json "$candidate" || true)"
    if rzr_dispatcher_candidate_matches "$json" herdr "$HERDR_PANE_ID"; then
      rzr_dispatcher_add_candidate "$candidate" herdr "$HERDR_PANE_ID"
    fi
  fi
  if [ -n "${CODEX_THREAD_ID:-}" ]; then
    candidate="$(rzr_driver_id_for codex "$CODEX_THREAD_ID")"
    json="$(rzr_dispatcher_target_json "$candidate" || true)"
    if rzr_dispatcher_candidate_matches "$json" codex "$CODEX_THREAD_ID"; then
      rzr_dispatcher_add_candidate "$candidate" codex "$CODEX_THREAD_ID"
    fi
  fi
  if [ -n "${HERDR_PANE_ID:-}${CODEX_THREAD_ID:-}" ]; then
    while IFS= read -r json; do
      candidate="$(printf '%s' "$json" | jq -r '.driver_id')"
      if [ -n "${HERDR_PANE_ID:-}" ] && rzr_dispatcher_candidate_matches "$json" herdr "$HERDR_PANE_ID"; then
        rzr_dispatcher_add_candidate "$candidate" herdr "$HERDR_PANE_ID"
      fi
      if [ -n "${CODEX_THREAD_ID:-}" ] && rzr_dispatcher_candidate_matches "$json" codex "$CODEX_THREAD_ID"; then
        rzr_dispatcher_add_candidate "$candidate" codex "$CODEX_THREAD_ID"
      fi
    done < <(rzr_watchtower_target_json || true)
  fi
  [ "${#dispatcher_candidates[@]}" -eq 1 ] || return 0
  json="$(rzr_dispatcher_target_json "${dispatcher_candidates[0]}" || true)"
  rzr_dispatcher_candidate_matches "$json" "${dispatcher_backends[0]}" "${dispatcher_identities[0]}" || return 0
  printf '%s\n' "$json"
  return 0
}

# Validate the fully-resolved launch tuple. Fast is intentionally Codex-only in
# stage 1 and limited to the model whose catalog advertises the priority tier.
rzr_profile_validate() {  # <harness> <model> <effort> <fast>
  local harness="$1" model="$2" effort="$3" fast="$4"
  case "$harness" in claude|codex|copilot|pi) ;; *) rzr_die "harness '$harness': not wired (known: claude codex copilot pi)" ;; esac
  case "$effort" in ''|low|medium|high|xhigh|max) ;; *) rzr_die "invalid effort '$effort' (low|medium|high|xhigh|max)" ;; esac
  case "$fast" in true|false) ;; *) rzr_die "fast must resolve to true or false" ;; esac
  if [ "$fast" = true ]; then
    [ "$harness" = codex ] || rzr_die "fast mode is currently supported only for the codex harness"
    [ "$model" = gpt-5.6-sol ] || rzr_die "fast mode is currently supported only for codex model gpt-5.6-sol"
  fi
}

# Require the public Copilot options Rozoro relies on. Capability checking is
# more robust than a version floor for a self-updating CLI.
rzr_copilot_capabilities() {
  command -v copilot >/dev/null 2>&1 || { echo "rzr: copilot not found on PATH" >&2; return 1; }
  local help flag
  help="$(copilot --help 2>&1)" || { echo "rzr: could not inspect 'copilot --help'; upgrade or repair GitHub Copilot CLI" >&2; return 1; }
  for flag in --model --effort --autopilot --yolo --no-ask-user --no-auto-update --session-id --resume; do
    printf '%s\n' "$help" | grep -F -- "$flag" >/dev/null || {
      echo "rzr: GitHub Copilot CLI is missing required capability $flag; upgrade Copilot CLI" >&2
      return 1
    }
  done
}

# Return success when a version string falls in [2.1.240,2.2.0).
rzr_claude_version_supported() {  # <raw-version>
  local version="$1" major minor patch
  [[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || return 1
  major="${BASH_REMATCH[1]}"; minor="${BASH_REMATCH[2]}"; patch="${BASH_REMATCH[3]}"
  [ "$major" -eq 2 ] || return 1
  [ "$minor" -eq 1 ] || return 1
  [ "$patch" -ge 240 ] || return 1
}

# Map a resolved profile to the launch args a harness expects AFTER the `--` in
# `herdr agent start ... -- <arg>...`. Emits NUL-separated args (so a rule value
# containing newlines survives being read back into an array; bash-3.2 safe via
# `read -d ''`). Returns 1 for an unknown harness so a preset can never boot one
# with the wrong flags.
#
# `permmode` is a generic "run autonomously" signal. Claude passes its literal
# value and Pi uses --approve. Codex and Copilot are unconditionally autonomous;
# their permmode input cannot weaken the spawner invariant. `effort` maps to each
# harness's native flag/config.
#
# The 5th arg is a PATH to a rendered system-prompt file (handoff protocol +
# preset rules). Claude takes it through --append-system-prompt-file; Pi's
# --append-system-prompt accepts either text or a file path. The 6th optional arg
# is a preallocated harness session id (used by Pi and Copilot for exact linking).
rzr_claude_event_capability() {
  command -v claude >/dev/null 2>&1 || { echo "rzr: event-bus opt-in requires Claude Code >=2.1.240 <2.2.0" >&2; return 1; }
  local version
  version="$(claude --version 2>/dev/null | sed 's/ .*//')" || return 1
  if rzr_claude_version_supported "$version"; then return 0; fi
  echo "rzr: Claude event hooks are certified only for >=2.1.240 <2.2.0 (found: $version)" >&2; return 1
}

# Generate a private Claude watchtower settings overlay. The caller supplies the
# already validated Herdr pane and stable driver identity; this never edits user
# or project settings and remains opt-in.
rzr_claude_watchtower_settings() {  # <output-path> <driver-id> <adapter-session> <native-session> <herdr-pane>
  local target="$1" driver="$2" session="$3" native="$4" pane="$5" binary
  binary="$(command -v claude)" || return 1
  python3 - "$target" "$RZR_REPO/hooks/claude-rozoro-event.py" "$RZR_HOME" "$driver" "$session" "$native" "$pane" "$binary" <<'PY' || return 1
import json, os, secrets, shlex, stat, subprocess, sys
path, hook, home, driver, session, native, pane, binary = sys.argv[1:]
name = "claude-event-settings.json"; expected=os.path.join(home,"watchtowers",driver,name)
if path != expected: raise SystemExit("watchtower settings path does not match driver capability")
flags=os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0)
root=os.open(home,flags)
try:
    towers=os.open("watchtowers",flags,dir_fd=root)
    try: fd=os.open(driver,flags,dir_fd=towers)
    finally: os.close(towers)
finally: os.close(root)
try:
    info=os.fstat(fd)
    if info.st_uid!=os.geteuid() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)&0o077: raise SystemExit("watchtower settings directory must be owner-private")
    try: old=os.stat(name,dir_fd=fd,follow_symlinks=False)
    except FileNotFoundError: old=None
    if old is not None and (not stat.S_ISREG(old.st_mode) or old.st_uid!=os.geteuid() or old.st_nlink!=1): raise SystemExit("refusing unsafe watchtower settings destination")
    version=subprocess.run([binary,"--version"],capture_output=True,text=True,timeout=15,check=True).stdout.strip().split(maxsplit=1)[0]
    match=__import__("re").fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version)
    if not match or not ((2, 1, 240) <= tuple(map(int, match.groups())) < (2, 2, 0)):
        raise SystemExit("Claude capability drift")
    real=os.path.realpath(binary); bi=os.stat(real); proof=path+".capability.json"
    proof_name=name+".capability.json"; proof_tmp=proof_name+".tmp"
    try:
        proof_fd=os.open(proof_tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600,dir_fd=fd)
        try:
            payload=json.dumps({"version":version,"binary":real,"identity":[bi.st_dev,bi.st_ino]}).encode()
            os.write(proof_fd,payload); os.fsync(proof_fd)
        finally: os.close(proof_fd)
        os.replace(proof_tmp,proof_name,src_dir_fd=fd,dst_dir_fd=fd)
    finally:
        try: os.unlink(proof_tmp,dir_fd=fd)
        except FileNotFoundError: pass
    command=shlex.join(["env","ROZORO_ROLE=watchtower",f"ROZORO_DRIVER_ID={driver}",f"ROZORO_SESSION_ID={session}",f"ROZORO_NATIVE_SESSION_ID={native}",f"ROZORO_HERDR_PANE_ID={pane}",f"ROZORO_HOME={home}","python3",hook,"--claude-binary",binary,"--capability-proof",proof])
    entry=[{"hooks":[{"type":"command","command":command,"timeout":2}]}]
    data=(json.dumps({"hooks":{e:entry for e in ("SessionStart","UserPromptSubmit","SubagentStart","SubagentStop","Stop","SessionEnd")}},sort_keys=True,separators=(",",":"))+"\n").encode()
    tmp=".claude-watchtower-"+secrets.token_hex(12)+".tmp"
    try:
        out=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600,dir_fd=fd)
        try:
            view=memoryview(data)
            while view: view=view[os.write(out,view):]
            os.fsync(out)
        finally: os.close(out)
        os.replace(tmp,name,src_dir_fd=fd,dst_dir_fd=fd); os.fsync(fd)
    finally:
        try: os.unlink(tmp,dir_fd=fd)
        except FileNotFoundError: pass
finally: os.close(fd)
PY
}

# Generate a task-local Claude settings overlay. It is passed explicitly with
# --settings and never mutates user or project Claude configuration.
rzr_claude_event_settings() {  # <task-id> <exact-session-id>
  local task_id="$1" session_id="$2" target
  target="$(rzr_task_dir "$task_id")/claude-event-settings.json"
  local binary; binary="$(command -v claude)" || return 1
  python3 - "$target" "$RZR_REPO/hooks/claude-rozoro-event.py" "$RZR_HOME" "$task_id" "$session_id" "$binary" <<'PY' || return 1
import json, os, secrets, shlex, stat, subprocess, sys
path, hook, home, task, session, binary = sys.argv[1:]
parent, name = os.path.split(path)
flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
dirfd = os.open(parent, flags)
try:
    info = os.fstat(dirfd)
    if info.st_uid != os.geteuid() or not stat.S_ISDIR(info.st_mode):
        raise SystemExit("refusing unowned Claude settings directory")
    os.fchmod(dirfd, 0o700)
    if stat.S_IMODE(os.fstat(dirfd).st_mode) != 0o700:
        raise SystemExit("Claude settings directory is not private")
    try:
        final = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        final = None
    if final is not None and (not stat.S_ISREG(final.st_mode) or final.st_uid != os.geteuid()):
        raise SystemExit("refusing unsafe Claude settings destination")
    version=subprocess.run([binary,"--version"],capture_output=True,text=True,timeout=15,check=True).stdout.strip().split(maxsplit=1)[0]
    match=__import__("re").fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version)
    if not match or not ((2, 1, 240) <= tuple(map(int, match.groups())) < (2, 2, 0)):
        raise SystemExit("Claude capability drift")
    real=os.path.realpath(binary); bi=os.stat(real); proof=path+".capability.json"
    try:
        with open(proof+".tmp","w") as out: json.dump({"version":version,"binary":real,"identity":[bi.st_dev,bi.st_ino]},out); out.flush(); os.fsync(out.fileno())
        os.chmod(proof+".tmp",0o600); os.replace(proof+".tmp",proof)
    finally:
        try: os.unlink(proof+".tmp")
        except FileNotFoundError: pass
    command = shlex.join([
        "env",  "ROZORO_ROLE=crew",
        f"ROZORO_TASK_ID={task}", f"ROZORO_SESSION_ID={session}",
        f"ROZORO_HOME={home}", "python3", hook, "--claude-binary", binary,
        "--capability-proof", proof,
    ])
    entry = [{"hooks": [{"type": "command", "command": command, "timeout": 2}]}]
    settings = {"hooks": {event: entry for event in (
        "SessionStart", "UserPromptSubmit", "SubagentStart", "SubagentStop", "Stop", "SessionEnd"
    )}}
    data = (json.dumps(settings, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = ".claude-settings-" + secrets.token_hex(12) + ".tmp"
    file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, file_flags, 0o600, dir_fd=dirfd)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        os.fsync(dirfd)
    finally:
        try: os.unlink(temporary, dir_fd=dirfd)
        except FileNotFoundError: pass
finally:
    os.close(dirfd)
PY
  printf '%s' "$target"
}

rzr_codex_hook_args() {  # <task-id>
  local task="$1" command
  command="$(printf 'env ROZORO_HOME=%q ROZORO_TASK_ID=%q python3 %q' "$RZR_HOME" "$task" "$RZR_REPO/hooks/codex-rozoro-event.py")"
  local event value
  for event in SessionStart UserPromptSubmit Stop SessionEnd; do
    value="$(python3 - "$command" <<'PY'
import json,sys
print('[{hooks=[{type="command",command='+json.dumps(sys.argv[1])+',timeout=2}]}]')
PY
)"
    printf '%s\0%s\0' --config "hooks.$event=$value"
  done
  printf '%s\0' --dangerously-bypass-hook-trust
}

rzr_harness_args() {  # <harness> <model> <effort> <permission-mode> <sysprompt-file> [session-id] [fast] [task-id]
  local harness="$1" model="$2" effort="$3" permmode="$4" sysfile="$5" session_id="${6:-}" fast="${7:-false}" task_id="${8:-}"
  rzr_profile_validate "$harness" "$model" "$effort" "$fast"
  case "$harness" in
    claude)
      [ -n "$model" ]    && printf '%s\0%s\0' --model "$model"
      [ -n "$session_id" ] && printf '%s\0%s\0' --session-id "$session_id"
      [ -n "$effort" ]   && printf '%s\0%s\0' --effort "$effort"
      [ -n "$permmode" ] && printf '%s\0%s\0' --permission-mode "$permmode"
      [ -n "$sysfile" ]  && printf '%s\0%s\0' --append-system-prompt-file "$sysfile"
      ;;
    codex)  # codex --yolo --model <m> --config model_reasoning_effort=<e> [priority tier]
      printf '%s\0' --yolo
      [ -n "$model" ]    && printf '%s\0%s\0' --model "$model"
      [ -n "$effort" ]   && printf '%s\0%s\0' --config "model_reasoning_effort=$effort"
      [ "$fast" = true ] && printf '%s\0%s\0' --config service_tier=priority
      [ -z "$task_id" ] || rzr_codex_hook_args "$task_id"
      ;;
    copilot)
      printf '%s\0%s\0%s\0%s\0' --no-auto-update --autopilot --yolo --no-ask-user
      [ -n "$model" ]      && printf '%s\0%s\0' --model "$model"
      [ -n "$effort" ]     && printf '%s\0%s\0' --effort "$effort"
      [ -n "$session_id" ] && printf '%s\0%s\0' --session-id "$session_id"
      ;;
    pi)
      # Managed Pi crews explicitly load the checkout-owned event-bus producer,
      # even when their cwd is an arbitrary target repository.
      printf '%s\0%s\0' --extension "$RZR_BIN/../.pi/extensions/rozoro-watchtower.ts"
      [ -n "$model" ]      && printf '%s\0%s\0' --model "$model"
      [ -n "$effort" ]     && printf '%s\0%s\0' --thinking "$effort"
      [ -n "$permmode" ]   && printf '%s\0' --approve
      [ -n "$sysfile" ]    && printf '%s\0%s\0' --append-system-prompt "$sysfile"
      [ -n "$session_id" ] && printf '%s\0%s\0' --session-id "$session_id"
      ;;
    *) return 1 ;;
  esac
  # Known harness: succeed regardless of which optional fields were empty (a
  # trailing false `[ -n "" ]` test must not become the function's exit status).
  return 0
}

# --- task metadata (KEY=VALUE, one per line) -------------------------------
rzr_meta_path() { rzr_validate_task_component "$1"; printf '%s/%s.meta' "$RZR_STATE" "$1"; }

rzr_meta_set() {  # <id> <key> <value>
  local f; f=$(rzr_meta_path "$1")
  local tmp; tmp="$f.tmp.$$"
  { [ -f "$f" ] && grep -v "^$2=" "$f"; echo "$2=$3"; } > "$tmp" 2>/dev/null || true
  mv "$tmp" "$f"
}

rzr_meta_get() {  # <id> <key>
  local f; f=$(rzr_meta_path "$1")
  [ -f "$f" ] || return 1
  sed -n "s/^$2=//p" "$f" | head -n 1
}

rzr_task_exists() { [ -f "$(rzr_meta_path "$1")" ]; }

rzr_task_ids() {  # list known task ids
  local f
  for f in "$RZR_STATE"/*.meta; do
    [ -e "$f" ] || continue
    basename "$f" .meta
  done
}

rzr_pane_of() {  # <id> -> pane id, or fail
  rzr_meta_get "$1" pane || rzr_die "task '$1' has no recorded pane (spawn it first)"
}

# --- observed status (single token, on disk, atomic) -----------------------
# The last agent status a watcher saw for a task, mirrored to disk so the DRIVER
# can reconcile crew state without attaching its own watcher (rzr_status_get).
# Under the single-driver model there is one writer per file; the write is
# atomic (temp + mv) and the value is an idempotent token, so even overlapping
# watchers converge (last-writer-wins) with no torn reads and no lock needed.
# This replaces the in-process associative-array state the watcher used to hold
# (which also made it require bash 4+; disk state is bash-3.2 safe).
rzr_status_path() { printf '%s/%s.status' "$RZR_STATE" "$1"; }

rzr_status_set() {  # <id> <status>
  local f tmp; f=$(rzr_status_path "$1"); tmp="$f.tmp.$$"
  printf '%s\n' "$2" > "$tmp" && mv "$tmp" "$f"
}

rzr_status_get() {  # <id> -> last observed status, or fail if never seen
  local f; f=$(rzr_status_path "$1")
  [ -f "$f" ] || return 1
  head -n 1 "$f"
}

# Live agent status of a pane. One of: idle working done blocked unknown
# (a real agent), shell (pane exists, no agent - e.g. --no-agent), or gone
# (pane no longer exists).
rzr_agent_snapshot() {  # <pane> -> status<TAB>ordered-revision
  local out
  if out=$(rzr_herdr agent get "$1" 2>/dev/null); then
    printf '%s' "$out" | jq -r '[.result.agent_status // .result.agent.agent_status // .agent_status // "unknown", (.result.state_change_seq // .result.agent.state_change_seq // .state_change_seq // "")] | @tsv' 2>/dev/null || printf 'unknown\t\n'
    return
  fi
  if rzr_herdr pane get "$1" >/dev/null 2>&1; then printf 'shell\t\n'; else printf 'gone\t\n'; fi
}

rzr_agent_status() { rzr_agent_snapshot "$1" | cut -f1; }

# `herdr agent start` can return agent_not_ready after it has successfully
# claimed the pane and launched the harness, while the harness is still crossing
# its startup readiness gate. In that case starting it again risks colliding with
# the agent that already owns the pane; wait for that launch to become interactive
# instead. Returns success only for a real, interactive agent.
rzr_wait_agent_ready() {  # <pane> [attempts]
  local pane="$1" attempts="${2:-20}" out ready attempt=0
  while [ "$attempt" -lt "$attempts" ]; do
    if out=$(rzr_herdr agent get "$pane" 2>/dev/null); then
      ready=$(printf '%s' "$out" | jq -r '
        (.result.agent // .result // .) as $a |
        if ($a.interactive_ready // false) == true then "true" else "false" end
      ' 2>/dev/null || echo false)
      [ "$ready" = true ] && return 0
    fi
    sleep 0.5
    attempt=$((attempt + 1))
  done
  return 1
}

# --- watchtower registration + durable wake ledger -------------------------
# A watchtower (the resident driver session) registers ONE validated delivery
# target, then a background `rzr-watch --wake` records actionable crew edges into
# a durable per-driver ledger and delivers a fixed, content-free nudge through the
# registered backend. State lives under watchtowers/<driver-id>/ so a crashed or
# restarted watcher never loses a pending notification.
#
# Why registration (not env-var sniffing): a Claude or Pi process launched from a
# Codex environment inherits a STALE CODEX_THREAD_ID and would otherwise wake the
# wrong conversation. Registration pins an immutable identity whose declared
# harness is validated against live herdr state, and auto backend selection
# refuses to guess from raw environment variables.
#
# Files:
#   target.json  - driver identity + backend (written once by rzr-register)
#   pending.json - generation/delivered + affected tasks (locked read-modify-write;
#                  overlapping watchers for one driver are supported)
#   ack          - last generation the driver reconciled (written by reconcile)
#
# Delivery is at-least-once and coalesced. Let g=generation (bumped on every
# actionable edge), d=delivered (last generation nudged), a=ack (last generation
# reconciled). The watcher delivers a nudge iff  g > a  AND  d <= a : at most one
# outstanding (delivered-but-unacked) nudge exists no matter how many edges burst,
# and once the driver acks, any edges that arrived meanwhile deliver a fresh nudge.
# generation is persisted BEFORE the backend call, so a crash between deliver and
# recording success re-delivers (a duplicate fixed nudge is acceptable; a lost
# actionable edge is not).
# shellcheck disable=SC2034 # Consumed by the separate rzr-watch command.
RZR_WAKE_MESSAGE="Rozoro notification pending; run ./bin/rozoro reconcile."

rzr_watchtowers_dir() { printf '%s/watchtowers' "$RZR_HOME"; }
rzr_driver_dir() {  # <driver-id>
  rzr_validate_task_component "$1" "driver id"
  printf '%s/%s' "$(rzr_watchtowers_dir)" "$1"
}

# Create/validate the watchtower root and one driver directory without following
# either final component. Existing entries must be owned real directories.
rzr_driver_dir_prepare() {  # <driver-id> -> path
  local id="$1"; rzr_validate_task_component "$id" "driver id"
  RZR_DRIVER_HOME="$RZR_HOME" RZR_DRIVER_ID="$id" python3 - <<'PY'
import os, stat
home=os.environ["RZR_DRIVER_HOME"]
def directory(parent, name):
    try: info=os.stat(name,dir_fd=parent,follow_symlinks=False)
    except FileNotFoundError:
        os.mkdir(name,0o700,dir_fd=parent); info=os.stat(name,dir_fd=parent,follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid():
        raise SystemExit("unsafe watchtower directory")
    fd=os.open(name,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0),dir_fd=parent)
    os.fchmod(fd,0o700)
    return fd
root=os.open(home,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0))
try:
    towers=directory(root,"watchtowers")
    try:
        driver=directory(towers,os.environ["RZR_DRIVER_ID"]); os.close(driver)
    finally: os.close(towers)
finally: os.close(root)
print(os.path.join(home,"watchtowers",os.environ["RZR_DRIVER_ID"]))
PY
}

# A filesystem-safe, stable driver id derived from an immutable backend identity
# (a herdr pane "wX:pN" or a Codex thread id). Same identity -> same ledger dir
# across restarts, so a resumed watcher reattaches instead of orphaning pending.
rzr_driver_id_for() {  # <backend> <identity> -> driver-id
  RZR_DRV_BACKEND="$1" RZR_DRV_IDENTITY="$2" python3 - <<'PY'
import os, re
backend = os.environ["RZR_DRV_BACKEND"]
ident = os.environ["RZR_DRV_IDENTITY"]
safe = re.sub(r'[^A-Za-z0-9._-]', '_', ident).strip('_') or "x"
print(f"{backend}-{safe}"[:120])
PY
}

# Live harness + readiness of a herdr pane, so registration can prove the declared
# driver harness actually matches the pane before pinning it as the wake target.
# One line: "<harness> <interactive_ready:true|false>" (harness empty if unknown).
#
# Real herdr (0.8.x) reports the harness in a field literally named `agent` under
# `.result.agent` (e.g. .result.agent.agent == "claude"), alongside agent_status
# and interactive_ready. Accept a few shapes so a schema tweak degrades to "unknown
# harness" (registration refuses) rather than a wrong match.
rzr_pane_harness_ready() {  # <pane>
  local out
  out=$(rzr_herdr agent get "$1" 2>/dev/null) || { printf ' false\n'; return 0; }
  printf '%s' "$out" | jq -r '
    (.result.agent // .result // .) as $a |
    (($a.agent // $a.kind // $a.harness // "") | ascii_downcase) as $h |
    (($a.interactive_ready // false) | tostring) as $ready |
    "\($h) \($ready)"' 2>/dev/null || printf ' false\n'
}

# Write a file atomically with user-only permissions (temp in the same dir + mv).
rzr_write_private() {  # <path>  (content on stdin)
  local path="$1" tmp; tmp="$path.tmp.$$"
  ( umask 077; cat > "$tmp" ) && chmod 600 "$tmp" 2>/dev/null; mv "$tmp" "$path"
}

# Read one field from a driver's ledger integers (generation/delivered/ack).
# ack lives in its own single-writer file; generation/delivered live in
# pending.json. Missing/malformed -> 0, so a fresh ledger reads as all-zero.
rzr_ledger_int() {  # <driver-dir> <generation|delivered|ack>
  local dir="$1" field="$2"
  if [ "$field" = ack ]; then
    local v; v=$(cat "$dir/ack" 2>/dev/null || echo 0)
    case "$v" in ''|*[!0-9]*) echo 0 ;; *) echo "$v" ;; esac
    return 0
  fi
  RZR_LEDGER_PENDING="$dir/pending.json" RZR_LEDGER_FIELD="$field" python3 - <<'PY'
import json, os
try:
    d = json.load(open(os.environ["RZR_LEDGER_PENDING"]))
    print(int(d.get(os.environ["RZR_LEDGER_FIELD"], 0)))
except Exception:
    print(0)
PY
}

# Record one semantic action edge. An edge ID makes overlapping watchers
# idempotent while legacy callers without an edge ID retain per-call bumps.
rzr_ledger_bump() {  # <driver-dir> <task-id> <status> [edge-id]
  local dir="$1"
  mkdir -p "$(rzr_watchtowers_dir)"; chmod 700 "$(rzr_watchtowers_dir)" 2>/dev/null || true
  RZR_LEDGER_PENDING="$dir/pending.json" RZR_LEDGER_ID="$2" RZR_LEDGER_STATUS="$3" RZR_LEDGER_EDGE="${4:-}" \
  RZR_LEDGER_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)" python3 - <<'PY'
import fcntl, json, os
p = os.environ["RZR_LEDGER_PENDING"]
authority_fd = os.open(os.path.join(os.path.dirname(os.path.dirname(p)), ".authority.lock"), os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(authority_fd, fcntl.LOCK_SH)
os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
if os.path.lexists(os.path.join(os.path.dirname(p), ".event-bus-authority")):
    raise SystemExit("legacy generation refused: driver is event-bus authoritative; explicitly disable authority before fallback")
lock_fd = os.open(p + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(lock_fd, fcntl.LOCK_EX)
try:    d = json.load(open(p))
except Exception:
    d = {"schema": 1, "generation": 0, "delivered": 0, "tasks": {},
         "delivery_state": "idle", "retries": 0, "last_error": "", "updated": ""}
task = d.setdefault("tasks", {}).get(os.environ["RZR_LEDGER_ID"], {})
edge = os.environ["RZR_LEDGER_EDGE"]
if edge and task.get("edge_id") == edge:
    os.close(lock_fd)
    raise SystemExit(0)
d["generation"] = int(d.get("generation", 0)) + 1
d["tasks"][os.environ["RZR_LEDGER_ID"]] = {
    "status": os.environ["RZR_LEDGER_STATUS"], "edge_id": edge or None,
    "updated": os.environ["RZR_LEDGER_TS"]}
d["updated"] = os.environ["RZR_LEDGER_TS"]
tmp = p + ".tmp.%d" % os.getpid()
os.umask(0o077)
json.dump(d, open(tmp, "w"), indent=2)
os.replace(tmp, p)
os.close(lock_fd)
os.close(authority_fd)
PY
}

# Update the watcher-owned pending.json delivery bookkeeping after a delivery
# attempt: mark the exact attempted generation delivered on success, or record a
# soft failure/defer reason without advancing delivered (so it retries).
rzr_ledger_record() {  # <driver-dir> <state> [error-text] [attempted-generation]
  local dir="$1" state="$2" err="${3:-}" attempted="${4:-}"
  if [ "$state" = delivered ]; then
    case "$attempted" in ''|*[!0-9]*) rzr_die "delivered ledger record requires the attempted generation" ;; esac
  fi
  RZR_LEDGER_PENDING="$dir/pending.json" RZR_LEDGER_STATE="$state" RZR_LEDGER_ERR="$err" \
  RZR_LEDGER_ATTEMPTED="$attempted" \
  RZR_LEDGER_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)" python3 - <<'PY'
import fcntl, json, os
p = os.environ["RZR_LEDGER_PENDING"]
authority_fd = os.open(os.path.join(os.path.dirname(os.path.dirname(p)), ".authority.lock"), os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(authority_fd, fcntl.LOCK_SH)
if os.path.lexists(os.path.join(os.path.dirname(p), ".event-bus-authority")):
    raise SystemExit("legacy delivery refused: driver is event-bus authoritative; explicitly disable authority before fallback")
lock_fd = os.open(p + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(lock_fd, fcntl.LOCK_EX)
try:    d = json.load(open(p))
except Exception:
    d = {"schema": 1, "generation": 0, "delivered": 0, "tasks": {}, "retries": 0}
state = os.environ["RZR_LEDGER_STATE"]
if state == "delivered":
    # Record exactly what this backend call attempted, not a newer generation
    # that may have arrived while the call was in flight. Keep this monotonic in
    # case overlapping calls complete out of order.
    attempted = int(os.environ["RZR_LEDGER_ATTEMPTED"])
    d["delivered"] = max(int(d.get("delivered", 0)), attempted)
    d["last_error"] = ""
else:
    d["retries"] = int(d.get("retries", 0)) + 1
    d["last_error"] = os.environ["RZR_LEDGER_ERR"]
d["delivery_state"] = state
d["updated"] = os.environ["RZR_LEDGER_TS"]
tmp = p + ".tmp.%d" % os.getpid()
os.umask(0o077)
json.dump(d, open(tmp, "w"), indent=2)
os.replace(tmp, p)
os.close(lock_fd)
os.close(authority_fd)
PY
}

# Coalescing gate: deliver iff generation > ack AND delivered <= ack.
rzr_ledger_should_deliver() {  # <driver-dir> -> 0 (yes) / 1 (no)
  local dir="$1" g a d
  [ ! -e "$dir/.event-bus-authority" ] && [ ! -L "$dir/.event-bus-authority" ] || return 1
  g=$(rzr_ledger_int "$dir" generation); a=$(rzr_ledger_int "$dir" ack); d=$(rzr_ledger_int "$dir" delivered)
  [ "$g" -gt "$a" ] && [ "$d" -le "$a" ]
}

# Advance the driver's ack to the given generation (single-writer file, atomic).
rzr_ledger_ack() {  # <driver-dir> <generation>
  local dir="$1"; mkdir -p "$(rzr_watchtowers_dir)"; chmod 700 "$(rzr_watchtowers_dir)" 2>/dev/null || true
  RZR_LEDGER_ACK="$dir/ack" RZR_LEDGER_VALUE="$2" python3 - <<'PY'
import fcntl, json, os
p=os.environ["RZR_LEDGER_ACK"]; value=int(os.environ["RZR_LEDGER_VALUE"])
authority_fd=os.open(os.path.join(os.path.dirname(os.path.dirname(p)), ".authority.lock"),os.O_CREAT|os.O_RDWR,0o600)
fcntl.flock(authority_fd,fcntl.LOCK_SH)
os.makedirs(os.path.dirname(p),mode=0o700,exist_ok=True)
if os.path.lexists(os.path.join(os.path.dirname(p), ".event-bus-authority")):
    raise SystemExit("legacy ACK refused: driver is event-bus authoritative; explicitly disable authority before fallback")
pending=os.path.join(os.path.dirname(p),"pending.json")
lock_fd=os.open(pending+".lock",os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(lock_fd,fcntl.LOCK_EX)
try: data=json.load(open(pending))
except FileNotFoundError: data={"schema":1,"generation":0,"delivered":0,"tasks":{}}
if value>int(data.get("generation",0)): raise SystemExit("legacy ACK exceeds generation")
data["delivered"]=max(int(data.get("delivered",0)),value)
os.umask(0o077); pending_tmp=pending+f".tmp.{os.getpid()}"
with open(pending_tmp,"w") as stream: json.dump(data,stream,indent=2); stream.flush(); os.fsync(stream.fileno())
os.replace(pending_tmp,pending)
tmp=p+f".tmp.{os.getpid()}"
with open(tmp,"w") as stream: stream.write(str(value)+"\n"); stream.flush(); os.fsync(stream.fileno())
os.replace(tmp,p); os.close(lock_fd); os.close(authority_fd)
PY
}

rzr_target_field() {  # <driver-dir> <field>
  local dir="$1" field="$2" driver json
  driver="${dir##*/}"
  [ "$dir" = "$(rzr_driver_dir "$driver")" ] || return 1
  json="$(rzr_watchtower_target_json "$driver" || true)"
  [ -n "$json" ] || return 1
  printf '%s' "$json" | jq -r --arg k "$field" '.[$k] // empty' 2>/dev/null
}

# Resolve the registered wake target for `--wake`. With an explicit id, require it
# is registered. Otherwise derive candidate driver ids from the CURRENT
# environment's immutable identities and accept the single registered match. Never
# guess a backend from a bare environment variable: an unregistered or ambiguous
# environment is a hard error (register first).
rzr_resolve_driver_dir() {  # [explicit-driver-id] -> prints driver dir
  local explicit="${1:-}" candidate target existing duplicate
  local -a matches=()
  if [ -n "$explicit" ]; then
    target="$(rzr_watchtower_target_json "$explicit" || true)"
    [ -n "$target" ] || rzr_die "driver '$explicit' is not registered (run: ./bin/rozoro register --harness <h>)"
    printf '%s' "$(rzr_driver_dir "$explicit")"; return 0
  fi
  while IFS= read -r target; do
    candidate="$(printf '%s' "$target" | jq -r '.driver_id')"
    if { [ -n "${HERDR_PANE_ID:-}" ] && rzr_dispatcher_candidate_matches "$target" herdr "$HERDR_PANE_ID"; } ||
       { [ -n "${CODEX_THREAD_ID:-}" ] && rzr_dispatcher_candidate_matches "$target" codex "$CODEX_THREAD_ID"; }; then
      duplicate=0
      if [ "${#matches[@]}" -gt 0 ]; then
        for existing in "${matches[@]}"; do [ "$existing" = "$candidate" ] && duplicate=1; done
      fi
      [ "$duplicate" -eq 1 ] || matches+=("$candidate")
    fi
  done < <(rzr_watchtower_target_json || true)
  case ${#matches[@]} in
    0) rzr_die "--wake found no registered watchtower for this environment (run: ./bin/rozoro register --harness <h>)" ;;
    1) printf '%s' "$(rzr_driver_dir "${matches[0]}")" ;;
    *) rzr_die "--wake is ambiguous: multiple registered targets match this environment; pass --driver <id>" ;;
  esac
}

# --- home lock (atomic mkdir, stale-pid reclaim) ---------------------------
# Serializes mutating operations (spawn) so two orchestrators never race on the
# same home. Read-only tools (list, watch) do not take it.
RZR_LOCK_DIR="$RZR_STATE/.lock"

rzr_lock_acquire() {  # [<max-wait-seconds>]  (0/absent = try once)
  local max="${1:-0}" waited=0 held
  while :; do
    if mkdir "$RZR_LOCK_DIR" 2>/dev/null; then
      echo $$ > "$RZR_LOCK_DIR/pid"
      date -u +%Y-%m-%dT%H:%M:%SZ > "$RZR_LOCK_DIR/since" 2>/dev/null || true
      return 0
    fi
    held=$(cat "$RZR_LOCK_DIR/pid" 2>/dev/null || true)
    if [ -n "$held" ] && ! kill -0 "$held" 2>/dev/null; then
      # holder is dead - reclaim and retry immediately
      rm -rf "$RZR_LOCK_DIR"
      continue
    fi
    if [ "$max" -le 0 ] || [ "$waited" -ge "$max" ]; then
      echo "rzr: home lock held by pid ${held:-?}" >&2
      return 1
    fi
    sleep 1; waited=$((waited + 1))
  done
}

rzr_lock_release() {
  local held; held=$(cat "$RZR_LOCK_DIR/pid" 2>/dev/null || true)
  [ "$held" = "$$" ] && rm -rf "$RZR_LOCK_DIR"
  return 0
}

# Run <fn/cmd...> while holding the home lock, then always release it.
rzr_with_lock() {  # <max-wait> <cmd...>
  local max="$1"; shift
  rzr_lock_acquire "$max" || return 1
  local rc=0
  "$@" || rc=$?
  rzr_lock_release
  return "$rc"
}
