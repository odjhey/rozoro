---
name: no-mistakes-branch-recovery
description: >-
  Recover a branch that is stuck, divergent, or left in ambiguous custody during
  or after a no-mistakes/AXI run. This is a crew-facing No-Mistakes Runner skill:
  the Watchtower dispatches the dedicated runner with these instructions and
  judges the returned custody/evidence report.
metadata:
  execution-owner: crew
  crew-role: no-mistakes-runner
  watchtower-action: dispatch-and-pass
  derived-from:
    - docs/runbooks/no-mistakes-custody.md
    - docs/runbooks/human-gates-and-evidence.md
---

# No-mistakes branch recovery

Use this skill only for branch/custody recovery around a no-mistakes run. The
current no-mistakes/AXI structured output is authoritative. This skill packages
the recovery decision process; it does not replace or override the tool's own
instructions.

This skill is executed by the dedicated **No-Mistakes Runner crew**, not by the
Watchtower. The Watchtower decides that recovery work is needed, dispatches or
resumes that runner with these instructions, then uses the runner's exact-head
report to decide what happens next. The Watchtower must not take over branch
mutation merely because recovery is awkward.

Explicit operator instructions and repository-local rules take precedence.

## Goal

Return the affected branch to an unambiguous, clean custody state without losing
work, moving the wrong ref, or carrying stale review/test/CI evidence forward.

The normal path is unattended: diagnose, use the supported recovery action,
verify the resulting exact head, report the evidence, and return control to the
Watchtower.

## 1. Freeze competing mutations and identify custody

Before changing anything:

- identify the no-mistakes run/task and affected branch/worktree;
- determine whether the pipeline still owns the branch;
- capture the submitted head/tree and any final head/tree reported by the run;
- capture the current local branch head, upstream/remote head, PR head, and
  required CI head when they exist;
- read the current structured `branch_sync` state, especially `next_action`.

If a run is still active, do not manually edit, commit, pull, rebase, reset,
merge, push, replace refs, stash, or otherwise move the owned branch. Interact
through the supported no-mistakes/AXI control path only.

Unexpected ref movement or identity mismatch is evidence to reconcile, not a
reason to guess which head should win.

## 2. Prefer the supported recovery path

Follow the current structured `branch_sync.next_action` exactly when it names a
supported sync/recovery operation.

- Reattach or respond to the matching active run rather than starting a
  replacement.
- Use the recovery/sync action offered by no-mistakes/AXI rather than an
  equivalent-looking manual Git command.
- Observe the resulting structured state before issuing another control action.
- Do not abort or bypass a gate merely to regain the branch.

Do not translate a vague or unknown `next_action` into an improvised `git reset`,
`git stash`, `git rebase`, force-push, branch replacement, state/database edit,
or other home-grown repair.

## 3. Verify custody actually returned

After the supported recovery reaches a terminal state, verify:

- the run reports custody returned to the user/operator;
- the worktree is in the expected cleanliness state;
- the branch points at the expected exact commit/tree;
- local, remote, PR, pipeline-final, reviewed/tested, and CI identities agree
  wherever repository policy requires equality;
- no unaccounted commits or uncommitted changes were lost.

Do not treat command success, terminal idleness, or a generic `done` message alone
as proof that custody is safe.

## 4. Invalidate stale assurance after head movement

Any recovery that changes the branch head creates a new assurance boundary.
Report which attestations are stale and which checks must be repeated against the
new exact head, including independent review, testing, no-mistakes validation,
and exact-head CI when applicable.

Never claim that review/test/CI from the old head proves the recovered head.

## 5. Bounded unattended recovery

Execute the recovery without waiting for operator input when all of these hold:

- the action is explicitly supported by no-mistakes/AXI or an existing repository
  recovery policy;
- the action is bounded to the affected task/branch;
- the expected before/after heads are known;
- the action is reversible or already authorized by repository/operator policy;
- no branch-protection, secret, product-scope, or destructive-operation boundary
  is being bypassed.

Record the chosen action, evidence, resulting heads, and why it was safe in the
crew handoff/report. The Watchtower owns the subsequent routing decision.

## 6. Unsupported or ambiguous recovery

If the structured tool does not offer a supported path and repository policy does
not already define one, leave the branch untouched and report `needs-action` or
the equivalent unresolved state to the Watchtower with enough evidence for it to
file a GitHub issue. Do not invent a manual settlement recipe.

The report should contain:

- affected repository, task, branch, and PR;
- run ID and custody state;
- submitted/final/local/remote/PR heads;
- observed divergence or failure;
- supported recovery attempted and its result;
- options considered and the recommended next action;
- exact preconditions that must still hold before any future mutation;
- stop conditions if identities change; and
- review/test/no-mistakes/CI work that must be rerun afterward.

Do not copy a historical one-off settlement or CAS/reset recipe into normal
procedure merely because it worked once. If such a procedure becomes broadly
safe and desired, land it as an explicit repository policy or supported tool
operation first.

## 7. Report

Return:

- run/task and affected branch;
- custody state before recovery;
- exact heads observed;
- structured `branch_sync.next_action`;
- recovery action taken, if any;
- custody state and exact head after recovery;
- stale assurance invalidated and checks to rerun;
- unsupported-recovery issue brief for the Watchtower, if needed.
