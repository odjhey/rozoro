# Pi + Claude event-bus production cutover

Status: G3 landed; G4/G5 release gate

## Authority

`rozorod` and its SQLite event store are the single semantic owner for managed Pi
and supported Claude sessions. `status` and `reconcile` always use the daemon;
there is no opt-in flag or automatic legacy fallback. Pi's extension is only a
reconnecting protocol adapter and fixed-wake actuator. Claude hooks are only
lifecycle producers. Herdr remains host, liveness source, and safe wake actuator.

Pi's adapter is a producer under the same protocol contract as the Claude hook.
It reserves `producer_seq` durably per session in `producer-seq/<session-id>.seq`,
the file `lib/rozoro_monitor/client.py` owns, so a resumed Pi session continues a
contiguous sequence instead of restarting it or jumping to a wall-clock value.
The cursor advances only after the daemon ACKs an event: a lagging cursor merely
replays a sequence the reducer discards as stale, while a leading one would leave
a permanent reducer gap that no resync path drains.

Pi exposes no background-job snapshot to the extension, so its capability model
has no background axis to observe. Its `turn.stop` therefore certifies
`background_active: false` — a stopped Pi foreground turn leaves nothing
outstanding. This is the Pi analogue of the Claude rule in
`docs/claude-hook-capability.md`, where clear is certified only from an
authoritative empty `Stop.background_tasks` snapshot.

`rzr-watch` remains available only as an explicit legacy/diagnostic observer for
Codex, Copilot, old releases, and manual Herdr transport diagnosis. Do not run it
beside a managed Pi or supported-Claude driver.

## Upgrade boundary

Before installing this release, use the prior release to reconcile every legacy
driver whose `watchtowers/<driver>/pending.json` has `generation > ack`. Stop old
watchers, then upgrade and start the daemon. The new release does not import the
JSON ledger: first daemon-backed status/reconcile atomically refuses a dirty
ledger and identifies the driver. This is intentional; never delete or edit the
ledger to bypass the refusal.

```sh
# prior release
./bin/rozoro reconcile --driver <driver>
# new release
./bin/rozoro doctor              # verifies Python >=3.11 and other prerequisites
./bin/rozoro monitor start
./bin/rozoro monitor status --json
./bin/rozoro status <task> --json
```

Existing `tasks/<id>/brief.md`, append-only `handoff.md`, `session.json`, ACK
cursors, task identities, and `.meta` membership are not migrated or rewritten.

## Schema 7 lifecycle-correctness migration

Schema 7 is an atomic, evidence-preserving repair. Before the first new-binary
start, stop producers and reconcile until every driver's latest, delivered, and
ACK generations are equal. The spool must be empty and no unconfirmed delivery
offer may remain. Startup refuses the migration if any precondition is false.

With the old daemon cleanly stopped, take a SQLite-safe backup (including WAL
state, preferably with SQLite's backup API), then start the new daemon. Migration
retains every event envelope, durable sequence, historical generation/snapshot,
delivery audit, authority identity, task file, handoff, session link, and report
ACK cursor. It captures exact Herdr `agent.list` immediately before the transaction and
requires it to agree with validated owner-private metadata before populating
active membership. Any unavailable or inconsistent inventory aborts and rolls
back the migration. It retires absent projection history from future snapshots, repairs current report
authority read-only, and quarantines the mutable timestamp-scale Pi gap signature.
It does not create a notification.

After verifying schema/version, row counts, equal cursors, and active membership,
perform one controlled reload of live Pi crew/watchtower adapters. Their durable
producer custody then starts or continues at a contiguous baseline. Custody is
format-versioned and semantically bound to the configured session, role, and
task/driver; foreign envelopes and unsupported downgrade markers fail closed
before transmission. Quarantined
sessions remain unknown until that registration is accepted; Herdr text is never
used to invent lifecycle state. Complete the documented Pi+Claude live soak
before beginning adapter PR17. This implementation does not perform that live
rollout.

A migration exception rolls the complete transaction back to schema 6. Schema-6
binaries refuse schema 7 rather than guessing. To roll back after successful
migration, first restore equal cursors and empty spool/offers, stop cleanly, and
restore the complete pre-migration backup. Never open schema 7 with an old binary.
Without a backup, the supported fallback is an explicit event-bus DB reset at
equal cursors; that intentionally discards monitor history but does not edit task
folders, handoffs, links, or report ACK cursors.

## Fresh install and health

The monitor requires Python >=3.11. Python 3.10 is not yet supported, and EOL
Python 3.9 is out of policy. If doctor reports an unsupported runtime, run
`brew install python` and ensure Homebrew's `python3` precedes older interpreters
on PATH.
The start command performs the same version check before spawning `rozorod`, so
adapter/spool callers receive the runtime error directly instead of waiting for
a generic readiness timeout.

Managed Pi and supported-Claude launch/spawn/resume safely start the monitor
concurrently and wait for its health endpoint before starting the adapter. A
failed readiness check aborts launch. Pi is passed the checkout-owned extension
explicitly even when its task cwd is another repository. No `ROZORO_EVENT_BUS*`
variable is required or supported.

Use `monitor status --json` to diagnose: daemon down (`running=false`), Herdr
`connected`/`disconnected`, adapter-derived `unknown`, delivery `settled` when no
generation is pending or awaiting ACK, `deferred`, `delivered` with generation
above ACK, retry/error counters, and spool backlog. A live pane with a
disconnected adapter remains `unknown`, never quiescent.

## Rollback

First reconcile until the selected driver's generation, delivered, and ACK
cursors are equal. While the daemon is still running, transactionally tombstone
its authority and remove the persistent marker, then stop it and restore the
prior release:

```sh
./bin/rozoro rollback --driver <driver>
./bin/rozoro monitor stop
# restore prior release only now
```

The rollback command refuses unequal cursors and removes the marker only after
the daemon commits the tombstone. Task folders and handoffs are unchanged. Do
not run old and new owners concurrently.

For a pre-v5/pre-v6 monitor schema downgrade, see
[`docs/event-bus-rollback.md`](event-bus-rollback.md).

## Release evidence

G3 is the merged, reviewed exact-Claude-2.1.240 evidence in
`claude-watchtower-live-gate.md` and
`tests/fixtures/claude-watchtower-g3-2.1.240.json`.

G4/G5 structural evidence is recorded in
`tests/fixtures/event-bus-g4-g5.json`. It covers the real Pi fixed-wake/reconcile
path, delivered-unacked restart, metadata isolation, clustered completion,
five daemon restarts with zero synthetic completion, fresh/upgrade/rollback
smokes, refusal of a dirty old ledger, all required health states, durable task
and handoff preservation, and single ownership. Raw paths, prompts, session IDs,
transcripts, and model prose are intentionally excluded.

The resident daemon delivers and supersedes issue #25's monitor scope; no second
resident watcher is planned.
