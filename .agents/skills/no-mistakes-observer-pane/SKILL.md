---
name: no-mistakes-observer-pane
description: >-
  Open and manage the untracked sibling Herdr pane that displays an active
  no-mistakes run beside Watchtower. Use for every active no-mistakes gate once a
  run exists, unless the installed Herdr cannot create the pane safely.
---

# No-mistakes observer pane

Use this in **Watchtower for every active no-mistakes gate**. The observer is UI
only: it is not a Rozoro crew, task, session, custody owner, or control authority.

This is the normal visibility path, not an optional convenience. Once Watchtower
has submitted or reattached to an actual no-mistakes run, open the observer pane
automatically when the supported Herdr pane operation is available.

Failure to create the observer must not alter branch custody or block the run.
Record the observation failure and continue driving the real run through
no-mistakes/AXI.

## Open

When an active no-mistakes run exists:

1. Create a sibling Herdr pane to the right of the **Watchtower pane** using the
   supported local Herdr pane operation.
2. Preserve focus on the Watchtower pane after creating the observer.
3. In the observer pane, run `no-mistakes attach` for the active run using the
   supported invocation for the installed no-mistakes version.
4. Treat the pane as untracked display only. Do not register it as a Rozoro
   crew/task/session.

Do not wait for an operator request before opening it. If the installed Herdr
version does not provide a supported way to create the pane, skip it, record that
reason, and continue the no-mistakes gate rather than inventing terminal-control
commands.

## Observe only

The observer may display pipeline progress, findings, and gates. It must not:

- edit repository files;
- move refs or branches;
- become a second AXI/no-mistakes controller;
- answer gates by itself;
- become a Rozoro crew; or
- be treated as evidence that custody returned or checks passed.

Watchtower drives decisions through the structured no-mistakes/AXI interface.
The pane is only a human-readable projection of that run.

## Close

Close the observer pane when the no-mistakes run is terminal, abandoned, or no
longer needs live display. Closing it has no task or pipeline lifecycle meaning.

## Reporting

Do not create a separate durable task for the observer. If pane creation failed,
record the reason in the Watchtower decision/task notes so the missing side pane
is explainable. If the pane displays a meaningful state transition, reconcile it
against authoritative no-mistakes/AXI state before acting.