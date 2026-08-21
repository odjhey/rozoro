#!/usr/bin/env bash
# fl-lib.sh - shared helpers for firstmate-light.
#
# A deliberately tiny orchestrator over the herdr terminal backend. Every task
# is one herdr TAB holding one PANE running one agent. State lives on disk under
# state/, so a restart is a non-event. Sourced by the fl-* commands; not run
# directly.
#
# Concepts:
#   task id   - caller-chosen short slug (e.g. "t1", "fixlogin"); names state/<id>.meta
#   pane      - herdr pane id "wX:pN"; the terminal the agent runs in (authority)
#   tab       - herdr tab id "wX:tN"; the clickable container for the pane
#
# Requires: herdr (0.8.x), jq.

set -euo pipefail

FL_LIB_SRC="${BASH_SOURCE[0]}"
FL_BIN="$(cd "$(dirname "$FL_LIB_SRC")" && pwd)"
# Home for all on-disk state. Defaults to ~/.rozoro so the driver's state lives
# outside any one checkout and survives a restart. Precedence: ROZORO_HOME (the
# rozoro name) > FL_HOME (legacy) > default.
FL_HOME="${ROZORO_HOME:-${FL_HOME:-$HOME/.rozoro}}"
FL_STATE="$FL_HOME/state"
# Per-task folders: the durable record of a task's INPUT (brief.md), append-only
# OUTPUT (handoff.md), and resume link (session.json). Data, so it lives under
# FL_HOME with state/ — survives teardown, never enters the code repo.
FL_TASKS="$FL_HOME/tasks"
# Shipped seeds (the handoff brief template). Code, so it resolves relative to
# this checkout, not FL_HOME. Override with FL_TEMPLATES.
FL_REPO="$(cd "$FL_BIN/.." && pwd)"
FL_TEMPLATES="${FL_TEMPLATES:-$FL_REPO/templates}"
mkdir -p "$FL_STATE"

# Path to a task's durable folder (does not create it).
fl_task_dir() { printf '%s/%s' "$FL_TASKS" "$1"; }

fl_die() { echo "fl: $*" >&2; exit 1; }

command -v herdr >/dev/null 2>&1 || fl_die "herdr not found on PATH"
command -v jq    >/dev/null 2>&1 || fl_die "jq not found on PATH"

# --- herdr invocation ------------------------------------------------------
# Talks to the running herdr server over its control socket. A single local
# server needs no --session; set FL_SESSION to target a named one.
fl_herdr() {  # <herdr args...>
  if [ -n "${FL_SESSION:-}" ]; then
    herdr --session "$FL_SESSION" "$@"
  else
    herdr "$@"
  fi
}

# The workspace new tabs are created in. Defaults to the orchestrator's own
# herdr workspace so every task tab is a sibling you can click to (the flat
# "tabs" layout). Override with FL_WORKSPACE.
fl_workspace() { printf '%s' "${FL_WORKSPACE:-${HERDR_WORKSPACE_ID:-}}"; }

# Path to the herdr control socket (for the native pane.agent_status_changed
# push stream that fl-watch consumes). Resolves the named session's socket, or
# the single local server's when FL_SESSION is unset.
fl_socket_path() {
  if [ -n "${FL_SESSION:-}" ]; then
    herdr session list --json 2>/dev/null \
      | jq -r --arg n "$FL_SESSION" '.sessions[]? | select(.name==$n) | .socket_path // empty' 2>/dev/null | head -1
  else
    herdr session list --json 2>/dev/null \
      | jq -r '.sessions[0].socket_path // empty' 2>/dev/null | head -1
  fi
}

# The raw-socket event subscriber (wire transport for fl-watch). Ships alongside
# the bin/ scripts; requires python3 (stdlib only).
fl_eventwait_py() { printf '%s/herdr-eventwait.py' "$FL_BIN"; }

# --- crewmember presets (spawn profiles) -----------------------------------
# A preset bundles HOW a crew agent is booted - harness, model, effort, and any
# standing crew RULES - never WHAT its task is (the task prompt is always passed
# verbatim). Presets are one JSON file per name under $FL_HOME/crew/<name>.json.
# `rules` are crew-behavioral (e.g. "open a draft PR, never push"), deliberately
# distinct from REPO rules, which the agent auto-loads from its --cwd.
FL_CREW="$FL_HOME/crew"

fl_crew_path() { printf '%s/%s.json' "$FL_CREW" "$1"; }
fl_crew_exists() { [ -f "$(fl_crew_path "$1")" ]; }

# Create the built-in `default` preset on first use: sonnet claude, no rules
# (so the default crew is pure verbatim - nothing injected).
fl_crew_ensure_default() {
  mkdir -p "$FL_CREW"
  local f; f=$(fl_crew_path default)
  [ -f "$f" ] && return 0
  cat > "$f" <<'JSON'
{
  "harness": "claude",
  "model": "sonnet",
  "permission_mode": "auto",
  "effort": "",
  "rules": []
}
JSON
}

fl_crew_field() {  # <preset> <field> -> value, or empty
  local f; f=$(fl_crew_path "$1")
  [ -f "$f" ] || return 1
  jq -r --arg k "$2" '.[$k] // empty' "$f" 2>/dev/null
}

fl_crew_rules() {  # <preset> -> rules joined by newlines (empty if none)
  local f; f=$(fl_crew_path "$1")
  [ -f "$f" ] || return 1
  jq -r '(.rules // []) | join("\n")' "$f" 2>/dev/null
}

# Map a resolved profile to the launch args a harness expects AFTER the `--` in
# `herdr agent start ... -- <arg>...`. Emits NUL-separated args (so a rule value
# containing newlines survives being read back into an array; bash-3.2 safe via
# `read -d ''`). Returns 1 for an unknown harness so a preset can never boot one
# with the wrong flags.
#
# `permmode` is a generic "run autonomously" signal: when non-empty, claude
# passes its literal value (--permission-mode <v>), codex uses --yolo, and
# copilot uses --mode autopilot --allow-all. `effort` and `rules` are only
# expressible for claude today; other harnesses ignore them (a set `rules` on a
# non-claude preset warns, since it would silently not apply).
#
# Verified on this machine: claude. Wired from the operator's known invocations
# but NOT verified here: codex (not installed), copilot, pi.
fl_harness_args() {  # <harness> <model> <effort> <permission-mode> <rules-text>
  local harness="$1" model="$2" effort="$3" permmode="$4" rules="$5"
  case "$harness" in
    claude)
      [ -n "$model" ]    && printf '%s\0%s\0' --model "$model"
      [ -n "$effort" ]   && printf '%s\0%s\0' --effort "$effort"
      [ -n "$permmode" ] && printf '%s\0%s\0' --permission-mode "$permmode"
      [ -n "$rules" ]    && printf '%s\0%s\0' --append-system-prompt "$rules"
      ;;
    codex)  # codex --yolo --model <m> "prompt"
      [ -n "$permmode" ] && printf '%s\0' --yolo
      [ -n "$model" ]    && printf '%s\0%s\0' --model "$model"
      [ -n "$rules" ]    && echo "fl: harness 'codex' has no system-prompt flag; preset rules ignored" >&2
      ;;
    copilot)  # copilot --model <m> --mode autopilot --allow-all "prompt"
      [ -n "$model" ]    && printf '%s\0%s\0' --model "$model"
      [ -n "$permmode" ] && printf '%s\0%s\0%s\0' --mode autopilot --allow-all
      [ -n "$rules" ]    && echo "fl: harness 'copilot' has no system-prompt flag; preset rules ignored" >&2
      ;;
    pi)  # pi takes no launch flags; model/effort/permission/rules are ignored
      [ -n "$rules" ] && echo "fl: harness 'pi' takes no flags; preset rules ignored" >&2
      : ;;
    *) return 1 ;;
  esac
  # Known harness: succeed regardless of which optional fields were empty (a
  # trailing false `[ -n "" ]` test must not become the function's exit status).
  return 0
}

# --- task metadata (KEY=VALUE, one per line) -------------------------------
fl_meta_path() { printf '%s/%s.meta' "$FL_STATE" "$1"; }

fl_meta_set() {  # <id> <key> <value>
  local f; f=$(fl_meta_path "$1")
  local tmp; tmp="$f.tmp.$$"
  { [ -f "$f" ] && grep -v "^$2=" "$f"; echo "$2=$3"; } > "$tmp" 2>/dev/null || true
  mv "$tmp" "$f"
}

fl_meta_get() {  # <id> <key>
  local f; f=$(fl_meta_path "$1")
  [ -f "$f" ] || return 1
  sed -n "s/^$2=//p" "$f" | head -n 1
}

fl_task_exists() { [ -f "$(fl_meta_path "$1")" ]; }

fl_task_ids() {  # list known task ids
  local f
  for f in "$FL_STATE"/*.meta; do
    [ -e "$f" ] || continue
    basename "$f" .meta
  done
}

fl_pane_of() {  # <id> -> pane id, or fail
  fl_meta_get "$1" pane || fl_die "task '$1' has no recorded pane (spawn it first)"
}

# --- observed status (single token, on disk, atomic) -----------------------
# The last agent status a watcher saw for a task, mirrored to disk so the DRIVER
# can reconcile crew state without attaching its own watcher (fl_status_get).
# Under the single-driver model there is one writer per file; the write is
# atomic (temp + mv) and the value is an idempotent token, so even overlapping
# watchers converge (last-writer-wins) with no torn reads and no lock needed.
# This replaces the in-process associative-array state the watcher used to hold
# (which also made it require bash 4+; disk state is bash-3.2 safe).
fl_status_path() { printf '%s/%s.status' "$FL_STATE" "$1"; }

fl_status_set() {  # <id> <status>
  local f tmp; f=$(fl_status_path "$1"); tmp="$f.tmp.$$"
  printf '%s\n' "$2" > "$tmp" && mv "$tmp" "$f"
}

fl_status_get() {  # <id> -> last observed status, or fail if never seen
  local f; f=$(fl_status_path "$1")
  [ -f "$f" ] || return 1
  head -n 1 "$f"
}

# Live agent status of a pane. One of: idle working done blocked unknown
# (a real agent), shell (pane exists, no agent - e.g. --no-agent), or gone
# (pane no longer exists).
fl_agent_status() {  # <pane>
  local out
  if out=$(fl_herdr agent get "$1" 2>/dev/null); then
    printf '%s' "$out" \
      | jq -r '.result.agent_status // .result.agent.agent_status // .agent_status // "unknown"' 2>/dev/null \
      | grep . || echo unknown
    return
  fi
  if fl_herdr pane get "$1" >/dev/null 2>&1; then echo shell; else echo gone; fi
}

# --- home lock (atomic mkdir, stale-pid reclaim) ---------------------------
# Serializes mutating operations (spawn) so two orchestrators never race on the
# same home. Read-only tools (list, watch) do not take it.
FL_LOCK_DIR="$FL_STATE/.lock"

fl_lock_acquire() {  # [<max-wait-seconds>]  (0/absent = try once)
  local max="${1:-0}" waited=0 held
  while :; do
    if mkdir "$FL_LOCK_DIR" 2>/dev/null; then
      echo $$ > "$FL_LOCK_DIR/pid"
      date -u +%Y-%m-%dT%H:%M:%SZ > "$FL_LOCK_DIR/since" 2>/dev/null || true
      return 0
    fi
    held=$(cat "$FL_LOCK_DIR/pid" 2>/dev/null || true)
    if [ -n "$held" ] && ! kill -0 "$held" 2>/dev/null; then
      # holder is dead - reclaim and retry immediately
      rm -rf "$FL_LOCK_DIR"
      continue
    fi
    if [ "$max" -le 0 ] || [ "$waited" -ge "$max" ]; then
      echo "fl: home lock held by pid ${held:-?}" >&2
      return 1
    fi
    sleep 1; waited=$((waited + 1))
  done
}

fl_lock_release() {
  local held; held=$(cat "$FL_LOCK_DIR/pid" 2>/dev/null || true)
  [ "$held" = "$$" ] && rm -rf "$FL_LOCK_DIR"
  return 0
}

# Run <fn/cmd...> while holding the home lock, then always release it.
fl_with_lock() {  # <max-wait> <cmd...>
  local max="$1"; shift
  fl_lock_acquire "$max" || return 1
  local rc=0
  "$@" || rc=$?
  fl_lock_release
  return "$rc"
}
