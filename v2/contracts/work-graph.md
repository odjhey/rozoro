---
name: v2_contract_work_graph
description: "v2 contract (new): Workset, typed dependency edges, GraphPatch with lineage, readiness derivation, and the workset command set."
type: contract
tags: [contracts, work-graph, v2]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 addition** — introduced by [proposal 0001](../proposals/0001-orchestrator-primitives-alignment.md) (P1/P13, charter D5). No live counterpart.

# Work graph

Part of the [contracts index](./README.md). Durable plan structure for the [Work Graph context](../bounded-contexts/work-graph.md). All records follow the shared [conventions](./conventions.md): closed schemas, bounded integers, append-only history with cursor/version separation.

## Workset

```json
{
  "schema": 1,
  "workset_id": "<display>--<ULID26>",
  "goal": { "description": "…", "success_criteria": ["…"], "constraints": ["…"] },
  "policy": { "mission": "…", "policy_sha256": "…" },
  "budget": { "attempts": 30, "tokens": null, "cost": null, "wall_seconds": null },
  "graph_version": 4,
  "terminal": null
}
```

- `workset_id` follows task-key identity rules (reservation by collision, safe components).
- `terminal ∈ {succeeded, failed, escalated, cancelled} | null`; `succeeded` is written only by an operator-acceptance command (P12).
- `budget` ceilings are the machine-checked form of the v1 attempt-budget prose (10→20→30, ≤3 replans map onto `attempts` plus per-loop limits in [attempts](./attempts.md)); null = unlimited on that axis.

## Nodes and edges

Nodes are task references (`task_key`) plus a node kind: `work` (default), `integration`, `verification`. Edges are typed and **closed**:

```text
requires             upstream must be accepted before downstream is ready
must_verify_before   downstream may not be accepted until upstream is accepted
fallback_to          downstream becomes ready only when upstream reaches terminal failure
invalidates          a new accepted artifact upstream marks downstream-bound evidence stale
```

Starting set per P1; additions (`optional_after`, `produces_for`, …) require a decision-log entry, not ad-hoc use. Cycles are rejected at patch time; unreachable nodes are reported, not silently kept.

## GraphPatch — the only mutation

```json
{
  "schema": 1,
  "patch_id": "<ulid>",
  "workset_id": "…",
  "base_version": 3,
  "ops": [ { "op": "add_node|remove_node|add_edge|remove_edge|split_node|change_budget", "…": "…" } ],
  "reason": "…",
  "triggering_evidence": ["<evidence ids>"],
  "author": { "kind": "watchtower|crew|operator", "id": "…", "attempt_id": null },
  "applied_version": 4,
  "applied_at": "<ISO8601Z>"
}
```

- Patches apply transactionally against an exact `base_version` (optimistic concurrency; a stale base is a refusal, never a merge).
- Patch history is append-only; graph version N is reproducible by replaying patches 1..N — the same evidence discipline as the event log.
- Planner/Replanner crews emit patch data in their handoffs (P11, phase 2+); the core validates structure, the watchtower decides application. A patch that removes in-flight work requires the affected tasks to be settled or explicitly cancelled in the same patch.

## Readiness

`graph.ready(workset_id)` derives, never stores:

```text
ready(node) ⟺ ∀ requires-upstream accepted
            ∧ node's task not tracked-live with an open attempt
            ∧ workset budget not exhausted
            ∧ (fallback nodes: their upstream terminally failed)
```

Output is an ordered list with the blocking reason for every non-ready node — the graph analogue of conservative availability: the answer explains itself.

## Commands (P13)

```text
workset.create | workset.get | workset.accept | workset.cancel
graph.patch    | graph.ready | graph.history
```

Mapped into the [command catalogue](../core-and-commands.md). All follow command rules: full validation before mutation, typed results, `unknown` over inference.

## Deferred (recorded seams)

- **Claims/leases** (P9): the schema reserves nothing, but readiness derivation is specified so a claim layer can sit between `ready` and dispatch without changing either side.
- **Cross-workset edges**: out of scope; a dependency between worksets is modeled by an operator-level decision, not an edge, until real need is evidenced.
