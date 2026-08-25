---
name: crew-model-selection
description: >-
  Choose the task kind, model, reasoning effort, and dispatch path for a fresh
  Watchtower crew. Use immediately before Watchtower spawns a new crew so current
  standard model policy, Quick Crew eligibility, No-Mistakes harness fallback,
  and the applicable brief-* guideline are resolved from the canonical sources.
---

# Crew model selection

Use this in **Watchtower immediately before every fresh crew dispatch**. Do not
answer from remembered defaults.

## Resolve the dispatch

1. Read `templates/watchtower-crew-dispatch-guidelines.md`. Treat it as the source
   of truth for standard role assignment, canonical model IDs, reasoning effort,
   and current No-Mistakes execution-target fallback policy.
2. Read `.agents/skills/quick-crew-routing/SKILL.md` when the work might qualify
   for the bounded Quick Crew fast path. Quick Crew does not replace or rewrite
   the standard model map.
3. Choose the task kind/role first, then choose the model and reasoning effort for
   that role. Keep harness/profile/target identity separate from model ID and
   reasoning effort.
4. If the selected task kind is **No-Mistakes Runner**, read
   `.agents/skills/no-mistakes-harness-selection/SKILL.md` and use it to select
   the runner harness/model/account target. When no-mistakes model selection is
   `auto`, the selected runner harness/model is the workflow model; do not mutate
   global no-mistakes model configuration merely to select it.
5. If the selected task kind has a `brief-*` guideline, load it and render the
   applicable role contract, constraints, task-specific evidence, and report
   shape into the crew brief before dispatch.

## Current briefing map

- Task Decomposer / Escalation Replanner -> `brief-task-planner`
- Reviewer -> `brief-reviewer`
- Tester -> `brief-tester`
- No-Mistakes branch recovery -> `brief-no-mistakes-recovery`
- Coder modifying Rozoro -> `brief-rozoro-coder`
- Quick Scout -> `brief-quick-scout`
- Quick Coder -> `brief-quick-coder`

A normal coder working in another repository follows the bounded task plus that
repository's own rules unless another applicable briefing guideline exists.

## Rules

- Current standard role/model/effort selection wins over older snapshots or
  machine-local policy copies.
- Current No-Mistakes target/fallback order wins over older snapshots or
  machine-local policy copies.
- In No-Mistakes `auto` mode, target selection is performed by choosing the
  runner's actual invoking harness/model/account context. Global no-mistakes
  model save/override/restore is not part of the normal selection path.
- Use canonical model IDs exactly as written. Do not invent shorthand model
  names.
- Standard crew is the default. Quick Crew is an explicit bounded fast path only.
- The uploaded cross-machine blanket Pi-harness rule was discarded and must not
  be inferred as a global default.
- Rozoro does not currently transmit skill objects/references to crew sessions.
  The relevant `brief-*` content must be incorporated into the actual task brief.
- If a canonical source is missing, ambiguous, or internally inconsistent, report
  that condition instead of guessing.

Follow-up on an existing live task normally uses the same crew/context via
`./bin/rozoro send`; do not re-run fresh-crew selection merely because another
turn is needed. Re-run selection when Watchtower is dispatching a new task-kind
crew, such as reviewer, tester, replanner, No-Mistakes Runner, or replacement
coder.