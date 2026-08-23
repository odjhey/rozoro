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
RZR_HOME="${ROZORO_HOME:-${RZR_HOME:-$HOME/.rozoro}}"
bad=0; ok=0
pass() { printf '  \033[32m ok \033[0m %s\n' "$1"; ok=$((ok + 1)); }
warn() { printf '  \033[33mwarn\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; bad=$((bad + 1)); }

echo "rozoro doctor"
echo "  home: $RZR_HOME"
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

echo "role preferences (per-machine coder/planner):"
if command -v jq >/dev/null 2>&1 && command -v herdr >/dev/null 2>&1; then
  . "$BIN/rzr-lib.sh"           # idempotent if already sourced above
  set +e
  for role in $(rzr_role_names); do
    role_harness="$(rzr_role_field "$role" harness)"
    role_model="$(rzr_role_field "$role" model)"
    if rzr_role_exists "$role"; then
      origin="$(rzr_role_path "$role")"
      if [ -n "$role_harness" ] && command -v "$role_harness" >/dev/null 2>&1; then
        pass "$role -> $role_harness/$role_model ($origin)"
      else
        # A host-local file naming a missing harness is a real misconfiguration -
        # unlike the default crew preset, --role is opt-in per spawn, so this
        # only bites the roles someone actually configured.
        fail "$role -> harness '${role_harness:-unknown}' not found on PATH ($origin)"
      fi
    else
      origin="built-in fallback"
      if [ -n "$role_harness" ] && command -v "$role_harness" >/dev/null 2>&1; then
        pass "$role -> $role_harness/$role_model ($origin)"
      else
        warn "$role -> harness '${role_harness:-unknown}' not found on PATH ($origin) - unused until --role $role is passed"
      fi
    fi
  done
else warn "skipped (needs jq + herdr)"; fi

echo
if [ "$bad" -eq 0 ]; then
  echo "all good ($ok checks passed) — try: ./bin/rozoro start t1 --body <file> --cwd <repo>"
  exit 0
else
  echo "$bad check(s) failed — resolve the above, then re-run ./bin/rozoro doctor"
  exit 1
fi
