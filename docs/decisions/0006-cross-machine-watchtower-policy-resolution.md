# ADR-0006: Resolve cross-machine Watchtower policy differences

review: approved
date: 2026-08-25

## Context

A second Watchtower policy set captured from other machines contained practices
that had worked in production-like use, but it also duplicated current Rozoro
policy and carried stale or machine-specific choices. Importing the snapshot
wholesale would create multiple sources of truth for model routing,
no-mistakes fallback, lifecycle operations, and role ownership.

The useful non-duplicate material was Quick Crew routing, a ten-attempt
implementation budget with deferral, and a no-mistakes observer pane. The
snapshot also conflicted with current Rozoro model assignments, current
no-mistakes target fallback, and contained a blanket Pi-harness rule.

## Options

1. Import the resolved snapshot wholesale — preserves the other-machine policy as
   written, but creates duplicate and conflicting authorities.
2. Ignore it — avoids drift, but loses practices that proved useful elsewhere.
3. Dedupe against current Rozoro policy, keep current authorities where they
   conflict, and import only distinct reusable behavior.

## Choice

Choose option 3.

The following current Rozoro policies remain authoritative:

- standard role/model/effort selection in
  `templates/watchtower-crew-dispatch-guidelines.md`;
- the current no-mistakes execution-target/fallback policy, including the two
  configured Claude targets followed by Pi `gpt-5.6-luna` high where applicable;
- Rozoro lifecycle/dispatch semantics in the existing Watchtower policy; and
- role separation between Watchtower and crew.

Import these distinct practices:

- **Quick Crew** — `gpt-5.3-codex-spark` low may be used for a bounded Quick
  Scout or Quick Coder fast path. Standard crew remains the default, Quick Crew
  is not retried, and consequential output still receives normal assurance.
- **Attempt budget** — derive coder attempts from durable task/session/turn
  history. A lineage has ten coder attempts. Attempt 10 may complete its normal
  review/test/gate sequence, but a finding that would require another coder turn
  does not start attempt 11.
- **Deferral** — an exhausted lineage is parked while other runnable work exists.
  Deferred lineages are reconsidered when the runnable queue is empty, or earlier
  if materially new evidence/tooling changes the premise or the operator
  explicitly reprioritizes them.
- **No-mistakes observer pane** — Watchtower may create an untracked sibling
  Herdr pane and run `no-mistakes attach` for visibility. The observer is not a
  Rozoro crew and has no custody or mutation authority.

Discard the uploaded blanket **Pi harness for Watchtower crews** rule as
machine-specific rather than global Rozoro policy.

Crew-oriented skills are Watchtower briefing guidelines only in the current
implementation. They use the `brief-*` naming convention: Watchtower loads the
applicable guideline, renders its role contract/constraints/report shape into the
crew brief, then dispatches the corresponding task-kind crew. Rozoro does not
currently deliver skill objects/references to crew sessions.

## Consequences

- Model routing and no-mistakes fallback keep a single current authority instead
  of being copied from snapshots.
- Useful cross-machine practices become reusable skills without reviving stale
  role mappings.
- Quick Crew is explicitly an optimization, not a lower-assurance replacement for
  the normal pipeline.
- The attempt budget bounds repair loops without adding a new persisted attempt
  lifecycle; attempts remain derived from coder turns.
- Budget exhaustion does not stall an unattended Watchtower while independent
  work remains.
- Observer panes improve visibility without polluting Rozoro task/session state.
- `brief-*` makes crew-brief construction discoverable from the skill name itself.
- Future cross-machine snapshots should be treated as evidence to reconcile, not
  automatically as a new policy authority.
