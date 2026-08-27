# Eager delivery mission

The shipped `eager-delivery` mission (`templates/missions/eager-delivery.md`)
runs a fleet at minimum chain depth for products that are not
mission-critical: one **Ship Crew** per deliverable, merge early and repair
forward, and a deliberately dumb Watchtower that routes handoffs instead of
judging them. It restores the dispatch doctrine of the v0.0.1-era watchtower
policy — dispatch eagerly, intent + pointer briefs, follow-up by `send` to
the live crew — inside the ADR-0013 mission-composition contract.

## When to choose it

Prefer `eager-delivery` when:

- the product is not mission-critical and delivery latency matters more than
  standing role separation;
- deliverables are bounded tasks whose ship bar is decent test coverage
  against the repository's contracts and design docs;
- post-merge repair is acceptable: findings file as issues and repairs land
  as follow-up tasks rather than blocking the current ship.

Prefer the shipped `delivery` mission when work needs role-separated
assurance, no-mistakes gate custody, repair-incident accounting, or
pre-merge evidence reconciliation. The eager mission's own text tells the
Watchtower to recommend `delivery` when it sees that shape of work.

## The three roles

- **Ship Crew** — end to end: investigate, implement, validate, land. Ships
  with proportionate test coverage demonstrating the contracted behavior.
- **Delivery Planner-Merger** — for multi-task work, one crew generates the
  delivery plan (parallel work-item count, stacking/dependency sequence,
  merge order) and stays live to execute the merges and stacking itself.
- **Contract Keeper** — modifies and checks doc contracts and design docs;
  violations route as post-merge repair tasks, never shipping blockers.

There is no No-Mistakes Runner, standing Reviewer, or standing Tester in this
mission, and the Watchtower carries no classification table: it dispatches,
relays handoffs, and routes what a handoff asks for.

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
- dispatch → landed wall clock;
- post-merge repair tasks and filed-issue counts (the cost side of merging
  early).

`./bin/rozoro lineage` stitches per-agent inbound, handoff, and turn-boundary
history for these comparisons.

## Exclusions

- Repository policy still governs: branch protection and the repository's own
  checks are untouched, and `/afk` still controls the final merge mutation.
- The mission's role list is closed (no ad-hoc specialists, per the shared
  facts contract); it widens by mission edit, not at runtime.
- Filed issues are a real backlog, not a write-only log: deep security
  findings land there deliberately because the product is not
  mission-critical. Do not carry this mission onto a product where that
  trade-off is wrong.
- Repository-specific instructions and explicit operator constraints still
  override runbook guidance.
