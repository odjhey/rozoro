# Role-separated delivery

Use role separation when a change needs independent assurance or controlled publication.

## Roles and gates

- **Decomposer/planner:** bounds scope, contracts, dependencies, acceptance criteria, and ambiguity. It does not implement.
- **Coder:** implements the bounded task and behavioral tests. It does not certify its own work or run no-mistakes.
- **Reviewer:** independently evaluates correctness, contracts, compatibility, and scope at an exact commit. It does not quietly edit production code.
- **Tester:** independently exercises behavior, failure modes, weak-test risks, and acceptance criteria at an exact commit. It does not quietly fix findings.
- **Replanner:** resolves non-converging scope or contract conflicts and supplies a revised bounded task. It does not implement.
- **No-mistakes gate:** external pipeline owned by no-mistakes. Watchtower submits/reattaches the run, drives supported gates, reconciles exact-head/custody evidence, and routes findings. It is not a Rozoro crew role.
- **Merge Finisher:** lands an already-authorized candidate through the repository/provider-supported merge path, captures the actual merge commit, performs required post-merge checks/actions, and reports exact delivery evidence. It does not quietly fix implementation defects or regenerate stale assurance.
- **Watchtower/operator policy:** decides whether current evidence is sufficient to enter the no-mistakes gate, whether a candidate is eligible to land, and what to route when a gate/merge/post-merge step fails.

A small task may omit roles when the operator and repository policy permit it. Never imply independence where the same actor performed both sides.

## Flow

1. Bound the task and decision authority.
2. Implement and commit on an isolated feature branch.
3. Have independent review and testing name the exact commit inspected.
4. Return ordinary findings to the coder in a batch. Re-run review/test on the new exact commit.
5. Replan rather than loop when findings expose a contract conflict or scope change.
6. When the clean committed candidate is ready for no-mistakes, Watchtower invokes `no-mistakes-gate` directly instead of spawning another crew.
7. no-mistakes owns its pipeline worktree, internal agents, branch custody, fixes, PR/CI work, and structured recovery state. Watchtower owns submission/reattachment, bounded gate decisions, and final evidence reconciliation.
8. If no-mistakes changes the head, repeat any exact-head assurance required by repository policy.
9. Route local no-mistakes findings back to the coder; route contract/scope failures to replanning.
10. When Watchtower decides the candidate has the required landing evidence, dispatch a fresh **Merge Finisher** with `brief-merge-finisher` instead of merging in Watchtower.
11. The Merge Finisher revalidates the exact PR head/evidence, performs the supported merge, records the actual landed commit, and completes required post-merge verification/cleanup.
12. Route merge blockers or post-merge implementation failures back to the appropriate coder/replanner task kind. Watchtower reconciles the final landed identity and decides whether delivery is complete.

## Reports

Keep the lifecycle handoff fields unchanged. Roles may additionally report `attempt_count` and `caused_by` as ordinary report metadata; these fields do not alter Rozoro verdict parsing or lifecycle semantics.

Crew reports should name: scope, checks, findings, blockers, assumptions, exact commit, whether a correction is local or needs replanning, and unresolved decisions.

The no-mistakes gate record should name the submitted and final exact heads, run ID/outcome, PR/CI evidence, custody state, supported recovery action, and the routing consequence of any findings.

The Merge Finisher report should name the expected/current PR head, pre-merge evidence checked, merge method/path, provider result, actual merge/landed commit, required post-merge checks/actions, cleanup performed, and any delivery failure that needs another routed task.