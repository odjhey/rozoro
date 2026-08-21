#!/usr/bin/env bash
# rzr-lock.sh - inspect or drive the home lock directly.
#
# Usage:
#   rzr-lock.sh status     show whether the lock is held, by whom, since when
#   rzr-lock.sh acquire    take the lock and hold it until you press Enter/Ctrl-C
#                         (demonstrates that a second holder is refused)
#
# The lock is an atomic mkdir of state/.lock recording the holder pid. A holder
# whose pid is dead is treated as stale and reclaimed on the next acquire, so a
# crashed orchestrator never wedges the home. rzr-spawn.sh takes it around the
# create-tab/write-meta mutation so two spawns cannot race.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

case "${1:-status}" in
  status)
    if [ -d "$RZR_LOCK_DIR" ]; then
      pid=$(cat "$RZR_LOCK_DIR/pid" 2>/dev/null || echo "?")
      since=$(cat "$RZR_LOCK_DIR/since" 2>/dev/null || echo "?")
      if [ "$pid" != "?" ] && kill -0 "$pid" 2>/dev/null; then
        echo "held by pid $pid since $since"
      else
        echo "held by pid $pid since $since (STALE - dead holder, next acquire reclaims)"
      fi
    else
      echo "free"
    fi
    ;;
  acquire)
    rzr_lock_acquire 0 || exit 1
    trap 'rzr_lock_release' EXIT INT TERM
    echo "rzr: lock held by pid $$; press Enter to release"
    read -r _ || true
    ;;
  *) rzr_die "usage: rzr-lock.sh status|acquire" ;;
esac
