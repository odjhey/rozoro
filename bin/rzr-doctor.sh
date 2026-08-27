#!/usr/bin/env bash
# rzr-doctor.sh - preflight a rozoro machine: deps, herdr server, preset.
#
# Usage:
#   rzr-doctor.sh                      run every check and summarize
#
# rozoro creates its own dirs lazily ($ROZORO_HOME/{state,crew,tasks}), so there
# is nothing to "install" - this only verifies the preconditions a fresh machine
# needs: the external binaries, the resolved default harness, and a reachable
# herdr server. Exits non-zero if a hard dependency is missing.
#
# It does NOT source rzr-lib.sh up front: rzr-lib hard-fails when herdr/jq are
# absent, which is exactly the case a doctor must report gracefully.
set -uo pipefail   # deliberately not -e: run all checks, then summarize

BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RZR_HOME_RAW="${ROZORO_HOME:-${RZR_HOME:-$HOME/.rozoro}}"
if command -v python3 >/dev/null 2>&1; then
  RZR_HOME="$(RZR_HOME_RAW="$RZR_HOME_RAW" python3 - <<'PY' 2>/dev/null
import os
raw=os.environ["RZR_HOME_RAW"]; expanded=os.path.expanduser(raw)
if raw.startswith("~") and expanded.startswith("~"): raise SystemExit(2)
print(os.path.abspath(expanded))
PY
)" || RZR_HOME="<unresolved:$RZR_HOME_RAW>"
else
  case "$RZR_HOME_RAW" in '~') RZR_HOME="$HOME" ;; '~/'*) RZR_HOME="$HOME/${RZR_HOME_RAW#\~/}" ;; /*) RZR_HOME="$RZR_HOME_RAW" ;; *) RZR_HOME="$PWD/$RZR_HOME_RAW" ;; esac
fi
bad=0; ok=0
pass() { printf '  \033[32m ok \033[0m %s\n' "$1"; ok=$((ok + 1)); }
warn() { printf '  \033[33mwarn\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; bad=$((bad + 1)); }

echo "rozoro doctor"
echo "  home: $RZR_HOME"
echo "  bin:  $BIN"

echo "dependencies:"
for c in herdr jq; do
  if command -v "$c" >/dev/null 2>&1; then pass "$c ($(command -v "$c"))"
  else fail "$c not found on PATH"; fi
done
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found on PATH"
elif python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  pass "python3 $(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))') ($(command -v python3); monitor minimum is 3.11)"
else
  fail "python3 >=3.11 required for the resident monitor (Python 3.10 is not yet supported; EOL Python 3.9 is out of policy; found $(python3 --version 2>&1) at $(command -v python3)); on macOS run: brew install python and put its python3 ahead of older interpreters on PATH"
fi

echo "herdr server:"
if command -v herdr >/dev/null 2>&1; then
  if herdr tab list >/dev/null 2>&1; then pass "reachable (herdr tab list answered)"
  else fail "herdr present but server not answering — start herdr and run inside a session"; fi
else warn "skipped (herdr missing)"; fi

echo "default crew preset:"
if command -v jq >/dev/null 2>&1 && command -v herdr >/dev/null 2>&1; then
  . "$BIN/rzr-lib.sh"           # safe now: both hard deps present
  set +e                       # rzr-lib turns on -e; undo it so checks still summarize
  if rzr_crew_exists default; then pass "configured ($(rzr_crew_path default))"
  else pass "using built-in fallback (no $(rzr_crew_path default))"; fi
  default_harness="$(rzr_crew_field default harness)"
  if [ -n "$default_harness" ] && command -v "$default_harness" >/dev/null 2>&1; then
    pass "default harness $default_harness ($(command -v "$default_harness"))"
    if [ "$default_harness" = copilot ]; then
      capability_error="$(rzr_copilot_capabilities 2>&1)"
      if [ $? -eq 0 ]; then pass "Copilot CLI has required managed-crew capabilities"
      else fail "$capability_error"; fi
    fi
  else
    fail "default harness '${default_harness:-unknown}' not found on PATH"
  fi
else warn "skipped (needs jq + herdr)"; fi

echo
if [ "$bad" -eq 0 ]; then
  echo "all good ($ok checks passed) — try: ./bin/rozoro start t1 --body <file> --cwd <repo>"
  exit 0
else
  echo "$bad check(s) failed — resolve the above, then re-run ./bin/rozoro doctor"
  exit 1
fi
