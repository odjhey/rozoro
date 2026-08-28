---
name: v2_work_graph_context
description: "Work Graph bounded context (v2, new) — worksets, typed dependencies, graph patches, ready derivation, and integration nodes; the durable home of the plan."
type: bounded-context
tags: [ddd, work-graph, v2]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 addition** — introduced by [proposal 0001](../proposals/0001-orchestrator-primitives-alignment.md) (P1/P9/P10/P11, charter D5). No live counterpart: in v1 the plan exists only in the watchtower's context window and mission prose.

# Work Graph

**Core question:** what work exists *in relation to other work*, and what is runnable now?

## Responsibility

Own the durable representation of the plan: worksets, the typed dependency graph over tasks, graph versioning through patches, and the mechanical derivation of readiness. This context finally applies Rozoro's founding principle — fleet state must not live in conversational memory — to the plan itself, not just to individual tasks.

## Aggregate root: the workset

A workset is a coherent delivery unit under one goal: member tasks, typed edges, a policy reference (mission/policy digest), budgets, and an explicit terminal state. Its identity and lifecycle are independent of any watchtower session; a fresh or compacted watchtower re-primes from the graph the way it already re-primes from the attention ledger.

```text
Workset
├── goal (operator intent, success criteria, constraints)
├── members: Task references (tasks keep their own aggregate; see durable-tasks)
├── edges: typed dependencies between members
├── budget: attempts / tokens / cost / wall-clock ceilings
├── graph versions: v1 →(patch)→ v2 →(patch)→ …
└── terminal state: succeeded (operator-accepted) | failed | escalated | cancelled
```

## Key behaviors

- **Patch-only mutation.** The graph changes only through `GraphPatch` records with lineage (reason, triggering evidence, changed nodes/edges, author, prior version). There is no in-place edit; replanning is a patch, inspectable after the fact.
- **Mechanical readiness.** The core answers *what is runnable now*: dependency satisfaction × task state × remaining budget. It is a pure derivation, like availability in Lifecycle Evidence.
- **Judgment stays outside.** *Where and how* a ready task runs is the watchtower's decision under ADR-0012 precedence (P10). Planner and Replanner crews **emit GraphPatch data, not prose plans** (P11, phase 2+); the watchtower validates and applies patches, it does not invent graph semantics.
- **Integration is a node kind.** Merge/integration work (the v1 Workset Merger role) is first-class in the graph with `must_verify_before` edges to delivery, so fan-in ordering is data, not conversation.

## Invariants

- A task may belong to at most one workset; tasks remain valid outside any workset (the v1 single-task flow is the degenerate case and must keep working).
- Edges are typed and closed (see the [work-graph contract](../contracts/work-graph.md)); an unknown edge type is a validation error, not a soft warning.
- Readiness is derived, never stored; a stored "ready" flag would be a second truth.
- `invalidates` edges connect graph structure to evidence staleness: a change to the upstream node marks dependent evidence stale (the changed-head reconciliation rule, structurally).
- Terminal `succeeded` requires operator acceptance (P12); no gate output can terminate a workset on its own.

## Deferred seam: claims and leases (P9)

With one primary watchtower (ADR-0001), the tracked-task refusal in Session Hosting is a sufficient lease. The multi-writer seam is recorded here so it can be added without redesign: a future `Claim {work_item, executor, lease, expiry}` with `claim/renew/expire/steal` semantics slots between readiness and dispatch. Nothing in this context may assume there will never be a second dispatcher.

## Boundary rule

Work Graph owns plan structure, versioning, and readiness derivation. It does not own task content (Durable Tasks), execution records (Attempts, in Durable Tasks' orbit), runtime truth (Lifecycle Evidence), dispatch judgment (Policy & Steering / watchtower), or merge mechanics (the repository domain — an integration *node* tracks that work; the repo does it).
