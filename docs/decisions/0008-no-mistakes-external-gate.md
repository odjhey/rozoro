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

A second orchestration problem surfaced in the same refactor: `brief-*` skills
turned Watchtower from a judgment layer into a prompt forwarder. Role policy and
task prompts need to stay separate. Policy informs Watchtower; Watchtower writes
the smallest task-specific brief.

Removing the wrapper crew also removes the accidental terminal home for the
no-mistakes graph. Attaching that graph to arbitrary agent panes would recreate a
false ownership relationship, while repeatedly splitting the Watchtower pane
would not scale to multiple concurrent gates or support cross-run learning.

## Options

1. Keep a dedicated No-Mistakes Runner crew as a wrapper around no-mistakes.
2. Treat no-mistakes as a Watchtower-managed external gate/job: submit or
   reattach the run directly, observe structured state, answer supported gates,
   reconcile exact-head/custody evidence, and route findings back to normal crew.
3. Fold no-mistakes into Coder/Reviewer/Tester and let those crews run it
   opportunistically.

For crew briefing:

A. Keep role-specific `brief-*` skills as prompt templates.
B. Keep role/model policy in the canonical dispatch guide and let Watchtower
   synthesize concise task-specific briefs.

For graph visibility:

I. Attach each no-mistakes graph to the current Watchtower or agent pane.
II. Maintain a dedicated untracked **no-mistakes Observatory** Herdr tab with one
    pane per active run when supported.

## Choice

Choose option 2, briefing option B, and graph visibility option II.

No-mistakes is **not a Rozoro crew role**.

When a clean committed candidate is ready for no-mistakes assurance:

1. Watchtower invokes `no-mistakes-gate` directly.
2. It records the exact submitted branch/head/tree and operator intent.
3. It inspects current no-mistakes/AXI state and reattaches to a matching run
   instead of creating a duplicate.
4. It submits through the repository's supported no-mistakes path, including the
   configured `no-mistakes` Git remote where that is the repository contract.
5. It observes and drives the run through the supported no-mistakes/AXI control
   surface.
6. It responds to bounded gates within current authority and preserves/surfaces
   unsupported decisions without blocking unrelated work.
7. It keeps the run visible in the no-mistakes Observatory for operator learning
   and inspection while structured no-mistakes/AXI state remains authoritative.
8. It reconciles the final exact head, PR, CI, branch sync, and custody state.
9. It routes local defects to Coder and task-boundary problems to Replanner.
10. If landing is allowed, it dispatches Merge Finisher for the actual merge and
    required post-merge work.

No-mistakes owns its own pipeline-agent/model/account/fallback configuration.
Rozoro selects models for Rozoro crews only. If the desired no-mistakes internal
selection policy cannot be expressed by the installed no-mistakes version, that
is a no-mistakes integration/configuration gap, not a reason to spawn a wrapper
crew or mutate model configuration around each run.

The `no-mistakes-observatory` skill owns only the visualization surface. Prefer
one persistent, untracked Herdr Observatory tab per Watchtower workspace and one
pane per active run. The Observatory is never a crew, task, session, custody
owner, mailbox owner, or second control plane.

Keep terminal graph/scrollback through the associated landing/post-merge episode
when practical. This supports qualitative learning about expensive stages,
retry/fix loops, CI repair, and model/agent behavior. Durable optimization should
use run IDs and structured no-mistakes telemetry where available; missing timing,
retry, fix, or model data is an instrumentation gap rather than a reason to scrape
the TUI.

Current no-mistakes ownership stops at preparing/updating a clean PR, watching CI
and mergeability, and fixing supported conflicts/failures. The final merge remains
a separate repository/provider mutation. When Watchtower judges landing is
allowed, it dispatches the **Merge Finisher** (`gpt-5.6-luna`, low).

Crew briefs are authored by Watchtower. The removed `brief-*` layer is not
replaced by another prompt schema. Default brief style is intent + pointer + only
the context, constraints, and evidence the selected specialist needs.

For new implementation work, raw operator intent normally goes through Planner
before Coder unless the task is already genuinely bounded, is a normal repair
turn, or clearly qualifies for Quick Coder.

## Consequences

- Remove the No-Mistakes Runner from `crew-model-selection` and the canonical
  Rozoro crew role table.
- Remove `no-mistakes-harness-selection`; no outer crew exists whose harness would
  select the pipeline model.
- Remove the `brief-*` prompt-template layer.
- Keep role/model boundaries in the canonical dispatch policy while restoring
  Watchtower-authored task prompts.
- Keep no-mistakes defects in the normal delivery loop: local repairs go to Coder;
  contract/scope failures go to Replanner.
- Replace the ad-hoc side observer pane with a dedicated no-mistakes Observatory
  Herdr surface grouped away from agent panes.
- Preserve terminal graph/scrollback long enough to study the full gate-to-landing
  episode; use structured run evidence for durable optimization.
- Add Merge Finisher as the final merge/post-merge repository mutation owner.
- Avoid outer-versus-inner model ambiguity, duplicate agent orchestration,
  mechanically templated crew prompts, and false graph ownership by an agent pane.
- A future Rozoro adapter may integrate no-mistakes run events and telemetry into
  the resident monitor/event bus, but semantic ownership remains with
  no-mistakes/AXI.
- Tight polling of `axi status` is not the desired long-term integration; prefer
  event/edge-driven observation where supported.
