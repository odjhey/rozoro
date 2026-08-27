#!/usr/bin/env bats
load test_helper/common
bats_require_minimum_version 1.5.0

make_engine() {
  name="$1"
  mkdir -p "$TEST_ROOT/engines"
  cat > "$TEST_ROOT/engines/$name" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = info ]; then
  exit 0
fi
{
  printf 'call'
  printf '\t%s' "$@"
  printf '\n'
} >> "$ENGINE_LOG"
SH
  chmod +x "$TEST_ROOT/engines/$name"
}

make_unavailable_engine() {
  name="$1"
  mkdir -p "$TEST_ROOT/engines"
  cat > "$TEST_ROOT/engines/$name" <<'SH'
#!/usr/bin/env bash
exit 125
SH
  chmod +x "$TEST_ROOT/engines/$name"
}

@test "pinned test environment provides real Git to the unprivileged CI user" {
  [ "$(id -u)" -ne 0 ]
  run git --version
  assert_success
  assert_output_contains "git version"

  repo="$TEST_ROOT/git-contract"
  home="$TEST_ROOT/isolated-home"
  mkdir -p "$repo" "$home"
  export HOME="$home"
  export GIT_CONFIG_NOSYSTEM=1
  export GIT_CONFIG_GLOBAL=/dev/null

  run git init -q "$repo"
  assert_success
  printf 'ignored.txt\n' > "$repo/.gitignore"
  printf 'tracked\n' > "$repo/tracked.txt"
  printf 'untracked\n' > "$repo/untracked.txt"
  printf 'ignored\n' > "$repo/ignored.txt"
  run git -C "$repo" config --local user.name "CI Gate"
  assert_success
  run git -C "$repo" config --local user.email "ci-gate@example.invalid"
  assert_success
  run git -C "$repo" add .gitignore tracked.txt
  assert_success
  run git -C "$repo" check-ignore -q ignored.txt
  assert_success
  run git -C "$repo" ls-files
  assert_success
  assert_output_contains ".gitignore"
  assert_output_contains "tracked.txt"
  case "$output" in
    *untracked.txt*|*ignored.txt*) return 1 ;;
  esac
  [ ! -e "$home/.gitconfig" ]
}

@test "runner prefers Podman and applies its SELinux-safe option" {
  make_engine podman
  make_engine docker
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env PATH="$TEST_ROOT/engines:$PATH" TEST_JOBS=4 bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
  assert_file_contains "$ENGINE_LOG" $'call\tbuild'
  assert_file_contains "$ENGINE_LOG" "$REPO_ROOT/tests/Containerfile"
  assert_file_contains "$ENGINE_LOG" $'localhost/rozoro-tests:bats-1.14.0\t'
  assert_file_contains "$ENGINE_LOG" $'call\trun\t--rm\t--network\tnone\t--read-only'
  assert_file_contains "$ENGINE_LOG" "$REPO_ROOT:/workspace:ro"
  assert_file_contains "$ENGINE_LOG" $'label=disable\tlocalhost/rozoro-tests:bats-1.14.0\t--formatter\ttap\t--jobs\t4\t/workspace/tests'
}

@test "runner falls back to Docker without Podman-only options" {
  make_engine docker
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env PATH="$TEST_ROOT/engines:$PATH" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
  assert_file_contains "$ENGINE_LOG" $'call\tbuild'
  assert_file_contains "$ENGINE_LOG" $'call\trun'
  case "$(cat "$ENGINE_LOG")" in
    *label=disable*) return 1 ;;
  esac
}

@test "runner skips unavailable Podman and uses Docker" {
  make_unavailable_engine podman
  make_engine docker
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env PATH="$TEST_ROOT/engines:$PATH" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
  assert_file_contains "$ENGINE_LOG" $'call\tbuild'
  assert_file_contains "$ENGINE_LOG" $'call\trun'
  case "$(cat "$ENGINE_LOG")" in
    *label=disable*) return 1 ;;
  esac
}

@test "CONTAINER_ENGINE selects an explicit executable" {
  make_engine custom-engine
  export ENGINE_LOG="$TEST_ROOT/engine.log"

  run env CONTAINER_ENGINE="$TEST_ROOT/engines/custom-engine" bash "$REPO_ROOT/tests/run.sh"
  assert_success
  [ "$(wc -l < "$ENGINE_LOG")" -eq 2 ]
}

@test "missing explicit container engine fails before a build" {
  run -127 env CONTAINER_ENGINE=missing-engine bash "$REPO_ROOT/tests/run.sh"
  [ "$status" -eq 127 ]
  assert_output_contains "CONTAINER_ENGINE 'missing-engine' was not found on PATH"
}

@test "runner explains when neither container engine is installed" {
  mkdir -p "$TEST_ROOT/no-engines"
  ln -s "$(command -v bash)" "$TEST_ROOT/no-engines/bash"
  ln -s "$(command -v cat)" "$TEST_ROOT/no-engines/cat"
  ln -s "$(command -v dirname)" "$TEST_ROOT/no-engines/dirname"

  run -127 env PATH="$TEST_ROOT/no-engines" "$TEST_ROOT/no-engines/bash" "$REPO_ROOT/tests/run.sh"
  [ "$status" -eq 127 ]
  assert_output_contains "the test suite requires Podman or Docker"
}
