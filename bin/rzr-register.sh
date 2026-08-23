#!/usr/bin/env bash
# rzr-register.sh - register this watchtower's validated wake-delivery target.
#
# Usage:
#   rzr-register.sh --harness <claude|codex|copilot|pi> [--backend auto|codex|herdr]
#                   [--driver-id <id>] [--quiet]
#
# Writes watchtowers/<driver-id>/target.json pinning ONE immutable delivery
# identity for `rzr-watch --wake`. The declared harness is validated against live
# state before it is pinned, so a stale inherited CODEX_THREAD_ID can never wake
# the wrong conversation:
#   - codex backend: requires CODEX_THREAD_ID and a Codex CLI with `queue`; the
#     declared harness must be codex.
#   - herdr backend: requires HERDR_PANE_ID and that the pane REPORTS the declared
#     harness and is interactive_ready.
#   - auto: picks codex only when the declared harness is codex and the Codex
#     queue is available; otherwise the validated herdr pane. It never selects a
#     backend from the mere presence of an environment variable.
#
# Prints the driver id (unless --quiet). Idempotent for the same identity.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

HARNESS="" BACKEND="auto" DRIVER_ID="" QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --harness) HARNESS="${2:-}"; shift 2 ;;
    --backend) BACKEND="${2:-}"; shift 2 ;;
    --driver-id) DRIVER_ID="${2:-}"; shift 2 ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) rzr_die "unknown flag: $1" ;;
  esac
done

case "$HARNESS" in
  claude|codex|copilot|pi) ;;
  "") rzr_die "--harness is required (claude|codex|copilot|pi)" ;;
  *)  rzr_die "unsupported --harness '$HARNESS' (claude|codex|copilot|pi)" ;;
esac
case "$BACKEND" in auto|codex|herdr) ;; *) rzr_die "unsupported --backend '$BACKEND'" ;; esac

codex_ok() { [ -n "${CODEX_THREAD_ID:-}" ] && command -v codex >/dev/null 2>&1 && codex queue --help >/dev/null 2>&1; }

# Validate the herdr pane actually runs the declared harness before pinning it.
validate_herdr() {
  [ -n "${HERDR_PANE_ID:-}" ] || rzr_die "herdr backend requires HERDR_PANE_ID from the resident pane"
  local line hp ready
  line=$(rzr_pane_harness_ready "$HERDR_PANE_ID")
  hp="${line%% *}"; ready="${line##* }"
  [ -n "$hp" ] || rzr_die "herdr does not report a harness for pane '$HERDR_PANE_ID' (is the agent live?)"
  [ "$hp" = "$HARNESS" ] || rzr_die "declared harness '$HARNESS' does not match pane '$HERDR_PANE_ID' (herdr reports '$hp') — refusing to wake the wrong session"
  [ "$ready" = true ] || rzr_die "pane '$HERDR_PANE_ID' is not interactive_ready yet"
}

case "$BACKEND" in
  codex)
    [ "$HARNESS" = codex ] || rzr_die "codex backend requires --harness codex"
    codex_ok || rzr_die "codex backend requires CODEX_THREAD_ID and a Codex CLI with 'queue'"
    IDENTITY="$CODEX_THREAD_ID" ;;
  herdr)
    validate_herdr
    IDENTITY="$HERDR_PANE_ID" ;;
  auto)
    if [ "$HARNESS" = codex ] && codex_ok; then
      BACKEND=codex; IDENTITY="$CODEX_THREAD_ID"
    else
      validate_herdr
      BACKEND=herdr; IDENTITY="$HERDR_PANE_ID"
    fi ;;
esac

[ -n "$DRIVER_ID" ] || DRIVER_ID="$(rzr_driver_id_for "$BACKEND" "$IDENTITY")"
DIR="$(rzr_driver_dir "$DRIVER_ID")"
mkdir -p "$(rzr_watchtowers_dir)"; chmod 700 "$(rzr_watchtowers_dir)"
mkdir -p "$DIR"; chmod 700 "$DIR"

RZR_REG_OUT="$DIR/target.json" RZR_REG_ID="$DRIVER_ID" RZR_REG_HARNESS="$HARNESS" \
RZR_REG_BACKEND="$BACKEND" RZR_REG_IDENTITY="$IDENTITY" RZR_REG_OWNER="$PPID" \
RZR_REG_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)" python3 - <<'PY'
import json, os
tmp = os.environ["RZR_REG_OUT"] + ".tmp.%d" % os.getpid()
os.umask(0o077)
json.dump({"schema": 1, "driver_id": os.environ["RZR_REG_ID"],
           "harness": os.environ["RZR_REG_HARNESS"], "backend": os.environ["RZR_REG_BACKEND"],
           "identity": os.environ["RZR_REG_IDENTITY"], "owner_pid": os.environ["RZR_REG_OWNER"],
           "created": os.environ["RZR_REG_TS"]}, open(tmp, "w"), indent=2)
os.replace(tmp, os.environ["RZR_REG_OUT"])
PY

[ "$QUIET" -eq 1 ] || echo "$DRIVER_ID"
