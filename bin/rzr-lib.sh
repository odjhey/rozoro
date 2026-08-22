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
mkdir -p "$RZR_STATE"

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
# A preset bundles HOW a crew agent is booted - harness, model, effort, and any
# standing crew RULES - never WHAT its task is (the task prompt is always passed
# verbatim). Presets are one JSON file per name under $RZR_HOME/crew/<name>.json.
# `rules` are crew-behavioral (e.g. "open a draft PR, never push"), deliberately
# distinct from REPO rules, which the agent auto-loads from its --cwd.
RZR_CREW="$RZR_HOME/crew"

rzr_crew_path() { printf '%s/%s.json' "$RZR_CREW" "$1"; }
rzr_crew_exists() { [ -f "$(rzr_crew_path "$1")" ]; }

# The personal default file is authoritative when present. If it is absent,
# resolve `default` to an in-memory fallback without creating or changing any
# file under $RZR_HOME. Claude is the no-flag fallback; an explicit Codex harness
# gets the lower-cost gpt-5.6-sol/low profile.
rzr_crew_builtin_default() {
  case "${1:-claude}" in
    claude) cat <<'JSON'
{
  "harness": "claude",
  "model": "sonnet",
  "permission_mode": "auto",
  "effort": "",
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
  "rules": []
}
JSON
      ;;
    *) jq -n --arg harness "$1" '{harness: $harness, model: "", permission_mode: "auto", effort: "", rules: []}' ;;
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

rzr_crew_field() {  # <preset> <field> -> value, or empty
  rzr_crew_json "$1" | jq -r --arg k "$2" '.[$k] // empty' 2>/dev/null
}

rzr_crew_rules() {  # <preset> -> rules joined by newlines (empty if none)
  rzr_crew_json "$1" | jq -r '(.rules // []) | join("\n")' 2>/dev/null
}

# Map a resolved profile to the launch args a harness expects AFTER the `--` in
# `herdr agent start ... -- <arg>...`. Emits NUL-separated args (so a rule value
# containing newlines survives being read back into an array; bash-3.2 safe via
# `read -d ''`). Returns 1 for an unknown harness so a preset can never boot one
# with the wrong flags.
#
# `permmode` is a generic "run autonomously" signal: when non-empty, claude
# passes its literal value (--permission-mode <v>), copilot uses --mode
# autopilot --allow-all, and pi uses --approve so project-local resources load
# without an interactive trust gate. Codex is deliberately always launched with
# --yolo; its permmode input cannot weaken that spawner invariant. `effort` maps
# to a native flag for claude, Pi's --thinking, and Codex's
# model_reasoning_effort config override.
#
# The 5th arg is a PATH to a rendered system-prompt file (handoff protocol +
# preset rules). Claude takes it through --append-system-prompt-file; Pi's
# --append-system-prompt accepts either text or a file path. The 6th optional arg
# is a preallocated harness session id (currently used by Pi for exact linking).
#
# Verified on this machine: Claude, Codex, and Pi argument parsing. Wired from
# the operator's known invocation but NOT verified here: Copilot.
rzr_harness_args() {  # <harness> <model> <effort> <permission-mode> <sysprompt-file> [session-id]
  local harness="$1" model="$2" effort="$3" permmode="$4" sysfile="$5" session_id="${6:-}"
  case "$harness" in
    claude)
      [ -n "$model" ]    && printf '%s\0%s\0' --model "$model"
      [ -n "$effort" ]   && printf '%s\0%s\0' --effort "$effort"
      [ -n "$permmode" ] && printf '%s\0%s\0' --permission-mode "$permmode"
      [ -n "$sysfile" ]  && printf '%s\0%s\0' --append-system-prompt-file "$sysfile"
      ;;
    codex)  # codex --yolo --model <m> --config model_reasoning_effort=<e> "prompt"
      printf '%s\0' --yolo
      [ -n "$model" ]    && printf '%s\0%s\0' --model "$model"
      [ -n "$effort" ]   && printf '%s\0%s\0' --config "model_reasoning_effort=$effort"
      ;;
    copilot)  # copilot --model <m> --mode autopilot --allow-all "prompt"
      [ -n "$model" ]    && printf '%s\0%s\0' --model "$model"
      [ -n "$permmode" ] && printf '%s\0%s\0%s\0' --mode autopilot --allow-all
      ;;
    pi)
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
rzr_agent_status() {  # <pane>
  local out
  if out=$(rzr_herdr agent get "$1" 2>/dev/null); then
    printf '%s' "$out" \
      | jq -r '.result.agent_status // .result.agent.agent_status // .agent_status // "unknown"' 2>/dev/null \
      | grep . || echo unknown
    return
  fi
  if rzr_herdr pane get "$1" >/dev/null 2>&1; then echo shell; else echo gone; fi
}

# --- unlanded-work guard (teardown safety) ---------------------------------
# A crew's --cwd may hold work teardown would otherwise discard silently:
# uncommitted/untracked changes, or commits with no pushed upstream. One reason
# per line on stdout; nothing printed means clean, not a git repo, or gone.
rzr_unlanded_reasons() {  # <cwd>
  local cwd="$1" upstream ahead
  [ -d "$cwd" ] || return 0
  git -C "$cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  [ -n "$(git -C "$cwd" status --porcelain 2>/dev/null)" ] && echo "uncommitted or untracked changes"
  if upstream=$(git -C "$cwd" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
    ahead=$(git -C "$cwd" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
    [ "$ahead" -gt 0 ] && echo "$ahead unpushed commit(s) (ahead of $upstream)"
  else
    git -C "$cwd" rev-parse HEAD >/dev/null 2>&1 && echo "no upstream tracking branch (commits may be unpushed)"
  fi
  return 0
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
