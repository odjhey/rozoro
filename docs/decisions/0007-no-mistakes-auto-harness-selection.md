# ADR-0007: Select no-mistakes auto model through the invoking harness

review: approved
date: 2026-08-25

## Context

The previous Watchtower policy selected a no-mistakes execution target by
mutating global no-mistakes model configuration around each invocation. That
required save/override/restore locking and made concurrent unattended operation
more fragile.

Current no-mistakes `auto` selection has a simpler contract: no-mistakes uses the
model of the harness that invoked it. If Watchtower can launch the intended
harness/model/account context directly, that invocation already expresses the
workflow target.

Separately, the no-mistakes observer-pane policy existed only as a discoverable
skill whose trigger said live visibility was useful. Watchtower did not reliably
invoke it, so the expected sibling Herdr panel was often absent.

## Options

1. Keep mutating global no-mistakes model configuration for every target choice.
2. In `auto`, select the target by launching the No-Mistakes Runner under the
   intended harness/model/account context; keep the existing ordered fallback
   list and treat an unlaunchable target as unavailable.
3. Let no-mistakes or the runner choose any convenient provider/model dynamically.

For observation:

A. Keep the side pane optional/discovery-driven.
B. Make the observer a normal Watchtower step for every active No-Mistakes Runner
   when the installed Herdr provides a supported pane operation.

## Choice

Choose option 2 and observation option B.

When no-mistakes model selection is `auto`:

- Watchtower selects the workflow target by selecting the **runner's actual
  invoking harness/model/account context**.
- A Claude/Sonnet target means the runner itself is launched as Claude with
  Sonnet in the intended account context. A Pi fallback means the runner itself
  is launched as Pi with exact `gpt-5.6-luna` at high effort.
- no-mistakes then inherits that invoking harness/model.
- Global no-mistakes model save/override/restore is not part of the normal target
  selection path.
- The canonical fallback order remains authoritative; the inheritance principle
  does not add undeclared providers such as Codex to that order.
- If a configured account/profile target cannot be independently launched by
  current Rozoro capabilities, treat it as unavailable and continue to the next
  configured target. Do not mutate global no-mistakes config as a workaround.

For every No-Mistakes Runner:

- after the runner has created an active no-mistakes run, Watchtower invokes the
  `no-mistakes-observer-pane` skill;
- it opens the untracked sibling Herdr pane and runs `no-mistakes attach` there;
- the observer remains display-only and never becomes a Rozoro crew/custody
  owner; and
- if the installed Herdr lacks/fails the supported pane operation, Watchtower
  records the reason and continues the real run rather than inventing terminal
  control commands.

## Consequences

- No-mistakes target selection becomes per-run and concurrency-friendly whenever
  Watchtower can launch the desired harness/account context directly.
- The previous global-configuration ceremony is removed from the normal `auto`
  path.
- First-class alternate Claude account/profile launch remains a Rozoro capability
  question rather than a reason to mutate no-mistakes global model state.
- The current fallback order remains a policy decision independent of the generic
  fact that `auto` inheritance also works for other harnesses.
- The no-mistakes observer pane is now deterministic Watchtower behavior instead
  of an optional skill that may never be selected.
