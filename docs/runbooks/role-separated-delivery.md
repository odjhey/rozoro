# Role-separated delivery

Use role separation when a change needs independent assurance or controlled publication.

## Roles and gates

- **Decomposer/planner:** turns raw intent into bounded scope, contracts, dependencies, acceptance criteria, and explicit ambiguity. It does not implement.
- **Coder:** implements the bounded task and behavioral tests. It does not certify its own work or run no-mistakes.
- **Reviewer:** independently evaluates correctness, contracts, compatibility, and scope at an exact commit. It does not quietly edit production code.
- **Tester:** independently exercises behavior, failure modes, weak-test risks, and acceptance criteria at an exact commit. It does not quietly fix findings.
- **Replanner:** resolves non-converging scope or contract conflicts and supplies a revised bounded task. It does not implement.
- **No-mistakes gate:** external pipeline owned by no-mistakes. Watchtower submits/reattaches the run, drives supported gates, reconciles exact-head/custody evidence, and routes findings. It is not a Rozoro crew role.
- **No-mistakes Observatory:** untracked Herdr visualization surface for active run graphs. It is not a crew, task, custody owner, or control plane.
- **Merge Finisher:** lands an already-authorized candidate through the repository/provider-supported merge path, captures the actual landed identity, performs required post-merge checks/actions, and reports delivery evidence. It does not quietly fix implementation defects or regenerate stale assurance.
- **Watchtower/operator policy:** decides what task kind runs next, when the candidate is ready for no-mistakes, when landing is allowed, and what to route when a gate/merge/post-merge step fails.

A small task may omit roles when repository/operator policy permits it. Never imply independence where the same actor performed both sides.

## Flow

1. For raw implementation intent, normally dispatch Planner first unless the task is already genuinely bounded or clearly qualifies for Quick Coder.
2. Implement and commit on an isolated feature branch.
3. Have independent review and testing name the exact commit inspected.
4. Return ordinary findings to the coder. Re-run required assurance on the new exact commit.
5. Replan rather than loop when findings expose a contract conflict or scope change.
6. When the clean committed candidate is ready for no-mistakes, Watchtower invokes `no-mistakes-gate` directly instead of spawning another crew.
7. no-mistakes owns its pipeline worktree, internal agents/model selection, branch custody, fixes, PR/CI work, and structured recovery state. Watchtower owns submission/reattachment, bounded gate decisions, and final evidence reconciliation.
8. Once the run exists, expose its graph in the dedicated no-mistakes Observatory. Keep structured no-mistakes/AXI state authoritative.
9. If no-mistakes changes the head, repeat any exact-head assurance required by repository policy.
10. Route local no-mistakes findings back to Coder; route contract/scope failures to Replanner.
11. When Watchtower decides the candidate has the required landing evidence, dispatch a fresh **Merge Finisher** instead of merging in Watchtower.
12. The Merge Finisher revalidates the exact PR head/evidence, performs the supported merge, records the actual landed identity, and completes required post-merge verification/cleanup.
13. Route merge blockers or post-merge implementation failures back to the appropriate Coder/Replanner task kind. Watchtower reconciles the final landed evidence and decides whether delivery is complete.

## Briefing style

Watchtower writes each crew prompt itself. Prefer **intent + pointer + only the
context, constraints, and evidence this specialist needs**. The role policy is
orchestration guidance, not a prompt template.

Do not duplicate repository rules the crew will load from its target `--cwd` or
force every role into the same checklist/report schema.

## Learning surface

The no-mistakes Observatory is for qualitative learning across runs: stage shape,
retry/fix loops, CI repair, and other visible pipeline behavior. Keep terminal
run scrollback available through the associated landing/post-merge episode when
practical.

For durable optimization, retain run IDs and prefer structured no-mistakes data
for timing, retries, fixes, findings, agent/model usage, and outcomes. Missing
structured telemetry is an instrumentation gap, not a reason to scrape the TUI.

## Reports

Keep the lifecycle handoff fields unchanged. Roles may additionally report
`attempt_count` and `caused_by` as ordinary metadata; these do not alter Rozoro
verdict parsing or lifecycle semantics.

Crew reports should provide enough exact evidence for Watchtower to route the
next action without requiring one fixed role-specific schema.

The no-mistakes gate record should name the submitted and final exact heads, run
ID/outcome, PR/CI evidence, custody state, supported recovery action, and routing
consequence of findings.

The Merge Finisher should report the expected/current PR head, merge path/result,
actual landed identity, required post-merge evidence, and any delivery failure
that needs another routed task.
