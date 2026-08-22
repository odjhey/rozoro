#!/usr/bin/env bats
# Unit tests for the durable wake ledger state machine (rzr-lib helpers).
load test_helper/common

# Drive the ledger helpers in a subshell so rzr-lib's `set -e` stays contained.
drive() { run bash -c ". \"$REPO_ROOT/bin/rzr-lib.sh\"; dir=\"$ROZORO_HOME/watchtowers/d\"; $1"; }

@test "ledger coalesces a burst into one outstanding nudge until acked" {
  drive '
    rzr_ledger_bump "$dir" t1 done                                  # g=1
    rzr_ledger_should_deliver "$dir" && echo D1 || echo N1          # yes: 1>0 && 0<=0
    rzr_ledger_record "$dir" delivered                              # d=1
    rzr_ledger_bump "$dir" t2 idle                                  # g=2 (burst)
    rzr_ledger_bump "$dir" t3 blocked                               # g=3 (burst)
    rzr_ledger_should_deliver "$dir" && echo D2 || echo N2          # no: outstanding nudge (d=1>a=0)
    rzr_ledger_ack "$dir" 3                                         # driver reconciled through g=3
    rzr_ledger_should_deliver "$dir" && echo D3 || echo N3          # no: 3>3 false
    rzr_ledger_bump "$dir" t1 done                                  # g=4 arrived after ack
    rzr_ledger_should_deliver "$dir" && echo D4 || echo N4          # yes: 4>3 && 1<=3
  '
  assert_success
  assert_output_contains D1
  assert_output_contains N2
  assert_output_contains N3
  assert_output_contains D4
}

@test "ledger persists generation before delivery and survives a re-read" {
  drive '
    rzr_ledger_bump "$dir" t1 done
    echo "gen=$(rzr_ledger_int "$dir" generation) del=$(rzr_ledger_int "$dir" delivered) ack=$(rzr_ledger_int "$dir" ack)"
  '
  assert_success
  assert_output_contains 'gen=1 del=0 ack=0'
  [ -f "$ROZORO_HOME/watchtowers/d/pending.json" ]
  [ "$(jq -r '.tasks.t1.status' "$ROZORO_HOME/watchtowers/d/pending.json")" = done ]
}

@test "ledger files are created user-only" {
  drive 'rzr_ledger_bump "$dir" t1 done; rzr_ledger_ack "$dir" 1'
  assert_success
  [ "$(file_perm "$ROZORO_HOME/watchtowers/d/pending.json")" = 600 ]
  [ "$(file_perm "$ROZORO_HOME/watchtowers/d/ack")" = 600 ]
}

@test "concurrent watcher bumps do not lose generations or affected tasks" {
  drive '
    mkdir -p "$dir"
    for i in $(seq 1 24); do (rzr_ledger_bump "$dir" "t$i" done) & done
    wait
    echo "gen=$(rzr_ledger_int "$dir" generation) tasks=$(jq ".tasks | length" "$dir/pending.json")"
  '
  assert_success
  assert_output_contains 'gen=24 tasks=24'
}
