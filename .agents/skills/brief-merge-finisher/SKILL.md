---
name: brief-merge-finisher
description: >-
  Brief a Merge Finisher crew to land an already-approved candidate and perform
  required post-merge verification. Use when Watchtower has decided the candidate
  has sufficient pre-merge evidence and needs a crew to execute the supported
  merge path, capture the actual landed commit, check post-merge state, and report
  any delivery failure without quietly fixing production code.
---

# Merge finisher briefing guideline

Use this when **Watchtower is preparing the brief for a Merge Finisher crew**.
The candidate should already have the pre-merge evidence required by repository
policy. Watchtower decides that landing may proceed; the dispatched crew performs
the repository/provider mutations and reports the resulting exact identities.

Do not merge or perform post-merge repository work in Watchtower merely because
this skill is loaded.

Explicit operator instructions, branch protection, and repository-local delivery
rules take precedence over this guideline.

## Inputs to include in the brief

Include the smallest complete landing packet:

- repository and pull request;
- expected PR/candidate head;
- exact reviewed/tested/no-mistakes head identities that must still apply;
- required pre-merge checks and their expected state;
- allowed merge method or repository merge policy;
- required post-merge checks, release/deploy observation, or cleanup that belongs
  to this task; and
- any explicit stop conditions or exclusions.

Do not ask the Merge Finisher to reconstruct product intent or redesign the
change.

## Pre-merge contract to brief

Before mutating anything, require the crew to:

1. fetch the current PR/head and compare it with the expected candidate head;
2. confirm required review/test/no-mistakes/CI evidence still applies to that exact
   head;
3. confirm the PR is mergeable through the repository's supported path and that
   required protections/checks are satisfied; and
4. stop without merging if the head moved, evidence is stale, required checks are
   missing/failing, mergeability changed, or the requested merge would bypass
   repository policy.

A stale or mismatched head is a routing result, not permission to regenerate
assurance inside the Merge Finisher role.

## Merge contract to brief

- Use the repository/provider-supported merge path and the allowed merge method.
- Do not bypass branch protection, force-update refs, disable checks, or widen
  permissions merely to make the merge succeed.
- Do not edit production code while acting as Merge Finisher.
- Capture the actual merge commit (or equivalent landed identity) returned by the
  provider; do not infer it from the pre-merge PR head.
- If the merge races with another head change or provider state changes, stop and
  report the exact current state instead of retrying destructively.

## Post-merge contract to brief

After a successful merge, perform the post-merge activities required by the task
or repository policy, for example:

- verify required CI/checks on the actual merge commit;
- observe required release/deploy/publication state when that is part of the
  repository's normal delivery contract;
- verify the PR is closed/merged at the expected landed identity;
- verify the target branch points at the expected merge result where applicable;
- perform branch/worktree cleanup only when repository policy explicitly makes it
  part of normal landing; and
- collect durable links/identities needed for the final Watchtower decision.

Do not treat a successful merge command as proof that post-merge delivery is
healthy.

If a post-merge check fails, do not quietly implement a repair or roll back unless
an existing repository/operator policy explicitly authorizes that exact action.
Report the failure to Watchtower so it can route a coder, replanner, or other
appropriate task kind.

## Report shape to brief

Require:

- pre-merge expected head and actual PR head checked;
- pre-merge evidence/checks verified;
- merge method/path used;
- provider merge result;
- actual merge/landed commit identity;
- post-merge checks/actions performed and their exact evidence;
- cleanup performed, if any;
- any stale evidence, merge blocker, race, or post-merge failure;
- whether the result is fully landed/healthy or needs another routed task; and
- links or identifiers Watchtower needs for its final delivery record.

The Merge Finisher reports delivery facts. Watchtower remains the judgment layer
that decides whether the overall task is complete.