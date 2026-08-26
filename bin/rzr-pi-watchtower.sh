#!/usr/bin/env bash
# Launch or exactly resume the supported Pi watchtower in the current Herdr pane.
set -euo pipefail
RZR_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$RZR_BIN/.." && pwd)"
RESUME="" CWD="$ROOT" PRESET="" WT_NAME="" MODEL="" EFFORT="" VERSION="" PRESET_SHA="" POLICY_SHA="" POLICY_ID=""
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
if [ -n "$PRESET$WT_NAME" ]; then . "$RZR_BIN/rzr-lib.sh"; fi
if [ -n "$WT_NAME" ]; then rzr_validate_wt_metadata "$WT_NAME" "watchtower name"; fi
if [ -n "$PRESET" ]; then
  RESOLVED="$(rzr_wtpreset_resolve "$PRESET")" || rzr_die "watchtower preset '$PRESET' has invalid or unsafe content"
  [ "$(printf '%s' "$RESOLVED" | jq -r '.document.harness')" = pi ] || rzr_die "watchtower preset '$PRESET' is not for harness pi"
  [ -n "$WT_NAME" ] || WT_NAME="$PRESET"
  MODEL="$(printf '%s' "$RESOLVED" | jq -r '.document.model // empty')"
  EFFORT="$(printf '%s' "$RESOLVED" | jq -r '.document.effort // empty')"
  VERSION="$(printf '%s' "$RESOLVED" | jq -r '.document.version // 0')"
  PRESET_SHA="$(printf '%s' "$RESOLVED" | jq -r '.sha256')"
  POLICY_ID="$(rzr_file_identity "$ROOT/templates/watchtower.md")"
  POLICY_SHA="${POLICY_ID##*:}"
fi
if [ -n "$WT_NAME" ]; then
  export ROZORO_WT_NAME="$WT_NAME" ROZORO_WT_PRESET="$PRESET" ROZORO_WT_PRESET_VERSION="$VERSION"
  export ROZORO_WT_PRESET_SHA256="$PRESET_SHA" ROZORO_WT_POLICY_SHA256="$POLICY_SHA"
  export ROZORO_WT_MODEL="$MODEL" ROZORO_WT_EFFORT="$EFFORT"
  ROZORO_WT_DRIVER="$(rzr_driver_id_for herdr "$HERDR_PANE_ID")"
  export ROZORO_WT_DRIVER
fi
cd "$CWD"
args=(--extension "$ROOT/.pi/extensions/rozoro-watchtower.ts" --approve --append-system-prompt "$ROOT/templates/watchtower.md")
[ -z "$RESUME" ] || args+=(--session "$RESUME")
[ -z "$MODEL" ] || args+=(--model "$MODEL")
[ -z "$EFFORT" ] || args+=(--thinking "$EFFORT")
[ -z "$POLICY_ID" ] || [ "$(rzr_file_identity "$ROOT/templates/watchtower.md")" = "$POLICY_ID" ] || rzr_die "watchtower policy changed during launch"
exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"
