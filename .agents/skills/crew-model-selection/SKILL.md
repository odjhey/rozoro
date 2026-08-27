---
name: crew-model-selection
description: >-
  Choose the task kind, harness, model, reasoning effort, and dispatch path for a
  fresh Rozoro crew. Use immediately before Watchtower spawns planning, coding,
  review, testing, no-mistakes, workset-merging, or Quick Crew work.
---

# Crew model selection

Use this immediately before every **fresh** Rozoro crew dispatch.

## 1. Choose the task kind

Read `templates/watchtower-crew-dispatch-guidelines.md` for current role intent
and dispatch semantics. Concrete model/effort assignments per role come from
durable operator policy under `$ROZORO_HOME/watchtower-policies/` (for example
`roles-and-models.md`), not from the repository template (ADR-0012).

Choose among the roles that fit the next bounded action:

- Task Decomposer / Planner
- Coder
- Reviewer
- Tester
- Escalation Replanner
- No-Mistakes Runner
- Workset Merger
- Quick Scout / Quick Coder when `quick-crew-routing` qualifies

For new implementation work, Planner is the normal bridge from raw intent to a
bounded **workset execution strategy** when scope, dependencies, acceptance
criteria, parallelism, stacking, fan-out/fan-in, or integration order are not
already clear.

Planner decides which bounded tasks may run concurrently, which must be sequential
or stacked, their dependency/base relationships, and intended integration order.
Watchtower dispatches according to that strategy rather than independently grading
tasks into parallel or serial execution.

A normal repair turn stays with the existing Coder while the task boundary still
holds. Use Replanner when evidence requires changing the task graph, parallel/
stacking strategy, dependencies, or implementation direction.

Use a Workset Merger when candidate tasks need the current Planner/Replanner
strategy executed against actual branches, when no-mistakes results need to be
interpreted against the integrated workset, or when an accepted workset is ready
for landing/post-merge work. The merger validates and realizes the plan; it does
not silently replace the Planner's execution strategy.

Use a No-Mistakes Runner when an exact committed candidate is ready to enter or
reattach to the configured no-mistakes pipeline.

## 2. Resolve this machine's execution target

If `$ROZORO_HOME/config/machine.md` exists, read the relevant availability and
preference notes. The default location is `~/.rozoro/config/machine.md`.

Treat that file as machine-local routing input, not semantic truth. Verify the
selected harness/profile can actually run. Keep these identities separate:

- task kind / role;
- harness or launcher;
- account/profile;
- model ID;
- reasoning effort; and
- optional fast/priority tier.

Role assignments from the durable operator policy
(`$ROZORO_HOME/watchtower-policies/`) are the starting point. When the assigned
target is unavailable, or no durable policy exists on this machine, select a
compatible available target described by the machine profile or current Rozoro
crew presets. Explicit operator requirements and repository-local constraints
take precedence.

For no-mistakes, the selected Rozoro crew model is the model used by the thin
No-Mistakes Runner itself. The no-mistakes pipeline's own agent/model/fallback is
resolved by its repository/global configuration and selected `NM_HOME` profile.

## 3. Write the task-specific brief

Watchtower writes the brief in its own words. Prefer:

**intent + pointer + only the context, constraints, and evidence this crew needs**

Useful role-specific context includes:

- Planner: source request, operator constraints, and expected workset outcome. Ask
  for bounded tasks plus dependencies, parallel groups, stacks/sequences, fan-in,
  and intended integration order where applicable.
- Coder: bounded task/repair finding and acceptance source, including the task's
  position/base in the workset when the plan makes that relevant.
- Reviewer/Tester: exact candidate head and task/acceptance pointer.
- Replanner: current workset/task plan, failed evidence, current execution
  strategy, and cumulative attempt/replan counters.
- No-Mistakes Runner: repository/workset identity, exact candidate head/base,
  intended no-mistakes profile when one is known, and the requested submit/attach
  behavior.
- Workset Merger: current Planner/Replanner execution strategy, participating task
  branches/heads, assurance/no-mistakes results, target branch/PR policy, and
  current `/afk` state.
- Quick Crew: the exact narrow action plus its stop/escalation boundary.

The crew can read repository-local rules and inspect the repository from `--cwd`;
do not duplicate material that is already discoverable there unless it is needed
to disambiguate this turn.

## 4. Follow-up versus fresh crew

Use `./bin/rozoro send` when the next turn belongs to the same live task and role.
Run fresh selection when Watchtower intentionally changes task kind or replaces the
active crew, for example Planner -> parallel/stacked Coders, Coder -> Reviewer,
candidate -> No-Mistakes Runner, or planned candidate set -> Workset Merger.

If current policy or machine availability is ambiguous, report the ambiguity and
choose the safest usable target that preserves the requested role boundary.
