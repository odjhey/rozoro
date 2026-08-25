# ADR-0008: Treat no-mistakes as an external gate

review: approved
date: 2026-08-25
supersedes: ADR-0007

## Context

ADR-0007 modeled no-mistakes as work performed by a dedicated Rozoro
No-Mistakes Runner crew. Watchtower selected that crew's harness/model and the
crew then invoked no-mistakes.

That adds an unnecessary orchestration layer. No-mistakes already owns the
pipeline that matters here: disposable worktrees, branch custody, its internal
review/fix/test/document/CI-repair agents, PR/CI work, structured gates, and
recovery state exposed through no-mistakes/AXI.

The wrapper crew also created repeated ambiguity about whether the outer runner
model or an inner no-mistakes model was authoritative. It made Rozoro responsible
for target/account/fallback decisions that belong to no-mistakes' own pipeline
configuration.

## Options

1. Keep a dedicated No-Mistakes Runner crew as a wrapper around no-mistakes.
2. Treat no-mistakes as a Watchtower-managed external gate/job: submit or
   reattach the run directly, observe structured state, answer supported gates,
   reconcile exact-head/custody evidence, and route findings back to normal crew.
3. Fold no-mistakes into the Coder/Reviewer/Tester roles and let those crews run
   it opportunistically.

## Choice

Choose option 2.

No-mistakes is **not a Rozoro crew role**.

When a clean committed candidate is ready for no-mistakes assurance:

1. Watchtower invokes the `no-mistakes-gate` skill directly.
2. It records the exact submitted branch/head/tree and operator intent.
3. It inspects current no-mistakes/AXI state and reattaches to a matching run
   instead of creating a duplicate.
4. It submits through the repository's supported no-mistakes path, including the
   configured `no-mistakes` Git remote where that is the repository contract.
5. It observes and drives the run through the supported no-mistakes/AXI control
   surface.
6. It responds to bounded gates within current authority and preserves/surfaces
   unsupported decisions without blocking unrelated work.
7. It reconciles the final exact head, PR, CI, branch sync, and custody state.
8. It routes actionable repository findings back to the active coder or to the
   Escalation Replanner when the task boundary changed.
9. If the gate result is acceptable and landing is authorized by current
   repository/operator policy, Watchtower dispatches a **Merge Finisher** crew to
   perform the actual merge and required post-merge activities. Watchtower does
   not merge the repository itself.

No-mistakes owns its own pipeline-agent/model/account/fallback configuration.
Rozoro selects models for Rozoro crews only. If the desired no-mistakes internal
selection policy cannot be expressed by the installed no-mistakes version, that
is a no-mistakes integration/configuration gap, not a reason to spawn a wrapper
crew or mutate global model configuration around each run.

The `no-mistakes-observer-pane` remains useful but attaches to the **active run
beside Watchtower**. It is an untracked display surface only and never a crew,
task, session, custody owner, or second control plane.

## Consequences

- Remove the No-Mistakes Runner from `crew-model-selection` and the canonical
  Rozoro crew role table.
- Remove `no-mistakes-harness-selection`; no outer crew exists whose harness would
  select the pipeline model.
- Remove `brief-no-mistakes-recovery`; custody/recovery is driven through the
  Watchtower-owned no-mistakes gate and current structured recovery instructions.
- Keep no-mistakes defects in the normal delivery loop: local repairs go back to
  the coder; contract/scope failures go to replanning.
- Gate success transitions to a separate Merge Finisher crew for merge and
  post-merge repository/provider work; Watchtower remains the judgment/routing
  layer.
- Keep the side Herdr panel, but attach it to the active no-mistakes run beside
  Watchtower.
- Avoid outer-versus-inner model ambiguity and duplicate agent orchestration.
- A future Rozoro adapter may integrate no-mistakes run events into the resident
  monitor/event bus, but the semantic owner remains no-mistakes/AXI.
- Tight polling of `axi status` is not the desired long-term integration; prefer
  event/edge-driven observation when the installed interface supports it.
