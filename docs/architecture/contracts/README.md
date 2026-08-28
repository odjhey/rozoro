---
name: contracts_index
description: "Index of Rozoro's published contracts: conventions, storage layouts, the CLI port, the wire protocol, external ports, and policy formats."
type: index
tags: [architecture, contracts]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Published contracts

These files document the current system's deliberate contracts — the interfaces breaking which breaks users, tests, or coexisting components. They are derived from code and tests, not aspiration; anything marked as a *seam* is catalogued in [rewrite seams](../rewrite-seams.md) for the contract/ports improvement work.

Read [conventions](./conventions.md) first; every other contract assumes it.

## Storage contracts

- [Home layout](./home-layout.md) — the `$ROZORO_HOME` namespace: resolution rule, directory ownership, the reset boundary.
- [Task folder](./task-folder.md) — `tasks/<key>/`: identity, brief, session link, ack cursors; what survives teardown.
- [Handoff](./handoff.md) — the crew report grammar: turn blocks, verdicts, the waiting triad, open items, cursors.

## Interface contracts

- [CLI](./cli.md) — the `rozoro`/`rzr` verb surface as an inbound port; data plane vs control plane.
- [Event protocol](./event-protocol.md) — protocol v1 NDJSON: lifecycle events, requests, the prose-free notification, the frozen report tuple matrix.
- [Registration](./registration.md) — driver identity, the validated wake target, policy attribution, event-bus authority.

## External ports

- [Herdr port](./herdr-port.md) — the terminal-hosting backend: consumed facets, event stream, and what Rozoro refuses to trust it for.
- [Harness adapters](./harness-adapters.md) — per-harness launch mapping, lifecycle production, capability gates, session discovery, exact resume.

## Policy contracts

- [Policy composition](./policy-composition.md) — crew/watchtower presets, missions, policy digests, precedence, policy-as-code enforcement.
- [Attention ledger](./attention-ledger.md) — durable attention items: the interim Watchtower Mailbox.
- [Dated artifacts](./dated-artifacts.md) — immutable policy snapshots and conservative progress reports.

## Contract discipline

- Wire schemas are closed (unknown fields rejected); config schemas are open (unknown keys tolerated). Never invert this.
- Several Markdown files outside this directory are **verbatim-pinned by tests** (`tests/python/test_policy_contracts.py`, `test_watchtower_docs.py`): the delivery mission, the dispatch guidelines, the role-separated-delivery runbook, `docs/watchtower-shared-facts.md`, the README attribution table, and the ADR index ordering. Treat those files as code; run the suite after editing them.
- Provider/backend types stop at adapters: Herdr JSON shapes, harness CLI flags, and session-store layouts never leak into durable formats.
