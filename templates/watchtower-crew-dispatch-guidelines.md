# Watchtower crew dispatch guidelines

Use these defaults when dispatching **Rozoro crew**. Watchtower selects a task
kind, resolves an available execution target for this machine, and writes the
smallest useful task-specific brief.

This file owns **role contracts and dispatch semantics only**. Concrete
harness/model/effort assignments are durable operator policy under
`$ROZORO_HOME/watchtower-policies/`; this template intentionally names no models.

For every fresh shipped, aliased, mission, or ad-hoc role, first apply explicit
operator requirements and repository constraints, then the role contract and all
durable policy (including global denials), then filter authorized candidates by
freshly verified machine availability. Resolve an exact durable entry, a
documented canonical alias, or one uniquely compatible nearest analog whose
boundary contains and is only narrowed by the mission. Never splice role
authority and target preferences. Missing or unavailable assignments, ambiguous
availability, conflicting constraints, and non-unique analogs block unless an
explicitly authorized fallback exists.

The precedence can be summarized as **operator > repository > durable policy >
machine availability filter > compatible preset realization**. The machine profile
and preset layers do not authorize a target: `$ROZORO_HOME/config/machine.md` is
availability/capacity evidence, and a crew preset only realizes an already-authorized
selection. Launcher defaults and presets cannot supply missing policy. See ADR-0012.

## Briefing style

Prefer concise, natural briefs:

**intent + pointer + only the context, constraints, and evidence that matter to
this crew**

The target repository is discoverable from `--cwd`. Plans, handoffs, findings, and
workset state are added when they materially constrain the current turn.

## Standard crew roles

### Task Decomposer / Planner

Turn raw intent into bounded executable work when scope, dependencies, acceptance
criteria, execution strategy, integration order, or repository boundaries are not
already clear.

The Planner owns the **workset execution strategy**. For work that can fan out, it
should decide and record:

- the bounded tasks in the workset;
- dependency edges between tasks;
- which tasks may run in parallel;
- which tasks must be sequential or stacked;
- the base/parent relationship for stacked work when known;
- fan-out and fan-in points or execution waves when useful;
- the intended integration/merge order; and
- constraints that would invalidate that strategy and require replanning.

Prefer parallel work where tasks are genuinely independent. Prefer stacking when a
later task semantically or mechanically depends on an earlier candidate. Do not
serialize independent work merely because it belongs to the same workset, and do
not parallelize tasks whose branch/base or contract dependencies require order.

Produce enough structure for Watchtower to dispatch the workset without inventing
its own scheduling strategy and for the Workset Merger to preserve the intended
stack/integration shape. Unknown repository facts may remain explicit assumptions
or discovery tasks rather than being treated as settled.

The Planner also records the workset **assurance map**: for each task or for the
workset as a whole,

- the acceptance and judgment questions;
- the role that owns each question's evidence;
- the evidence each question requires;
- the change classes that invalidate that evidence; and
- which assurance work may run concurrently.

For small bounded tasks a concise default map is enough — for example
"correctness/contract judgment: Reviewer; behavior/test-design judgment: Tester;
mechanical evidence: no-mistakes gate; every candidate-changing edit invalidates
gate evidence; an edit invalidates a judgment only when it changes that
judgment's question." Do not demand a heavyweight planning artifact merely to
satisfy the map; do demand that later reconciliation has questions to check
changes against.

## Verification ordering

Mechanics precede judgment. When a Coder reports a committed candidate, the
No-Mistakes Runner must be the first post-Coder verification hop for that exact
head. Reviewer and Tester must follow only after the gate reports green for the exact
final head reported by the run, which may differ from the submitted head when the
pipeline changes the candidate. The sole exception is that, after the gate reports
red, Watchtower may dispatch an explicitly labeled red-candidate judgment recording
`gate_status: red`, the exact red commit/tree/base/merge-base, and a reason limited
to a suspected design dead end, contract ambiguity, acceptance risk, or deeper
direction within those categories that the gate cannot provide. That judgment must
be labeled "not verification of record," does not bypass or replace No-Mistakes,
can never satisfy the gate, and does not authorize redundant suite execution.

Every repair, gate fix, test contribution, integration, or other candidate-changing
action creates a new exact candidate, invalidates prior gate and Reviewer/Tester
attestations for that new head, and must re-enter No-Mistakes. A mechanical-only
change still requires that gate rerun, but does not require fresh Reviewer or Tester
judgment unless it creates or changes a design, contract, correctness, acceptance,
behavior/test-design, or other judgment question.

Old gate and Reviewer/Tester observations remain context bound only to their old
head; never relabel them as observations of, or assurance produced for, a new head.
The Workset Merger, or a named reconciliation owner it explicitly routes, records
a **changed-head reconciliation** for every candidate-changing action: old
commit/tree/base/merge-base identities, new commit/tree/base/merge-base
identities, changed paths and cause, affected judgment questions (behavior,
contracts, correctness, security, test design, documentation, integration, and
delivery, as applicable), the evidence that remains current, the evidence that
became stale, the minimum next checks required, the rationale, whether fresh
judgment is required, and the named owner.
Whenever any new head retains judgment from an old head, including after a
mechanical gate fix or a Tester/Test Designer contribution, this named-owner
reconciliation is mandatory. It must contain every field above even when its
explicit fresh-judgment decision is "no fresh judgment required." Missing or
incomplete reconciliation fails closed: do not dispatch post-gate Reviewer/Tester
judgment for the changed head, and final readiness must reject the candidate,
until the reconciliation exists. This record is changed-head provenance, not
rewritten old evidence.

After a Reviewer finding is repaired, always gate the repaired candidate. Request
fresh Reviewer judgment for each changed review question and fresh Test Designer
judgment for each changed behavior/test-design question; when neither is affected,
record the scoped no-new-judgment rationale in the reconciliation without rewriting
old-head judgments. Apply the same rule after a rebase, merge, or other integration:
gate the exact integrated head, request fresh Reviewer and/or Test Designer judgment
for each affected question, and otherwise preserve old evidence only as context
alongside the explicit changed-head reconciliation provenance.

When a ratchet proposal picks its codification channel, scope it to the pipeline
step that owns its delivery (source-verified against no-mistakes v1.57.0):
review-owned judgment (correctness, contracts, invariants) goes to
`review.path_instructions`; docs-ownership policy goes to `document.instructions`;
mechanically checkable rules go to the repository suite or a lint rule. The gate's
Review step drops findings whose delivery a later step owns, so a lint- or
docs-flavored `path_instructions` entry is silently discarded — pick the channel
by ownership, not convenience.

## Evidence-deficit dispatch

Proportional assurance is the default generic model for every artifact type —
implementation, documentation, configuration, generated output, dependency,
pipeline-fix, rebase, and integration changes alike. Watchtower neither reruns
broad Reviewer/Tester scopes after every candidate change nor waves a change
through because it looks small. After the gate, it dispatches only the
**evidence deficits** the changed-head reconciliation identifies against the
assurance map:

- **mechanical/provenance-only change:** exact-head gate rerun; retain prior
  judgment with the recorded rationale;
- **design/contract/correctness change:** gate plus focused Reviewer judgment on
  the affected questions;
- **behavior/test-design change:** gate plus focused Tester judgment on the
  affected questions;
- **both:** gate plus focused Reviewer and focused Tester, normally in parallel
  on the same head;
- **integration/base change:** Workset Merger changed-head reconciliation first,
  then only the affected assurance;
- **no affected judgment question:** no redundant Reviewer/Tester rerun; record
  the scoped no-new-judgment rationale in the reconciliation.

Impact class comes from the reconciliation's affected-question analysis, never
from file type, file count, or diff size. When the impact of a change is
uncertain, the deficit is the impact analysis itself — route a focused judgment
turn to settle it rather than guessing "small means safe."

### Fan-in and convergence

- When the affected questions leave Reviewer and Tester independent and the
  workset strategy permits it, fan both out on one frozen exact head and collect
  both results before routing one combined repair batch, rather than
  interleaving repairs per finding.
- A candidate-changing repair re-enters the exact-head gate once, then reruns
  only the questions its reconciliation marks affected.
- Two repeated failures with the same root cause trigger an ownership/authority
  checkpoint — reconsider which role owns the fix, whether the task boundary or
  plan is wrong (Replanner), or whether the operator must decide — rather than a
  blind third attempt down the same route.
- Where feasible, turn repeated finding classes into repository tests, lint
  rules, or explicit gate/policy configuration so the gate owns future
  enforcement.
- Assurance-only reruns — gate, Reviewer, or Tester turns dispatched for
  evidence deficits — consume no Coder implementation attempts when no
  candidate-writing Coder turn occurred; `attempt-budget` owns the accounting.

### Coder

Implement one bounded task. Follow repository-local rules and the supplied task
boundary. Repair concrete reviewer/tester/no-mistakes/integration findings when
Watchtower routes them back and the task boundary still holds.

Report the exact committed candidate head and tree, plus its base and merge-base,
ready for the No-Mistakes gate so later roles can reason about the exact
implementation that was produced.

### Reviewer

Review a gate-green exact candidate in fresh context, applying judgment
to its design, contracts, correctness reasoning, surrounding-code fit, and
acceptance fit. Separate correctness defects from optional cleanup and provide
evidence precise enough to route a repair or accept the judgment.

This is a judgment-only role: do not execute the repository test suite. The
No-Mistakes gate owns mechanical execution evidence bound to the exact head. For
every repeated finding class, the handoff must propose codification as
`review.path_instructions` in `.no-mistakes.yaml`, a test joining the repository
suite, or a lint rule, so the gate owns future enforcement; novel and contextual
judgment remains crew work.

### Tester

Examine a gate-green exact candidate as a test designer, not a redundant
suite runner. Drive behavior exploratorily from intended use cases and meaningful
failure modes, covering boundaries, invalid inputs, retries, partial failures,
state transitions, integrations, regressions, and weak-test risks that matter to
the task. The durable deliverable is a new or extended test that joins the
repository suite, or a patch-level test specification when the workflow does not
permit a contribution, so the gate can enforce it on future candidates.

Do not run the full existing repository suite as verification of record; bind
exploratory findings and test contributions to the tested head. A test contribution
creates a new candidate that must re-enter the gate rather than being presumed
green. For every repeated finding class, the handoff must propose
`review.path_instructions` in `.no-mistakes.yaml`, a repository-suite test, or a
lint rule; once codified, the gate owns future enforcement while novel and
contextual test judgment remains crew work.

### Escalation Replanner

Use when implementation/review/test/integration loops stop converging or new
evidence changes the task boundary, dependency graph, parallel/stacking strategy,
or implementation direction.

Give it the current bounded task/workset plan, useful failure evidence, and the
lineage's current `attempt_count`, `attempt_limit`, and `replan_count`. It owns a
revised execution strategy: tasks, dependencies, parallel groups, stacks, fan-in,
and intended integration order where those need to change. It explains what
changed so Watchtower, fresh Coders, and the Workset Merger do not simply repeat
the failed direction.

Replanning **extends** the cumulative Coder budget; it never resets it. The normal
lineage starts with `attempt_limit=10`. A materially revised replan extends that
limit by 10, capped at **30 total Coder attempts**. Keep `attempt_count` cumulative
across fresh Coders, branches, worktrees, and revised plans.

A lineage may use at most **3 Replanner turns**. Track `replan_count` explicitly.
The third Replanner turn may still restructure/split/defer the work, but the hard
Coder ceiling remains 30 and it does not create attempts 31–40. Use the
`attempt-budget` skill for the exact routing rules.

### No-Mistakes Runner

Operate the configured no-mistakes pipeline for an exact committed candidate.
This is a thin execution/listening role, not another independent code reviewer.

The gate is the first verification hop after a Coder's committed candidate and the
re-entry point after every repair or candidate-changing action. Its rerun is the
verification of record for mechanical confidence; do not replace it with fresh
Reviewer or Tester crews merely to repeat suite, lint, format, or other mechanical
checks. For every run, report separate submitted and final candidate records, each with its
exact commit, tree, base, and merge-base identities. When the gate changes the head,
do not collapse those records. Final readiness must reject any missing identity.

Give it:

- repository and workset/task identity;
- exact candidate branch, commit/tree, base, and merge-base;
- operator intent/acceptance pointer that no-mistakes needs — pass it as
  explicit intent at submission where the installed flow supports it (explicit
  intent is authoritative; otherwise the pipeline infers intent from local agent
  session transcripts, which may select the wrong session or a stale summary);
- the selected no-mistakes profile when the machine profile names one; and
- whether it should submit a new run or reattach to a known run.

The runner uses the repository's trusted no-mistakes configuration plus the
selected global profile (`~/.no-mistakes/config.yaml` or another `NM_HOME`). It may
submit through the configured `no-mistakes` Git remote or use the supported
CLI/AXI flow for the installed version.

Once a run exists, keep the runner available to listen/attach and report actionable
structured state. The runner reports run ID; separate submitted and final candidate
commit/tree/base/merge-base records; findings/gate state; fixes performed by
no-mistakes; PR/CI state; and custody/recovery state.
Interpretation that depends on dependency order or integrated workset state goes
to the Workset Merger.

Use no-mistakes' native global/repository `agent`, ordered fallback, and
`agent_config` mechanisms for pipeline-agent model/effort selection. A machine
profile may name multiple no-mistakes profiles/accounts and the environment needed
to start them. Verify the effective profile with the installed no-mistakes tools.

`CLAUDE_CONFIG_DIR` is a Claude harness environment variable, not a documented
no-mistakes config field. A one-shot environment prefix on the no-mistakes CLI is
not assumed to reconfigure an already-running no-mistakes daemon. When separate
Claude identities are required, prefer explicit machine-profile/no-mistakes
profiles (for example separate `NM_HOME` instances) whose daemon environment is
known and verified.

### Workset Merger

Own integration and landing execution for one workset.

Give it the workset intent, Planner/Task Decomposer execution strategy when one
exists, participating task branches/heads, known dependencies, review/test/
no-mistakes/CI evidence, repository merge policy, and current `/afk` state.

The Planner/Replanner owns the intended parallel/stacking strategy. The merger
should execute and reconcile that strategy against actual crew results, not invent
a different work decomposition merely because integration is difficult.

The merger should:

1. reconstruct the current workset graph from the plan plus actual crew results;
2. validate the planned dependency, stacking, and merge order against current
   branch/head reality;
3. re-fetch exact branch/PR heads before mutation;
4. integrate candidate branches in the order required by the current plan;
5. detect stale evidence, an invalidated stack assumption, or integration failures
   and route a bounded repair or Replanner recommendation back to Watchtower;
6. read no-mistakes results in workset context and decide whether findings are
   local repair, integration fallout, or evidence that the plan/dependency strategy
   must be revised;
7. ensure the final integrated head has the assurance required by repository
   policy; and
8. when authorized, perform the final supported merge and required post-merge
   checks/actions, reporting the actual landed identity.

If actual repository evidence invalidates the Planner's strategy, preserve that
evidence and request Replanner. The Workset Merger may make mechanical integration
choices within the declared strategy, but it does not silently redesign which
tasks should have been parallel, stacked, split, or reordered.

For a single-task workset with no stacking, the same role reduces to the simple
landing/post-merge case.

`/afk on` allows the final merge when evidence and repository/operator policy are
sufficient. `/afk off` stops the merger immediately before the final merge
mutation and asks the operator to confirm.

## Failure classification and repair specialists

Watchtower classifies each actionable edge; crew recommendations are not
self-authorizing. Exactly one of the following closed statuses applies per edge;
separate edges may be routed independently:

| Status | Exclusive definition for one actionable edge | Owner / route | Accounting |
|---|---|---|---|
| `DONE` | No required implementation, assurance, decision, repair, replan, external dependency, delivery, or required acceptance remains. | Watchtower records closure; operator acceptance remains where not delegated. | None |
| `NEEDS_IMPLEMENTATION` | Product/repository behavior or code must change within the current task and direction. | Existing Coder; otherwise reclassify `NEEDS_REPLAN`. | Next candidate-writing Coder increments `attempt_count`. |
| `NEEDS_TESTS` | Behavior exploration, test-design judgment, or durable test contribution is missing; no product defect is established. | Tester/Test Designer; a contribution creates a candidate and re-enters the gate. | No Coder attempt unless reclassified. |
| `NEEDS_REVIEW` | Independent design/contract/correctness/scope judgment is missing. | Reviewer after a green exact-head gate, except labeled red-candidate advisory. | None |
| `NEEDS_DECISION` | A policy, contract, scope, risk, priority, waiver, or authority choice is required. | Governing decision owner, else operator. | None merely for deciding. |
| `NEEDS_REPLAN` | Evidence invalidates task, direction, dependency graph, stack/fan-in, or integration order. | Escalation Replanner. | Its turn increments `replan_count`. |
| `NEEDS_INFRA_REPAIR` | A non-gate execution substrate (toolchain/workspace/harness runtime/corpus or fixture provisioning) is defective or absent. | Bounded Infrastructure Repair Specialist. | Mutating repair increments `infra_repair_count`. |
| `NEEDS_GATE_REPAIR` | A required check, CI/no-mistakes configuration, adapter, or check fixture is defective, stale, or not meaningful; not a functioning check rejecting a defect. | Bounded Gate Repair Specialist; Runner retains rerun/green authority. | Mutating repair increments `gate_repair_count`. |
| `BLOCKED_EXTERNAL` | No authorized internal repair/decision can clear the edge; an external actor, service, credential/quota, event, or execution target is required. | Watchtower records dependency, owner, and objective resume trigger; no blind retry. | None |

For repair incidents: Every repair incident records `repair_lineage_id`, linked
`implementation_lineage_id` when applicable, `infra_repair_count`,
`gate_repair_count`, `repair_limit: 3`, and `caused_by`. Counts derive from durable
history and never reset across actors, sessions, branches, worktrees, resumes, or
reclassification. Only an authorized mutating repair increments exactly one repair
counter; diagnosis/reruns/reports do not. The combined per-incident cap is
`infra_repair_count + gate_repair_count <= 3`. Two unsuccessful same-root attempts
require an ownership/authority checkpoint; attempt 3 needs a changed hypothesis
and named owner. No fourth attempt is allowed. Repair counters never increment
`attempt_count` or `replan_count`; product-code work is reclassified
`NEEDS_IMPLEMENTATION`, while only a true plan change is `NEEDS_REPLAN`.

### Infrastructure and Gate Repair Specialists

The delivery mission explicitly opts in to these bounded ad-hoc roles. Infrastructure
Repair owns only the declared non-gate substrate repair. Gate Repair owns only the
declared check/configuration/adapter/fixture repair; the No-Mistakes Runner retains
gate operation, rerun, and green determination. A reporting channel never determines
classification.

## Ad-hoc specialists

A mission may dispatch one only when its mission text explicitly opts in. An opted-in ad-hoc role instance has one bounded work item and lasts until it
reports `DONE`, hands back a classified unresolved edge, or is stopped. `send` may
only finish that declared job; expanded scope, authority, or evidence shape needs
a new declaration and instance. Before dispatch, record in the task/work item and
attention ledger: `role_instance_id`, role name, mission, task/work-item ID,
creation time, unowned-gap rationale, must/must-not boundary, stop condition,
expected evidence, analogous standard role (or none), routing-policy source and
selected/fallback target, creating Watchtower registration/policy attribution,
and later termination/outcome.

It may execute only that job and create a bounded repair artifact only when
authorized. It may not absorb or waive operator priority/final acceptance;
Watchtower classification/routing; repository contract/policy/scope decisions;
Planner/Replanner strategy; Coder product implementation; Reviewer acceptance;
Tester acceptance; Runner gate operation/green determination; or Merger
integration/landing/post-merge authority. It may not merge, waive evidence, accept
its own work, or broaden its brief.

Count materially equivalent functions per mission (same purpose, authority
boundary, and evidence shape; renaming does not reset). The third creation
requires graduation review and may finish. A fourth dispatch is prohibited until
the mission names a permanent role/contract or its decision authority records why
it remains ad hoc and sets a new bounded review point.

Ad-hoc routing uses the same fail-closed ADR-0012 precedence: **operator >
repository > durable policy > machine availability filter > compatible preset
realization**. Resolve an exact durable role entry, documented alias, or one unique
nearest analog whose authority contains the bounded specialist; global denials and
repository constraints remain binding. The machine profile only filters authorized
candidates, and presets only realize them.

Immediately before each fresh dispatch, verify launcher/harness, account/profile,
exact model ID, effort/tier, required credentials, and capacity. Use only an
operator/policy-authorized fallback when the selected target is unavailable;
otherwise record attempted targets/reasons and classify `BLOCKED_EXTERNAL`, or
`NEEDS_DECISION` only when an authorized policy choice can resolve the edge. A
same-live-crew follow-up reselects only on lost availability or changed task kind.

## Quick Crew

`quick-crew-routing` owns eligibility for the bounded fast path. The Quick Crew
model/effort target comes from durable operator policy and machine availability,
like every other role; when no eligible fast target is available, route to the
appropriate standard role instead of inventing another quick tier.

Use Quick Crew for narrow, mechanical, low-risk work where latency matters.
Eligibility depends on impact certainty and risk, never on apparent file count,
diff size, or task size: a one-line contract, configuration, or dependency change
is not quick merely because it is small. When the work expands beyond the
boundary, route it into the appropriate standard role.

## Watchtower

Watchtower's own harness/model/effort is launch selection, not crew dispatch: the
canonical operator path is a versioned watchtower preset under
`$ROZORO_HOME/watchtower-presets/` (ADR-0011), which the launcher records in the
registration attribution.

Watchtower owns cross-project/workset priority, dispatch, routing, operator
interaction, and the global view. It may manage multiple repositories at once by
choosing `--cwd` per crew.

Watchtower starts with the context it has. It accumulates useful project knowledge
from repository docs, plans, crew handoffs, gate results, operator steering, and
delivery outcomes. Reuse durable results when they matter; load deeper context on
demand rather than trying to preload a project's entire history.

Within a workset, dispatch according to the Planner/Replanner strategy: start
independent tasks in parallel, preserve required stacks/sequences, and wait at
fan-in points only when the plan requires it. Delegate integration/landing
execution to the Workset Merger and no-mistakes execution/listening to the
No-Mistakes Runner.

Watchtower routes their results, handles cross-workset priorities, enforces the
cumulative attempt/replan budget, and involves the operator when `/afk` or a
genuine authority boundary requires it.

## Repair-loop report fields

Implementation and replanning crews should provide these when the lineage is in a
repair loop:

```text
attempt_count: 17
attempt_limit: 20
replan_count: 1
repair_lineage_id: repair-example-1
implementation_lineage_id: implementation-example-1
infra_repair_count: 0
gate_repair_count: 1
repair_limit: 3
caused_by: tester finding on retry/idempotency behavior
```

These are ordinary report metadata derived from durable lineage history rather
than Rozoro lifecycle fields. Watchtower remains responsible for reconciling the
actual counts before dispatch.
