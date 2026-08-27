#!/usr/bin/env bash
# Replay one agent's full communication history, or index every agent.
set -euo pipefail
BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$BIN/rzr-lineage.py" "$@"
