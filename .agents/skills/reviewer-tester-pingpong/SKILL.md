---
name: reviewer-tester-pingpong
description: >-
  Drive one primary ship crew and one independent read-only reviewer/tester crew
  through repeated fix and re-review rounds with Rozoro. Use when the operator
  wants the same implementer and reviewer retained until review is clean, CI
  passes, and an explicit merge policy is satisfied.
---

# Reviewer/tester ping-pong

Use Rozoro's project skill for command details. This skill adds the coordination
policy for a two-crew acceptance loop.

## Intake

Before dispatch, establish the task, target repository, and merge policy. Treat
the policy as an authorization boundary: `do not merge`, `merge only after
operator approval`, or `merge when clean`. If it is absent or ambiguous, default
to `do not merge` and report that assumption.

Assign two stable task IDs:

- **Primary:** owns investigation, implementation, tests, commits, pushes, and PR
  updates. This is the only crew allowed to change the deliverable.
- **Reviewer:** independently reviews and tests the primary's current result. Its
  brief must say read-only: do not edit, commit, push, merge, or repair anything.

Use `rozoro start <name> --body <file> --cwd <repo>` for each new crew. Start the
primary first; start the reviewer once there is a concrete branch, commit, or PR
to inspect. Give the reviewer the acceptance criteria and target pointer, but do
not prime it with the primary's conclusions.

## Loop

1. Wait for the primary's handoff, verify its artifact pointer, and send that
   target to the reviewer.
2. Require the reviewer to inspect the diff and run appropriate tests. It must
   return actionable findings with evidence, or explicitly report a clean review
   and the tests it ran.
3. Send every finding to the same primary with `rozoro send <primary-id> ...`.
   Do not fix findings in the driver or start a replacement implementer.
4. When the primary reports fixes, send the updated target and fix summary to the
   same reviewer with `rozoro send <reviewer-id> ...`. Require regression review,
   not just confirmation that the named lines changed.
5. Repeat until the reviewer reports no actionable findings and required CI is
   passing on the current commit. A green older commit does not count.

Read each crew's durable handoff with `rozoro status <id>` after actionable
events. Keep both crews live throughout the loop so `rozoro send` preserves their
conversation context. If one was already reaped, use `rozoro resume`, never a
cold replacement, and continue with the same task ID. Do not teardown either crew
until acceptance and the merge-policy outcome are recorded.

## Finish

Before declaring success, verify all of these independently:

- the primary's current commit is the commit the reviewer approved;
- the reviewer reports no remaining actionable findings;
- required CI checks for that commit pass; and
- the explicit merge policy was followed.

Only merge when the policy authorizes it. If approval is required, stop cleanly
and ask for it. If merging is forbidden, leave the reviewed result unmerged. Then
report the branch/PR, reviewed commit, tests and CI, review outcome, and merge
state; reap crews only after the result is accepted.
