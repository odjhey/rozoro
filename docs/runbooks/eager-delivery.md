# Eager delivery mission

The shipped `eager-delivery` mission (`templates/missions/eager-delivery.md`)
runs a fleet at minimum chain depth: one generalist **Ship Crew** per
deliverable, end to end, with the mechanical gate as the codified assurance
layer. It restores the dispatch doctrine of the v0.0.1-era watchtower policy —
dispatch eagerly, intent + pointer briefs, follow-up by `send` to the live
crew — inside the ADR-0013 mission-composition contract.

## When to choose it

Prefer `eager-delivery` when:

- deliverables are bounded, single-repository tasks;
- the target repositories carry a trusted mechanical gate (no-mistakes, CI,
  repo checks) that owns codified verification;
- delivery latency matters more than standing role separation.

Prefer the shipped `delivery` mission when work needs planned worksets,
dependency stacks and integration ordering, role-separated assurance, or
repair-incident accounting. The eager mission's own text tells the Watchtower
to recommend `delivery` when it sees that shape of work.

## Selecting the mission with a preset

Missions are selected by the preset `mission` **field**, never by preset name
(ADR-0011/ADR-0013). Presets are operator-local files under
`$ROZORO_HOME/watchtower-presets/` (default `~/.rozoro/watchtower-presets/`);
they are launch metadata and are not shipped in this repository.

Example `~/.rozoro/watchtower-presets/eager-001.json`:

```json
{
  "harness": "pi",
  "model": "gpt-5.6-sol",
  "effort": "high",
  "mission": "eager-delivery",
  "version": 1,
  "notes": "one-hop fleet; mission eager-delivery"
}
```

An unpreset launch, or a preset without a `mission` field, still runs the
shipped `delivery` mission; nothing about existing launches changes.

## Comparing the two missions

Every launch records the composed policy hash tuple, and every task folder
under `$ROZORO_HOME/tasks/` durably keeps the brief and sysprompt the crew
received, so eras and missions are comparable after the fact. The metrics that
motivated this mission, per deliverable:

- driver hops (dispatches + sends) — the eager target is ~1;
- crews per deliverable;
- dispatch → accepted wall clock;
- repeated gate finding classes (each repeat is a missed ratchet).

`./bin/rozoro lineage` stitches per-agent inbound, handoff, and turn-boundary
history for these comparisons.

## Exclusions

- The mission does not change gate behavior: `.no-mistakes.yaml` and repository
  checks remain authoritative, and gate-configuration changes still travel as
  their own separate PRs with operator awareness.
- The mission's role list is closed (no ad-hoc specialists, per the shared
  facts contract); it widens by mission edit, not at runtime.
- Repository-specific instructions and explicit operator constraints still
  override runbook guidance.
