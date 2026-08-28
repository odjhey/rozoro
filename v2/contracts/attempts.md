---
name: v2_contract_attempts
description: "v2 contract (new): first-class Attempt and Loop records, budgets, and the normalized failure-class taxonomy beneath mission routing statuses."
type: contract
tags: [contracts, attempts, failures, v2]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 addition** — introduced by [proposal 0001](../proposals/0001-orchestrator-primitives-alignment.md) (P2/P4, charter D6). Replaces the v1 practice of deriving attempt counters from history prose (attempt-budget skill) with typed durable records the skill reads and writes.

# Attempts, loops, and failure classes

Part of the [contracts index](./README.md). An attempt is one execution of a task's work by an executor. Attempts are **first-class and append-only**: retries never overwrite task state, so "which approach repeatedly fails", "did retry 3 differ from retry 2", and "which executor produced the accepted artifact" stay answerable.

## Attempt

```json
{
  "schema": 1,
  "attempt_id": "<ulid>",
  "task_key": "…",
  "workset_id": null,
  "parent_attempt_id": null,
  "kind": "fresh | follow-up | restart",
  "executor": { "harness": "…", "model": "…", "runtime": "herdr", "descriptor_sha": "…" },
  "native_session": "<uuid>",
  "turns": { "first": 3, "last": 5 },
  "input_snapshot": { "brief_sha": "…", "graph_version": 4, "upstream_artifacts": ["…"] },
  "artifact_refs": ["…"],
  "evidence_refs": ["…"],
  "result": "accepted | rejected | abandoned | in-progress",
  "failure_class": null,
  "budget_spent": { "tokens": null, "cost": null, "wall_seconds": 812 },
  "started_at": "…", "finished_at": null
}
```

- **`kind` is load-bearing** and unique to Rozoro's stateful crews (research-model gap §2.7): `follow-up` continues the same native conversation (v1 `send`), `restart` is a new conversation on the same task key, `fresh` is a first attempt. Budget policy may price these differently; lineage links them via `parent_attempt_id`.
- `executor` records model/harness/runtime **separately** (failures happen at different layers) plus the capability-descriptor hash in force at dispatch — the typed successor of v1's `dispatcher_*` attribution.
- `input_snapshot` pins what the attempt saw, so a replan or upstream change is distinguishable from executor variance.
- Attempts bind to turns, not the reverse: Lifecycle Evidence stays the authority on turn facts; the attempt record cites them.

## Loop

A loop is a bounded, progress-measured retry contract — the typed form of the attempt-budget prose:

```json
{
  "schema": 1,
  "loop_id": "<ulid>",
  "task_key": "…",
  "trigger": "gate-rejected | verdict-failed | …",
  "progress_measure": "failing_checks_count",
  "stop": { "success": "progress_measure == 0", "failure": "same failure_class 3 consecutive", "max_attempts": 5 },
  "escalation": "replan | operator",
  "attempts": ["<attempt ids>"],
  "state": "open | succeeded | exhausted | escalated"
}
```

The distinction this buys: **productive iteration vs stuck** is a recorded judgment over a measured series, not a feeling. The v1 budget ladder maps directly: implementation lineages get `max_attempts` 10→20→30 by replan tier; repair loops carry the `infra + gate ≤ 3` cap. Only a `replan` escalation consumes the replan counter — the rule the policy-contract tests already pin in prose.

## Failure classes (P4)

Normalized, closed, recorded on attempts:

```text
contract | execution | environment | dependency | verification |
integration | resource | timeout | no-progress | conflict | unknown
```

Failure classes are **facts beneath routing**: the mission-owned 9-status set stays the routing vocabulary (test-pinned prose, unchanged), and routing keys on classes instead of re-diagnosing prose. Reference mapping:

| Failure class | Typical routing status |
|---|---|
| contract | `NEEDS_REPLAN` or `NEEDS_DECISION` |
| execution, verification | `NEEDS_IMPLEMENTATION` / `NEEDS_TESTS` / `NEEDS_REVIEW` |
| environment, resource, timeout | `NEEDS_INFRA_REPAIR` |
| dependency | blocked edge — routing waits, no status consumed |
| integration, conflict | Workset Merger / integration node |
| no-progress | loop failure condition → escalation |
| unknown | `NEEDS_DECISION`, never silently retried |

The mapping is mission policy (a mission may route differently); the classes themselves are core facts. Retry policy differs by class by design: a `timeout` may retry the same executor; a `contract` failure must not.

## Invariants

- Append-only: an attempt's terminal fields are written once; corrections are new records citing the old.
- No attempt without a task; no loop without attempts; budgets check **cumulative** spend across the lineage (parent chain), never per-branch — the v1 rule that a fresh worktree never resets the count.
- `unknown` failure class is a first-class honest answer and always escalates to judgment rather than auto-retry.
