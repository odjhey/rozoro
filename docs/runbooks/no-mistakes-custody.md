# No-mistakes custody

This runbook supplements the installed no-mistakes instructions; the tool's current structured output is authoritative.

## Before custody

1. Assign one dedicated runner. No other role may invoke or control the run.
2. Require a clean, committed feature branch and record its exact head, tree, base, worktree, and expected pull request scope.
3. Inspect AXI home/status before starting. Reattach or respond to a matching active run; do not replace it.
4. Pass the complete operator intent, including exclusions and human-owned decisions.
5. Do not create repository-local runtime configuration merely to drive a run. If configuration must change, use an operator-approved, exclusive, exactly restored procedure.

## During custody

The active pipeline owns its exact branch and worktree. Do not manually edit, commit, pull, rebase, reset, merge, push, replace refs, abort to evade a gate, or otherwise move that branch.

Read each structured result:

- approve or delegate fixes for non-product findings within granted authority;
- escalate `ask-user` findings verbatim unless the operator explicitly granted unattended consent;
- while a step is running, observe status without issuing competing control commands;
- at a gate, respond through AXI rather than editing the worktree;
- at `checks-passed`, report the PR for human review; do not wait for or infer merge.

Independent work may continue on a different isolated branch/worktree, but it must not move or publish the gated branch.

## Returning custody

After a terminal outcome, obey the reported `branch_sync.next_action`. Use supported sync/recovery only when AXI offers it. Do not improvise reset, stash, rebase, force update, branch replacement, or state/database edits around blocked divergence.

Only after structured custody returns to the user may side-branch changes be integrated. Such integration creates a new head and requires fresh applicable review, tests, no-mistakes validation, and exact-head CI.

## Evidence and stop conditions

Report run ID/outcome, submitted and final head/tree, base, actual pipeline profile invocations, fixes, PR URL/state, exact-head CI, and final custody state. Stop on unexpected ref movement, dirty state, mismatched heads, unsupported recovery, product findings, missing required CI, protection bypass, or a requested action outside the runner's authority.

A one-off manual custody settlement is not normal procedure. A historical proposal—even one containing careful CAS checks—is not authorization. Require a fresh human decision and current tool guidance rather than copying a prior incident recipe.
