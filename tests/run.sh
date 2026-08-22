#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v bats >/dev/null 2>&1; then
  cat >&2 <<'EOF'
error: bats-core 1.14.x is required on PATH.
macOS: brew install bats-core
Other platforms: npm install -g bats, or install v1.14.0 from
https://github.com/bats-core/bats-core/releases/tag/v1.14.0
EOF
  exit 127
fi

version="$(bats --version 2>/dev/null || true)"
case "$version" in
  'Bats 1.14.'*) ;;
  *)
    echo "error: bats-core 1.14.x is required; found: ${version:-unknown}" >&2
    echo "install v1.14.0: https://github.com/bats-core/bats-core/releases/tag/v1.14.0" >&2
    exit 2
    ;;
esac

exec bats --formatter tap "$ROOT/tests"
