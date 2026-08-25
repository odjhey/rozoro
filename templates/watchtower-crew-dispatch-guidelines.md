# Watchtower crew dispatch guidelines

Use these defaults when dispatching **Rozoro crew**. Watchtower selects a task
kind, resolves an available execution target for this machine, and writes the
smallest useful task-specific brief.

Canonical model IDs and reasoning effort below are **preferred role defaults**.
`crew-model-selection` may choose a compatible available target using the optional
`$ROZORO_HOME/config/machine.md`, current crew presets, repository constraints, or
explicit operator instructions.

## Briefing style

Prefer concise, natural briefs:

**intent + pointer + only the context, constraints, and evidence that matter to
this crew**

The target repository is discoverable from `--cwd`. Plans, handoffs, findings, and
workset state are added when they materially constrain the current turn.

## Standard crew roles

### Task Decomposer / Planner — `gpt-5.6-sol`, high

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

### Coder — `gpt-5.6-sol`, low

Implement one bounded task. Follow repository-local rules and the supplied task
boundary. Repair concrete reviewer/tester/no-mistakes/integration findings when
Watchtower routes them back and the task boundary still holds.

Report the candidate head and useful evidence so later roles can reason about the
exact implementation that was produced.

### Reviewer — `gpt-5.6-luna`, high

Review an exact candidate in fresh context against the task, contracts,
surrounding code, and acceptance criteria. Separate correctness defects from
optional cleanup and provide evidence precise enough to route a repair or accept
the candidate.

### Tester — `gpt-5.6-luna`, high

Exercise an exact candidate from its intended use case and meaningful failure
modes. Cover boundaries, invalid inputs, retries, partial failures, state
transitions, integrations, regressions, and weak-test risks that matter to the
task. Bind the result to the tested head.

### Escalation Replanner — `gpt-5.6-sol`, high

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

### No-Mistakes Runner — `gpt-5.6-luna`, high

Operate the configured no-mistakes pipeline for an exact committed candidate.
This is a thin execution/listening role, not another independent code reviewer.

Give it:

- repository and workset/task identity;
- exact candidate branch/head/base;
- operator intent/acceptance pointer that no-mistakes needs;
- the selected no-mistakes profile when the machine profile names one; and
- whether it should submit a new run or reattach to a known run.

The runner uses the repository's trusted no-mistakes configuration plus the
selected global profile (`~/.no-mistakes/config.yaml` or another `NM_HOME`). It may
submit through the configured `no-mistakes` Git remote or use the supported
CLI/AXI flow for the installed version.

Once a run exists, keep the runner available to listen/attach and report actionable
structured state. The runner reports run ID, submitted/final heads, findings/gate
state, fixes performed by no-mistakes, PR/CI state, and custody/recovery state.
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

### Workset Merger — `gpt-5.6-luna`, high

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

`quick-crew-routing` owns eligibility for the bounded fast path. Eligible Quick
Scout and Quick Coder prefer `gpt-5.3-codex-spark` at low effort.

Use Quick Crew for narrow, mechanical, low-risk work where latency matters. When
the work expands beyond that boundary, route it into the appropriate standard
role.

## Watchtower — `gpt-5.6-sol`, high preferred

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
