#!/usr/bin/env bats
# Pi home contract: real launcher -> fake Pi -> real registrar -> fake Herdr.
load test_helper/common

make_pi_registrar() {
  export HERDR_PANE_ID=home-matrix-pane PI_OBSERVED="$TEST_ROOT/pi-observed"
  fake_pane "$HERDR_PANE_ID" idle pi true
  mkdir -p "$TEST_ROOT/bin"
  cat > "$TEST_ROOT/bin/pi" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf 'home=%s\ncwd=%s\n' "$ROZORO_HOME" "$PWD" > "$PI_OBSERVED"
printf 'policy=%s:%s:%s:%s:%s\n' "$ROZORO_WT_POLICY_SHA256" "$ROZORO_WT_POLICY_CORE_SHA256" "$ROZORO_WT_POLICY_MISSION_NAME" "$ROZORO_WT_POLICY_MISSION_SOURCE" "$ROZORO_WT_POLICY_MISSION_SHA256" >> "$PI_OBSERVED"
printf 'arg=%s\n' "$@" >> "$PI_OBSERVED"
[ "${PI_FORCE_FAIL:-0}" != 1 ] || { printf 'forced-failure\n' >> "$PI_OBSERVED"; exit 73; }
"$REPO_ROOT/bin/rzr-register.sh" --harness pi --quiet
SH
  chmod +x "$TEST_ROOT/bin/pi"
  export PATH="$TEST_ROOT/bin:$PATH" REPO_ROOT
}

snapshot_path() {
  if [ ! -e "$1" ] && [ ! -L "$1" ]; then printf 'ABSENT\n'; return; fi
  if [ -d "$1" ]; then printf 'DIR\n'; directory_snapshot "$1"; return; fi
  printf 'FILE\n'; python3 - "$1" <<'PY'
import hashlib, os, sys
p=sys.argv[1]
print(oct(os.lstat(p).st_mode), hashlib.sha256(open(p,'rb').read()).hexdigest())
PY
}

snapshot_decoys() {
  local label=$1 selected=$2 path; shift 2
  : > "$BATS_TEST_TMPDIR/decoys-$label.before"
  for path in "$@"; do
    [ -n "$path" ] || continue
    case "$path" in /*) ;; *) continue ;; esac
    [ "$path" = "$selected" ] && continue
    printf 'PATH %s\n' "$path" >> "$BATS_TEST_TMPDIR/decoys-$label.before"
    snapshot_path "$path" >> "$BATS_TEST_TMPDIR/decoys-$label.before"
  done
}

assert_decoys_unchanged() {
  local label=$1 selected=$2 path; shift 2
  : > "$BATS_TEST_TMPDIR/decoys-$label.after"
  for path in "$@"; do
    [ -n "$path" ] || continue
    case "$path" in /*) ;; *) continue ;; esac
    [ "$path" = "$selected" ] && continue
    printf 'PATH %s\n' "$path" >> "$BATS_TEST_TMPDIR/decoys-$label.after"
    snapshot_path "$path" >> "$BATS_TEST_TMPDIR/decoys-$label.after"
  done
  cmp "$BATS_TEST_TMPDIR/decoys-$label.before" "$BATS_TEST_TMPDIR/decoys-$label.after"
}

assert_projection_only_in() {
  local selected=$1 target history
  target="$selected/watchtowers/herdr-home-matrix-pane/target.json"
  history="${target%/target.json}/registrations.jsonl"
  [ -f "$target" ] && [ -f "$history" ]
  [ "$(jq -r .identity "$target")" = home-matrix-pane ]
  [ "$(jq -r .harness "$target")" = pi ]
  [ "$(wc -l < "$history" | tr -d ' ')" = 1 ]
  [ "$(jq -r .identity "$history")" = home-matrix-pane ]
  [ "$(jq -r '[.policy_sha256,.policy_core_sha256,.policy_mission_name,.policy_mission_source,.policy_mission_sha256] | all(type == "string" and length > 0)' "$target")" = true ]
}

assert_pi_observation() {
  local label=$1 expected=$2 cwd=$3
  grep -Fx "home=$expected" "$PI_OBSERVED"
  grep -Fx "cwd=$cwd" "$PI_OBSERVED"
  grep -E '^policy=[0-9a-f]{64}:[0-9a-f]{64}:delivery:shipped:[0-9a-f]{64}$' "$PI_OBSERVED"
  grep -A1 -Fx 'arg=--session' "$PI_OBSERVED" | grep -Fx "arg=session-$label"
  grep -A1 -Fx 'arg=--model' "$PI_OBSERVED" | grep -Fx "arg=model-$label"
  grep -Fx "arg=passthrough-$label" "$PI_OBSERVED"
}

run_home_row() {
  local label=$1 public=$2 legacy=$3 expected=$4 xdg default
  xdg="$TEST_ROOT/xdg-$label" default="$HOME/.rozoro"
  mkdir -p "$expected" "$TEST_ROOT/work-$label"; chmod 700 "$expected"
  snapshot_decoys "$label" "$expected" "$public" "$legacy" "$xdg" "$default"
  rm -f "$PI_OBSERVED"
  run env ROZORO_HOME="$public" RZR_HOME="$legacy" XDG_STATE_HOME="$xdg" \
    HERDR_PANE_ID="$HERDR_PANE_ID" PI_OBSERVED="$PI_OBSERVED" FAKE_HERDR_ROOT="$FAKE_HERDR_ROOT" \
    FAKE_HERDR_LOG="$FAKE_HERDR_LOG" PATH="$PATH" REPO_ROOT="$REPO_ROOT" HOME="$HOME" \
    "$REPO_ROOT/bin/rzr-pi-watchtower.sh" --resume "session-$label" --cwd "$TEST_ROOT/work-$label" -- --model "model-$label" "passthrough-$label"
  assert_success
  assert_pi_observation "$label" "$expected" "$TEST_ROOT/work-$label"
  assert_projection_only_in "$expected"
  assert_decoys_unchanged "$label" "$expected" "$public" "$legacy" "$xdg" "$default"
}

@test "P L B E D R T X select, hold, and project one absolute Pi home" {
  make_pi_registrar
  run_home_row P "$TEST_ROOT/home-P" "$TEST_ROOT/legacy-P" "$TEST_ROOT/home-P"
  run_home_row L '' "$TEST_ROOT/home-L" "$TEST_ROOT/home-L"
  run_home_row B "$TEST_ROOT/home-B" "$TEST_ROOT/legacy-B" "$TEST_ROOT/home-B"
  run_home_row E '' "$TEST_ROOT/home-E" "$TEST_ROOT/home-E"
  mkdir -p "$HOME/.rozoro"; chmod 700 "$HOME/.rozoro"
  run_home_row D '' '' "$HOME/.rozoro"

  expected_R="$TEST_ROOT/anchor/relative-home"; xdg_R="$TEST_ROOT/xdg-R"; legacy_R="$TEST_ROOT/legacy-R"
  mkdir -p "$expected_R" "$TEST_ROOT/work-R"; chmod 700 "$TEST_ROOT/anchor"
  snapshot_decoys R "$expected_R" "$legacy_R" "$xdg_R" "$HOME/.rozoro"
  rm -f "$PI_OBSERVED"
  run bash -c 'cd "$1" && env ROZORO_HOME=relative-home RZR_HOME="$2" XDG_STATE_HOME="$3" HERDR_PANE_ID="$4" PI_OBSERVED="$5" FAKE_HERDR_ROOT="$6" FAKE_HERDR_LOG="$7" PATH="$8" REPO_ROOT="$9" HOME="${10}" "${9}/bin/rzr-pi-watchtower.sh" --resume session-R --cwd "${11}" -- --model model-R passthrough-R' _ \
    "$TEST_ROOT/anchor" "$legacy_R" "$xdg_R" "$HERDR_PANE_ID" "$PI_OBSERVED" "$FAKE_HERDR_ROOT" "$FAKE_HERDR_LOG" "$PATH" "$REPO_ROOT" "$HOME" "$TEST_ROOT/work-R"
  assert_success
  assert_pi_observation R "$expected_R" "$TEST_ROOT/work-R"
  assert_projection_only_in "$expected_R"
  assert_decoys_unchanged R "$expected_R" "$legacy_R" "$xdg_R" "$HOME/.rozoro"

  run_home_row T '~/' '' "$HOME"
  export HOME="$TEST_ROOT/xdg-default-home"; mkdir -p "$HOME/.rozoro"; chmod 700 "$HOME/.rozoro"
  run_home_row X '' '' "$HOME/.rozoro"
}

@test "supported named-user tilde uses a provisioned passwd home and cleans success and failure" {
  make_pi_registrar
  account_record="$(ROZORO_TEST_NAMED_USER="${ROZORO_TEST_NAMED_USER:-}" python3 - <<'PY'
import os, pwd
requested=os.environ.get("ROZORO_TEST_NAMED_USER")
rows=[]
if requested:
    try: rows=[pwd.getpwnam(requested)]
    except KeyError: raise SystemExit(f"named-user gate account {requested!r} is absent from passwd")
else:
    rows=list(pwd.getpwall())
for row in rows:
    if row.pw_name and row.pw_name != str(row.pw_uid) and os.path.isdir(row.pw_dir) and os.access(row.pw_dir, os.W_OK|os.X_OK):
        print(row.pw_name); print(row.pw_dir); break
else:
    raise SystemExit("named-user gate provisioning absent: set ROZORO_TEST_NAMED_USER to a passwd-backed account with a writable home")
PY
)"
  account="$(printf '%s\n' "$account_record" | sed -n '1p')"; account_home="$(printf '%s\n' "$account_record" | sed -n '2p')"
  unique=".rozoro-h1-${BATS_TEST_NUMBER}-$$"; selected="$account_home/$unique"; failed="$account_home/$unique-fail"
  legacy="$TEST_ROOT/legacy-Tuser"; xdg="$TEST_ROOT/xdg-Tuser"; default="$HOME/.rozoro"; public_decoy="$TEST_ROOT/public-decoy-Tuser"
  sentinel="$account_home/.rozoro-h1-sentinel-${BATS_TEST_NUMBER}-$$"; printf 'preserve\n' > "$sentinel"
  snapshot_decoys Tuser-pre /no-selected-home "$selected" "$failed" "$legacy" "$xdg" "$default" "$public_decoy" "$account_home"
  run bash -c 'set -u; selected=$1; failed=$2; sentinel=$3; cleanup() { rc=$?; rm -rf -- "$selected" "$failed"; test ! -e "$selected"; test ! -e "$failed"; test "$(cat "$sentinel")" = preserve; exit "$rc"; }; trap cleanup EXIT HUP INT TERM; test ! -e "$selected"; test ! -e "$failed"; mkdir -m 700 "$selected" "$failed"; env ROZORO_HOME="~'$account'/$4" RZR_HOME="$5" XDG_STATE_HOME="$6" HERDR_PANE_ID="$7" PI_OBSERVED="$8" FAKE_HERDR_ROOT="$9" FAKE_HERDR_LOG="${10}" PATH="${11}" REPO_ROOT="${12}" HOME="${13}" "${12}/bin/rzr-pi-watchtower.sh" --resume session-Tuser --cwd "${14}" -- --model model-Tuser passthrough-Tuser || exit; test -f "$selected/watchtowers/herdr-home-matrix-pane/target.json"; test -f "$selected/watchtowers/herdr-home-matrix-pane/registrations.jsonl"; env PI_FORCE_FAIL=1 ROZORO_HOME="~'$account'/$4-fail" RZR_HOME="$5" XDG_STATE_HOME="$6" HERDR_PANE_ID="$7" PI_OBSERVED="${8}-failed" FAKE_HERDR_ROOT="$9" FAKE_HERDR_LOG="${10}" PATH="${11}" REPO_ROOT="${12}" HOME="${13}" "${12}/bin/rzr-pi-watchtower.sh" --cwd "${14}" && exit 90; test "$?" -eq 73; test -f "${8}-failed"; grep -Fx forced-failure "${8}-failed"; test ! -e "$failed/watchtowers"; test -z "$(find "$failed" -mindepth 1 -print -quit)"' _ \
    "$selected" "$failed" "$sentinel" "$unique" "$legacy" "$xdg" "$HERDR_PANE_ID" "$PI_OBSERVED" "$FAKE_HERDR_ROOT" "$FAKE_HERDR_LOG" "$PATH" "$REPO_ROOT" "$HOME" "$TEST_ROOT"
  assert_success
  [ ! -e "$selected" ] && [ ! -e "$failed" ]; [ "$(cat "$sentinel")" = preserve ]
  assert_pi_observation Tuser "$selected" "$TEST_ROOT"
  assert_decoys_unchanged Tuser-pre /no-selected-home "$selected" "$failed" "$legacy" "$xdg" "$default" "$public_decoy" "$account_home"
  rm -f "$sentinel"
}

@test "unresolved tilde user rejects before creating any home or state path" {
  make_pi_registrar
  unresolved='~rozoro-home-matrix-user-that-cannot-exist/subdir'
  literal="$TEST_ROOT/$unresolved"; legacy="$TEST_ROOT/legacy-unresolved"; xdg="$TEST_ROOT/xdg-unresolved"; default="$HOME/.rozoro"
  snapshot_decoys unresolved /no-selected-home "$literal" "$legacy" "$xdg" "$default"
  rm -f "$PI_OBSERVED"
  run bash -c 'cd "$1" && env ROZORO_HOME="$2" RZR_HOME="$3" XDG_STATE_HOME="$4" HERDR_PANE_ID="$5" PI_OBSERVED="$6" FAKE_HERDR_ROOT="$7" FAKE_HERDR_LOG="$8" PATH="$9" HOME="${10}" "${11}/bin/rzr-pi-watchtower.sh" --cwd "$1"' _ \
    "$TEST_ROOT" "$unresolved" "$legacy" "$xdg" "$HERDR_PANE_ID" "$PI_OBSERVED" "$FAKE_HERDR_ROOT" "$FAKE_HERDR_LOG" "$PATH" "$HOME" "$REPO_ROOT"
  assert_failure
  [ ! -e "$PI_OBSERVED" ]
  assert_decoys_unchanged unresolved /no-selected-home "$literal" "$legacy" "$xdg" "$default"
}
