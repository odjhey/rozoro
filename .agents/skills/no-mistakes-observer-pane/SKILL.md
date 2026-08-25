---
name: no-mistakes-observer-pane
description: >-
  Open and manage an untracked sibling Herdr pane that attaches to an active
  no-mistakes run for live observation without creating another Rozoro crew or
  stealing branch custody. This is Watchtower-owned operational behavior.
metadata:
  execution-owner: watchtower
  watchtower-action: invoke-directly
  derived-from: uploaded-watchtower-policy/03-no-mistakes-runner.md
---

# No-mistakes observer pane

Use an observer pane when live no-mistakes visibility is useful during a runner
session. The observer is **not** another crew member and has no repository
ownership or mutation authority.

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

If the local Herdr version does not provide a supported way to create the pane,
skip the observer rather than inventing terminal-control commands.

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
otherwise no longer needs live observation. Closing the observer has no task
lifecycle meaning and must not reap or mutate the runner task.

## Reporting

The Watchtower does not need to create a separate durable task record for the
observer. If observation surfaces a meaningful state transition, reconcile it
through the actual runner/task evidence rather than treating terminal display as
a second source of truth.
