---
name: afk
description: >-
  Read or change Watchtower unattended merge authority. Use when the operator says
  /afk, /afk on, /afk off, asks whether automatic landing is enabled, or changes
  whether final merges require fresh operator confirmation.
---

# AFK / unattended mode

`/afk` controls **final merge authority** for worksets.

Default state for a new Watchtower is **ON**.

## Commands

- `/afk` or `/afk status` — report the current state.
- `/afk on` — allow an otherwise-ready Workset Merger to perform the final merge
  without asking the operator again.
- `/afk off` — require operator confirmation immediately before the final merge
  mutation.

Keep the state for the current Watchtower session/workspace. If Rozoro later gains
a first-class persisted operator-mode field, that field should become the durable
source instead of inventing a parallel skill-specific state store.

## ON

The Workset Merger may land a workset when all of these are true:

- repository/provider policy permits the merge;
- required exact-head review/test/no-mistakes/CI evidence is current;
- dependency and stacking order are resolved;
- the requested change remains inside existing operator authority; and
- there is no unresolved decision that specifically requires operator judgment.

The merger records the actual landed identity and performs required post-merge
checks/actions.

## OFF

The Workset Merger may prepare the integration, verify evidence, resolve merge
order, and report the exact proposed landing action. It stops immediately before
the final merge mutation and asks the operator for confirmation.

Once confirmed, the same live merger may continue if its exact-head evidence is
still current. Revalidate changed provider/repository state before mutation.

## Boundary

This toggle grants or withholds **automatic final merge permission only**. It does
not grant permission to bypass branch protection, force-push protected history,
perform destructive recovery, expand task scope, approve product/design choices,
expose secrets, or override repository-local policy.

Other reversible orchestration and crew routing continue in either state.
