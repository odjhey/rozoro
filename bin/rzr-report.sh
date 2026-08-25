#!/usr/bin/env bash
# rzr-report.sh - generate static HTML fleet reports from the rozorod event store.
#
# Usage:
#   ./bin/rozoro report [durations|timeline|all] [--out DIR] [--home DIR]
#
# Read-only over $ROZORO_HOME/monitor.db (mode=ro; never touches the daemon or
# any delivery/ACK cursor). Writes dated, self-contained HTML files to
# <home>/reports/ by default and prints the paths it wrote.
#
# Deliberately does NOT source rzr-lib.sh: reporting needs neither herdr nor jq,
# and must stay usable on a box that only holds the durable state.
set -euo pipefail
BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$BIN/rzr-report.py" "$@"
