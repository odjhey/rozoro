# Pi + Claude event-bus production cutover

Status: G3 landed; G4/G5 release gate

## Authority

`rozorod` and its SQLite event store are the single semantic owner for managed Pi
and supported Claude sessions. `status` and `reconcile` always use the daemon;
there is no opt-in flag or automatic legacy fallback. Pi's extension is only a
reconnecting protocol adapter and fixed-wake actuator. Claude hooks are only
lifecycle producers. Herdr remains host, liveness source, and safe wake actuator.

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
./bin/rozoro doctor              # verifies Python >=3.10 and other prerequisites
./bin/rozoro monitor start
./bin/rozoro monitor status --json
./bin/rozoro status <task> --json
```

Existing `tasks/<id>/brief.md`, append-only `handoff.md`, `session.json`, ACK
cursors, task identities, and `.meta` membership are not migrated or rewritten.

## Fresh install and health

The monitor requires Python >=3.10 and does not support stock macOS Python
3.9.6. If doctor reports an unsupported runtime, run `brew install python` and
ensure that installation's `python3` precedes the stock interpreter on PATH.
The start command performs the same version check before spawning `rozorod`, so
adapter/spool callers receive the runtime error directly instead of waiting for
a generic readiness timeout.

Managed Pi and supported-Claude launch/spawn/resume safely start the monitor
concurrently and wait for its health endpoint before starting the adapter. A
failed readiness check aborts launch. Pi is passed the checkout-owned extension
explicitly even when its task cwd is another repository. No `ROZORO_EVENT_BUS*`
variable is required or supported.

Use `monitor status --json` to diagnose: daemon down (`running=false`), Herdr
`connected`/`disconnected`, adapter-derived `unknown`, delivery `deferred`,
`delivered` with generation above ACK, retry/error counters, and spool backlog.
A live pane with a disconnected adapter remains `unknown`, never quiescent.

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
