---
name: v2_charter
description: "The v2 rewrite charter: goals, ground rules, phase plan, and decision log. Clean dependency-free core first; real integrations only after the core is proven."
type: index
tags: [v2, rewrite, charter]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Rozoro v2

This branch (`v2`) is the rewrite. It exists because the [live architecture suite](../docs/architecture/README.md) showed the current system has the **right invariants implemented across too many divergent surfaces** — five home resolvers, three filesystem-safety toolkits, fenced legacy stacks, prose-only contracts ([rewrite seams](./rewrite-seams.md)). v2 keeps the invariants and rebuilds the structure.

`master` stays live and untouched; v2 grows beside it on this branch and cuts over only when the core is proven.

## What v2 is

1. **A clean, dependency-free core** — domain + application logic with zero third-party dependencies and zero knowledge of Herdr, harness CLIs, terminals, or storage engines. See [core and commands](./core-and-commands.md).
2. **Dedicated ports and commands** — every external effect behind an explicit port; every operation an explicit command. The core is assembled from ports at a composition root; nothing reaches around them.
3. **Dedicated tests by kind** — behavioural (what the system promises), capability (what each adapter/backend can certify), and technical (sensitive mechanics: durability, concurrency, security). See [test strategy](./test-strategy.md).
4. **Clear adapter guidelines** — a written contract for how integrations are built, so adapters stay thin and conformant. See [ports and adapters](./ports-and-adapters.md).

## Ground rules

- **Core before integrations.** No real Herdr/harness integration lands until the core passes its full behavioural suite against fakes. The fakes are written first, from the port contracts — the same way `tests/fakes/herdr` already defines the v1 port boundary.
- **The questions are already answered.** Design questions resolve by citation, not re-litigation: the [contracts](./contracts/README.md) define the semantics, the [bounded contexts](./bounded-contexts/README.md) define ownership, the [ADRs](../docs/decisions/README.md) define the decisions, and [rewrite seams](./rewrite-seams.md) defines what changes. A v2 deviation from any of these gets its own ADR.
- **Invariants are non-negotiable.** The wire-level separations (event ≠ delivery ≠ ACK; prose-free notification; frozen report tuples), the durability orderings (spool→send, commit→ack, generation→deliver, target→history), conservative evidence (`unknown` over inference), and the fenced threat model carry over exactly.
- **Durable formats carry over.** v2 reads and writes the same durable artifacts as v1 (task folders, handoff grammar, registration records, home layout) unless a format change gets an ADR with a migration path. Coexistence with a live v1 on the same home is the default assumption.

## Phase plan

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **0 — Charter** (this) | v2 docs, decision log, skeleton | Docs merged to `v2` |
| **1 — Core** | `rozoro_core`: domain model, commands, ports, in-memory/fake adapters | Full behavioural suite green against fakes; import-boundary test enforced; technical tests for the durability orderings |
| **2 — Adapters** | Storage adapter (SQLite), filesystem adapter (home/task folders), then Herdr + harness adapters, each with a capability/conformance suite | Each adapter passes the shared port conformance tests + its capability suite |
| **3 — Surfaces** | CLI and daemon as thin adapters over commands | v1 CLI behavioural parity for the kept verb set; v1 tests ported or retired with rationale |
| **4 — Cutover** | Coexistence validation, migration notes, `bin/` swap | Live gate equivalent of the v1 cutover evidence discipline |

## Decision log

Decisions made for v2, each traceable to prior evidence. New entries need a short ADR under `docs/decisions/` (same conventions as v1).

| # | Decision | Basis |
|---|---|---|
| D1 | Core language is **Python ≥3.11, stdlib-only**; the CLI becomes a thin Python surface with a minimal `bin/rozoro` launcher. The bash 3.2 floor is **retired for v2 code** (it constrained v1's shell implementation, not the product). | v1's semantic core (`lib/rozoro_monitor`) is already stdlib Python ≥3.11; the bash layer is where the duplication lives. |
| D2 | `v2/` on this branch is the **target-state architecture mirror** of `docs/architecture/`, iterated independently; the v2 effort never edits the live docs. Code placement is decided at phase-1 start (own decision entry); everything moves to its final location at cutover. | `master` is in production use; the live docs must keep describing it while v2 diverges. |
| D3 | The prose-only concepts stay out of the core in phase 1 (worksets, attempt budgets, role rosters remain policy-plane), **except** the `heads:` handoff line, which becomes a parsed optional field. | ADR-0005 boundary; `heads:` is the one prose contract the canonical parser is already asked to honor. |
| D4 | The caller-less protocol surface (`driver.snapshot`, bare `reconcile`, `ack-generation`, `background.stop` emitters) is **not carried into v2** unless a phase-2 adapter needs it. | [Rewrite seams — orphaned surfaces](./rewrite-seams.md#orphaned-and-caller-less-surfaces). |

## Reading order

1. [Goal and scope](./goal-and-scope.md)
2. [Core and commands](./core-and-commands.md)
3. [Ports and adapters](./ports-and-adapters.md)
4. [Test strategy](./test-strategy.md)
5. The [v2 mirror](./README.md) of the architecture suite — iterate target-state changes there.
6. The [live architecture suite](../docs/architecture/README.md) — the frozen description of v1; cite it, never edit it from v2.
