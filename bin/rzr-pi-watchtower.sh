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
unset ROZORO_WT_NAME ROZORO_WT_PRESET ROZORO_WT_PRESET_VERSION ROZORO_WT_PRESET_SHA256 ROZORO_WT_POLICY_SHA256 ROZORO_WT_MODEL ROZORO_WT_EFFORT ROZORO_WT_DRIVER
if [ -n "$PRESET$WT_NAME" ]; then
  # shellcheck disable=SC1091 # The library path is resolved beside this script.
  . "$RZR_BIN/rzr-lib.sh"
fi
if [ -n "$WT_NAME" ]; then rzr_validate_wt_metadata "$WT_NAME" "watchtower name"; fi
if [ -n "$PRESET" ]; then
  RESOLVED="$(rzr_wtpreset_resolve "$PRESET")" || rzr_die "watchtower preset '$PRESET' has invalid or unsafe content"
  [ "$(printf '%s' "$RESOLVED" | jq -r '.document.harness')" = pi ] || rzr_die "watchtower preset '$PRESET' is not for harness pi"
  [ -n "$WT_NAME" ] || WT_NAME="$PRESET"
  MODEL="$(printf '%s' "$RESOLVED" | jq -r '.document.model // empty')"
  EFFORT="$(printf '%s' "$RESOLVED" | jq -r '.document.effort // empty')"
  VERSION="$(printf '%s' "$RESOLVED" | jq -r '.document.version // 0')"
  PRESET_SHA="$(printf '%s' "$RESOLVED" | jq -r '.sha256')"
fi
if [ -n "$WT_NAME" ]; then
  POLICY_ID="$(rzr_file_identity "$ROOT/templates/watchtower.md")"
  POLICY_SHA="${POLICY_ID##*:}"
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
if [ -n "$POLICY_ID" ]; then
  exec python3 - "$ROOT/templates/watchtower.md" "$POLICY_ID" "${args[@]}" "$@" <<'PY'
import hashlib, os, stat, sys
path, expected = sys.argv[1:3]
fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode): raise SystemExit("watchtower policy is not a regular file")
    digest = hashlib.sha256()
    chunks = []
    while True:
        chunk = os.read(fd, 65536)
        if not chunk: break
        chunks.append(chunk); digest.update(chunk)
    actual = f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{digest.hexdigest()}"
    if actual != expected: raise SystemExit("watchtower policy changed during launch")
    policy = b"".join(chunks).decode()
finally:
    os.close(fd)
pi_args = sys.argv[3:]
for index, value in enumerate(pi_args[:-1]):
    if value == "--append-system-prompt" and pi_args[index + 1] == path:
        pi_args[index + 1] = policy
        break
else:
    raise SystemExit("watchtower policy argument missing")
os.environ["ROZORO_WATCHTOWER"] = "1"
os.execvpe("pi", ["pi"] + pi_args, os.environ)
PY
fi
exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"
