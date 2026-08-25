---
name: attempt-budget
description: >-
  Enforce Watchtower's cumulative coder-attempt and replan budget from durable
  task/session/turn history. Use when routing a non-converging implementation
  lineage, deciding whether another Coder or Replanner turn is allowed, or
  deferring exhausted work.
---

# Attempt and replan budget

Use existing durable task/session/turn history as the source of accounting. The
budget belongs to the implementation lineage, not to an individual crew session,
branch, or plan document.

## Counters

Track these values across the lineage:

- `attempt_count` — cumulative Coder implementation attempts already used;
- `replan_count` — cumulative Escalation Replanner turns already used;
- `attempt_limit` — current Coder ceiling opened by planning/replanning; and
- `caused_by` — the finding/evidence that caused the current Coder or Replanner
  turn when useful.

Do not reset either counter when dispatching a fresh Coder, creating a new branch,
resuming a task, revisiting deferred work, or producing a revised plan.

## Coder attempts

A new lineage starts with:

```text
attempt_count: 0
replan_count: 0
attempt_limit: 10
```

Count a Coder attempt when a Coder implementation turn changes the candidate head
or deliberately validates that head as its implementation attempt.

Planner, Reviewer, Tester, Replanner, No-Mistakes Runner, Workset Merger, and
Watchtower turns do not themselves consume Coder attempts. Integration/landing
work consumes a Coder attempt only when a finding is routed back into a new Coder
implementation turn.

## Replanning extends the lineage

Replanning is the bounded mechanism for extending a non-converging implementation
lineage instead of silently resetting its attempt counter.

A Replanner turn should receive the current plan/task, useful evidence from failed
attempts, `attempt_count`, `replan_count`, and the current `attempt_limit`.

When the Replanner produces a materially revised executable plan:

1. increment `replan_count`;
2. preserve `attempt_count` exactly as-is;
3. extend `attempt_limit` by another 10 Coder attempts, up to the hard lineage
   ceiling of **30 Coder attempts**; and
4. record what changed in the plan and which evidence justified the extension.

Example progression:

```text
initial plan:  replan_count=0  attempt_limit=10
replan #1:     replan_count=1  attempt_limit=20
replan #2:     replan_count=2  attempt_limit=30
replan #3:     replan_count=3  attempt_limit=30
```

A lineage may use at most **3 Replanner turns**. The third Replanner turn is still
useful for final restructuring, dependency correction, or deciding that the work
should be split/deferred, but the hard Coder ceiling remains 30; it does not open
attempts 31–40.

Replanning may happen before the current attempt limit is exhausted when evidence
shows the task boundary, dependency graph, or implementation direction is wrong.
Do not burn remaining attempts merely to reach the boundary before replanning.

A Replanner turn that only restates the same plan or fails to produce a materially
usable revised direction still increments `replan_count`; it does not create an
unbounded retry loophole.

## At a Coder ceiling

When `attempt_count == attempt_limit`, finish any assurance already running for
that exact candidate: review, testing, no-mistakes, workset integration,
exact-head CI, landing, and post-merge verification as applicable.

If that evidence accepts and lands the candidate, complete normally.

If another Coder repair is required:

- if `attempt_limit < 30` and `replan_count < 3`, route the accumulated evidence to
  the Escalation Replanner rather than starting another Coder directly;
- if the hard 30-attempt ceiling is reached, or 3 replans have already been used,
  defer/escalate the lineage instead of creating another implementation attempt.

Never grant a fresh ten attempts merely because the Coder, branch, worktree, or
plan document changed.

## Deferral

Record a durable deferral summary with:

- project/workset/task lineage identity;
- `attempt_count`, `attempt_limit`, and `replan_count`;
- current branch/PR and exact candidate head;
- current review/test/no-mistakes/integration/delivery state;
- blocking findings;
- approaches and planning directions already attempted;
- relevant dependencies or external blockers;
- the evidence that would require another Coder attempt or another replan; and
- an objective resumption trigger.

Continue other runnable independent work.

Reconsider deferred work when the runnable queue is empty, when materially new
information/tooling changes the premise, or when the operator reprioritizes it.
Retain the prior counters when reconsidering. New evidence does not silently reset
the lineage budget.

## Routing consequences

- Quick Coder is for the bounded fast path, not repeated repair loops.
- Replanning is allowed before exhaustion when scope/dependency/contract evidence
  changes the task boundary or the implementation direction is not converging.
- A Workset Merger may retry a provider/transient integration or landing operation
  when repository/operator policy permits and the candidate/evidence remains
  applicable; that is not a Coder attempt.
- Integration or no-mistakes findings that require code changes route to
  Coder/Replanner and therefore participate in the same cumulative lineage budget.
- Budget exhaustion of one lineage does not block unrelated worksets.
