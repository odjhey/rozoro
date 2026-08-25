# No-mistakes custody

This runbook supplements the installed no-mistakes instructions; the tool's
current structured output is authoritative.

No-mistakes is an external pipeline/job owned by no-mistakes itself. Watchtower
drives the run directly through the supported no-mistakes/AXI interface. Do not
spawn a dedicated No-Mistakes Runner crew merely to proxy the tool.

## Before custody

1. Require a clean, committed feature branch and record its exact head, tree,
   base, worktree, and expected pull request scope.
2. Preserve the complete operator intent, important exclusions, and acceptance
   criteria.
3. Inspect AXI/no-mistakes home/status before starting. Reattach or respond to a
   matching active run; do not replace it with a duplicate.
4. Submit through the repository's supported no-mistakes path, including the
   configured `no-mistakes` Git remote where that is the repository contract.
5. Record the resulting run ID and submitted exact identity.
6. Do not create repository-local runtime configuration merely to drive a run.
   Internal pipeline agent/model/fallback configuration belongs to no-mistakes.

## During custody

The active no-mistakes pipeline owns its exact branch and disposable worktree. Do
not manually edit, commit, pull, rebase, reset, merge, push, replace refs, stash,
abort to evade a gate, or otherwise move that pipeline-owned state.

Read each structured result:

- while a step is running, observe status without issuing competing control
  commands;
- at an approval or decision gate, respond through AXI/no-mistakes within current
  Watchtower authority;
- when a question requires operator/product authority that Watchtower does not
  have, preserve the run safely, surface the exact evidence in a GitHub issue or
  decision record, and continue unrelated work;
- when the pipeline reports actionable implementation defects, preserve the run
  evidence and route those findings back to the active coder, or to replanning if
  they change the task boundary;
- at a successful terminal/checks-passed state, reconcile the actual PR, final
  head, required CI, and custody state before treating the gate as complete.

Independent work may continue on a different isolated branch/worktree, but it
must not move or publish the no-mistakes-owned branch.

## Observatory

No agent pane owns the no-mistakes graph.

Use `no-mistakes-observatory` to maintain one persistent, untracked Herdr
Observatory tab for the Watchtower workspace. Prefer one pane per active
no-mistakes run, labeled with enough task/run identity to distinguish concurrent
gates. Run `no-mistakes attach` there using the supported invocation for the
installed version.

The Observatory is a display projection only. Structured no-mistakes/AXI state
remains the source of truth, and Observatory failure must not change custody or
block the run.

Keep a terminal graph/scrollback available through the associated landing and
post-merge episode when practical so the operator can inspect the whole delivery
path. Observatory cleanup has no pipeline lifecycle meaning.

For optimization work, retain the run ID and prefer structured timing, retry,
fix, finding, agent/model, and outcome data exposed by no-mistakes. Treat missing
telemetry as an instrumentation gap rather than scraping terminal pixels or
assuming TUI text is a stable machine contract.

## Returning custody

After a terminal outcome, obey the reported `branch_sync.next_action` or other
structured recovery instruction. Use supported sync/recovery only when
no-mistakes/AXI offers it.

Do not improvise reset, stash, rebase, force update, branch replacement, or
state/database edits around blocked divergence.

Only after structured custody returns may other repository work move that branch.
Any integration or recovery that creates a new head requires fresh applicable
review, tests, no-mistakes validation, and exact-head CI according to repository
policy.

## Internal pipeline agents

Rozoro does not select no-mistakes' internal pipeline agent by selecting an outer
crew harness. There is no outer No-Mistakes Runner crew in this model.

Treat current no-mistakes configuration and structured output as authoritative for
its own review/fix/test/document/CI-repair agent, model, account, and fallback
behavior. If the desired internal selection policy cannot be expressed by the
installed no-mistakes version, track that as a no-mistakes integration/config
capability gap rather than wrapping the pipeline in another LLM.

## Evidence and stop conditions

Record:

- run ID and outcome;
- submitted and final head/tree;
- base and branch;
- pipeline-agent/model evidence exposed by no-mistakes;
- fixes performed by the pipeline;
- PR URL/state and exact-head CI;
- final custody state; and
- supported recovery action, if any.

Stop competing mutations on unexpected ref movement, dirty pipeline-owned state,
mismatched heads, unsupported recovery, missing required CI, protection bypass,
or a requested action outside current Watchtower authority.

A historical one-off custody settlement is not normal procedure. Do not copy a
manual CAS/reset/rebase recipe into a new incident unless current tool/repository
policy explicitly supports it.
