---
name: v2_core_and_commands
description: "The v2 core: package layout, dependency rules, the command catalogue, and how commands map to v1 verbs."
type: architecture
tags: [v2, core, commands]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Core and commands

## Layout

```text
<code-root>/            # location decided at phase-1 start (charter D2)
├── core/rozoro_core/
│   ├── domain/            pure model: identities, task, handoff, events, availability,
│   │                      generations, registration — no I/O imports at all
│   ├── application/       commands + queries; orchestrates domain via ports
│   ├── ports/             port Protocols (typing.Protocol) + port error types
│   └── codec/             protocol-v1 wire codec (pure bytes <-> messages)
├── adapters/              phase 2+: sqlite/, homefs/, herdr/, harness/<name>/
├── surfaces/              phase 3: cli/, daemon/
└── tests/
    ├── behavioural/       black-box over commands with fakes
    ├── capability/        per-adapter certification suites (phase 2+)
    ├── technical/         sensitive mechanics: durability, concurrency, security, boundaries
    ├── conformance/       shared per-port suites any adapter must pass
    └── fakes/             the reference fake per port
```

## Dependency rules (enforced, not aspirational)

```text
domain      →  (nothing but stdlib data structures/typing)
application →  domain, ports
codec       →  domain (message types only)
ports       →  domain (types in signatures)
adapters    →  core (any of it) + stdlib I/O; NEVER another adapter's internals
surfaces    →  application + adapters (composition root lives here)
tests       →  anything
```

- **Stdlib-only everywhere in `v2/`**; inside `core/`, `domain/` and `application/` additionally must not import I/O modules (`os`, `socket`, `sqlite3`, `subprocess`, `pathlib` file ops, `asyncio`) — time, randomness, filesystem, and transport arrive through ports.
- Enforced by a technical test that walks the AST of every module and asserts the import matrix — the v2 analogue of v1's home-resolution source audit (the pattern is proven; reuse it).
- One implementation per concept. The five home resolvers, three fs-safety toolkits, and duplicated version gates of v1 each collapse to a single module ([rewrite seams](./rewrite-seams.md#duplicated-implementations-of-one-contract)).

## Commands

Commands are the application layer's public surface; the CLI and daemon are thin adapters over them (phase 3). Names follow the verb semantics of the [v1 CLI contract](./contracts/cli.md); the plane split is preserved as a *type* split — data-plane inputs are opaque text, control-plane inputs are closed enums.

| Command | v1 verb(s) | Notes |
|---|---|---|
| `ReserveTask`, `RenderBrief` | `start` (first half), `render` | Identity + durable record creation. |
| `SpawnSession` | `spawn`, `start` (second half) | Emits port calls: create host, launch harness, record binding. |
| `ResumeSession`, `RestartSession` | `resume`, `control restart` | Exact-conversation vs new-conversation, same key. |
| `SendText` | `send` | Data plane: opaque text only. |
| `ControlSession(verb)` | `control` | Control plane: closed enum `{interrupt, cancel, key, stop}`. |
| `TeardownHosting` | `teardown` | Liveness only; durable record untouched by construction (the command has no reference to the task folder port). |
| `IngestEvent` | (hooks → daemon) | Spool/ordering semantics via the EventIngress + Store ports. |
| `GetTaskStatus`, `ListTasks`, `GetLineage` | `status`, `list`, `lineage` | Queries; pure reads by construction. |
| `AckTaskBlocks` | `ack` | Task ACK cursor. |
| `ReconcileDriver` | `reconcile` | Delta by default; ACKs exactly the snapshotted generation. |
| `RegisterDriver`, `ActivateAuthority`, `RollbackAuthority` | `register`, launcher internals, `rollback` | Validation before write; transactional authority. |
| `LaunchWatchtower` | `pi-watchtower`, `claude-watchtower` | Policy composition + attribution; harness specifics behind the Harness port. |
| `RecordAttention`, `UpdateAttention`, `PrimeAttention` | (ledger skill scripts) | The interim mailbox becomes a first-class command set (ADR-0004 stays the target). |
| `CreateWorkset`, `AcceptWorkset`, `CancelWorkset`, `ApplyGraphPatch`, `QueryReady` | (new — proposal 0001) | Patch-only graph mutation; readiness derived, never stored. `AcceptWorkset` is operator-only. |
| `RecordArtifact`, `RecordEvidence`, `RecordGateVerdict` | (new — proposal 0001) | Version-bound records; reject subject-less evidence at the schema. |
| `OpenLoop`, `RecordAttempt`, `EscalateLoop` | (new — proposal 0001) | Append-only attempt/loop lineage; budgets checked cumulatively. |
| `MonitorHealth`, `MonitorStop`, `MonitorReset` | `monitor …` | Reset keeps the coherent-boundary rule. |

Rules:

- Every command validates completely before its first port call (v1's "fail before Herdr mutation", generalized).
- Commands return typed results/errors; no command formats human prose (surfaces do).
- Anything a command cannot certify is `unknown` in its result — conservative evidence is a return-type discipline, not a convention.
