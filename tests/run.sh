#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="localhost/rozoro-tests:bats-1.14.0"

if [ -n "${CONTAINER_ENGINE:-}" ]; then
  if ! command -v "$CONTAINER_ENGINE" >/dev/null 2>&1; then
    echo "error: CONTAINER_ENGINE '$CONTAINER_ENGINE' was not found on PATH" >&2
    exit 127
  fi
  engine="$CONTAINER_ENGINE"
else
  engine=""
  for candidate in podman docker; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" info >/dev/null 2>&1; then
      engine="$candidate"
      break
    fi
  done
  if [ -z "$engine" ]; then
    cat >&2 <<'EOF'
error: the test suite requires Podman or Docker.
Start either container engine, or set CONTAINER_ENGINE to its executable.
EOF
    exit 127
  fi
fi

"$engine" build \
  --file "$ROOT/tests/Containerfile" \
  --tag "$IMAGE" \
  "$ROOT/tests"

run_args=(
  run
  --rm
  --network none
  --read-only
  --workdir /workspace
  --volume "$ROOT:/workspace:ro"
  --tmpfs /tmp:rw,exec,nosuid
  --env HOME=/tmp
  --env TMPDIR=/tmp
  --user "$(id -u):$(id -g)"
)

# Rootless Podman on SELinux hosts cannot read a bind mount without relabeling it.
# Disabling labels for this read-only, networkless test container avoids changing
# labels in the contributor's checkout. Docker does not need this Podman option.
case "${engine##*/}" in
  podman) run_args+=(--security-opt label=disable) ;;
esac

# The bats image bundles GNU parallel, so tests run --jobs-wide by default.
# Every test sandboxes its state under $BATS_TEST_TMPDIR (see test_helper),
# which keeps concurrent tests independent. TEST_JOBS=1 restores serial runs.
jobs="${TEST_JOBS:-$(getconf _NPROCESSORS_ONLN)}"

exec "$engine" "${run_args[@]}" "$IMAGE" --formatter tap --jobs "$jobs" /workspace/tests
