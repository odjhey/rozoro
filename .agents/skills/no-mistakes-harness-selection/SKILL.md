---
name: no-mistakes-harness-selection
description: >-
  Select the actual runner harness/model for a fresh No-Mistakes Runner when
  no-mistakes model selection is `auto`. Use immediately before Watchtower
  dispatches that runner. The runner harness/model is the no-mistakes workflow
  target; there is no separate outer-runner model selection.
---

# No-mistakes harness selection

Use this in **Watchtower immediately before a fresh No-Mistakes Runner dispatch**
when the effective no-mistakes model-selection setting is `auto`.

In `auto`, no-mistakes uses the model of the harness that invoked it. Therefore
Watchtower selects the workflow target by launching the runner under the intended
harness/model. Do not rewrite global no-mistakes model configuration merely to
select that target.

## One selection, not outer + inner

The **No-Mistakes Runner harness/model and the no-mistakes workflow target are the
same selection in `auto` mode**.

There is no fixed outer runner model that then chooses a different inner workflow
model. In particular, do **not** spawn a Pi `gpt-5.6-luna` runner and tell it to
use Claude Sonnet inside no-mistakes. Under `auto`, that Pi runner selects Pi as
the invoking harness/model.

If the first configured target is Claude Sonnet and it is available, the runner
itself must be launched as Claude Sonnet in the intended account context. Only if
that target is unavailable should Watchtower move to the next configured target.

## Selection procedure

1. Read `templates/watchtower-crew-dispatch-guidelines.md` for the current ordered
   No-Mistakes execution targets. That ordered list remains authoritative.
2. Confirm the effective no-mistakes model-selection mode is `auto` before using
   harness inheritance. If it is not `auto`, follow the explicit configured mode
   instead of assuming inheritance.
3. Try the configured targets in order. For each target, launch the **runner
   itself** using that target's actual harness/model/account context.
4. Once that runner is live, it invokes no-mistakes normally. With model selection
   `auto`, no-mistakes inherits that same runner harness/model; no second inner
   target selection and no save/override/restore ceremony for global
   no-mistakes model configuration is needed.
5. If the selected target is usage-limited, cooling down, or cannot be launched
   in its required account/profile context, treat that target as unavailable and
   immediately try the next configured target. Do not wait when a later configured
   target is ready.
6. If every configured target is unavailable, report that condition. Do not pick
   an undeclared harness/model.

## Current target semantics

The canonical dispatch policy currently orders the No-Mistakes targets as:

1. Claude Sonnet using the primary/default Claude account context.
2. Claude Sonnet using the configured secondary Claude account context.
3. Pi using exact `gpt-5.6-luna` at high reasoning effort.

For a Claude target, the runner itself must actually be launched as Claude/Sonnet
in the intended account context; conceptually this is the same selection as
`claude --model sonnet` under that account. For Pi, launch the runner itself as Pi
with `gpt-5.6-luna` and high effort.

The inheritance principle also applies when no-mistakes is invoked from other
supported harnesses such as Codex, but that fact does **not** add Codex to the
fallback list. Only targets declared by the canonical dispatch policy are normal
Watchtower choices.

If Rozoro cannot independently launch a configured account/profile target, do not
mutate global no-mistakes configuration as a workaround. Treat that target as
currently unavailable and continue through the configured fallback order; track
first-class account/profile launch support separately.

## Report

Record:

- no-mistakes selection mode (`auto` or explicit);
- selected fallback position;
- runner harness and exact model;
- account/profile identity in a non-secret stable form when applicable;
- fallback reason when a prior target was unavailable; and
- confirmation from the no-mistakes result of the harness/model actually used.

The runner harness/model and reported no-mistakes harness/model should agree in
`auto` mode. A mismatch is a policy/execution error to investigate, not an
expected outer-versus-inner distinction.

Keep harness identity, account/profile identity, model ID, and reasoning effort
separate. Never infer one from a human-readable label.