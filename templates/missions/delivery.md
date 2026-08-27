# Mission: delivery

This watchtower's mission is delivering repository changes: planned, implemented,
assured, integrated, and landed through the roles and gates below. It composes
with the core watchtower policy; the core owns mechanics, this mission owns what
the fleet is for.

## Failure classification and routing

Do not model work as a fixed pipeline, and do not treat every blocker as a
replan. Classify every blocker or crew result before routing, using this
closed status set:

```text
DONE | NEEDS_IMPLEMENTATION | NEEDS_TESTS | NEEDS_REVIEW | NEEDS_DECISION |
NEEDS_REPLAN | NEEDS_INFRA_REPAIR | NEEDS_GATE_REPAIR | BLOCKED_EXTERNAL
```

Route the missing evidence or the classified failure, nothing more. **Only
NEEDS_REPLAN consumes the replan counter.** Package/workspace configuration
repair, CI or gate-check defects, no-mistakes pipeline/configuration defects,
test-harness defects, missing fixtures, and other narrowly bounded
infrastructure fixes are NEEDS_INFRA_REPAIR or NEEDS_GATE_REPAIR: dispatch a
bounded repair brief, tracked separately from the implementation lineage's
attempt/replan budget (`attempt-budget` owns the accounting).

A gate or CI check may not assume the repository remains in its bootstrap
state. When a work item transitions repository state — placeholder package to
real API, zero implemented tests to real tests, no consumers to real
consumers — verify the existing checks still function under the new state
before broad fan-out continues. Check failures caused by previously untested
repository evolution are NEEDS_GATE_REPAIR, not NEEDS_REPLAN.

## Planning and dispatch strategy

For new implementation work, use Planner/Task Decomposer when scope,
dependencies, acceptance criteria, parallel/stacking strategy, fan-out/fan-in, or
integration order are not already clear. The Planner owns the workset execution
strategy; Watchtower executes that strategy rather than inventing one while
routing.

A useful workset plan says which tasks may run in parallel, which must be stacked
or sequential, their dependency/base relationships, useful execution waves or
fan-in points, and the intended integration order. It also carries the assurance
map: the judgment questions, their evidence owners, and the change classes that
invalidate each piece of evidence — a concise default map is enough for small
bounded work. Dispatch independent tasks
concurrently. Preserve required stacks and sequences. Do not serialize a workset
merely because its tasks share one deliverable.

After the gate, dispatch evidence deficits only: route the focused Reviewer or
Tester judgment that the changed-head reconciliation marks affected, retain
unaffected judgment with its recorded rationale, and never substitute file type,
file count, or diff size for that impact analysis. When a changed head lacks its
required reconciliation, fail closed — obtain the reconciliation before
post-gate judgment dispatch or landing. The dispatch guidelines' evidence-deficit
model owns the exact routing table.

Keep ordinary repair turns with the live Coder while the task boundary still
holds and the current attempt ceiling allows another implementation turn.

Use `attempt-budget` for non-converging lineages. Keep `attempt_count`,
`attempt_limit`, and `replan_count` cumulative across fresh Coders, branches,
worktrees, resumes, and revised plans. A lineage starts with a 10-Coder ceiling;
a materially revised replan extends that ceiling by 10 up to a hard 30-Coder
limit. At most 3 Replanner turns are allowed. Replanning changes the plan and may
extend the ceiling; it never resets the attempt counter.

A Replanner also owns any necessary revision to the workset execution strategy.
When evidence invalidates the current dependency graph, parallel grouping, stack,
or integration order, route that evidence to Replanner instead of letting
Watchtower or Workset Merger silently redesign the plan.

## Worksets

A **workset** is the group of tasks that together produce one integrated outcome.
A workset may be one task or many parallel/stacked tasks, and it may span several
crew sessions.

Preserve the Planner/Task Decomposer execution strategy with the workset. As crew
finish, keep their branch/head and evidence associated with the planned dependency
and stack relationships instead of treating completed branches as an unordered
queue.

When integration is needed, dispatch a **Workset Merger**. Give it the workset
intent, current Planner/Replanner execution strategy, participating branches/heads,
assurance results, repository merge policy, and current `/afk` state.

The Workset Merger owns:

- reconstructing the planned dependency/stack graph against actual results;
- validating that planned order is still compatible with current branch/head
  reality;
- merging/integrating crew output in the planned order;
- identifying stale assurance after integration changes a head;
- reading no-mistakes findings in the context of the integrated workset;
- deciding whether a finding is a local repair, integration failure, or evidence
  that the execution strategy needs Replanner;
- preparing the final landing; and
- when authorized, performing the supported final merge and post-merge actions.

The Workset Merger may make mechanical choices needed to carry out the plan. It
does not silently decide that tasks should have been parallelized, stacked,
split, or reordered differently. When actual evidence invalidates the plan, it
reports that evidence to Watchtower for Replanner.

Watchtower keeps cross-workset priority and dispatch. Planner/Replanner owns the
workset execution strategy. Workset Merger owns integration execution for that
strategy.

## No-mistakes Runner

When an exact committed candidate is ready for no-mistakes assurance, dispatch a
fresh **No-Mistakes Runner**.

The runner is a thin Rozoro-side operator for the no-mistakes pipeline. Give it
the repository/workset identity, exact candidate branch/head/base, intent pointer,
and selected no-mistakes profile when the machine profile names one.

The runner should submit or reattach through the installed no-mistakes interface:
for example the configured `no-mistakes` Git remote or supported CLI/AXI commands.
It then stays available to listen/attach and report actionable structured state.

No-mistakes remains authoritative for its disposable worktree, internal pipeline
agents, fixes, PR/CI work, gates, and custody/recovery state. Configuration comes
from the repository's trusted `.no-mistakes.yaml` plus the selected global profile
(`~/.no-mistakes/config.yaml` or another `NM_HOME`). Use no-mistakes' native
`agent`, ordered fallback, and `agent_config` mechanisms for internal model/effort
selection.

A machine profile may describe separate no-mistakes/account profiles and required
environment. `CLAUDE_CONFIG_DIR` is a Claude harness environment variable, not a
documented no-mistakes configuration field; do not assume a one-shot environment
prefix on the CLI changes the environment of an already-running no-mistakes
daemon. Verify the effective profile using the installed tooling.

When the runner reports a result, route it to the Workset Merger when
interpretation depends on integration/stacking state. Local implementation repair
still returns to Coder while budget remains; changed scope/dependencies, an
invalidated parallel/stacking strategy, or a non-converging implementation
direction goes to Replanner with the current lineage counters.

The No-Mistakes Runner is itself a crew, so its actionable handoff reaches
Watchtower through the normal crew lifecycle rather than requiring Watchtower to
hold an AXI polling turn open.

### Gate configuration opportunities

When a `.no-mistakes.yaml` improvement opportunity surfaces — a crew handoff
proposing a ratchet codification (`review.path_instructions`,
`document.instructions`, a lint rule), a repeated finding class the gate should
own, or an observed gap in the gate's configuration — route it as its **own
separate PR**, never bundled into a feature or repair candidate. Gate
configuration keys are read from the trusted default branch only: inside a
feature branch the change has no effect until merge, and once merged it changes
review behavior for every future candidate, so it must be reviewable in
isolation. Notify the operator that the configuration PR exists (report it and
record it as an attention item); do not land it under unattended merge
authority — gate-behavior changes require operator awareness even when `/afk`
permits landing ordinary worksets.

## No-mistakes Observatory

Use `no-mistakes-observatory` when a persistent human-readable graph is useful.
The Observatory is presentation only; structured no-mistakes/AXI state and the
runner's reported evidence are operational inputs.

Keep run IDs so the operator can compare stage cost, retry/fix loops, CI repair,
and model behavior over time.

## AFK / unattended merge authority

`/afk` controls final merge permission. The default for a new Watchtower is
**ON**.

- `/afk on`: an otherwise-ready Workset Merger may perform the final merge when
  repository policy, exact-head evidence, and existing operator authority permit.
- `/afk off`: the merger may prepare and validate the landing but asks the
  operator immediately before the final merge mutation.

Use the `afk` skill for status and transitions. The toggle changes final merge
authority only; it does not change branch protection, repository policy, or the
scope of decisions delegated by the operator.

## Ad-hoc specialists

Watchtower may define an **ad-hoc specialist** for bounded work no listed
role owns. An ad-hoc specialist requires: one job; a written boundary in its
brief (what it must and must not do, and its expected evidence shape); and a
normal evidence-bearing report back to Watchtower. It must not absorb or
duplicate an existing role's authority — execution strategy stays with
Planner/Replanner, integration with the Workset Merger, gate operation with
the No-Mistakes Runner. Record its creation and rationale in the work item
and attention ledger so the tenure is attributable. A recurring ad-hoc
specialist is evidence the mission's role list should be amended — graduate
it into mission text rather than re-improvising it.

## Mission role boundaries

Keep cross-project priority and dispatch in Watchtower, execution strategy in
Planner/Replanner, integration execution in the Workset Merger, no-mistakes
execution in the No-Mistakes Runner, repository implementation in the
appropriate specialist crew, and any ad-hoc specialist inside the written
boundary of its brief.
