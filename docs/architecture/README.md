---
name: architecture_index
description: "Landing point for Rozoro's architecture: product thesis, ubiquitous language, bounded contexts, published contracts, and rewrite seams."
type: index
tags: [architecture]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Rozoro architecture

This directory is the canonical description of Rozoro's architecture, **derived from the current code and test suite** (2026-08-28), written in preparation for the rewrite and the contract/ports improvements. It supersedes `docs/architecture.md`.

The style is DDD-inspired rather than dogmatic: bounded contexts, ubiquitous language, published contracts, ports, and explicit invariants are used where they improve reasoning — the goal is that fleet-coordination concepts stay stable while harnesses, terminal backends, and delivery mechanics change.

## Start here

1. [Product architecture](./product-architecture.md) — thesis, context map, planes, ports, evidence discipline, non-goals.
2. [Ubiquitous language](./ubiquitous-language.md) — canonical terms and non-equivalences.
3. [Bounded contexts](./bounded-contexts/README.md) — six contexts, each with ownership, invariants, and a boundary rule.
4. [Published contracts](./contracts/README.md) — conventions, storage layouts, the CLI port, the wire protocol, external ports, policy formats.
5. [Rewrite seams](./rewrite-seams.md) — the code-verified inventory of orphans, duplications, prose-only concepts, and asymmetries the rewrite should address.

## Bounded contexts

- [Durable Tasks](./bounded-contexts/durable-tasks.md) — what work exists, and what has been reported?
- [Session Hosting](./bounded-contexts/session-hosting.md) — where is this agent running right now?
- [Lifecycle Evidence](./bounded-contexts/lifecycle-evidence.md) — what is certifiably true about each session now?
- [Wake Delivery](./bounded-contexts/wake-delivery.md) — when and how may the watchtower be interrupted?
- [Registration & Authority](./bounded-contexts/registration-and-authority.md) — which resident session may be woken, under which recorded policy?
- [Policy & Steering](./bounded-contexts/policy-and-steering.md) — how should the fleet be run, and what did the watchtower decide?

## Architectural backbone

> Harness-native evidence certifies runtime truth; the daemon persists facts before anything notifies; delivery is coalesced, content-free, and quiescent-gated; the watchtower reconciles, judges, and routes under a hash-attributable composed policy; the operator alone accepts.

## Relationship to other docs

- `docs/index.md` — product direction and principles (still current).
- `docs/watchtower-shared-facts.md`, `docs/ubiquitous-language.md` — the mission-era invariant sheet and the prior glossary; both remain test-relevant. This suite's [ubiquitous language](./ubiquitous-language.md) is the superset verified against code.
- `docs/decisions/` — ADRs remain the decision record; this suite cites them by number.
- `docs/runbooks/` — operator procedures under the shipped missions.
- Evidence/gate records (`claude-hook-capability.md`, `claude-watchtower-live-gate.md`, `event-bus-cutover.md`, `event-bus-rollback.md`, `dated-watchtower-artifacts.md`) — dated capability evidence; consult for provenance, not for current architecture.

**Caution:** several prose files are verbatim-pinned by tests (`test_policy_contracts.py`, `test_watchtower_docs.py`) — the delivery mission, dispatch guidelines, the role-separated-delivery runbook, `watchtower-shared-facts.md`, the README attribution table, and the ADR index. Treat them as code and run `./tests/run.sh` after editing.
