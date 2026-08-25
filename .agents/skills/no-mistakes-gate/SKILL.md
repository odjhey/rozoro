---
name: no-mistakes-gate
description: >-
  Submit a no-mistakes validation run and reconcile it when Rozoro delivers a
  no-mistakes notification. Use when a clean committed candidate is ready for
  no-mistakes assurance or when Watchtower wakes for an actionable no-mistakes
  run edge. Do not spawn a No-Mistakes Runner crew and do not poll from Watchtower.
---

# No-mistakes gate

No-mistakes is an external pipeline/job, not a Rozoro crew role.

The Watchtower is **push-driven**. It submits or reattaches a run, records its
identity, then returns idle. A deterministic no-mistakes event adapter observes
run state and publishes normalized events into `rozorod`; actionable edges wake
Watchtower through the same durable generation/reconcile path used by crew.

## Ownership boundary

Watchtower owns:

- deciding when a candidate is ready for the gate;
- supplying operator intent and exclusions;
- submitting or reattaching the run;
- recording task/run/head identity;
- reconciling an actionable run after a Rozoro notification;
- responding to supported gates within existing authority; and
- routing findings or success to the next task kind.

The no-mistakes event adapter owns:

- observing no-mistakes/AXI run transitions while Watchtower is idle;
- publishing normalized, idempotent no-mistakes events to `monitor.sock` (with
  the existing durable spool/ACK fallback when the daemon is unavailable); and
- never making routing, approval, repository, or product decisions.

`rozorod` owns persistence, reduction, coalescing, pending generations, retry, and
Watchtower wake delivery.

No-mistakes owns its disposable worktree, pipeline custody, internal agents/model
selection, fixes, PR/CI work, and structured recovery surface.

The Observatory owns nothing; it is a human-readable visualization only.

## Submit or reattach

Before submission:

1. Require a clean committed candidate.
2. Record repository, branch, exact head/tree, base, expected PR scope, intent,
   exclusions, and acceptance source.
3. Inspect current no-mistakes/AXI state once to avoid duplicating a matching run.
4. Submit through the repository's supported no-mistakes path, including the
   configured `no-mistakes` Git remote where applicable, or reattach as supported
   by the installed no-mistakes version.
5. Record the resulting run ID and bind it to the originating Rozoro task/lineage
   for later notification reconciliation.
6. Ensure the no-mistakes event adapter is tracking that run.
7. Expose the run in `no-mistakes-observatory` for operator inspection.
8. Return Watchtower to normal idle/push-driven operation.

Do not keep a Watchtower turn alive to wait for the run and do not build a polling
loop around `axi status`.

## Notification contract

The adapter should emit source events for meaningful run transitions. Persist all
source events; coalesce only Watchtower wakeups.

At minimum distinguish:

- progress-only state: persist, no wake;
- approval/decision/input required: actionable wake;
- actionable defect/failure/cancellation: actionable wake;
- terminal/checks-passed success: actionable wake; and
- custody/recovery state requiring a supported next action: actionable wake.

Every event needs stable run/task identity and an idempotent event ID. The daemon
notification itself stays content-light; Watchtower gets authoritative detail by
reconciling the referenced no-mistakes run state after wake.

A wake does **not** mean the Observatory changed visually. The event adapter and
structured no-mistakes state are the operational path.

## On Watchtower wake

When Rozoro reports a pending no-mistakes generation:

1. run the normal Rozoro reconciliation path;
2. identify the affected task/run(s);
3. read current structured no-mistakes/AXI state for those run IDs;
4. act only on current state, tolerating duplicate/at-least-once notifications;
5. record/ack the reconciled generation; and
6. return idle once no immediate decision or dispatch remains.

Routing examples:

- **running/fixing/checking only** — normally no actionable wake; if observed due
  to replay/reconciliation, record and return idle;
- **approval/decision gate** — respond through supported AXI/no-mistakes controls
  when current policy authorizes the decision;
- **local implementation defect** — route evidence to the active Coder;
- **scope/contract failure** — dispatch Replanner;
- **terminal success** — reconcile final exact head, PR, required CI, branch sync,
  and custody; if landing is allowed, dispatch Merge Finisher;
- **unsupported recovery/authority** — preserve state and surface the issue without
  inventing Git surgery.

## Observatory

Use `no-mistakes-observatory` to keep each run's graph/TUI visible for operator
inspection and optimization. The Observatory is not the notification mechanism,
not a stable telemetry API, and not a source of operational truth.

Retain run IDs and prefer structured no-mistakes evidence for stage timing,
retries, fixes, findings, agent/model usage, and outcomes when available.

## Custody and model ownership

While no-mistakes owns its pipeline branch/worktree, do not issue competing Git
mutations. Follow supported structured recovery instructions exactly.

Rozoro selects models for Rozoro crews only. no-mistakes owns its internal
pipeline-agent/model/account/fallback configuration. If desired internal routing
cannot be expressed by the installed version, track that as an integration gap;
do not add a wrapper LLM crew.

## Evidence to retain

For each gate keep:

- originating Rozoro task/lineage;
- run ID;
- submitted and final exact head/tree;
- base and branch;
- actionable event/reconcile history;
- relevant gate decisions;
- fixes/findings reported by no-mistakes;
- PR URL/state and exact-head CI;
- final custody/recovery state; and
- next routed action, including Merge Finisher when ready to land.
