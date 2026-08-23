#!/usr/bin/env bash
# rzr-resume.sh - reopen a task's EXACT conversation as a fresh herdr tab.
#
# Usage:
#   rzr-resume.sh <id> [--cwd <dir>] [--permission-mode <mode>] [--model <m>]
#                 [--effort <e>] [--fast|--no-fast]
#                 [--label <text>] [--prompt <text> | --brief <file>]
#
#   <id>        a task previously started (its tasks/<id>/session.json must exist)
#   --cwd       working dir for the tab (default: the cwd recorded at link time)
#   --permission-mode  autonomous permission signal for non-Codex harnesses;
#               Codex always resumes with --yolo
#   --model     model override for the resumed run (default: session's own)
#   --effort    reasoning effort override (default: durable profile/session)
#   --fast      use Codex's priority service tier (currently gpt-5.6-sol only)
#   --no-fast   disable fast from the durable profile
#   --label     tab label (default: the recorded display name, then the id)
#   --prompt    a follow-up delivered VERBATIM once the resumed agent is ready
#   --brief     file whose contents become that follow-up (also verbatim)
#
# Why this exists: a `done` crew that was reaped still holds its whole
# conversation on disk (the harness transcript linked in tasks/<id>/session.json).
# When follow-up arrives, re-spawning a NEW crew starts cold — it has to rebuild
# context from handoff.md. `resume` instead relaunches the recorded Claude,
# Codex, Copilot, or Pi session in a new pane, so the crew picks up with full memory.
#
# Prefer NOT closing over closing-and-resuming: if the crew is still live, use
# rzr-send.sh (same live context) rather than tearing down and resuming. This
# verb is for the case where teardown already happened.
#
# Claude, Codex, Copilot, and Pi sessions are supported. The task must NOT be currently tracked
# — a live agent already owns the unique name; resume is for a reaped task whose
# name is free again.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

ID="" ; CWD_OV="" ; PERMMODE_OV="" ; MODEL_OV="" ; EFFORT_OV="" ; FAST_OV="" ; LABEL="" ; PROMPT="" ; BRIEF=""
while [ $# -gt 0 ]; do
  case "$1" in
    --cwd)             CWD_OV="$2"; shift 2 ;;
    --permission-mode) PERMMODE_OV="$2"; shift 2 ;;
    --model)           MODEL_OV="$2"; shift 2 ;;
    --effort)          EFFORT_OV="$2"; shift 2 ;;
    --fast)            FAST_OV="true"; shift ;;
    --no-fast)         FAST_OV="false"; shift ;;
    --label)           LABEL="$2"; shift 2 ;;
    --prompt)          PROMPT="$2"; shift 2 ;;
    --brief)           BRIEF="$2"; shift 2 ;;
    -h|--help) sed -n '2,/^set -euo pipefail$/{ /^set -euo pipefail$/d; p; }' "$0"; exit 0 ;;
    -*) rzr_die "unknown flag: $1" ;;
    *)  [ -z "$ID" ] && ID="$1" && shift || rzr_die "unexpected arg: $1" ;;
  esac
done
[ -n "$ID" ] || rzr_die "need a task id (rzr-resume.sh <id> ...)"
rzr_validate_task_component "$ID"
AGENT_NAME="$(rzr_task_agent_name "$ID")"
if [ -z "$LABEL" ]; then
  IDENTITY="$(rzr_task_dir "$ID")/identity.json"
  [ -s "$IDENTITY" ] && LABEL="$(jq -r '.display_name // empty' "$IDENTITY" 2>/dev/null || true)"
  LABEL="${LABEL:-$ID}"
fi

# A live/tracked task still owns the unique agent name — resuming would collide.
# If it's still around, the right move is to continue it in place, not resume.
rzr_task_exists "$ID" && rzr_die "task '$ID' is still tracked (state/$ID.meta) — it's live; continue it with './bin/rozoro send $ID \"...\"' instead of resuming"

# The durable link is the whole point: session_id + the cwd it was born in.
SESS="$(rzr_task_dir "$ID")/session.json"
[ -s "$SESS" ] || rzr_die "no session link at $SESS — nothing to resume (was '$ID' ever started via ./bin/rozoro start / linked?). Start it fresh with './bin/rozoro start <name> --body <file> --cwd <repo>'"
UUID="$(jq -r '.session_id // empty' "$SESS" 2>/dev/null)"
[ -n "$UUID" ] || rzr_die "$SESS has no session_id — cannot resume; start '$ID' fresh instead"
HARNESS="$(jq -r '.harness // "claude"' "$SESS" 2>/dev/null)"
case "$HARNESS" in
  claude|codex|copilot|pi) ;;
  *) rzr_die "resume does not support harness '$HARNESS'; relaunch it your own way" ;;
esac
EVENT_BUS=false
[ "${ROZORO_EVENT_BUS:-0}" = 1 ] && [ "$HARNESS" = claude ] && EVENT_BUS=true
[ "$EVENT_BUS" != true ] || rzr_claude_event_capability || exit 1
PROFILE_MODEL=""; PROFILE_EFFORT=""; PROFILE_PERMMODE=""; PROFILE_FAST="false"
if jq -e 'has("profile")' "$SESS" >/dev/null 2>&1; then
  jq -e '
    .profile as $p |
    ($p | type == "object") and
    (["harness", "model", "effort", "permission_mode"] |
      all(. as $k | ($p | has($k) | not) or ($p[$k] | type == "string"))) and
    (($p | has("fast") | not) or ($p.fast | type == "boolean"))
  ' "$SESS" >/dev/null 2>&1 || rzr_die "$SESS has an invalid profile"
  PROFILE_HARNESS="$(jq -r '.profile.harness // empty' "$SESS")"
  [ -z "$PROFILE_HARNESS" ] || [ "$PROFILE_HARNESS" = "$HARNESS" ] || rzr_die "$SESS profile harness does not match session harness"
  PROFILE_MODEL="$(jq -r '.profile.model // empty' "$SESS")"
  PROFILE_EFFORT="$(jq -r '.profile.effort // empty' "$SESS")"
  PROFILE_PERMMODE="$(jq -r '.profile.permission_mode // empty' "$SESS")"
  PROFILE_FAST="$(jq -r 'if .profile.fast == true then "true" else "false" end' "$SESS")"
fi
MODEL="${MODEL_OV:-$PROFILE_MODEL}"
EFFORT="${EFFORT_OV:-$PROFILE_EFFORT}"
PERMMODE="${PERMMODE_OV:-${PROFILE_PERMMODE:-auto}}"
FAST="${FAST_OV:-$PROFILE_FAST}"
case "$HARNESS" in codex|copilot) PERMMODE="yolo" ;; esac
rzr_profile_validate "$HARNESS" "$MODEL" "$EFFORT" "$FAST"
[ "$HARNESS" != copilot ] || rzr_copilot_capabilities || exit 1
CWD="${CWD_OV:-$(jq -r '.cwd // empty' "$SESS" 2>/dev/null)}"
[ -n "$CWD" ] || rzr_die "no cwd recorded in $SESS and none passed; give --cwd <dir>"
CWD="$(cd "$CWD" && pwd)" || rzr_die "bad cwd '$CWD'"
EVENT_SETTINGS=""
if [ "$EVENT_BUS" = true ]; then
  EVENT_SETTINGS="$(rzr_claude_event_settings "$ID" "$UUID")" || exit 1
fi

if [ -n "$BRIEF" ]; then
  [ -f "$BRIEF" ] || rzr_die "no brief file at $BRIEF"
  PROMPT="$(cat "$BRIEF")"
fi

# Re-inject the handoff protocol as a preamble to the follow-up. This is required
# for Claude because `claude --resume` does not re-apply its original system
# prompt, and keeps the contract explicit for Codex and Pi resumes too. The follow-up
# itself remains verbatim after the delimiter.
if [ -n "$PROMPT" ]; then
  rzr_render_handoff_protocol "$ID"
  HANDOFF="$(rzr_handoff_protocol_path "$ID")"
  PROMPT="[rozoro] This is a RESUMED turn. The handoff protocol still applies:

$(cat "$HANDOFF")

--- my follow-up ---
$PROMPT"
fi

do_resume() {
  local ws; ws="$(rzr_workspace)"
  local create_args=(tab create --cwd "$CWD" --label "$LABEL" --no-focus)
  [ -n "$ws" ] && create_args+=(--workspace "$ws")

  local out
  out=$(rzr_herdr "${create_args[@]}") || rzr_die "herdr tab create failed"
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
  rzr_meta_set "$ID" crew "resumed"
  rzr_meta_set "$ID" harness "$HARNESS"
  rzr_meta_set "$ID" model "${MODEL:-}"
  rzr_meta_set "$ID" effort "${EFFORT:-}"
  rzr_meta_set "$ID" fast "$FAST"
  rzr_meta_set "$ID" permission_mode "${PERMMODE:-}"
  rzr_meta_set "$ID" session "$UUID"
  rzr_meta_set "$ID" event_bus "$EVENT_BUS"
  rzr_meta_set "$ID" resumed "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"

  echo "rzr: resuming '$ID' (session $UUID) -> tab ${tab:-?} pane $pane (cwd $CWD)"

  # Resume the transcript, keep rozoro's standing autonomous-permission posture,
  # and re-apply a model only if asked.
  local -a pass=() start=()
  case "$HARNESS" in
    claude)
      pass=(--resume "$UUID")
      [ -n "$PERMMODE" ] && pass+=(--permission-mode "$PERMMODE")
      [ -n "$MODEL" ] && pass+=(--model "$MODEL")
      [ -n "$EFFORT" ] && pass+=(--effort "$EFFORT")
      [ -z "$EVENT_SETTINGS" ] || pass+=(--settings "$EVENT_SETTINGS")
      ;;
    codex)
      pass=(resume "$UUID")
      pass+=(--yolo)
      [ -n "$MODEL" ] && pass+=(--model "$MODEL")
      [ -n "$EFFORT" ] && pass+=(--config "model_reasoning_effort=$EFFORT")
      [ "$FAST" = true ] && pass+=(--config service_tier=priority)
      ;;
    copilot)
      pass=(--no-auto-update "--resume=$UUID" --autopilot --yolo --no-ask-user)
      [ -n "$MODEL" ] && pass+=(--model "$MODEL")
      [ -n "$EFFORT" ] && pass+=(--effort "$EFFORT")
      ;;
    pi)
      pass=(--session "$UUID")
      [ -n "$PERMMODE" ] && pass+=(--approve)
      [ -n "$MODEL" ] && pass+=(--model "$MODEL")
      [ -n "$EFFORT" ] && pass+=(--thinking "$EFFORT")
      # Pi rebuilds its system prompt on startup. Reapply the persisted handoff
      # protocol and crew rules when the original launch sysprompt survives.
      [ -s "$(rzr_task_dir "$ID")/sysprompt.md" ] && \
        pass+=(--append-system-prompt "$(rzr_task_dir "$ID")/sysprompt.md")
      ;;
  esac
  start=(agent start "$AGENT_NAME" --kind "$HARNESS" --pane "$pane" -- "${pass[@]}")

  # Same transient-busy retry as spawn: `tab create` can return before the shell
  # is ready.
  local sout="" rc=1 attempt=0
  while [ "$attempt" -lt 20 ]; do
    if sout=$(rzr_herdr "${start[@]}" 2>&1); then rc=0; break; fi
    case "$sout" in
      *agent_pane_busy*|*"not an available shell"*) sleep 0.5; attempt=$((attempt + 1)) ;;
      *agent_not_ready*) rzr_wait_agent_ready "$pane" 20 && rc=0; break ;;
      *) break ;;
    esac
  done
  if [ "$rc" -ne 0 ]; then
    rzr_meta_set "$ID" agent_start failed
    rzr_die "herdr agent start ($HARNESS resume) failed in pane $pane: $sout; the tab exists - inspect it, then './bin/rozoro teardown $ID' or retry"
  fi
  rzr_meta_set "$ID" agent_start ok

  if [ -n "$PROMPT" ]; then
    rzr_herdr agent prompt "$pane" "$PROMPT" >/dev/null 2>&1 \
      || echo "rzr: warning: follow-up prompt not confirmed delivered to $ID" >&2
    echo "rzr: delivered follow-up to resumed '$ID'"
  fi
}

rzr_with_lock 30 do_resume
