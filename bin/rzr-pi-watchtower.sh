#!/usr/bin/env bash
# Launch or exactly resume the supported Pi watchtower in the current Herdr pane.
set -euo pipefail
RZR_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$RZR_BIN/.." && pwd)"
. "$RZR_BIN/rzr-lib.sh"
RESUME="" CWD="$ROOT" PRESET="" WT_NAME="" MODEL="" EFFORT="" VERSION="" PRESET_SHA="" POLICY_SHA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --resume) RESUME="${2:-}"; [ -n "$RESUME" ] || { echo "rzr: --resume requires a Pi session id or file" >&2; exit 2; }; shift 2 ;;
    --cwd) CWD="${2:-}"; [ -d "$CWD" ] || { echo "rzr: --cwd requires an existing directory" >&2; exit 2; }; shift 2 ;;
    --preset) PRESET="${2:-}"; [ -n "$PRESET" ] || rzr_die "--preset requires a name"; shift 2 ;;
    --wt-name) WT_NAME="${2:-}"; [ -n "$WT_NAME" ] || rzr_die "--wt-name requires a name"; shift 2 ;;
    --) shift; break ;;
    -h|--help)
      echo "usage: ./bin/rozoro pi-watchtower [--preset <name>] [--wt-name <name>] [--resume <session-id-or-file>] [--cwd <dir>] [-- <pi-args...>]"
      exit 0 ;;
    *) echo "rzr: unknown pi-watchtower option '$1' (put Pi options after --)" >&2; exit 2 ;;
  esac
done
[ -n "${HERDR_PANE_ID:-}" ] || { echo "rzr: pi-watchtower requires the owning HERDR_PANE_ID" >&2; exit 1; }
if [ -n "$PRESET" ]; then
  rzr_wtpreset_exists "$PRESET" || rzr_die "no such watchtower preset '$PRESET'"
  rzr_wtpreset_validate "$PRESET" || rzr_die "watchtower preset '$PRESET' has invalid JSON or known field types"
  [ "$(rzr_wtpreset_field "$PRESET" harness)" = pi ] || rzr_die "watchtower preset '$PRESET' is not for harness pi"
  [ -n "$WT_NAME" ] || WT_NAME="$PRESET"
  MODEL="$(rzr_wtpreset_field "$PRESET" model)"; EFFORT="$(rzr_wtpreset_field "$PRESET" effort)"
  VERSION="$(rzr_wtpreset_field "$PRESET" version)"; VERSION="${VERSION:-0}"
  PRESET_SHA="$(rzr_sha256_file "$(rzr_wtpreset_path "$PRESET")")"
  POLICY_SHA="$(rzr_sha256_file "$ROOT/templates/watchtower.md")"
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
exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"
