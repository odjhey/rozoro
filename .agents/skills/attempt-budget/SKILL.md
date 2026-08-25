---
name: attempt-budget
description: >-
  Enforce Watchtower's ten-coder-attempt lineage budget from durable task/session/
  turn history. Use when routing a non-converging implementation lineage, deciding
  whether another coder attempt is allowed, or deferring exhausted work while
  other runnable tasks remain.
---

# Attempt budget and deferral

Use this in **Watchtower while routing implementation retries and deferred work**.
Use the existing task/session/turn history as the source of attempt accounting.
Do not add or assume a separate persisted attempt lifecycle merely to enforce the
budget.

## Counting attempts

Each implementation lineage has a budget of **10 coder attempts**.

Count a coder attempt when a coder implementation turn changes the candidate
head or deliberately validates that head as its implementation attempt.
Reviewer, tester, replanner, Merge Finisher, Watchtower, and no-mistakes turns do
not themselves consume coder attempts.

A replan, fresh coder, new branch, resumed task, later revisit, merge attempt, or
post-merge verification does not reset or increment the coder-attempt count unless
it results in a new Coder implementation turn. Preserve attribution through the
durable task history and use `attempt_count` / `caused_by` as report metadata where
available; they are not Rozoro lifecycle fields.

## Attempt 10

Attempt 10 is allowed to complete its normal assurance and delivery sequence.
Review, testing, CI, applicable no-mistakes work, Merge Finisher landing, and
post-merge verification may still run to determine whether that candidate is
acceptable and fully delivered.

If that sequence accepts and lands the candidate, continue normal completion.

If review/testing/gating/merge/post-merge evidence instead requires another coder
repair, **do not start coder attempt 11**. The implementation budget is exhausted.

## Deferral

Budget exhaustion defers the lineage; it does not stop the Watchtower.

Record a durable deferral summary containing at least:

- task/lineage identity;
- current PR/branch and exact candidate head;
- current check/review/test/gate/delivery state;
- blocking findings;
- approaches already attempted;
- relevant dependencies or external blockers;
- the evidence that caused the requested attempt 11; and
- an objective resumption trigger.

Then continue other runnable independent work.

**Deferred work is reconsidered when the runnable queue is empty**, or earlier
when materially new information/tooling changes the premise or an explicit
operator instruction reprioritizes it. Do not continuously churn deferred work
while other runnable tasks exist.

When a deferred lineage is reconsidered, retain the full prior attempt history.
Reconsideration does not silently grant attempts 11+; materially new information
must justify a new bounded decision recorded by the Watchtower.

## Routing consequences

- Quick Coder is never used for repeated repair attempts.
- Replanning can happen before budget exhaustion when loops expose a scope or
  contract problem, but replanning does not reset the coder-attempt count.
- Merge Finisher may retry a purely provider/transient landing operation only when
  repository/operator policy permits it and the exact candidate/evidence remains
  unchanged; that is still not a coder attempt.
- If merge/post-merge evidence requires code changes, route to Coder/Replanner and
  apply the existing coder-attempt budget.
- No-mistakes custody, branch protection, exact-head evidence, and standard
  assurance requirements remain unchanged.
- If an exhausted lineage needs a decision or unsupported mutation, file or
  update the appropriate GitHub issue rather than blocking unrelated work.
