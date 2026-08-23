# Event-bus database rollback

Schema v5 freezes delivery offers, connection epochs, task membership, and task
projections. Schema v6 additionally requires each generation snapshot to carry
immutable compatibility report fields (`heading`, `reason`, `pending`,
`inputs-needed`, `artifacts`, `open_items`, `acked_source`) so the CLI bridge
can render a frozen report without touching the live handoff. Older binaries
do not understand those records, so a binary revert is **not** a database
rollback.

Before running a pre-v5 (or pre-v6) monitor, stop the monitor and explicitly
reset only its event-bus database:

```sh
./bin/rozoro monitor stop
./bin/rozoro monitor reset --force
```

Reset removes `monitor.db` and its SQLite sidecars. It preserves authoritative
`tasks/` folders and handoff reports, from which later projection phases can
rebuild state. A populated v4 generation ledger is rejected during v5 startup
because v4 did not persist complete generation membership. During v6 startup,
any previously-persisted v4- or v5-origin database that still carries
`task_projections` rows — including generation-zero rows predating generation
tracking — is rejected too, because none of them carry the immutable
compatibility report fields above and `compat_complete` cannot be truthfully
backfilled; reset is required rather than manufacturing history.
