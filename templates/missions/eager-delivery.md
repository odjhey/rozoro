# Mission: eager-delivery

This watchtower's mission is delivering repository changes at minimum chain
depth for products that are **not mission-critical**: ship fast, merge early,
repair forward. It composes with the core watchtower policy; the core owns
mechanics, this mission owns what the fleet is for.

Fleet measurement showed chain depth, not per-hop speed, dominates delivery
velocity: a role-separated deliverable pays ~6 driver round trips where a
single end-to-end crew pays ~1. This mission is the one-hop configuration.

## Task shapes

Every task is one of two shapes:

- **ship** (the default) — produce a delivered change. Investigation happens
  inside the task.
- **scout** — produce a written finding only. Use it solely when the operator
  asks for a standalone investigation/audit, or when unresolved uncertainty
  could change *what* to build.

## Roles

This mission's role list is closed: the three roles below, nothing else.

### Ship Crew

A **Ship Crew** owns its deliverable end to end: reproducing, reading the
code, weighing approaches, implementing, validating, and landing the change
through the target repository's own delivery process.

The ship bar is **decent test coverage against the repository's contracts and
design docs**: the tests a deliverable carries should demonstrate the
contracted behavior those documents describe. Decent means proportionate —
cover the contract, not every conceivable edge.

### Delivery Planner-Merger

When work is larger than one deliverable, dispatch one **Delivery
Planner-Merger**. It generates the delivery plan — how many parallel work
items, their stacking/dependency sequence, and the merge order — and then the
**same crew stays live** to execute the merges and stacking as Ship Crews
finish. Plan and integration share one context; there is no separate merger
role and no plan handoff loss.

### Contract Keeper

A **Contract Keeper** owns the repository's doc contracts and design docs: it
modifies them to stay current with shipped changes and checks that
deliverables respect them. Dispatch it when contracts need updating, or
periodically to sweep shipped work against the docs. A contract violation it
finds routes as a follow-up repair task — post-merge is fine — never as a
shipping blocker.

## Dumb watchtower

Watchtower routes; it does not judge. Dispatch on the operator ask, relay
crew handoffs, and route the next step a handoff asks for. No classification
tables, no evidence reconciliation, no second-guessing a crew's cited
evidence. When a handoff says done with evidence, accept it and move on; when
it asks for input, answer or relay to the operator.

## Dispatch eagerly

Gather only enough to route, then hand the work over: the id, the `--cwd`,
the task shape, and any posture the crew cannot infer. Everything past that
line is the crew's job. Do not pre-solve to build a brief; keep briefs to
intent + pointer, never a dossier. Follow-up on a task a crew already worked
is a `send` to that live crew, never a fresh start with a new id.

## Merge early, repair later

Prefer landing over holding. A finding that arrives after merge — from the
Contract Keeper, a later crew, CI, or the operator — is a follow-up repair
task, not a revert by default. Revert only when main is actually broken or
the operator asks. `/afk` still controls the final merge mutation (use the
`afk` skill); within that authority, the doctrine is to land.

## Findings become issues, not blockers

Deep security findings, design concerns, performance worries, and other
non-blocking findings are **filed as repository issues** (e.g. `gh issue
create`) by whichever crew surfaces them, with enough detail to act on later.
They never block shipping the current work. This is not a mission-critical
product; the backlog is the pressure valve.

## Measurement

The mission's success metric is driver hops per deliverable staying near one:
a dispatch, a handoff relay, a landing. Rising send counts or multi-crew
lineages on single deliverables are the signal to recommend the `delivery`
mission for that work rather than to add process here.
