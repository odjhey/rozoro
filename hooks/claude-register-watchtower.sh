#!/usr/bin/env bash
# Claude Code SessionStart hook: register this watchtower's wake target.
#
# `rozoro register --harness claude` requires the herdr pane to report
# interactive_ready, but SessionStart fires while Claude Code is still
# booting -- well before herdr's own readiness probe flips true (measured
# ~2-3s gap in testing: SessionStart lands under 1s in, interactive_ready
# only lands once `herdr agent start`'s own readiness wait resolves). A
# single-shot call reliably fails at boot, so retry briefly instead.
#
# Best-effort and silent: exits 0 unconditionally so a missing herdr pane,
# a non-claude harness mismatch, or exhausted retries never blocks or
# fails a session start. If retries run out, the manual fallback documented
# in templates/watchtower.md (`!rozoro register --harness claude` at the
# first idle prompt) still applies.
#
# This hook fires for EVERY Claude session opened in this checkout -- a crew
# spawned to work on rozoro itself, or a plain dev session, included. Only a
# real watchtower should self-register as a wake target, so this is gated on
# a positive opt-in: ROZORO_ROLE=watchtower, set by the watchtower launch
# recipe in templates/watchtower.md. Without it, no-op immediately (no herdr
# call, no target.json, no boot delay).
set -u

[ "${ROZORO_ROLE:-}" = watchtower ] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROZORO="$ROOT/bin/rozoro"
[ -x "$ROZORO" ] || exit 0
[ -n "${HERDR_PANE_ID:-}" ] || exit 0

for _ in $(seq 1 20); do
  "$ROZORO" register --harness claude --quiet >/dev/null 2>&1 && exit 0
  sleep 0.5
done
exit 0
