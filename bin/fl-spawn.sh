#!/usr/bin/env bash
# fl-spawn.sh - spawn a task as a herdr TAB running an agent.
#
# Usage:
#   fl-spawn.sh <id> [--cwd <dir>] [--harness <kind>] [--label <text>]
#               [--prompt <text> | --brief <file>] [--no-agent]
#
#   <id>        short task slug; names state/<id>.meta and the tab label
#   --cwd       working directory for the tab (default: current dir)
#   --harness   agent kind to start (default: claude). herdr supported kinds:
#               pi claude codex gemini cursor opencode grok kimi ... (see
#               `herdr agent start --help`)
#   --label     tab label shown in herdr (default: the id)
#   --prompt    initial prompt to submit once the agent is ready
#   --brief     file whose contents become the initial prompt
#   --no-agent  create the tab + pane at a bare shell only (no agent); useful
#               for mechanically testing the tab plumbing without an agent
#
# Mechanism: one herdr `tab create` (a clickable tab in the orchestrator's own
# workspace), then `agent start` to bring up the agent in that tab's pane, then
# an optional `agent prompt` to deliver the first instruction. The pane id is
# recorded as the task's authority in state/<id>.meta.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fl-lib.sh"

ID="" ; CWD="$PWD" ; HARNESS="claude" ; LABEL="" ; PROMPT="" ; BRIEF="" ; NO_AGENT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --cwd)     CWD="$2"; shift 2 ;;
    --harness) HARNESS="$2"; shift 2 ;;
    --label)   LABEL="$2"; shift 2 ;;
    --prompt)  PROMPT="$2"; shift 2 ;;
    --brief)   BRIEF="$2"; shift 2 ;;
    --no-agent) NO_AGENT=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    -*) fl_die "unknown flag: $1" ;;
    *)  [ -z "$ID" ] && ID="$1" && shift || fl_die "unexpected arg: $1" ;;
  esac
done
[ -n "$ID" ] || fl_die "need a task id (fl-spawn.sh <id> ...)"
[ -n "$LABEL" ] || LABEL="$ID"
CWD="$(cd "$CWD" && pwd)" || fl_die "bad --cwd"
if [ -n "$BRIEF" ]; then
  [ -f "$BRIEF" ] || fl_die "no brief file at $BRIEF"
  PROMPT="$(cat "$BRIEF")"
fi

fl_task_exists "$ID" && fl_die "task '$ID' already exists (state/$ID.meta); pick another id or tear it down"

# --- the mutation: serialize spawns behind the home lock -------------------
do_spawn() {
  local ws; ws="$(fl_workspace)"
  local create_args=(tab create --cwd "$CWD" --label "$LABEL" --no-focus)
  [ -n "$ws" ] && create_args+=(--workspace "$ws")

  local out
  out=$(fl_herdr "${create_args[@]}") || fl_die "herdr tab create failed"

  # Parse the pane + tab ids from whatever shape herdr returns.
  local pane tab
  pane=$(printf '%s' "$out" | jq -r '
      .result.root_pane.pane_id // .result.pane.pane_id // .result.pane_id //
      .result.panes[0].pane_id // .pane_id // empty' 2>/dev/null)
  tab=$(printf '%s' "$out" | jq -r '
      .result.tab.tab_id // .result.tab_id // .result.root_pane.tab_id //
      .tab_id // empty' 2>/dev/null)
  [ -n "$pane" ] || fl_die "could not parse pane id from tab create output: $out"

  fl_meta_set "$ID" id "$ID"
  fl_meta_set "$ID" pane "$pane"
  fl_meta_set "$ID" tab "${tab:-}"
  fl_meta_set "$ID" workspace "${ws:-}"
  fl_meta_set "$ID" cwd "$CWD"
  fl_meta_set "$ID" harness "$HARNESS"
  fl_meta_set "$ID" created "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"

  echo "fl: task '$ID' -> tab ${tab:-?} pane $pane (cwd $CWD)"

  if [ "$NO_AGENT" -eq 1 ]; then
    echo "fl: --no-agent: pane left at a bare shell"
    return 0
  fi

  # Bring the agent up in the pane and wait for interactive readiness. The agent
  # NAME must be UNIQUE per herdr session: herdr rejects a second `agent start`
  # that reuses a live name (agent_name_taken), so naming every crew "$HARNESS"
  # would cap the whole fleet at one live agent. Use the task id as the name
  # (--kind stays the harness); everything else addresses the agent by pane.
  if ! fl_herdr agent start "$ID" --kind "$HARNESS" --pane "$pane" >/dev/null 2>&1; then
    fl_meta_set "$ID" agent_start failed
    fl_die "herdr agent start ($HARNESS) failed in pane $pane; the tab exists - inspect it, then 'fl-teardown.sh $ID' or retry"
  fi
  fl_meta_set "$ID" agent_start ok

  if [ -n "$PROMPT" ]; then
    fl_herdr agent prompt "$pane" "$PROMPT" >/dev/null 2>&1 \
      || echo "fl: warning: initial prompt not confirmed delivered to $ID" >&2
    echo "fl: delivered initial prompt to '$ID'"
  fi
}

fl_with_lock 30 do_spawn
