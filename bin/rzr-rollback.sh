#!/usr/bin/env bash
# Transactionally hand one clean driver back to a prior legacy release.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"
DRIVER=""
while [ $# -gt 0 ]; do case "$1" in --driver) DRIVER="${2:-}"; shift 2;; -h|--help) echo 'usage: ./bin/rozoro rollback --driver ID'; exit 0;; *) rzr_die "unknown flag: $1";; esac; done
[ -n "$DRIVER" ] || rzr_die "rollback requires --driver ID"
# The daemon transaction refuses unless generation=delivered=ack, tombstones the
# authority first, and only then does the bridge remove the persistent marker
# under the authority lock. Stop/restore the release only after this succeeds.
python3 "$RZR_BIN/rzr-event-bus-client.py" authority-disable --driver "$DRIVER" >/dev/null
echo "driver $DRIVER is cleanly tombstoned; now stop the monitor and restore the prior release"
