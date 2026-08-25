---
name: no-mistakes-gate
description: >-
  Submit and drive a no-mistakes validation run directly from Watchtower. Use
  when a clean committed candidate is ready for no-mistakes assurance. Watchtower
  submits or reattaches the run, observes AXI state, responds to gates, reconciles
  exact-head/custody evidence, and routes findings. Do not spawn a No-Mistakes
  Runner crew.
---

# No-mistakes gate

Use this in **Watchtower when a candidate is ready for no-mistakes validation**.
No-mistakes is an external pipeline/job, not a Rozoro crew role.

## Ownership boundary

Watchtower owns:

- deciding when the candidate is ready for the gate;
- supplying the full operator intent and exclusions;
- recording the submitted branch/head and run identity;
- observing structured run state;
- responding to supported gates within existing authority;
- reconciling final branch/PR/CI/custody evidence; and
- routing defects or unresolved decisions back to the appropriate crew.

No-mistakes owns:

- its disposable worktree and pipeline custody;
- its internal review/fix/test/document/CI-repair agents;
- internal agent/model/fallback selection;
- branch forwarding, PR creation, and CI monitoring performed by its pipeline; and
- the structured recovery actions it exposes through AXI/no-mistakes.

Do not insert another LLM between Watchtower and no-mistakes merely to invoke or
watch the pipeline.

## 1. Preflight

Before submission:

1. Require a clean, committed candidate branch.
2. Record the exact candidate head/tree, base, branch, and expected PR scope.
3. Preserve the complete operator intent, important exclusions, and acceptance
   criteria that no-mistakes must judge.
4. Inspect current no-mistakes/AXI state for a matching active run. Reattach to a
   matching run instead of creating a duplicate.
5. Do not mutate no-mistakes global model/agent configuration as part of normal
   Watchtower routing. Internal pipeline-agent selection belongs to no-mistakes.

## 2. Submit or reattach

Use the repository's supported no-mistakes submission path. Where the repository
is configured with a `no-mistakes` Git remote, submit the committed branch through
that remote; use AXI/no-mistakes to start, identify, or reattach to the matching
run as supported by the installed version.

Record at least:

- no-mistakes run ID;
- repository and branch;
- submitted exact head/tree;
- base;
- submitted intent; and
- current custody state.

Do **not** call `./bin/rozoro start` to create a No-Mistakes Runner crew.

## 3. Drive the run

Treat the current structured no-mistakes/AXI output as authoritative.

- **running/fixing/checking** — observe without issuing competing branch mutations.
- **approval/decision gate** — respond through the supported AXI/no-mistakes
  control path. Make bounded unattended decisions when existing operator/repository
  policy already authorizes them; otherwise preserve state and surface an issue
  with exact evidence while continuing unrelated work.
- **checks-passed / passed / terminal success** — reconcile the final exact head,
  PR, required CI, and returned custody. If the candidate is now eligible to land,
  dispatch a Merge Finisher using `brief-merge-finisher`; Watchtower does not
  perform the merge itself.
- **failed / cancelled / rejected** — preserve the run evidence and route actionable
  findings to the active coder or to replanning when the problem changes the task
  boundary.

Prefer event/edge-driven observation where the installed interface supports it.
Do not build a tight fixed-interval polling loop around `axi status`.

## 4. Observer pane

Once an active run exists, use `no-mistakes-observer-pane` to open the untracked
side pane and attach it to the run. The pane is presentation only; AXI/no-mistakes
structured state remains authoritative.

## 5. Custody and recovery

While no-mistakes owns the pipeline branch/worktree, do not manually edit, commit,
pull, rebase, reset, merge, push, stash, replace refs, or otherwise compete with
pipeline custody.

After terminal outcome, follow the structured `branch_sync.next_action` or other
supported recovery instruction exactly. Do not translate an unsupported or
ambiguous recovery state into improvised Git surgery.

If recovery changes the candidate head, invalidate stale review/test/no-mistakes/
CI evidence as required and route any new repository work to the proper crew.

## 6. Model and harness ownership

Rozoro selects models for **Rozoro crews**. It does not select no-mistakes'
internal pipeline model by choosing an outer crew harness, because there is no
outer No-Mistakes Runner crew in this design.

Treat the installed no-mistakes configuration and current structured output as the
source of truth for its internal agent/model/fallback behavior. If the desired
agent/account/fallback policy cannot be expressed there, that is a no-mistakes
integration/configuration gap to solve explicitly, not a reason to add a wrapper
crew or mutate model configuration around each run.

## 7. Report

Record:

- run ID and outcome;
- submitted and final exact head/tree;
- base and branch;
- structured gate/decision history relevant to the result;
- no-mistakes pipeline-agent/model evidence when reported by no-mistakes;
- fixes performed by the pipeline;
- PR URL/state and required exact-head CI;
- final custody state and supported recovery action, if any;
- stale assurance invalidated by head movement; and
- the next Rozoro routing decision, including `Merge Finisher` when the candidate
  is ready to land.