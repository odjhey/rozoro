---
name: adversarial-testing
description: >-
  Test a software change as an independent adversarial tester. This is a
  crew-facing assurance role: the Watchtower dispatches a tester with these
  instructions included in the crew brief rather than exercising repository
  behavior itself.
metadata:
  execution-owner: crew
  crew-role: tester
  watchtower-action: dispatch-and-brief
  derived-from: docs/runbooks/role-separated-delivery.md,templates/watchtower-crew-dispatch-guidelines.md
---

# Adversarial testing

Derive tests from the use case and contracts, not only from the implementation.

This skill is executed by a **crew member**, not by the Watchtower. The
Watchtower dispatches the tester with the applicable testing instructions,
bounded task, and relevant prior reports included in the crew brief, then judges
the returned evidence.

Explicit operator instructions and repository-local rules take precedence over this skill. Record the exact commit tested when commit identity is available.

## Test procedure

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
6. Do not quietly repair production code while acting as the independent tester. Return defects to the implementation owner unless the Watchtower explicitly changes your role.

## Report

Include:

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
