---
name: v2_policy_steering_context
description: "Policy & Steering bounded context — the prompt-plane: mechanics core, missions, dispatch guidelines, skills, attention ledger, dated artifacts, and the operator boundary."
type: bounded-context
tags: [ddd, policy, watchtower, skills]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/bounded-contexts/policy-and-steering.md`](../../docs/architecture/bounded-contexts/policy-and-steering.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Policy & Steering

**Core question:** how should the fleet be run, and what did the watchtower decide?

## Responsibility

Own everything the watchtower *reads and reasons with* rather than what the runtime *executes*: the mechanics core, missions, dispatch guidelines, operator policy, skills, and the durable records of watchtower decisions (attention ledger) and operator evidence (dated artifacts). This context is deliberately a **prompt/prose plane** layered above the mechanical core (ADR-0005): repository workflow policy stays out of Rozoro's runtime.

## Structure

```text
templates/watchtower.md                  mechanics core (how any watchtower operates)
templates/missions/<name>.md             what THIS fleet is for (exactly one composes)
templates/watchtower-crew-dispatch-…md   canonical role contracts (prose, test-pinned)
templates/crew-guidelines.md             repo-authoring rules pasted into briefs
$ROZORO_HOME/watchtower-policies/        durable operator role/model policy (ADR-0012)
$ROZORO_HOME/config/machine.md           machine availability facts (never authority)
.agents/skills/*                         watchtower tools (routing, budgets, reports…)
docs/runbooks/*                          operator procedures
```

Precedence (ADR-0012, test-pinned in order): **operator > repository > durable policy > machine availability > compatible preset realization**.

## Key behaviors

- **Mission composition** makes contradictory doctrines coexist safely: `delivery` (full role separation, closed 9-status routing, worksets, budgets) vs `eager-delivery` (one-hop, "dumb" routing watchtower). Which one a driver ran under is attributable by digest ([policy composition](../contracts/policy-composition.md)).
- **Policy as code**: the status taxonomy, replan accounting, repair caps, and precedence chain are asserted verbatim across mission, template, runbook, and skill by the test suite — referential integrity for prose.
- **Steering vocabulary is edge-based**: statuses classify an actionable edge, not a mutable whole-task state. Monitoring is edge-triggered with a heartbeat, never polling-as-attention.
- **Decisions are durable**: the [attention ledger](../contracts/attention-ledger.md) gives each `(task, reason)` a stable item with a handling log, surviving driver cycling and priming fresh/compacted sessions. [Dated artifacts](../contracts/dated-artifacts.md) freeze policy snapshots and conservative progress reports for the operator.
- **Budgets are derived, not stored**: attempt/replan/repair counters and lineage ids are computed from durable history by policy; Rozoro keeps no counter fields.

## Invariants

- Templates and skills name **no models**; concrete role/model assignments live in operator policy.
- Technical severity is fact; business priority and acceptance belong to the operator. `done` ≠ accepted; absence of objection ≠ approval (human gates require explicit decision).
- Skills are orchestration guidance for the watchtower, never prompt blocks pasted into crew sessions; crews load repository rules from their own `--cwd`.
- Conversational status never persists files; persisted reports are explicit, dated, and immutable.
- `/afk` governs **final merge authority only**, defaults ON, and never grants branch-protection bypass, destructive recovery, or scope expansion.

## Boundary rule

Policy & Steering owns judgment scaffolding and decision records. It does not own runtime truth (Lifecycle Evidence), delivery mechanics (Wake Delivery), registration (Registration & Authority), or the repository domain (external). Its prose binds only through composition at launch and through the operator reading it — a recorded gap is that skill bytes are not yet part of policy attribution.
