---
name: v2_contract_home_layout
description: "The $ROZORO_HOME shared data namespace: resolution rule, directory layout, ownership per entry, and the reset boundary."
type: contract
tags: [architecture, contracts, storage]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/contracts/home-layout.md`](../../docs/architecture/contracts/home-layout.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Home layout

Part of the [contracts index](./README.md). The home is Rozoro's single shared data namespace; every component (shell CLI, Python daemon, hooks, TS Pi extension, skills) resolves it identically.

## Resolution rule

```text
ROZORO_HOME  >  RZR_HOME (legacy)  >  $HOME/.rozoro
```

- Empty ≠ set: an empty variable falls through to the next source.
- `~`/`~user` are expanded; an unresolvable user home is a **hard error**, never a literal path.
- Relative values are anchored to the cwd **at load time**, then frozen absolute — later `cd` must not change the home ("select once, freeze absolute, survive later cd").
- The resolver re-exports `ROZORO_HOME` so children see one namespace.
- The home must be an owned, owner-private (0700), real (non-symlink) directory; created on demand by mutating components.

This rule is implemented independently in five places (shell lib, producer client, monitor CLI, poller, Pi extension) and pinned by the shared **home matrix** test cells (P/L/B/E/D/R/T/X) across bash, Python, Node, and Bun, plus a source-audit meta-test that fails if a new consumer of home resolution appears without matrix coverage.

## Layout and ownership

```text
$ROZORO_HOME/                       0700, owner-private
├── state/                          LIVE hosting state (deleted at teardown)
│   ├── <task-key>.meta             KEY=VALUE host binding (pane, tab, cwd, harness, …)
│   ├── <task-key>.status           single status token (legacy watcher)
│   ├── <task-key>.runtime.json     legacy watcher projection (schema_version 2) + .lock
│   └── .lock/                      home mutation lock (mkdir-based; pid + since)
├── tasks/<task-key>/               DURABLE task artifacts (survive teardown) → task-folder.md
├── crew/<name>.json                crew presets (spawn profiles)
├── watchtower-presets/<name>.json  watchtower presets (0600, nlink 1, owned)
├── watchtower-missions/<name>.md   operator-authored missions
├── watchtower-policies/*.md        durable operator role/model policy (prose; ADR-0012)
├── config/machine.md               machine-availability facts (prose; ADR-0009/0012)
├── artifacts/<category>/…          immutable dated operator artifacts → dated-artifacts.md
├── watchtowers/                    0700
│   ├── .authority.lock             legacy-ledger vs daemon authority gate
│   ├── attention/                  attention ledger (driver-surviving) → attention-ledger.md
│   └── <driver-id>/                per-driver → registration.md
│       ├── target.json             registration commit point
│       ├── registrations.jsonl     append-only history
│       ├── .event-bus-authority    marker, exact bytes "event-bus-v1\n"
│       ├── claude-event-settings.json (+ .capability.json)
│       ├── poller-ready.<incarnation>
│       └── pending.json / ack      legacy wake ledger (fenced)
├── monitor.db (+ -wal, -shm)       SQLite event log + projections (user_version 6)
├── monitor.sock                    daemon AF_UNIX socket (0600)
├── monitor.lock                    daemon ownership record {pid, socket_dev, socket_ino}
├── monitor.log                     daemon log (0600)
├── spool/<event_id>.json           durable producer outbox (+ .lock)
└── producer-seq/<session>.seq      per-session producer sequence cursors
```

## Boundary rules

- **`state/` vs `tasks/`** is the liveness/durability split: teardown deletes `state/<key>.*` and closes the tab but never touches `tasks/<key>/` or the recorded cwd (byte-for-byte, tested).
- **The reset boundary** is `monitor.db` + sidecars + `producer-seq/` + `spool/` as one coherent unit (`monitor reset --force`): removing any subset would let stale cursors or spooled events corrupt a fresh log. Reset preflights every entry before mutating any, refuses while the daemon runs, and preserves `tasks/`.
- **Skill-owned prose** (`watchtower-policies/`, `config/machine.md`, missions) is read by watchtower sessions at the prompt layer, not by `bin/` code. It is policy input, not runtime state.
- Tasks, crews, and attention are **not mission-namespaced**: coexisting watchtowers share one home and rely on operator discipline, not enforced partitioning (a recorded gap).
- Nothing under the home is a stable public API unless a contract file in this directory says so; `state/<key>.meta` in particular is explicitly not yet stable.
