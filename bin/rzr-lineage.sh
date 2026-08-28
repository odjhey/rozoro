#!/usr/bin/env bash
set -euo pipefail
BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$BIN/rzr-lineage.py" "$@"
