---
name: delivery-evidence
description: >-
  Reconcile exact-head review, test, no-mistakes, CI, integration, publication,
  and delivery evidence. Use when Watchtower or a Workset Merger must decide what
  evidence is current and what action should run next.
---

# Delivery evidence

Use exact identities. A verdict is useful only for the candidate it actually
examined.

## Build the evidence set

For a workset, retain:

1. **Intent and prerequisites** — target outcome, dependency/stacking constraints,
   repository policy, required checks, and the Planner's assurance map (judgment
   questions, evidence owners, invalidating change classes) when one exists.
2. **Candidate identities** — task branches/heads, integrated workset head, PR
   head, and actual landed identity.
3. **Assurance** — reviewer/tester attestations, no-mistakes run IDs/outcomes,
   exact-head CI, and relevant artifacts.
4. **Decision** — what evidence is current, what became stale, which judgment
   questions are affected, and the minimum next checks — the evidence deficits —
   now justified. Route those deficits only; a change with no affected judgment
   question justifies no redundant Reviewer/Tester rerun, and an apparently
   small change earns no skipped check its affected questions require.

Green CI or an agent verdict is one piece of evidence, not a substitute for
matching the exact head and required scope.

## Integration changes evidence

The Workset Merger owns dependency/stacking order and integration mutations.
Whenever integration creates a new head, compare that head with every assurance
artifact required by repository policy. Mark mismatched evidence stale and route
the new head through the assurance that actually applies.

Any candidate-changing action requires the named-owner changed-head
reconciliation before post-gate Reviewer/Tester judgment is dispatched for the
new head. Missing or incomplete reconciliation fails closed: hold judgment
dispatch and readiness until it exists.

No-mistakes findings whose meaning depends on the integrated workset should be
read by the Workset Merger alongside the plan/dependency graph and other crew
results.

## Final merge authority

Evidence readiness and merge authority are separate questions.

Use the `afk` skill for final merge permission:

- **`/afk on` (default):** an otherwise-ready Workset Merger may land within
  existing repository/operator authority.
- **`/afk off`:** the merger prepares the exact proposed landing and asks the
  operator immediately before the final merge mutation.

Neither state bypasses branch protection, expands scope, grants destructive
recovery authority, or overrides repository-local policy.

## Missing or conflicting evidence

When evidence is insufficient or contradictory, preserve the safe current state
and route the smallest action that can resolve it: another review/test/gate,
Coder repair, Replanner turn, provider retry, or operator decision when authority
is genuinely required.

Independent worksets may continue while one workset waits.

## Report

Return enough for the next role to act without reconstructing the whole history:

- project/workset identity;
- exact heads compared;
- current and stale assurance;
- dependency/integration state when relevant;
- decision and next route;
- current `/afk` state when landing is involved; and
- unresolved authority or provider blockers.
