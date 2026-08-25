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
criteria, integration order, or repository boundaries are not already clear.

For work that will fan out, identify which tasks are independent, which depend on
other tasks, and any intended stacking/integration order the Workset Merger should
preserve. Produce enough structure for coders to work independently without
pretending unknown repository facts are settled.

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
evidence changes the task boundary. Give it the original task plus the useful
failure evidence. It produces a revised bounded task/dependency plan for fresh
execution.

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

Own integration and landing reasoning for one workset.

Give it the workset intent, Planner/Task Decomposer output when available,
participating task branches/heads, known dependencies, review/test/no-mistakes/CI
evidence, repository merge policy, and current `/afk` state.

The merger should:

1. reconstruct the current workset graph from the plan plus actual crew results;
2. determine dependency, stacking, and merge order;
3. re-fetch exact branch/PR heads before mutation;
4. integrate candidate branches in the order required by the workset;
5. detect stale evidence or integration failures and route a bounded repair or
   replan recommendation back to Watchtower;
6. read no-mistakes results in workset context and decide whether findings are
   local repair, integration fallout, or a plan/dependency problem;
7. ensure the final integrated head has the assurance required by repository
   policy; and
8. when authorized, perform the final supported merge and required post-merge
   checks/actions, reporting the actual landed identity.

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

Within a workset, delegate integration/stacking/landing judgment to the Workset
Merger. Delegate no-mistakes execution/listening to the No-Mistakes Runner.
Watchtower routes their results, handles cross-workset priorities, and involves the
operator when `/afk` or a genuine authority boundary requires it.

## Experimental report fields

Implementation-related crews may provide `attempt_count` and `caused_by` when
useful for measuring repair loops. They remain ordinary report metadata rather
than Rozoro lifecycle fields.
