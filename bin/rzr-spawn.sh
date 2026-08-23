#!/usr/bin/env bash
# rzr-spawn.sh - spawn a task as a herdr TAB running an agent.
#
# Usage:
#   rzr-spawn.sh <id> --cwd <dir> [--crew <preset>] [--label <text>]
#               [--harness <kind>] [--model <m>] [--effort <e>] [--fast|--no-fast]
#               [--permission-mode <mode>] [--prompt <text> | --brief <file>]
#               [--no-agent]
#
#   <id>        exact task key; names state/<id>.meta (legacy unsuffixed ids work)
#   --crew      crewmember preset to boot from (default: "default" reads
#               $ROZORO_HOME/crew/default.json when present; otherwise Claude
#               Sonnet, or gpt-5.6-sol/low with --harness codex). See rzr-crew.sh.
#   --cwd       required working directory for the tab. The agent
#               loads THIS repo's own rules (AGENTS.md/skills) from here.
#   --label     concise tab label (default: the exact task key)
#   --harness   agent kind (overrides preset). Claude, Codex, Copilot, and Pi
#               are wired for model/effort.
#   --model     model for the crew, e.g. gpt-5.6-sol (overrides preset)
#   --effort    reasoning effort: low|medium|high|xhigh|max (overrides preset)
#   --fast      use Codex's priority service tier (currently gpt-5.6-sol only)
#   --no-fast   disable a preset's fast selection
#   --permission-mode  autonomous permission signal; Codex and Copilot always
#               launch with yolo permissions
#   --prompt    initial task, submitted VERBATIM once the agent is ready
#   --brief     file whose contents become the initial prompt (also verbatim)
#   --no-agent  create the tab + pane at a bare shell only (no agent)
#
# Precedence for harness/model/effort/fast/permission-mode: explicit flag > preset >
# built-in harness fallback, except Codex/Copilot permission is always yolo. The
# Claude/Pi system prompts contain the rendered handoff protocol plus any preset
# `rules`; the task prompt itself is passed verbatim (harnesses lacking a
# system-prompt channel instead get the protocol folded into the prompt).
#
# Mechanism: one herdr `tab create` (a clickable tab in the orchestrator's own
# workspace), then `agent start` to bring up the agent in that tab's pane, then
# an optional `agent prompt` to deliver the first instruction. The pane id is
# recorded as the task's authority in state/<id>.meta.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

ID="" ; CWD="" ; LABEL="" ; PROMPT="" ; BRIEF="" ; NO_AGENT=0
CREW="default" ; HARNESS_OV="" ; MODEL_OV="" ; EFFORT_OV="" ; PERMMODE_OV="" ; FAST_OV=""
while [ $# -gt 0 ]; do
  case "$1" in
    --crew)    CREW="$2"; shift 2 ;;
    --cwd)     [ $# -ge 2 ] || rzr_die "--cwd <dir> required"; CWD="$2"; shift 2 ;;
    --harness) HARNESS_OV="$2"; shift 2 ;;
    --model)   MODEL_OV="$2"; shift 2 ;;
    --effort)  EFFORT_OV="$2"; shift 2 ;;
    --fast)    FAST_OV="true"; shift ;;
    --no-fast) FAST_OV="false"; shift ;;
    --permission-mode) PERMMODE_OV="$2"; shift 2 ;;
    --label)   LABEL="$2"; shift 2 ;;
    --prompt)  PROMPT="$2"; shift 2 ;;
    --brief)   BRIEF="$2"; shift 2 ;;
    --no-agent) NO_AGENT=1; shift ;;
    -h|--help) sed -n '2,/^set -euo pipefail$/{ /^set -euo pipefail$/d; p; }' "$0"; exit 0 ;;
    -*) rzr_die "unknown flag: $1" ;;
    *)  [ -z "$ID" ] && ID="$1" && shift || rzr_die "unexpected arg: $1" ;;
  esac
done
[ -n "$ID" ] || rzr_die "need a task id (rzr-spawn.sh <id> ...)"
rzr_validate_task_component "$ID"
[ -n "$CWD" ] || rzr_die "--cwd <dir> required for a fresh task"
[ -n "$LABEL" ] || LABEL="$ID"
AGENT_NAME="$(rzr_task_agent_name "$ID")"
CWD="$(cd "$CWD" && pwd)" || rzr_die "bad --cwd"
if [ -n "$BRIEF" ]; then
  [ -f "$BRIEF" ] || rzr_die "no brief file at $BRIEF"
  PROMPT="$(cat "$BRIEF")"
fi

rzr_task_exists "$ID" && rzr_die "task '$ID' already exists (state/$ID.meta); pick another id or tear it down"

# --- resolve the crew profile (flag > preset > built-in harness fallback) --
rzr_crew_resolves "$CREW" || rzr_die "unknown crew preset '$CREW' (see: ./bin/rozoro crew list)"
rzr_crew_validate "$CREW" || rzr_die "crew preset '$CREW' has invalid JSON or known field types"
if rzr_crew_exists "$CREW"; then
  HARNESS="${HARNESS_OV:-$(rzr_crew_field "$CREW" harness)}" ; HARNESS="${HARNESS:-claude}"
  MODEL="${MODEL_OV:-$(rzr_crew_field "$CREW" model)}"
  EFFORT="${EFFORT_OV:-$(rzr_crew_field "$CREW" effort)}"
  PERMMODE="${PERMMODE_OV:-$(rzr_crew_field "$CREW" permission_mode)}"
  FAST="${FAST_OV:-$(rzr_crew_bool_field "$CREW" fast)}" ; FAST="${FAST:-false}"
  RULES="$(rzr_crew_rules "$CREW")"
else
  # Only the virtual `default` reaches here. Choose a coherent fallback profile
  # from the selected harness instead of mixing one harness with another's model.
  HARNESS="${HARNESS_OV:-claude}"
  MODEL="${MODEL_OV:-$(rzr_crew_builtin_field "$HARNESS" model)}"
  EFFORT="${EFFORT_OV:-$(rzr_crew_builtin_field "$HARNESS" effort)}"
  PERMMODE="${PERMMODE_OV:-$(rzr_crew_builtin_field "$HARNESS" permission_mode)}"
  FAST="${FAST_OV:-$(rzr_crew_builtin_field "$HARNESS" fast)}" ; FAST="${FAST:-false}"
  RULES=""
fi
rzr_profile_validate "$HARNESS" "$MODEL" "$EFFORT" "$FAST"

# Codex and Copilot crews are intentionally autonomous. Normalize after all
# preset/flag resolution so a personal preset cannot weaken that contract.
case "$HARNESS" in codex|copilot) PERMMODE="yolo" ;; esac

# Reject incompatible Copilot binaries before rendering or Herdr mutation.
[ "$HARNESS" != copilot ] || rzr_copilot_capabilities || exit 1

# The handoff protocol is rozoro overhead, kept OUT of the verbatim task prompt.
# Claude and Pi get it (plus any preset rules) through their system-prompt
# channels. Harnesses without one get the protocol folded into the delivered
# prompt, so they still report handoffs.
FOLDER="$(rzr_task_dir "$ID")"
rzr_render_handoff_protocol "$ID"
HANDOFF="$(rzr_handoff_protocol_path "$ID")"
SYSFILE=""
SESSION_ID=""
EVENT_BUS=false
[ "$HARNESS" = claude ] && EVENT_BUS=true
if [ "$EVENT_BUS" = true ] || [ "$HARNESS" = pi ]; then
  "$RZR_BIN/rzr-monitor.sh" start >/dev/null || rzr_die "resident monitor failed readiness"
fi
[ "$EVENT_BUS" != true ] || rzr_claude_event_capability || exit 1
case "$HARNESS" in
  pi|copilot)
    # Caller-selected UUIDs remove discovery races and provide exact identity.
    SESSION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')" ;;
  claude)
    # Event-bus hooks bind to an exact preallocated Claude conversation.
    [ "$EVENT_BUS" = true ] && SESSION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')" ;;
esac
EVENT_SETTINGS=""
if [ "$EVENT_BUS" = true ]; then
  EVENT_SETTINGS="$(rzr_claude_event_settings "$ID" "$SESSION_ID")" || exit 1
fi
if [ "$HARNESS" = claude ] || [ "$HARNESS" = pi ]; then
  SYSFILE="$FOLDER/sysprompt.md"
  { printf 'rozoro-task: %s\n\n' "$ID"
    cat "$HANDOFF"
    [ -n "$RULES" ] && printf '\n\n---\n## Crew rules\n\n%s\n' "$RULES"
  } > "$SYSFILE"
elif [ -n "$PROMPT" ]; then
  PROMPT="$(cat "$HANDOFF")
${RULES:+$RULES

}--- task ---
$PROMPT"
fi

# --- the mutation: serialize spawns behind the home lock -------------------
do_spawn() {
  local ws; ws="$(rzr_workspace)"
  local create_args=(tab create --cwd "$CWD" --label "$LABEL" --no-focus)
  [ -n "$ws" ] && create_args+=(--workspace "$ws")

  local out
  out=$(rzr_herdr "${create_args[@]}") || rzr_die "herdr tab create failed"

  # Parse the pane + tab ids from whatever shape herdr returns.
  local pane tab
  pane=$(printf '%s' "$out" | jq -r '
      .result.root_pane.pane_id // .result.pane.pane_id // .result.pane_id //
      .result.panes[0].pane_id // .pane_id // empty' 2>/dev/null)
  tab=$(printf '%s' "$out" | jq -r '
      .result.tab.tab_id // .result.tab_id // .result.root_pane.tab_id //
      .tab_id // empty' 2>/dev/null)
  [ -n "$pane" ] || rzr_die "could not parse pane id from tab create output: $out"

  rzr_meta_set "$ID" id "$ID"
  rzr_meta_set "$ID" display_name "$LABEL"
  rzr_meta_set "$ID" herdr_agent_name "$AGENT_NAME"
  rzr_meta_set "$ID" pane "$pane"
  rzr_meta_set "$ID" tab "${tab:-}"
  rzr_meta_set "$ID" workspace "${ws:-}"
  rzr_meta_set "$ID" cwd "$CWD"
  rzr_meta_set "$ID" crew "$CREW"
  rzr_meta_set "$ID" harness "$HARNESS"
  rzr_meta_set "$ID" model "${MODEL:-}"
  rzr_meta_set "$ID" effort "${EFFORT:-}"
  rzr_meta_set "$ID" fast "$FAST"
  rzr_meta_set "$ID" permission_mode "${PERMMODE:-}"
  [ -n "$SESSION_ID" ] && rzr_meta_set "$ID" session "$SESSION_ID"
  rzr_meta_set "$ID" event_bus "$EVENT_BUS"
  rzr_meta_set "$ID" created "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"

  echo "rzr: task '$ID' -> tab ${tab:-?} pane $pane (cwd $CWD)"

  if [ "$NO_AGENT" -eq 1 ]; then
    echo "rzr: --no-agent: pane left at a bare shell"
    return 0
  fi

  # Bring the agent up in the pane and wait for interactive readiness. The agent
  # NAME must be valid and UNIQUE per herdr session. Durable task keys include
  # uppercase ULIDs and may exceed Herdr's 32-character limit, so use their
  # stable transport-safe digest; everything else addresses the agent by pane.
  #
  # The crew profile (model/effort/fast/permission-mode/rules) is forwarded to the
  # underlying agent binary via herdr's `-- <arg>...` passthrough. Args arrive
  # NUL-separated (a rule value may contain newlines), read into an array here.
  local -a agent_args=()
  while IFS= read -r -d '' _a; do agent_args+=("$_a"); done \
    < <(rzr_harness_args "$HARNESS" "$MODEL" "$EFFORT" "$PERMMODE" "$SYSFILE" "$SESSION_ID" "$FAST")
  [ -z "$EVENT_SETTINGS" ] || agent_args+=(--settings "$EVENT_SETTINGS")
  local -a start=(agent start "$AGENT_NAME" --kind "$HARNESS" --pane "$pane")
  [ "${#agent_args[@]}" -gt 0 ] && start+=(-- "${agent_args[@]}")

  # `tab create` returns a pane id before its shell prompt is ready, so an
  # immediate `agent start` can race and get `agent_pane_busy` ("not an
  # available shell"). Retry that pre-launch transient with a short backoff.
  # Herdr may also report `agent_not_ready` after the harness has launched but
  # before it is interactive; do not launch it twice, just wait for readiness.
  local out="" rc=1 attempt=0
  while [ "$attempt" -lt 20 ]; do
    if out=$(rzr_herdr "${start[@]}" 2>&1); then rc=0; break; fi
    case "$out" in
      *agent_pane_busy*|*"not an available shell"*) sleep 0.5; attempt=$((attempt + 1)) ;;
      *agent_not_ready*) rzr_wait_agent_ready "$pane" 20 && rc=0; break ;;
      *) break ;;
    esac
  done
  if [ "$rc" -ne 0 ]; then
    rzr_meta_set "$ID" agent_start failed
    rzr_die "herdr agent start ($HARNESS) failed in pane $pane: $out; the tab exists - inspect it, then './bin/rozoro teardown $ID' or retry"
  fi
  rzr_meta_set "$ID" agent_start ok

  if [ -n "$PROMPT" ]; then
    rzr_herdr agent prompt "$pane" "$PROMPT" >/dev/null 2>&1 \
      || echo "rzr: warning: initial prompt not confirmed delivered to $ID" >&2
    echo "rzr: delivered initial prompt to '$ID'"
  fi
}

rzr_with_lock 30 do_spawn
