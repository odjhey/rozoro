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

Read `templates/watchtower-crew-dispatch-guidelines.md` for current role intent and
preferred model/effort defaults.

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
bounded coder task when scope, dependencies, acceptance criteria, or stacking are
not already clear. A normal repair turn stays with the existing coder while the
task boundary still holds.

Use a Workset Merger when completed or candidate tasks need dependency-aware
integration, when stacked branches must be ordered, when no-mistakes results need
to be interpreted against the integrated workset, or when an accepted workset is
ready for landing/post-merge work.

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

Preferred role defaults from the dispatch guide are the starting point. When the
preferred target is unavailable, select a compatible available target described by
the machine profile or current Rozoro crew presets. Explicit operator requirements
and repository-local constraints take precedence.

For no-mistakes, the selected Rozoro crew model is the model used by the thin
No-Mistakes Runner itself. The no-mistakes pipeline's own agent/model/fallback is
resolved by its repository/global configuration and selected `NM_HOME` profile.

## 3. Write the task-specific brief

Watchtower writes the brief in its own words. Prefer:

**intent + pointer + only the context, constraints, and evidence this crew needs**

Useful role-specific context includes:

- Planner: source request and operator constraints.
- Coder: bounded task/repair finding and acceptance source.
- Reviewer/Tester: exact candidate head and task/acceptance pointer.
- No-Mistakes Runner: repository/workset identity, exact candidate head/base,
  intended no-mistakes profile when one is known, and the requested submit/attach
  behavior.
- Workset Merger: workset intent, planner/decomposer result when available,
  participating task branches/heads, dependency clues, assurance/no-mistakes
  results, target branch/PR policy, and current `/afk` state.
- Quick Crew: the exact narrow action plus its stop/escalation boundary.

The crew can read repository-local rules and inspect the repository from `--cwd`;
do not duplicate material that is already discoverable there unless it is needed
to disambiguate this turn.

## 4. Follow-up versus fresh crew

Use `./bin/rozoro send` when the next turn belongs to the same live task and role.
Run fresh selection when Watchtower intentionally changes task kind or replaces the
active crew, for example Planner -> Coder, Coder -> Reviewer, candidate ->
No-Mistakes Runner, or several completed tasks -> Workset Merger.

If current policy or machine availability is ambiguous, report the ambiguity and
choose the safest usable target that preserves the requested role boundary.
