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
./bin/rozoro monitor start
./bin/rozoro monitor status --json
./bin/rozoro status <task> --json
```

Existing `tasks/<id>/brief.md`, append-only `handoff.md`, `session.json`, ACK
cursors, task identities, and `.meta` membership are not migrated or rewritten.

## Fresh install and health

Run `./bin/rozoro monitor start`; managed Claude spawn/resume generates the
version-pinned hook settings automatically, and a Pi watchtower extension
registers with `monitor.sock` automatically. No `ROZORO_EVENT_BUS*` variable is
required or supported.

Use `monitor status --json` to diagnose: daemon down (`running=false`), Herdr
`connected`/`disconnected`, adapter-derived `unknown`, delivery `deferred`,
`delivered` with generation above ACK, retry/error counters, and spool backlog.
A live pane with a disconnected adapter remains `unknown`, never quiescent.

## Rollback

Stop the daemon and restore the prior release. Task folders and handoffs are
unchanged. Before starting an old watcher, ensure the daemon has no unacknowledged
generation; otherwise reconcile on this release first. The prior release then
resumes its JSON ledger. Do not run old and new owners concurrently.

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
