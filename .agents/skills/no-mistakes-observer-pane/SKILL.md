---
name: no-mistakes-observer-pane
description: >-
  Open and manage the untracked sibling Herdr observer pane for a No-Mistakes
  Runner. Use for every No-Mistakes Runner dispatch once an active no-mistakes
  run exists, unless the local Herdr version cannot create the pane safely.
---

# No-mistakes observer pane

Use this in **Watchtower for every active No-Mistakes Runner**. The observer is
not another crew member and has no repository ownership or mutation authority.

This is the normal No-Mistakes observation path, not an optional convenience.
When the runner starts an actual no-mistakes run, Watchtower should open the
observer pane automatically when the supported Herdr pane operation is available.
Failure to create an observer must not alter branch custody or block the run; note
the observation failure and continue managing the real runner/task.

Current no-mistakes target/fallback and custody policy remain authoritative. This
skill only describes the observation surface.

## Open

When a No-Mistakes Runner has started an actual no-mistakes run:

1. Create a sibling Herdr pane to the right of the runner/harness pane using the
   supported local Herdr pane operation.
2. Preserve focus on the runner/harness pane after creating the observer.
3. In the observer pane, run `no-mistakes attach` once the active run exists.
4. Treat the pane as untracked observation only. Do not register it as a Rozoro
   crew/task/session.

Do not wait for an operator request before opening it. If the local Herdr version
does not provide a supported way to create the pane, skip the observer, record
that reason, and continue the runner rather than inventing terminal-control
commands.

## Observe only

The observer may display the active run and its gate/progress output. It must not:

- edit repository files;
- move refs or branches;
- drive AXI/no-mistakes control actions that belong to the runner;
- answer gates on behalf of the runner;
- become a second No-Mistakes Runner; or
- be treated as evidence that custody returned or checks passed.

The dedicated No-Mistakes Runner remains the only crew role that invokes or
controls the workflow.

## Close

Close the observer pane when the no-mistakes gate/run is accepted, abandoned, or
otherwise reaches a state where live observation is no longer useful. Closing the
observer has no task lifecycle meaning and must not reap or mutate the runner
task.

## Reporting

Watchtower does not create a separate durable task record for the observer. If
pane creation failed, include the reason in the Watchtower decision/task notes so
the absence of a side pane is explainable. If observation surfaces a meaningful
state transition, reconcile it through the actual runner/task evidence rather
than treating terminal display as a second source of truth.