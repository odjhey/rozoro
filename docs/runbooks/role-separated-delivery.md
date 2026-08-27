# Role-separated delivery

Use role separation when a change needs independent assurance, parallel work, or
controlled publication.

## Roles

- **Planner / Task Decomposer:** turns raw intent into bounded tasks and owns the
  workset execution strategy: dependencies, parallel groups, stacks/sequences,
  fan-out/fan-in points, and intended integration order.
- **Coder:** implements one bounded task and reports the exact candidate head.
- **Reviewer:** independently evaluates correctness and scope at an exact head.
- **Tester:** independently exercises behavior and failure modes at an exact head.
- **Replanner:** revises scope, dependencies, and the parallel/stacking execution
  strategy when evidence shows the current plan is wrong or repair loops stop
  converging, while carrying cumulative attempt/replan counters forward.
- **No-Mistakes Runner:** thin Rozoro crew that submits/reattaches an exact
  candidate to the configured no-mistakes pipeline, listens through its supported
  Git/CLI/AXI surface, and reports structured run evidence.
- **Workset Merger:** executes and reconciles the Planner/Replanner integration
  strategy against actual branches, reads assurance/no-mistakes results in that
  context, reports when the strategy has become invalid, and performs final
  merge/post-merge work when authorized.
- **Watchtower:** owns cross-project/workset priority, dispatch, routing, attempt/
  replan accounting, and operator interaction.

## Planning the workset

Planner/Task Decomposer decides how the workset should execute, not only how it is
split into task descriptions.

For a multi-task workset, record enough of the following to make dispatch and
integration unambiguous:

- bounded task identities and outcomes;
- dependency edges;
- tasks that may start concurrently;
- tasks that must wait for another task;
- stacked branch/base relationships where applicable;
- execution waves or fan-in points when useful;
- intended integration/merge order;
- assumptions whose failure should trigger replanning; and
- the assurance map: acceptance/judgment questions, their evidence owners, the
  evidence required, invalidating change classes, and which assurance may run
  concurrently (a concise default map is enough for small bounded work).

Parallelism is deliberate: independent tasks should not be serialized without a
reason, while dependent or stacked tasks should not be launched as if they were
independent.

## Workset flow

1. Planner records the workset strategy and assurance map. At a repository-evolution boundary, the Coder must flag it and supply/update the relevant check or fixture, and Planner maps it.
2. Watchtower dispatches Coder or a separately bounded repair actor according to the plan. It classifies each reported edge.
3. After every Coder, repair, test contribution, integration, or other candidate mutation, send the exact committed candidate to the **No-Mistakes Runner first**.
4. At an evolution boundary, the Runner explicitly verifies that checks execute meaningfully. Watchtower blocks broad judgment fan-out until that report. A broken/stale check is `NEEDS_GATE_REPAIR`; a functioning check exposing a candidate defect is classified as implementation/tests/replan according to evidence, never by reporting channel. A non-gate substrate defect is `NEEDS_INFRA_REPAIR`.
5. After the gate reports, record changed-head reconciliation. A mutation invalidates old gate evidence; reconciliation decides which Reviewer/Tester judgments are stale. Every new exact head re-enters the gate.
6. Only after a green gate on the final exact head, dispatch focused Reviewer/Tester evidence deficits, concurrently when independent and permitted. The existing explicitly labeled red-candidate advisory exception remains; it is not verification of record.
7. Route each edge by the table below to repair, implementation, tests, review, replan, decision, or external dependency.
8. Workset Merger integrates/lands according to the plan. Every integration-created head re-enters the gate and scoped evidence reconciliation. Apply `/afk`; preserve repository policy and no-mistakes configuration ownership.
9. Record `DONE` only after exact-head delivery evidence and required acceptance are complete.

A one-task workset follows the same flow with parallelism/stacking collapsed away.

## Closed per-edge status contract

A status classifies one **actionable edge**, not an all-purpose task state. Exactly one status applies to each edge. A work item may have multiple independent edges, classified and routed separately and dispatched concurrently when the plan permits. Watchtower is classifier/router and preserves evidence; crew recommendations never self-authorize or charge counters.

| Status | Exclusive definition | Owner / route |
|---|---|---|
| `DONE` | Nothing required remains, including delivery and required acceptance. | Watchtower records closure. |
| `NEEDS_IMPLEMENTATION` | Product/repository behavior or code must change within current task/direction. | Coder; next candidate-writing turn increments `attempt_count`. |
| `NEEDS_TESTS` | Behavior exploration, test-design judgment, or durable test contribution is missing without a product defect conclusion. | Tester/Test Designer; contributions re-enter gate. |
| `NEEDS_REVIEW` | Independent design/contract/correctness/scope judgment is missing. | Reviewer after green gate, except labeled advisory. |
| `NEEDS_DECISION` | Policy, contract, scope, risk, priority, waiver, or authority choice is required. | Named decision owner, else operator. |
| `NEEDS_REPLAN` | Evidence invalidates task/direction/dependency/stack/fan-in/integration order. | Replanner; its turn increments `replan_count`. |
| `NEEDS_INFRA_REPAIR` | Required non-gate execution substrate is defective/absent. | Bounded Infrastructure Repair Specialist. |
| `NEEDS_GATE_REPAIR` | Required check/configuration/adapter/fixture is broken, stale, or not meaningful; not a valid rejection. | Bounded Gate Repair Specialist; Runner retains operation/green authority. |
| `BLOCKED_EXTERNAL` | Only an external actor/service/credential/quota/event/target can unblock. | Watchtower records owner and resume trigger; no blind retry. |

## Attempt and replan budget

Use `attempt-budget` as the routing authority for non-converging implementation
lineages.

The normal progression is:

```text
initial plan:  attempt_limit=10  replan_count=0
replan #1:     attempt_limit=20  replan_count=1
replan #2:     attempt_limit=30  replan_count=2
replan #3:     attempt_limit=30  replan_count=3
```

`attempt_count` is cumulative. Replanning extends the lineage instead of resetting
it. The third Replanner turn is available for final restructuring, splitting,
parallel/stack strategy changes, or deferral decisions but does not authorize
Coder attempt 31.

At the current Coder ceiling, let assurance for the exact candidate finish. If
another code repair is required and another budget-extending replan is available,
replan. At the hard 30-attempt ceiling or after 3 Replanner turns, defer/escalate
the lineage rather than creating an unbounded retry loop.

## No-mistakes configuration

Repository `.no-mistakes.yaml` and the selected global no-mistakes profile are the
configuration authorities for the pipeline. Global configuration lives at
`~/.no-mistakes/config.yaml` unless `NM_HOME` selects another profile.

Current no-mistakes supports an `agent` value or ordered fallback list and
`agent_config` entries for per-agent model/effort. The optional Rozoro machine
profile may say which of those profiles/accounts are available locally; the
No-Mistakes Runner verifies the effective selection rather than rewriting config
for each run.

## Briefing

Watchtower writes each brief from the current task/workset state. Prefer
**intent + pointer + only the context, constraints, and evidence this specialist
needs**.

For Planner, include the workset intent and operator constraints; expect a usable
execution strategy, not only a list of tasks.

For Replanner, include the current task/workset plan, failed directions and
findings, and the current `attempt_count`, `attempt_limit`, and `replan_count`.

For Workset Merger, include the current Planner/Replanner strategy, participating
exact heads, assurance/no-mistakes evidence, target merge policy, and current
`/afk` state.

## Learning

The Watchtower is allowed to begin with incomplete project context. Plans, crew
handoffs, merged results, no-mistakes runs, and operator steering become reusable
durable context for later work in that project.

The optional no-mistakes Observatory is a qualitative learning surface. Keep run
IDs and prefer structured no-mistakes data for durable timing, retries, fixes,
findings, agent/model use, and outcomes.


## Repair incidents and ad-hoc specialists

Record `repair_lineage_id`, `implementation_lineage_id` when linked,
`infra_repair_count`, `gate_repair_count`, `repair_limit: 3`, and `caused_by`.
Counts come from durable history, never reset across sessions/specialists/branches/
worktrees/resumes/reclassification, and increment exactly one matching counter only
for an authorized mutating repair. Diagnosis/reruns/reports do not count. The hard
incident cap is `infra_repair_count + gate_repair_count <= 3`. Two failed same-root
attempts require an ownership/authority checkpoint; attempt 3 needs a changed
hypothesis and named owner. No fourth attempt: route decision, external block, or
replan only according to its exclusive definition. A genuinely unrelated root cause
gets a new repair lineage with rationale. Repair counters never increment Coder or
Replanner counters; product-code work becomes `NEEDS_IMPLEMENTATION`.

The delivery mission opts in to bounded Infrastructure and Gate Repair Specialists.
Each instance has one job until `DONE`, classified handback, or stop; `send` only
finishes that job. Before dispatch record role instance ID/name, mission, work item,
creation time, gap rationale, must/must-not boundary, stop, evidence shape, analogous
role, routing source and selected/fallback target, Watchtower attribution, and later
termination/outcome. They cannot absorb operator acceptance/priority, Watchtower
classification/routing, repository policy/contract/scope decisions, planning, product
implementation, review/test acceptance, Runner gate authority, or Merger authority;
they cannot merge, waive evidence, self-accept, or broaden scope. Third materially
equivalent creation triggers graduation review; fourth is prohibited until a
permanent contract or decision-authority exception with a new review point.

In every fresh dispatch, including ad-hoc, route **operator > repository > durable
operator policy (nearest analogous role and ordered fallback) > machine > preset**.
Immediately verify launcher/harness, account/profile, exact model, effort/tier,
credentials and capacity; use only policy-compatible fallback. Otherwise record
attempted targets and classify external block or an authorized decision need.

Repair report example:
```text
repair_lineage_id: repair-123
implementation_lineage_id: implementation-456
infra_repair_count: 1
gate_repair_count: 1
repair_limit: 3
caused_by: stale gate fixture
```
