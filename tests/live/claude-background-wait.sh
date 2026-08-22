#!/usr/bin/env bash
# Opt-in Stage 2 acceptance. Deliberately refuses to fake/scrape background jobs.
set -euo pipefail
[ "${RZR_LIVE_CLAUDE_BACKGROUND:-0}" = 1 ] || { echo "skip: set RZR_LIVE_CLAUDE_BACKGROUND=1"; exit 77; }
echo "herdr: $(herdr --version 2>&1)"
echo "Stage 2 blocked: the installed Herdr must expose normalized capability, synchronized active_count, ordered final-zero and outcome events." >&2
exit 77
