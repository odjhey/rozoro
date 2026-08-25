---
name: attempt-budget
description: >-
  Enforce Watchtower's ten-coder-attempt lineage budget from durable task/session/
  turn history. Use when routing a non-converging implementation lineage, deciding
  whether another coder attempt is allowed, or deferring exhausted work.
---

# Attempt budget and deferral

Use existing durable task/session/turn history as the source of attempt accounting.

## Counting attempts

Each implementation lineage has a budget of **10 coder attempts**.

Count a coder attempt when a Coder implementation turn changes the candidate head
or deliberately validates that head as its implementation attempt.

Planner, Reviewer, Tester, Replanner, No-Mistakes Runner, Workset Merger, and
Watchtower turns do not themselves consume coder attempts. Integration/landing
work consumes a coder attempt only when a finding is routed back into a new Coder
implementation turn.

A replan, fresh coder session, new branch, resumed task, later revisit, or merger
retry does not reset the lineage count. Preserve attribution through durable task
history; `attempt_count` and `caused_by` may be used as report metadata.

## Attempt 10

Attempt 10 may complete its normal assurance and integration sequence: review,
testing, no-mistakes, workset integration, exact-head CI, landing, and post-merge
verification as applicable.

If that sequence accepts and lands the candidate, complete normally.

If the evidence requires another Coder repair, the implementation budget is
exhausted and the lineage is deferred rather than starting attempt 11.

## Deferral

Record a durable deferral summary with:

- project/workset/task lineage identity;
- current branch/PR and exact candidate head;
- current review/test/no-mistakes/integration/delivery state;
- blocking findings;
- approaches already attempted;
- relevant dependencies or external blockers;
- the evidence that would require another coder attempt; and
- an objective resumption trigger.

Continue other runnable independent work.

Reconsider deferred work when the runnable queue is empty, when materially new
information/tooling changes the premise, or when the operator reprioritizes it.
Retain the prior attempt history when reconsidering.

## Routing consequences

- Quick Coder is for the bounded fast path, not repeated repair loops.
- Replanning may happen before budget exhaustion when scope/dependency/contract
  evidence changes the task boundary.
- A Workset Merger may retry a provider/transient integration or landing operation
  when repository/operator policy permits and the candidate/evidence remains
  applicable.
- Integration or no-mistakes findings that require code changes route to
  Coder/Replanner and therefore participate in the same lineage budget.
- Budget exhaustion of one lineage does not block unrelated worksets.
