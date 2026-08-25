---
name: adversarial-testing
description: >-
  Brief an adversarial Tester crew. Use when Watchtower is spawning a tester and
  needs to put the behavioral test contract, failure-mode coverage, exact-head
  expectations, and report shape into that crew's brief. Watchtower routes and
  judges the evidence; the dispatched crew performs the testing.
---

# Adversarial testing briefing guideline

Use this when **Watchtower is preparing the brief for an adversarial Tester
crew**. Include the applicable testing contract below together with the bounded
task, exact candidate head, acceptance criteria, and relevant prior reports.

Do not exercise repository behavior in Watchtower merely because this skill is
loaded. The dispatched tester performs the work; Watchtower consumes and routes
the returned evidence.

Explicit operator instructions and repository-local rules take precedence over this guideline.

## Test contract to brief

1. Read the task, acceptance criteria, contracts, and relevant repository rules.
2. Build scenarios from intended behavior and plausible failure modes before relying on implementation details.
3. Cover the cases that matter to the task, including as applicable:
   - happy path;
   - boundaries and invalid input;
   - retries and idempotency;
   - partial failures and cleanup;
   - state transitions;
   - concurrency or ordering;
   - integration boundaries;
   - regressions.
4. Inspect the quality of existing tests:
   - Would they fail if the implementation were wrong?
   - Are assertions strong enough?
   - Are mocks or fixtures hiding real failures?
   - Are important scenarios absent?
   - Could broken behavior still produce a green suite?
5. Prefer observable behavior: exit status, output, API behavior, persisted state, emitted events, or other externally meaningful effects. Do not treat source-text inspection as behavioral proof.
6. Do not quietly repair production code while acting as the independent tester. Return defects to the implementation owner unless Watchtower dispatches a different role later.
7. Do not run no-mistakes.

## Report shape to brief

Require:

- exact commit tested, when available;
- tests added or run;
- failures found and evidence;
- acceptance criteria with direct test evidence;
- scenarios still uncovered;
- weak or misleading existing tests;
- cases where broken behavior could still pass;
- whether each problem appears local or needs replanning;
- unresolved assumptions or decisions for the Watchtower.

A green suite means the exercised checks passed. It does not by itself prove the use case is complete.
