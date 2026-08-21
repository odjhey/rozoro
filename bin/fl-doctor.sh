#!/usr/bin/env bash
# fl-doctor.sh - preflight a rozoro machine: deps, herdr server, PATH, preset.
#
# Usage:
#   fl-doctor.sh                      run every check and summarize
#
# rozoro creates its own dirs lazily ($ROZORO_HOME/{state,crew,tasks}), so there
# is nothing to "install" - this only verifies the preconditions a fresh machine
# needs: the herdr/jq/python3 binaries, a reachable herdr server, bin/ on PATH,
# and a visible default crew preset. Exits non-zero if a hard dep is missing.
#
# It does NOT source fl-lib.sh up front: fl-lib hard-fails when herdr/jq are
# absent, which is exactly the case a doctor must report gracefully.
set -uo pipefail   # deliberately not -e: run all checks, then summarize

BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FL_HOME="${ROZORO_HOME:-${FL_HOME:-$HOME/.rozoro}}"
bad=0; ok=0
pass() { printf '  \033[32m ok \033[0m %s\n' "$1"; ok=$((ok + 1)); }
warn() { printf '  \033[33mwarn\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; bad=$((bad + 1)); }

echo "rozoro doctor"
echo "  home: $FL_HOME"
echo "  bin:  $BIN"

echo "dependencies:"
for c in herdr jq python3; do
  if command -v "$c" >/dev/null 2>&1; then pass "$c ($(command -v "$c"))"
  else fail "$c not found on PATH"; fi
done

echo "herdr server:"
if command -v herdr >/dev/null 2>&1; then
  if herdr tab list >/dev/null 2>&1; then pass "reachable (herdr tab list answered)"
  else fail "herdr present but server not answering — start herdr and run inside a session"; fi
else warn "skipped (herdr missing)"; fi

echo "PATH:"
case ":$PATH:" in
  *":$BIN:"*) pass "bin/ on PATH" ;;
  *) warn "bin/ not on PATH — add to your shell rc:  export PATH=\"$BIN:\$PATH\"" ;;
esac

echo "default crew preset:"
if command -v jq >/dev/null 2>&1 && command -v herdr >/dev/null 2>&1; then
  . "$BIN/fl-lib.sh"           # safe now: both hard deps present
  set +e                       # fl-lib turns on -e; undo it so checks still summarize
  fl_crew_ensure_default
  if fl_crew_exists default; then pass "present ($(fl_crew_path default))"
  else fail "could not create default preset under $FL_HOME/crew"; fi
else warn "skipped (needs jq + herdr)"; fi

echo
if [ "$bad" -eq 0 ]; then
  echo "all good ($ok checks passed) — try: fl-start.sh t1 --body <file> --cwd <repo>"
  exit 0
else
  echo "$bad check(s) failed — resolve the above, then re-run fl-doctor.sh"
  exit 1
fi
