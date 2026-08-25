---
name: brief-reviewer
description: >-
  Brief an independent Reviewer crew for an exact software head. Use when
  Watchtower is spawning a fresh reviewer and needs to put the correctness-review
  contract, exact-head requirements, and report shape into that crew's brief.
  Watchtower routes and judges the report; the dispatched crew performs review.
---

# Reviewer briefing guideline

Use this when **Watchtower is preparing the brief for an independent Reviewer
crew**. Include the applicable review contract below together with the bounded
task, exact candidate head, acceptance criteria, and relevant prior evidence.

Do not review repository code in Watchtower merely because this skill is loaded.
The dispatched reviewer performs the independent review; Watchtower consumes and
routes its report.

Explicit operator instructions and repository-local rules take precedence over this guideline.

## Review contract to brief

1. Record the exact commit being reviewed. If the head changes, the previous review does not automatically apply to the new head.
2. Read the task, acceptance criteria, relevant contracts, and repository rules before judging the change.
3. Inspect outside the diff when surrounding behavior is needed to determine correctness.
4. Evaluate behavior, compatibility, state transitions, failure handling, regressions, and scope. A green test suite is evidence, not proof.
5. Separate concrete defects from optional cleanup, style preferences, and speculative redesign.
6. Do not quietly fix production code while acting as the independent reviewer. Return findings to the implementation owner unless Watchtower explicitly dispatches a different role later.
7. Do not run no-mistakes.

## Report shape to brief

Require:

- verdict;
- exact commit reviewed;
- concrete findings with evidence;
- affected contract, invariant, requirement, or acceptance criterion;
- impact of each finding;
- correction required;
- whether each problem appears local or needs replanning;
- checks or evidence inspected;
- unresolved assumptions or decisions for the Watchtower.

If no blocking defect is found, require the reviewer to say what was actually inspected. Absence of findings is not proof for unreviewed surfaces.
