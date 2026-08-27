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

# Keep the TypeScript extension matrix in the same pinned, networkless suite as
# Bats. Its Node test runner exercises both native Node and Bun child paths.
# Capture TAP without a pipeline so the runner's status is not lost. Only
# top-level, exact TAP summary lines are accepted; child diagnostics are
# comment-indented by node:test and cannot impersonate this summary.
h3_tap="$(mktemp "${TMPDIR:-/tmp}/rozoro-h3-tap.XXXXXX")"
trap 'rm -f "$h3_tap"' EXIT
set +e
"$engine" "${run_args[@]}" --entrypoint node "$IMAGE" \
  --test --test-reporter=tap /workspace/tests/pi-extension-home-matrix.test.ts >"$h3_tap" 2>&1
h3_status=$?
set -e
cat "$h3_tap"
if [ "$h3_status" -ne 0 ]; then
  exit "$h3_status"
fi
if ! awk '
  /^1\.\.[0-9]+$/ { plan++; plan_value=$0; next }
  /^# tests [0-9]+$/ { tests++; tests_value=$3; next }
  /^# pass [0-9]+$/ { pass++; pass_value=$3; next }
  /^# fail [0-9]+$/ { fail++; fail_value=$3; next }
  /^# cancelled [0-9]+$/ { cancelled++; cancelled_value=$3; next }
  /^# skipped [0-9]+$/ { skipped++; skipped_value=$3; next }
  /^# todo [0-9]+$/ { todo++; todo_value=$3; next }
  END {
    exit !(plan == 1 && plan_value == "1..6" &&
           tests == 1 && tests_value == 6 && pass == 1 && pass_value == 6 &&
           fail == 1 && fail_value == 0 &&
           cancelled == 1 && cancelled_value == 0 &&
           skipped == 1 && skipped_value == 0 &&
           todo == 1 && todo_value == 0)
  }
' "$h3_tap"; then
  echo "error: H3 requires exactly 6 passing, non-skipped top-level tests" >&2
  exit 1
fi

exec "$engine" "${run_args[@]}" "$IMAGE" --formatter tap --jobs "$jobs" /workspace/tests
