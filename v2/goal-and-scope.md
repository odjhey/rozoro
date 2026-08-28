---
name: v2_goal_and_scope
description: "v2 phase-1 goal and scope: what the clean core must do, what is explicitly deferred, and the done criteria."
type: scope
tags: [v2, scope]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Goal and scope (phase 1 — the core)

## Goal

One statement: **implement the six bounded contexts' semantics as a single dependency-free core, driven entirely through commands and ports, provable without any real backend.**

When phase 1 is done, a test can spawn a fleet, feed lifecycle evidence, watch availability derive, see a generation freeze and a wake gate on quiescence, reconcile the delta, ack blocks, and resume a task — with every backend faked and every invariant asserted.

## In scope

- The **domain model** of the [ubiquitous language](./ubiquitous-language.md): task keys, briefs, handoff blocks and verdicts, turns, sessions, host bindings, drivers, registrations, incarnations, events, projections, availability, generations, offers, ACK cursors, attention items.
- The **command set** covering the v1 verb semantics ([CLI contract](./contracts/cli.md)) minus surface concerns — see [core and commands](./core-and-commands.md).
- The **ports** in the [catalogue](./ports-and-adapters.md#port-catalogue), each with an in-memory or fake implementation and a shared conformance suite.
- The **invariant mechanics** as core logic, not adapter behavior: the acknowledgement ladder, the frozen report-tuple matrix, conservative availability derivation, generation freezing, the delivery gate algebra, handoff parsing with both cursors, the waiting triad, drift detection.
- **Wire codec** for protocol v1 semantics (closed schemas, size limits, strict JSON) as a pure module — transport stays in adapters.

## Out of scope (deferred, with the phase that owns it)

- Real Herdr, harness CLIs, real session-store discovery — phase 2.
- SQLite persistence — phase 2 (phase 1 proves the Store port against in-memory + a trivial file adapter).
- CLI argument parsing, daemon process management, socket serving — phase 3.
- The legacy diagnostic stack — **not carried over**; v1 keeps it.
- Policy-plane content (missions, skills, runbooks, budgets) — unchanged, stays prose above the core (ADR-0005, D3).
- Multi-home, mission namespacing, and the Watchtower Mailbox graduation (ADR-0004) — explicitly not solved by the rewrite; the core must merely not make them harder.

## Done criteria (phase 1)

1. `v2/core` imports **only** the Python standard library, and its domain/application modules import no I/O modules at all — enforced by the import-boundary technical test.
2. The behavioural suite covers every guarantee currently pinned by v1's bats/python tests that concerns core semantics (the mapping table lives in [test strategy](./test-strategy.md)), green against fakes only.
3. Technical tests prove the durability orderings and concurrency invariants at the port contract level (a conforming adapter cannot violate them without failing conformance).
4. Every port has: a docstring contract, a fake, a conformance suite, and at least one negative capability case (what happens when the backend cannot certify).
5. No code path constructs prose destined for a resident conversation except the fixed wake constant.
