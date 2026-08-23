# Event-bus database rollback

Schema v5 freezes delivery offers, connection epochs, task membership, and task
projections. Older binaries do not understand those records, so a binary revert
is **not** a database rollback.

Before running a pre-v5 monitor, stop the monitor and explicitly reset only its
event-bus database:

```sh
./bin/rozoro monitor stop
./bin/rozoro monitor reset --force
```

Reset removes `monitor.db` and its SQLite sidecars. It preserves authoritative
`tasks/` folders and handoff reports, from which later projection phases can
rebuild state. A populated v4 generation ledger is rejected during v5 startup
because v4 did not persist complete generation membership; reset is required
rather than manufacturing history.
