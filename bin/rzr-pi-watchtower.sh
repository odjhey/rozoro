#!/usr/bin/env bash
# Launch or exactly resume the supported Pi watchtower in the current Herdr pane.
set -euo pipefail
RZR_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$RZR_BIN/.." && pwd)"
RESUME="" CWD="$ROOT" PRESET="" WT_NAME="" MODEL="" EFFORT="" VERSION="" PRESET_SHA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --resume) RESUME="${2:-}"; [ -n "$RESUME" ] || { echo "rzr: --resume requires a Pi session id or file" >&2; exit 2; }; shift 2 ;;
    --cwd) CWD="${2:-}"; [ -d "$CWD" ] || { echo "rzr: --cwd requires an existing directory" >&2; exit 2; }; shift 2 ;;
    --preset) PRESET="${2:-}"; [ -n "$PRESET" ] || { echo "rzr: --preset requires a name" >&2; exit 2; }; shift 2 ;;
    --wt-name) WT_NAME="${2:-}"; [ -n "$WT_NAME" ] || { echo "rzr: --wt-name requires a name" >&2; exit 2; }; shift 2 ;;
    --) shift; break ;;
    -h|--help) echo "usage: ./bin/rozoro pi-watchtower [--preset <name>] [--wt-name <name>] [--resume <session-id-or-file>] [--cwd <dir>] [-- <pi-args...>]"; exit 0 ;;
    *) echo "rzr: unknown pi-watchtower option '$1' (put Pi options after --)" >&2; exit 2 ;;
  esac
done
[ -n "${HERDR_PANE_ID:-}" ] || { echo "rzr: pi-watchtower requires the owning HERDR_PANE_ID" >&2; exit 1; }
for arg in "$@"; do
  case "$arg" in --append-system-prompt|--append-system-prompt=*|--system-prompt|--system-prompt=*)
    echo "rzr: Pi policy prompt options are launcher-owned" >&2; exit 2;; esac
done
unset ROZORO_WT_NAME ROZORO_WT_PRESET ROZORO_WT_PRESET_VERSION ROZORO_WT_PRESET_SHA256 ROZORO_WT_POLICY_SHA256 ROZORO_WT_POLICY_CORE_SHA256 ROZORO_WT_POLICY_MISSION_NAME ROZORO_WT_POLICY_MISSION_SOURCE ROZORO_WT_POLICY_MISSION_SHA256 ROZORO_WT_MODEL ROZORO_WT_EFFORT ROZORO_WT_DRIVER
# Policy resolution does not contact Herdr; the pane identity is transport input.
RZR_LIB_SKIP_HERDR_CHECK=1 RZR_LIB_NO_STATE_INIT=1
# shellcheck disable=SC1091
. "$RZR_BIN/rzr-lib.sh"
unset RZR_LIB_SKIP_HERDR_CHECK RZR_LIB_NO_STATE_INIT
EFFECTIVE_HOME="$RZR_HOME"
export ROZORO_HOME="$EFFECTIVE_HOME"
[ -z "$WT_NAME" ] || rzr_validate_wt_metadata "$WT_NAME" "watchtower name"
MISSION=delivery
if [ -n "$PRESET" ]; then
  rzr_validate_wtpreset_name "$PRESET"
  RESOLVED="$(rzr_wtpreset_resolve "$PRESET")" || exit $?
  [ "$(printf '%s' "$RESOLVED" | jq -r '.document.harness')" = pi ] || rzr_die "watchtower preset '$PRESET' is not for harness pi"
  [ -n "$WT_NAME" ] || WT_NAME="$PRESET"
  MODEL="$(printf '%s' "$RESOLVED" | jq -r '.document.model // empty')"
  EFFORT="$(printf '%s' "$RESOLVED" | jq -r '.document.effort // empty')"
  VERSION="$(printf '%s' "$RESOLVED" | jq -r '.document.version // 0')"
  PRESET_SHA="$(printf '%s' "$RESOLVED" | jq -r '.sha256')"
  PRESET_MISSION="$(printf '%s' "$RESOLVED" | jq -r '.document.mission // empty')"
  [ -z "$PRESET_MISSION" ] || MISSION="$PRESET_MISSION"
fi
POLICY="$(rzr_watchtower_policy_resolve "$ROOT" "$EFFECTIVE_HOME" "$MISSION")" || exit $?
SOURCE="$(printf '%s' "$POLICY" | jq -r .mission_source)"
if [ "$SOURCE" = shipped ]; then MISSION_FILE="$ROOT/templates/missions/$MISSION.md"
else MISSION_FILE="$EFFECTIVE_HOME/watchtower-missions/$MISSION.md"; fi
CORE_SHA="$(printf '%s' "$POLICY" | jq -r .core_sha256)"
MISSION_SHA="$(printf '%s' "$POLICY" | jq -r .mission_sha256)"
POLICY_SHA="$(printf '%s' "$POLICY" | jq -r .policy_sha256)"
export ROZORO_WT_NAME="$WT_NAME" ROZORO_WT_PRESET="$PRESET" ROZORO_WT_PRESET_VERSION="$VERSION"
export ROZORO_WT_PRESET_SHA256="$PRESET_SHA" ROZORO_WT_POLICY_SHA256="$POLICY_SHA"
export ROZORO_WT_POLICY_CORE_SHA256="$CORE_SHA" ROZORO_WT_POLICY_MISSION_NAME="$MISSION"
export ROZORO_WT_POLICY_MISSION_SOURCE="$SOURCE" ROZORO_WT_POLICY_MISSION_SHA256="$MISSION_SHA"
export ROZORO_WT_MODEL="$MODEL" ROZORO_WT_EFFORT="$EFFORT"
ROZORO_WT_DRIVER="$(rzr_driver_id_for herdr "$HERDR_PANE_ID")"; export ROZORO_WT_DRIVER
cd "$CWD"
args=(--extension "$ROOT/.pi/extensions/rozoro-watchtower.ts" --approve --append-system-prompt "$ROOT/templates/watchtower.md")
args+=(--append-system-prompt "$MISSION_FILE")
[ -z "$RESUME" ] || args+=(--session "$RESUME")
[ -z "$MODEL" ] || args+=(--model "$MODEL")
[ -z "$EFFORT" ] || args+=(--thinking "$EFFORT")
FINAL_POLICY="$(rzr_watchtower_policy_resolve "$ROOT" "$EFFECTIVE_HOME" "$MISSION" 2>/dev/null)" || rzr_die "watchtower policy changed during launch"
[ "$FINAL_POLICY" = "$POLICY" ] || rzr_die "watchtower policy changed during launch"
exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"
