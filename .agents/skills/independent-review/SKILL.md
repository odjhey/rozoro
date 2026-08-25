---
name: independent-review
description: >-
  Perform an independent correctness review of a software change at an exact
  commit. Use when asked to review implementation against its task, contracts,
  surrounding code, compatibility requirements, and acceptance criteria without
  quietly editing production code.
metadata:
  derived-from: docs/runbooks/role-separated-delivery.md,templates/watchtower-crew-dispatch-guidelines.md
---

# Independent review

Review the implementation as a separate assurance role.

Explicit operator instructions and repository-local rules take precedence over this skill. Do not claim independence if you authored the implementation being reviewed.

## Review procedure

1. Record the exact commit being reviewed. If the head changes, the previous review does not automatically apply to the new head.
2. Read the task, acceptance criteria, relevant contracts, and repository rules before judging the change.
3. Inspect outside the diff when surrounding behavior is needed to determine correctness.
4. Evaluate behavior, compatibility, state transitions, failure handling, regressions, and scope. A green test suite is evidence, not proof.
5. Separate concrete defects from optional cleanup, style preferences, and speculative redesign.
6. Do not quietly fix production code while acting as the independent reviewer. Return findings to the implementation owner unless the operator explicitly changes your role.

## Report

Include:

- verdict;
- exact commit reviewed;
- concrete findings with evidence;
- affected contract, invariant, requirement, or acceptance criterion;
- impact of each finding;
- correction required;
- whether each problem appears local or needs replanning;
- checks or evidence inspected;
- unresolved assumptions or human decisions.

If no blocking defect is found, say what was actually inspected. Do not turn absence of findings into a claim that unreviewed surfaces are correct.
