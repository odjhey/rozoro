#!/usr/bin/env bash
# Launch or exactly resume the supported Pi watchtower in the current Herdr pane.
set -euo pipefail
RZR_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$RZR_BIN/.." && pwd)"
RESUME="" CWD="$ROOT" PRESET="" WT_NAME="" MODEL="" EFFORT="" VERSION="" PRESET_SHA="" POLICY_SHA="" CORE_ID="" MISSION_ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --resume) RESUME="${2:-}"; [ -n "$RESUME" ] || { echo "rzr: --resume requires a Pi session id or file" >&2; exit 2; }; shift 2 ;;
    --cwd) CWD="${2:-}"; [ -d "$CWD" ] || { echo "rzr: --cwd requires an existing directory" >&2; exit 2; }; shift 2 ;;
    --preset) PRESET="${2:-}"; [ -n "$PRESET" ] || { echo "rzr: --preset requires a name" >&2; exit 2; }; shift 2 ;;
    --wt-name) WT_NAME="${2:-}"; [ -n "$WT_NAME" ] || { echo "rzr: --wt-name requires a name" >&2; exit 2; }; shift 2 ;;
    --) shift; break ;;
    -h|--help)
      echo "usage: ./bin/rozoro pi-watchtower [--preset <name>] [--wt-name <name>] [--resume <session-id-or-file>] [--cwd <dir>] [-- <pi-args...>]"
      exit 0 ;;
    *) echo "rzr: unknown pi-watchtower option '$1' (put Pi options after --)" >&2; exit 2 ;;
  esac
done
[ -n "${HERDR_PANE_ID:-}" ] || { echo "rzr: pi-watchtower requires the owning HERDR_PANE_ID" >&2; exit 1; }
unset ROZORO_WT_NAME ROZORO_WT_PRESET ROZORO_WT_PRESET_VERSION ROZORO_WT_PRESET_SHA256 ROZORO_WT_POLICY_SHA256 ROZORO_WT_MODEL ROZORO_WT_EFFORT ROZORO_WT_DRIVER
if [ -n "$PRESET$WT_NAME" ]; then
  # shellcheck disable=SC1091 # The library path is resolved beside this script.
  . "$RZR_BIN/rzr-lib.sh"
fi
if [ -n "$WT_NAME" ]; then rzr_validate_wt_metadata "$WT_NAME" "watchtower name"; fi
MISSION=delivery
if [ -n "$PRESET" ]; then
  RESOLVED="$(rzr_wtpreset_resolve "$PRESET")" || rzr_die "watchtower preset '$PRESET' has invalid or unsafe content"
  [ "$(printf '%s' "$RESOLVED" | jq -r '.document.harness')" = pi ] || rzr_die "watchtower preset '$PRESET' is not for harness pi"
  [ -n "$WT_NAME" ] || WT_NAME="$PRESET"
  MODEL="$(printf '%s' "$RESOLVED" | jq -r '.document.model // empty')"
  EFFORT="$(printf '%s' "$RESOLVED" | jq -r '.document.effort // empty')"
  VERSION="$(printf '%s' "$RESOLVED" | jq -r '.document.version // 0')"
  PRESET_SHA="$(printf '%s' "$RESOLVED" | jq -r '.sha256')"
  PRESET_MISSION="$(printf '%s' "$RESOLVED" | jq -r '.document.mission // empty')"
  [ -z "$PRESET_MISSION" ] || MISSION="$PRESET_MISSION"
fi
# Exactly one source may define the mission policy: the shipped repo mission or
# the operator mission. Ambiguity and absence both fail closed before launch.
SHIPPED_MISSION="$ROOT/templates/missions/$MISSION.md"
OPERATOR_MISSION="${ROZORO_HOME:-$HOME/.rozoro}/watchtower-missions/$MISSION.md"
if [ -f "$SHIPPED_MISSION" ] && [ -f "$OPERATOR_MISSION" ]; then
  echo "rzr: watchtower mission '$MISSION' is ambiguous (shipped and operator mission files both exist)" >&2; exit 1
elif [ -f "$SHIPPED_MISSION" ]; then MISSION_FILE="$SHIPPED_MISSION"
elif [ -f "$OPERATOR_MISSION" ]; then MISSION_FILE="$OPERATOR_MISSION"
else
  echo "rzr: watchtower mission '$MISSION' not found in templates/missions/ or \$ROZORO_HOME/watchtower-missions/" >&2; exit 1
fi
if [ -n "$WT_NAME" ]; then
  CORE_ID="$(rzr_file_identity "$ROOT/templates/watchtower.md")"
  MISSION_ID="$(rzr_file_identity "$MISSION_FILE")"
  POLICY_SHA="$(rzr_sha256_concat "$ROOT/templates/watchtower.md" "$MISSION_FILE")"
  export ROZORO_WT_NAME="$WT_NAME" ROZORO_WT_PRESET="$PRESET" ROZORO_WT_PRESET_VERSION="$VERSION"
  export ROZORO_WT_PRESET_SHA256="$PRESET_SHA" ROZORO_WT_POLICY_SHA256="$POLICY_SHA"
  export ROZORO_WT_MODEL="$MODEL" ROZORO_WT_EFFORT="$EFFORT"
  ROZORO_WT_DRIVER="$(rzr_driver_id_for herdr "$HERDR_PANE_ID")"
  export ROZORO_WT_DRIVER
fi
cd "$CWD"
args=(--extension "$ROOT/.pi/extensions/rozoro-watchtower.ts" --approve --append-system-prompt "$ROOT/templates/watchtower.md")
args+=(--append-system-prompt "$MISSION_FILE")
[ -z "$RESUME" ] || args+=(--session "$RESUME")
[ -z "$MODEL" ] || args+=(--model "$MODEL")
[ -z "$EFFORT" ] || args+=(--thinking "$EFFORT")
[ -z "$CORE_ID" ] || [ "$(rzr_file_identity "$ROOT/templates/watchtower.md")" = "$CORE_ID" ] || rzr_die "watchtower policy changed during launch"
[ -z "$MISSION_ID" ] || [ "$(rzr_file_identity "$MISSION_FILE")" = "$MISSION_ID" ] || rzr_die "watchtower mission changed during launch"
exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"
