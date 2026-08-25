# No-mistakes custody

This runbook supplements the installed no-mistakes instructions. Current
structured no-mistakes/AXI output is authoritative for a run.

Rozoro uses a dedicated **No-Mistakes Runner crew** as the thin operator for the
external pipeline. The runner submits or reattaches the exact committed candidate,
keeps the run observed/listened to, and reports structured evidence back to
Watchtower. no-mistakes itself owns the pipeline worktree, internal agents, fixes,
PR/CI work, and custody state.

## Configuration

Resolve configuration before starting a new run:

1. Read trusted repository configuration from `.no-mistakes.yaml` when present.
2. Read the selected global no-mistakes profile from
   `~/.no-mistakes/config.yaml`, or from the `NM_HOME` named by the machine
   profile.
3. Use no-mistakes' native `agent` or ordered agent list for pipeline-agent
   selection and `agent_config` for per-agent model/effort where needed.
4. Run the installed no-mistakes health/config checks needed to verify the selected
   profile is usable before relying on it.

Rozoro's optional `$ROZORO_HOME/config/machine.md` may describe which no-mistakes
profiles/accounts exist on this machine and how they are launched. Keep secrets
out of that text file; point to profile names/paths or environment-variable names
rather than credential values.

`CLAUDE_CONFIG_DIR` is a Claude harness environment variable. It is not listed as
a no-mistakes config field in the upstream global-config reference. Because
normal no-mistakes runs use a background daemon, setting `CLAUDE_CONFIG_DIR` only
on a one-shot `no-mistakes` client command is not treated as proof that the daemon
will launch Claude with that value. When multiple Claude identities are required,
use explicit, verified no-mistakes/machine profiles; separate `NM_HOME` instances
are the upstream-supported way to keep repeatable global configurations separate.

## Starting or reattaching a run

Give the No-Mistakes Runner:

- repository and workset/task identity;
- clean committed candidate branch, exact head/tree, and base;
- expected PR/delivery scope;
- operator intent, exclusions, and acceptance pointer; and
- selected no-mistakes profile when known.

The runner checks current no-mistakes state, reattaches a matching active run when
supported, or submits through the repository's configured path such as
`git push no-mistakes <branch>` or the installed CLI/AXI run command.

Record the run ID and submitted exact identity in the runner handoff/workset
evidence.

## During custody

The active no-mistakes pipeline owns its disposable worktree and pipeline-managed
branch state. Other independent work may continue in separate branches/worktrees.

The No-Mistakes Runner keeps the run available for observation/control through the
supported no-mistakes/AXI surface and reports meaningful transitions such as:

- approval/input required;
- actionable findings or failed stages;
- fixes that changed the candidate head;
- PR/CI progress that changes delivery state;
- terminal success/failure; and
- custody/recovery actions required by the tool.

Use supported no-mistakes/AXI controls for gate responses and recovery. Preserve
exact identities around any action that may change the candidate.

## Routing results

The runner reports structured evidence; Watchtower routes it.

- A local implementation defect returns to the relevant Coder while the task
  boundary still holds.
- A scope/dependency/contract problem goes to Replanner.
- A result whose meaning depends on branch ordering, stacking, or the integrated
  workset goes to the **Workset Merger**.
- A successful run joins the workset's delivery evidence. The Workset Merger
  determines whether additional integration invalidates that evidence and what
  assurance the final integrated head requires.

This keeps no-mistakes execution separate from workset integration judgment.

## Observatory

`no-mistakes-observatory` may maintain a persistent human-readable graph for
active runs. The Observatory is a display projection; run IDs and structured
no-mistakes/AXI evidence are the durable operational references.

Keep terminal graph/scrollback through the associated integration/landing episode
when practical so the operator can inspect stage cost, retries, fixes, CI repair,
and model behavior.

## Returning custody

After a terminal outcome, follow the structured `branch_sync.next_action` or other
recovery instruction exposed by the installed version. Record the final head/tree,
PR/CI state, and custody status.

Any later integration that creates a new head is a new exact candidate. The
Workset Merger decides which review/test/no-mistakes/CI evidence must be repeated
for that integrated head according to repository policy.

## Evidence to retain

For each run retain:

- originating project/workset/task identity;
- selected no-mistakes profile;
- run ID;
- submitted and final exact head/tree;
- base and branch;
- pipeline agent/model evidence exposed by no-mistakes;
- findings and fixes;
- gate decisions;
- PR URL/state and exact-head CI;
- final custody/recovery state; and
- routed next action.
