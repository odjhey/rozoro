# ADR-0010: CLI reconcile delivers the changed-task delta of a generation window

review: approved
date: 2026-08-26

## Context

`./bin/rozoro reconcile` printed one line for **every** task the driver had ever
tracked, on every run, and the Watchtower runs it constantly. In practice ~76% of
those lines were terminal, non-actionable tasks (`gone`, `quiescent`) plus a
static tail of malformed/missing-report zombies that never change but reprinted
forever — hundreds of lines of noise per reconcile.

Root cause: `Store._snapshot_rows` returned the latest snapshot for **all** tasks
through the delivered generation. But `bump_actionable` already records exactly
which task changed in each generation via a single insert-only
`pending_generation_tasks` row — a perfect delta key that delivery did not use.

ADR-0003 describes generations as *delivery batches of actionable changes*; the
full-state dump was an implementation convenience, not a decided contract. No
consumer parses the human line format, and `--json` is the structured contract
(extended additively here).

## Options

1. Keep the full-state dump and filter client-side. Rejected: it would still
   print the static zombie lines forever and still ship the full snapshot over
   the socket.
2. Compute a true changed-task delta at the store level for the CLI reconcile
   path, add a rollup summary line, and keep a `--full` escape hatch.
3. Retire/archive terminal task folders so the full dump shrinks. Real, but a
   larger lifecycle change; orthogonal to the per-reconcile output size.

## Choice

Choose option 2, scoped to the CLI path (`Store.reconcile_delivered`).

- `_snapshot_rows(through, changed_after=None)` restricts the latest-per-task
  snapshot to tasks touched by a generation in `(changed_after, through]` using
  `pending_generation_tasks`.
- `reconcile_delivered(driver_id, *, full=False)` returns
  `(delivered, reports, since, unchanged_count)`; the delta covers
  `(acked, delivered]` unless `full`. Because every generation inserts a
  `pending_generation_tasks` row, `delivered > acked` guarantees a non-empty
  delta, so the client's non-empty-reports ACK condition cannot stall.
- The protocol adds optional `scope` (`delta`/`full`, absent = delta) on
  `reconcile.pending` and optional `since`/`unchanged_count` on the result.
- The client omits `scope` by default so a new client degrades to today's
  behavior against an old daemon; it appends a rollup line and additive JSON
  fields. Fresh/compacted sessions recover unchanged state from the attention
  ledger (`prime`) or `--full`.

`Store.reconcile()` (the Pi registered-session path) is intentionally left
full-snapshot.

## Consequences

- Per-reconcile output drops from N-tasks lines to changed-tasks lines plus one
  rollup line.
- Fresh/compacted Watchtower sessions only see the delta; mitigated by `--full`
  and the attention ledger's `prime`.
- Version skew is safe by default; `--full` against an old daemon fails loudly
  with `invalid-field` (operator restarts the daemon).
- Out of scope / future work: retiring terminal task folders, and Pi adapter
  delta parity.
