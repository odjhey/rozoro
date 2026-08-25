# ADR-0009: Use workset mergers, runner crews, and machine-local routing profiles

review: approved
date: 2026-08-25
supersedes: ADR-0006, ADR-0008

## Context

A Watchtower is useful before it has complete project context and becomes more
useful as plans, task results, review findings, gate results, and landed outcomes
accumulate. Policy therefore needs to describe what a Watchtower should do now,
not require it to reconstruct which conventions were replaced on another machine
or in an earlier iteration.

A Watchtower may also manage unrelated repositories concurrently. Harness/model
availability is machine-specific, while implementation and delivery policy is
repository-specific. Encoding one machine's accounts or launcher layout into the
canonical Watchtower role policy makes that policy brittle.

Parallel work introduces a second ownership problem. Work decomposition is not
only a list of tasks: somebody must decide which tasks may execute concurrently,
which are stacked or sequential, where dependencies and fan-in points exist, and
what integration order the workset is expected to follow. That decision belongs
with the Planner/Task Decomposer because it has the intent and decomposition view.

Completed crew branches are still real evidence and may invalidate the planned
shape. The actor that integrates a workset therefore needs the Planner/Replanner
execution strategy, actual crew results, exact-head assurance, and no-mistakes
findings in one place, but should not silently become a second planner.

No-mistakes already owns its validation pipeline and supports global/repository
configuration for agent selection. Rozoro still benefits from a dedicated crew
that performs the operational submit/reattach/listen work so Watchtower stays
push-driven and the integration decision can remain with the workset owner.

Long repair loops also need a bounded way to change direction without pretending a
new Coder, branch, or revised plan is a fresh task. Replanning should be able to
extend a lineage, but the cumulative attempt/replan history must remain visible and
bounded.

Finally, unattended operation needs an explicit operator control over the final
merge mutation without turning all orchestration into a confirmation queue.

## Options

1. Keep Watchtower as the direct no-mistakes controller and use a simple final
   Merge Finisher after each candidate is judged ready.
2. Let each Coder merge its own output and interpret its own no-mistakes result.
3. Use Planner/Replanner to own workset execution strategy, a thin No-Mistakes
   Runner crew for pipeline operation, and a Workset Merger crew to realize the
   planned integration/landing against actual results, with machine-local routing
   hints, bounded cumulative replanning, and an explicit unattended merge toggle.

## Choice

Choose option 3.

### Watchtower context and project scope

A Watchtower may manage multiple projects. Every crew dispatch names its target
repository with `--cwd` and project-specific facts stay scoped to the project or
workset they came from.

A Watchtower is allowed to start with incomplete project context. It accumulates
useful context from repository docs, Planner/Task Decomposer outputs, crew
handoffs, review/test/no-mistakes evidence, Workset Merger decisions, delivery
outcomes, and operator steering. Durable results are reused when relevant; there
is no requirement to preload a project's full history before routing work.

### Planner / Task Decomposer execution strategy

Planner/Task Decomposer owns the intended **workset execution strategy**.
Decomposition should decide, where applicable:

- bounded work items;
- dependency edges;
- parallel groups or execution waves;
- sequential/stacked tasks and their base relationships;
- fan-out/fan-in points;
- intended integration/merge order; and
- assumptions whose failure should trigger replanning.

Watchtower schedules work according to that plan. Independent work should be
started concurrently when practical; dependent or stacked work should preserve
its required order.

Replanner owns revisions to this execution strategy when new evidence invalidates
the current task graph, stack, parallel grouping, or integration order.

### Machine-local routing profile

Add an optional human/agent-readable machine profile at:

```text
$ROZORO_HOME/config/machine.md
```

with default path `~/.rozoro/config/machine.md`.

The file may describe harness/model availability, named account/config profiles,
no-mistakes `NM_HOME` profiles, and local preference/capacity notes. It is text
policy, not a versioned machine protocol. Runtime availability must still be
verified.

Repository policy and explicit operator requirements remain authoritative. The
machine profile describes what this machine can or prefers to run; it does not
change repository semantics or grant authority.

### Attempt and replan budget

Implementation attempts are cumulative across a lineage. A fresh Coder, branch,
worktree, resume, or revised plan does not reset the counter.

The lineage begins with an `attempt_limit` of 10 Coder attempts. Replanner receives
the current plan/task, useful failure evidence, `attempt_count`, `attempt_limit`,
and `replan_count`.

A materially revised replan increments `replan_count`, preserves
`attempt_count`, and extends `attempt_limit` by 10 up to a hard ceiling of **30
Coder attempts**.

At most **3 Replanner turns** are allowed for a lineage. The third Replanner turn
may still restructure/split/defer the work, including changing its parallel/stack
strategy, but it cannot open Coder attempts 31–40. A replan that fails to produce
a useful new direction still consumes one of the three Replanner turns so
replanning cannot become an unbounded retry loop.

This produces the normal progression:

```text
initial plan:  attempt_limit=10  replan_count=0
replan #1:     attempt_limit=20  replan_count=1
replan #2:     attempt_limit=30  replan_count=2
replan #3:     attempt_limit=30  replan_count=3
```

Replanning may happen before the current attempt ceiling is exhausted when current
evidence shows the task boundary, dependency graph, execution strategy, or
implementation direction is wrong. Watchtower must not waste remaining attempts
merely to reach the ceiling.

### No-Mistakes Runner

No-Mistakes Runner is a Rozoro crew role. It is deliberately thin:

- receive an exact committed candidate and intended no-mistakes profile;
- inspect current no-mistakes state and submit or reattach through the supported
  Git/CLI/AXI path;
- keep the run available for listening/attachment;
- report structured run ID/head/findings/gates/PR/CI/custody evidence back to
  Watchtower; and
- avoid duplicating the review/fix/test logic already owned by no-mistakes.

The no-mistakes pipeline keeps ownership of its disposable worktree, internal
pipeline agents, fixes, PR/CI work, structured gates, and recovery state.

No-mistakes model/account routing should use native tool configuration where
possible. The current upstream global config supports an `agent` value or ordered
fallback list and `agent_config` for per-agent model/effort. `NM_HOME` can select
separate repeatable global profiles.

`CLAUDE_CONFIG_DIR` is treated as a Claude harness environment setting, not a
no-mistakes YAML field. Because normal no-mistakes gates execute through a
background daemon, Rozoro must not assume that prefixing one client invocation
with `CLAUDE_CONFIG_DIR` changes an already-running daemon's Claude environment.
Machine profiles that depend on that setting must describe and verify the daemon
profile that actually receives it.

### Workset Merger

A Workset Merger owns integration **execution and reconciliation** for one workset.
It receives the current Planner/Replanner execution strategy, participating task
branches and exact heads, assurance results, no-mistakes results, target merge
policy, and current unattended state.

It reconstructs the planned dependency/stack graph against current results,
validates that the plan is still executable, integrates branches in the planned
order, identifies assurance invalidated by integration, reads no-mistakes findings
in workset context, and reports whether the next action is a local repair, replan,
more assurance, provider retry, or landing.

The merger may make mechanical integration choices inside the current strategy. If
actual evidence invalidates the dependency graph, stack/base assumption, parallel
shape, or intended order, it preserves that evidence and routes the work back to
Replanner. It does not silently redesign the workset.

The same role performs the final supported merge and required post-merge actions
when authorized. A single-task workset is the degenerate case with no stacking or
parallelism.

### `/afk`

Add an `afk` Watchtower skill. `/afk` is **ON by default**.

- ON permits an otherwise-ready Workset Merger to perform the final merge within
  existing repository policy and operator authority.
- OFF permits preparation and validation but requires operator confirmation
  immediately before the final merge mutation.

The toggle affects final merge permission only. It does not bypass protection,
grant destructive recovery authority, broaden scope, or replace product/design
judgment that still belongs to the operator.

### Policy wording

Canonical Watchtower/skill guidance is written as current behavior. Historical
policy transitions stay in ADR history rather than being expressed as warnings a
fresh Watchtower must understand before it can act.

## Consequences

- One Watchtower can build context incrementally across several projects without
  mixing project facts.
- Planner/Task Decomposer becomes the explicit owner of task graph, parallelism,
  stacking, fan-in, and intended integration order; Watchtower schedules that
  graph and Workset Merger realizes it against actual results.
- Machine-specific harness/account availability stops leaking into canonical role
  definitions.
- Implementation lineages can change direction through explicit replanning without
  resetting cost/accounting; the hard 30-Coder/3-Replanner bounds keep repair loops
  finite.
- No-mistakes execution remains push-friendly through a dedicated crew while
  no-mistakes retains semantic ownership of its pipeline.
- Workset integration gets an explicit owner without making integration difficulty
  an excuse to silently rewrite the planned execution strategy.
- Final merge authority is visible and operator-controlled through `/afk` without
  imposing confirmations on normal routing.
- The simple Merge Finisher role is replaced by the broader Workset Merger role.
- `no-mistakes-gate` is no longer a Watchtower action skill; no-mistakes work is
  dispatched to the No-Mistakes Runner crew.
- A future machine-readable routing schema can be introduced explicitly without
  pretending the initial Markdown profile is already a stable protocol.
