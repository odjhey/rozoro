# Role-separated delivery

Use role separation when a change needs independent assurance or controlled publication.

## Roles

- **Decomposer/planner:** bounds scope, contracts, dependencies, acceptance criteria, and ambiguity. It does not implement.
- **Coder:** implements the bounded task and behavioral tests. It does not certify its own work or control no-mistakes.
- **Reviewer:** independently evaluates correctness, contracts, compatibility, and scope at an exact commit. It does not quietly edit production code.
- **Tester:** independently exercises behavior, failure modes, weak-test risks, and acceptance criteria at an exact commit. It does not quietly fix findings.
- **Replanner:** resolves non-converging scope or contract conflicts and supplies a revised bounded task. It does not implement.
- **No-mistakes runner:** alone controls the pipeline for its assigned branch. It is not the coder, reviewer, tester, or merger.
- **Human merger/operator:** owns product decisions, exceptional authority, and merge approval when required.

A small task may omit roles when the operator and repository policy permit it. Never imply independence where the same actor performed both sides.

## Flow

1. Bound the task and decision authority.
2. Implement and commit on an isolated feature branch.
3. Have independent review and testing name the exact commit inspected.
4. Return ordinary findings to the coder in a batch. Re-run review/test on the new exact commit.
5. Replan rather than loop when findings expose a contract conflict or scope change.
6. After approval, hand the clean committed branch to the dedicated pipeline runner.
7. If the pipeline changes the head, repeat any exact-head assurance required by repository policy.
8. Leave merge and product approval to their authorized owner.

## Reports

Keep the lifecycle handoff fields unchanged. Roles may additionally report `attempt_count` and `caused_by` as ordinary report metadata; these fields do not alter Rozoro verdict parsing or lifecycle semantics.

Reports should name: scope, checks, findings, blockers, assumptions, exact commit, whether a correction is local or needs replanning, and unresolved human decisions.
