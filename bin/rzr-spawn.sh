#!/usr/bin/env bash
# rzr-spawn.sh - spawn a task as a herdr TAB running an agent.
#
# Usage:
#   rzr-spawn.sh <id> [--crew <preset>] [--cwd <dir>] [--label <text>]
#               [--harness <kind>] [--model <m>] [--effort <e>]
#               [--permission-mode <mode>] [--prompt <text> | --brief <file>]
#               [--no-agent]
#
#   <id>        exact task key; names state/<id>.meta (legacy unsuffixed ids work)
#   --crew      crewmember preset to boot from (default: "default" reads
#               $ROZORO_HOME/crew/default.json when present; otherwise Claude
#               Sonnet, or gpt-5.6-sol/low with --harness codex). See rzr-crew.sh.
#   --cwd       working directory for the tab (default: current dir). The agent
#               loads THIS repo's own rules (AGENTS.md/skills) from here.
#   --label     concise tab label (default: the exact task key)
#   --harness   agent kind (overrides preset). Claude, Codex, and Pi are wired
#               for model/effort; other kinds have more limited mappings.
#   --model     model for the crew, e.g. gpt-5.6-sol (overrides preset)
#   --effort    reasoning effort: low|medium|high|xhigh|max (overrides preset)
#   --permission-mode  autonomous permission signal for non-Codex harnesses;
#               Codex always launches with --yolo
#   --prompt    initial task, submitted VERBATIM once the agent is ready
#   --brief     file whose contents become the initial prompt (also verbatim)
#   --no-agent  create the tab + pane at a bare shell only (no agent)
#
# Precedence for harness/model/effort/permission-mode: explicit flag > preset >
# built-in harness fallback, except Codex permission mode is always yolo. The
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

ID="" ; CWD="$PWD" ; LABEL="" ; PROMPT="" ; BRIEF="" ; NO_AGENT=0
CREW="default" ; HARNESS_OV="" ; MODEL_OV="" ; EFFORT_OV="" ; PERMMODE_OV=""
while [ $# -gt 0 ]; do
  case "$1" in
    --crew)    CREW="$2"; shift 2 ;;
    --cwd)     CWD="$2"; shift 2 ;;
    --harness) HARNESS_OV="$2"; shift 2 ;;
    --model)   MODEL_OV="$2"; shift 2 ;;
    --effort)  EFFORT_OV="$2"; shift 2 ;;
    --permission-mode) PERMMODE_OV="$2"; shift 2 ;;
    --label)   LABEL="$2"; shift 2 ;;
    --prompt)  PROMPT="$2"; shift 2 ;;
    --brief)   BRIEF="$2"; shift 2 ;;
    --no-agent) NO_AGENT=1; shift ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    -*) rzr_die "unknown flag: $1" ;;
    *)  [ -z "$ID" ] && ID="$1" && shift || rzr_die "unexpected arg: $1" ;;
  esac
done
[ -n "$ID" ] || rzr_die "need a task id (rzr-spawn.sh <id> ...)"
rzr_validate_task_component "$ID"
[ -n "$LABEL" ] || LABEL="$ID"
CWD="$(cd "$CWD" && pwd)" || rzr_die "bad --cwd"
if [ -n "$BRIEF" ]; then
  [ -f "$BRIEF" ] || rzr_die "no brief file at $BRIEF"
  PROMPT="$(cat "$BRIEF")"
fi

rzr_task_exists "$ID" && rzr_die "task '$ID' already exists (state/$ID.meta); pick another id or tear it down"

# --- resolve the crew profile (flag > preset > built-in harness fallback) --
rzr_crew_resolves "$CREW" || rzr_die "unknown crew preset '$CREW' (see: rzr-crew.sh list)"
if rzr_crew_exists "$CREW"; then
  HARNESS="${HARNESS_OV:-$(rzr_crew_field "$CREW" harness)}" ; HARNESS="${HARNESS:-claude}"
  MODEL="${MODEL_OV:-$(rzr_crew_field "$CREW" model)}"
  EFFORT="${EFFORT_OV:-$(rzr_crew_field "$CREW" effort)}"
  PERMMODE="${PERMMODE_OV:-$(rzr_crew_field "$CREW" permission_mode)}"
  RULES="$(rzr_crew_rules "$CREW")"
else
  # Only the virtual `default` reaches here. Choose a coherent fallback profile
  # from the selected harness instead of mixing one harness with another's model.
  HARNESS="${HARNESS_OV:-claude}"
  MODEL="${MODEL_OV:-$(rzr_crew_builtin_field "$HARNESS" model)}"
  EFFORT="${EFFORT_OV:-$(rzr_crew_builtin_field "$HARNESS" effort)}"
  PERMMODE="${PERMMODE_OV:-$(rzr_crew_builtin_field "$HARNESS" permission_mode)}"
  RULES=""
fi
case "$HARNESS" in
  claude|codex|copilot|pi) ;;
  *) rzr_die "harness '$HARNESS': not wired (known: claude codex copilot pi); add a case to rzr_harness_args in rzr-lib.sh" ;;
esac

# Codex crews are an intentionally autonomous spawner contract. Normalize the
# effective value after all preset/flag resolution so old personal presets with
# an empty permission_mode cannot silently launch an approval-gated session.
[ "$HARNESS" = codex ] && PERMMODE="yolo"

# The handoff protocol is rozoro overhead, kept OUT of the verbatim task prompt.
# Claude and Pi get it (plus any preset rules) through their system-prompt
# channels. Harnesses without one get the protocol folded into the delivered
# prompt, so they still report handoffs.
FOLDER="$(rzr_task_dir "$ID")"
rzr_render_handoff_protocol "$ID"
HANDOFF="$(rzr_handoff_protocol_path "$ID")"
SYSFILE=""
SESSION_ID=""
if [ "$HARNESS" = pi ]; then
  # Pi can start with a caller-selected UUID. Preallocating it removes transcript
  # discovery races and gives rzr-link/rzr-resume an exact durable identity.
  SESSION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
fi
if [ "$HARNESS" = claude ] || [ "$HARNESS" = pi ]; then
  SYSFILE="$FOLDER/sysprompt.md"
  { cat "$HANDOFF"
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
  rzr_meta_set "$ID" pane "$pane"
  rzr_meta_set "$ID" tab "${tab:-}"
  rzr_meta_set "$ID" workspace "${ws:-}"
  rzr_meta_set "$ID" cwd "$CWD"
  rzr_meta_set "$ID" crew "$CREW"
  rzr_meta_set "$ID" harness "$HARNESS"
  rzr_meta_set "$ID" model "${MODEL:-}"
  rzr_meta_set "$ID" effort "${EFFORT:-}"
  rzr_meta_set "$ID" permission_mode "${PERMMODE:-}"
  [ -n "$SESSION_ID" ] && rzr_meta_set "$ID" session "$SESSION_ID"
  rzr_meta_set "$ID" created "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"

  echo "rzr: task '$ID' -> tab ${tab:-?} pane $pane (cwd $CWD)"

  if [ "$NO_AGENT" -eq 1 ]; then
    echo "rzr: --no-agent: pane left at a bare shell"
    return 0
  fi

  # Bring the agent up in the pane and wait for interactive readiness. The agent
  # NAME must be UNIQUE per herdr session: herdr rejects a second `agent start`
  # that reuses a live name (agent_name_taken), so naming every crew "$HARNESS"
  # would cap the whole fleet at one live agent. Use the task id as the name
  # (--kind stays the harness); everything else addresses the agent by pane.
  #
  # The crew profile (model/effort/permission-mode/rules) is forwarded to the
  # underlying agent binary via herdr's `-- <arg>...` passthrough. Args arrive
  # NUL-separated (a rule value may contain newlines), read into an array here.
  local -a agent_args=()
  while IFS= read -r -d '' _a; do agent_args+=("$_a"); done \
    < <(rzr_harness_args "$HARNESS" "$MODEL" "$EFFORT" "$PERMMODE" "$SYSFILE" "$SESSION_ID")
  local -a start=(agent start "$ID" --kind "$HARNESS" --pane "$pane")
  [ "${#agent_args[@]}" -gt 0 ] && start+=(-- "${agent_args[@]}")

  # `tab create` returns a pane id before its shell prompt is ready, so an
  # immediate `agent start` can race and get `agent_pane_busy` ("not an
  # available shell"). Retry ONLY that transient case with a short backoff; any
  # other error is real and surfaces immediately (with herdr's message).
  local out="" rc=1 attempt=0
  while [ "$attempt" -lt 20 ]; do
    if out=$(rzr_herdr "${start[@]}" 2>&1); then rc=0; break; fi
    case "$out" in
      *agent_pane_busy*|*"not an available shell"*) sleep 0.5; attempt=$((attempt + 1)) ;;
      *) break ;;
    esac
  done
  if [ "$rc" -ne 0 ]; then
    rzr_meta_set "$ID" agent_start failed
    rzr_die "herdr agent start ($HARNESS) failed in pane $pane: $out; the tab exists - inspect it, then 'rzr-teardown.sh $ID' or retry"
  fi
  rzr_meta_set "$ID" agent_start ok

  if [ -n "$PROMPT" ]; then
    rzr_herdr agent prompt "$pane" "$PROMPT" >/dev/null 2>&1 \
      || echo "rzr: warning: initial prompt not confirmed delivered to $ID" >&2
    echo "rzr: delivered initial prompt to '$ID'"
  fi
}

rzr_with_lock 30 do_spawn
