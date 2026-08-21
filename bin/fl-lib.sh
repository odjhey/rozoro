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
FL_HOME="${FL_HOME:-$(cd "$FL_BIN/.." && pwd)}"
FL_STATE="$FL_HOME/state"
mkdir -p "$FL_STATE"

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
