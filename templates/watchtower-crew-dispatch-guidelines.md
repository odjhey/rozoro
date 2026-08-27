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

`$ROZORO_HOME/config/machine.md` is availability/capacity evidence, not role
authority. A crew preset only realizes an already-authorized selection; launcher
defaults and presets cannot supply missing policy. See ADR-0012.

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

## Quick Crew

`quick-crew-routing` owns eligibility for the bounded fast path. Global denials
apply to Quick Crew. Its target must be authorized by durable operator policy and
freshly verified as available. When no eligible fast assignment exists, route to
the appropriate standard role only if that role resolves independently;
otherwise block. Never invent a fast target or inherit a standard role's target.

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
caused_by: tester finding on retry/idempotency behavior
```

These are ordinary report metadata derived from durable lineage history rather
than Rozoro lifecycle fields. Watchtower remains responsible for reconciling the
actual counts before dispatch.
